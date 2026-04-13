# AZSaboteur

**Dynamic Azure Cloud Attack Lab Generator**

AZSaboteur procedurally generates attack scenarios composed of chained Azure misconfigurations, deploys them to a real Azure subscription, and drops you into a Kali Linux box to exploit them. Each run produces a unique attack chain — no two labs are the same.

---

## Overview

AZSaboteur is a security training tool that builds hands-on Azure exploitation labs on the fly. It works by:

1. **Generating** a randomized attack chain from a catalog of **16 vulnerability modules** spanning 5 categories: web, storage, compute, identity, and networking.
2. **Deploying** the scenario in two phases — Terraform creates the Azure infrastructure, then Ansible provisions the intentionally vulnerable services and plants flags.
3. **Connecting** the player via RDP to a Kali Linux VM inside the lab network. From there, you scan the environment, discover misconfigurations, and exploit the chain step-by-step to capture the final flag.

Each module defines what it **requires** (e.g. `network_access`, `sp_credentials`) and what it **provides** (e.g. `managed_identity_token`, `vm_shell`), allowing the engine to stitch together realistic multi-step attack paths.

---

## Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.11+ |
| Terraform | >= 1.5 |
| Ansible | `ansible-playbook` on PATH |
| sshpass | Any (for SSH ProxyJump through Kali) |
| Azure CLI | `az` logged in with an active subscription |
| xfreerdp | Optional — for RDP connection to the Kali box |

---

## Installation

```bash
git clone https://github.com/<org>/AZSaboteur.git
cd AZSaboteur
pip install -e ".[dev]"  # or: uv sync
```

---

## Quick Start

```bash
# Interactive mode — guided prompts
saboteur deploy

# Scripted mode — deploy a 3-step chain
saboteur deploy --chain-length 3 --region westeurope

# Infra-only (just Kali box, no attack chain)
saboteur deploy --chain-length 0

# Destroy when done
saboteur destroy
```

---

## Commands

| Command | Description |
|---|---|
| `saboteur generate` | Dry-run: generate a scenario without deploying |
| `saboteur deploy` | Generate and deploy a scenario to Azure |
| `saboteur destroy` | Tear down a deployed scenario |
| `saboteur status` | Show all tracked deployments |
| `saboteur validate <FLAG>` | Check if a flag string is correct |
| `saboteur list-modules` | Show available vulnerability modules |
| `saboteur clean` | Reset local state when destroy fails |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  saboteur CLI (Python)                          │
│  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ Scenario     │  │ Module Catalog           │  │
│  │ Engine       │──│ (modules/*.yaml)         │  │
│  └──────┬───────┘  └─────────────────────────┘  │
│         │                                       │
│  ┌──────▼───────┐  ┌─────────────────────────┐  │
│  │ Phase 1:     │  │ Phase 2:                │  │
│  │ Terraform    │──│ Ansible                 │  │
│  │ (infra)      │  │ (vuln apps)             │  │
│  └──────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────┘
         │                      │
         ▼                      ▼
┌─────────────────┐  ┌─────────────────────────┐
│ Azure Resources │  │ Vulnerable Services     │
│ (VMs, KV, Blob) │  │ (Flask apps, nginx,     │
│                 │  │  planted secrets)        │
└─────────────────┘  └─────────────────────────┘
```

The **Scenario Engine** reads module definitions, resolves dependency chains, and produces a Terraform variable file and Ansible inventory. **Phase 1** (Terraform) stands up the cloud resources — VMs, Key Vaults, Storage Accounts, Function Apps, etc. **Phase 2** (Ansible) SSH-es through the Kali box to configure each resource with its intended vulnerability and plant flags.

---

## Module Catalog

AZSaboteur ships with 16 vulnerability modules across 5 categories:

### Web

| ID | Name | Entry Point | Requires | Provides |
|---|---|---|---|---|
| `WEB-SSRF` | SSRF to IMDS Token Theft | Yes | `network_access` | `managed_identity_token` |
| `WEB-SQLI` | SQL Injection Credential Dump | Yes | `network_access` | `sql_credentials` |
| `WEB-CMDI` | Command Injection | Yes | `network_access` | `env_secrets` |
| `WEB-GITEXPOSE` | Exposed .git Directory | Yes | `network_access` | `app_secret` |

### Storage

| ID | Name | Entry Point | Requires | Provides |
|---|---|---|---|---|
| `STR-PUBLIC-BLOB` | Publicly Accessible Blob Container | Yes | `network_access` | `storage_key` |
| `STR-KEYVAULT-POLICY` | Lax Key Vault Access Policy | No | `managed_identity_token` | `keyvault_secret` |
| `STR-COSMOSDB-KEY` | Cosmos DB Primary Key Leak | No | `sql_credentials` | `cosmosdb_data` |
| `STR-SAS-OVERPERM` | Overly Permissive SAS Token | No | `env_secrets` | `storage_key` |

### Compute

| ID | Name | Entry Point | Requires | Provides |
|---|---|---|---|---|
| `CMP-IMDS` | Managed Identity Token via IMDS | No | `vm_shell` | `managed_identity_token` |
| `CMP-RUNCOMMAND` | VM Run Command Abuse | No | `full_access` | `vm_shell` |
| `CMP-FUNC-ENV` | Function App Environment Secrets | No | `sql_credentials` | `sp_credentials` |
| `CMP-AUTOMATION` | Automation Account Runbook Abuse | No | `sp_credentials` | `vm_shell` |

### Identity

| ID | Name | Entry Point | Requires | Provides |
|---|---|---|---|---|
| `IAM-OVERPERM-SP` | Over-privileged Service Principal | No | `sp_credentials` | `full_access` |
| `IAM-APPREG-SECRET` | App Registration with Leaked Secret | No | `app_secret` | `sp_credentials` |

### Networking

| ID | Name | Entry Point | Requires | Provides |
|---|---|---|---|---|
| `NET-NSG-OPEN` | Open NSG Rule | Yes | `network_access` | `internal_network_access` |
| `NET-MGMT-EXPOSED` | Exposed Management Port | Yes | `network_access` | `vm_shell` |

---

## Example Chains

The scenario engine chains modules by matching **provides → requires** links. Here are some examples it can generate:

### Short (2 steps)

```
WEB-SSRF → STR-KEYVAULT-POLICY
```

Exploit an SSRF vulnerability to steal a managed identity token from IMDS, then use that token to read secrets from a misconfigured Key Vault.

### Medium (3 steps)

```
NET-MGMT-EXPOSED → CMP-IMDS → STR-KEYVAULT-POLICY
```

Discover an exposed SSH port, log in with weak credentials to get a shell, query IMDS for a managed identity token, then pillage the Key Vault.

### Long (6 steps)

```
WEB-SQLI → CMP-FUNC-ENV → IAM-OVERPERM-SP → CMP-RUNCOMMAND → CMP-IMDS → STR-KEYVAULT-POLICY
```

Dump credentials via SQL injection, read Function App environment variables to obtain a service principal secret, escalate to Owner, run commands on a VM, grab an identity token from IMDS, and finally exfiltrate Key Vault secrets.

---

## Custom Kali Image (Optional)

Build a custom Kali image with pre-installed tools using Packer:

```bash
packer build -var subscription_id=<SUB_ID> packer/kali.pkr.hcl
saboteur deploy --image <IMAGE_RESOURCE_ID>
```

---

## Project Structure

```
AZSaboteur/
├── saboteur/           # Python CLI + scenario engine
├── modules/            # Vulnerability module definitions (YAML)
├── terraform/          # Infrastructure as code
├── ansible/            # Post-deploy provisioning
├── vulnerable-apps/    # Vulnerable Flask applications
├── packer/             # Kali image builder
├── scenarios/          # Generated scenario state
├── tests/              # Test suite
└── docs/               # Documentation
```

---

## Development

```bash
uv sync
uv run pytest tests/ -q
uv run ruff check .
```

---

## Disclaimer

⚠️ **This tool deploys intentionally vulnerable infrastructure.** Only use it in isolated Azure subscriptions for authorized security training. Do not deploy in production environments. You are solely responsible for any costs incurred and for securing or destroying the resources when finished.