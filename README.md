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
| Packer | >= 1.9 (optional — for building the Kali golden image) |
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
uv run saboteur deploy

# Scripted mode — deploy a 3-step chain
uv run saboteur deploy --chain-length 3 --region westeurope

# Infra-only (just Kali box, no attack chain)
uv run saboteur deploy --chain-length 0

# Destroy when done
uv run saboteur destroy
```

---

## Commands

| Command | Description |
|---|---|
| `saboteur generate` | Dry-run: generate a scenario without deploying |
| `saboteur deploy` | Generate and deploy a scenario to Azure |
| `saboteur connect` | Reconnect to the Kali box (starts VM, fixes NSG/xRDP if needed) |
| `saboteur credentials` | Print Kali box connection credentials |
| `saboteur destroy` | Tear down a deployed scenario |
| `saboteur reprovision` | Re-run Ansible on an existing deployment (~1-2 min) |
| `saboteur status` | Show all tracked deployments |
| `saboteur validate` | Interactive flag submission and progress tracker |
| `saboteur list-modules` | Show available vulnerability modules |
| `saboteur clean` | Reset local state when destroy fails |

---

## Architecture

```
┌─────────────────────────────────────────────────┐
│  saboteur CLI (Python)                          │
│  ┌──────────────┐  ┌─────────────────────────┐  │
│  │ Scenario     │  │ Module Catalog          │  │
│  │ Engine       │──│ (modules/*.yaml)        │  │
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
│                 │  │  planted secrets)       │
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
| `STR-PUBLIC-BLOB` | Publicly Accessible Blob Container | Yes | `network_access` | `sql_credentials` |
| `STR-KEYVAULT-POLICY` | Lax Key Vault Access Policy | No | `managed_identity_token` | `sp_credentials` |
| `STR-COSMOSDB-KEY` | Cosmos DB Primary Key Leak | No | `sql_credentials` | `app_secret` |
| `STR-SAS-OVERPERM` | Overly Permissive SAS Token | No | `env_secrets` | `sql_credentials` |

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
| `NET-NSG-OPEN` | Open NSG Rule | Yes | `network_access` | `vm_shell` |
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

### Long (9 steps)

```
WEB-CMDI → STR-SAS-OVERPERM → STR-COSMOSDB-KEY → IAM-APPREG-SECRET → CMP-AUTOMATION → CMP-IMDS → STR-KEYVAULT-POLICY → IAM-OVERPERM-SP → CMP-RUNCOMMAND
```

Inject commands to leak a SAS token, use it to read storage containing DB credentials, connect to Cosmos DB to find an app secret, authenticate as an App Registration, abuse an Automation Account runbook, steal a managed identity token from IMDS, raid the Key Vault for SP credentials, escalate to Owner, and run commands on a VM.

---

## Kali Golden Image (Recommended)

Build a Kali image once with Packer to get **reliable, fast deploys**. This bypasses the Azure marketplace entirely (which can intermittently fail on managed subscriptions) and cuts deploy time by ~15 minutes since all tools are pre-installed.

### One-time setup

```bash
# Create the image resource group
az group create -n rg-AZSaboteur-images -l westeurope

# Build the golden image (~15-20 min)
cd packer
packer init .
packer build -var "subscription_id=$(az account show --query id -o tsv)" .
```

This creates a managed image `kali-azsaboteur` in `rg-AZSaboteur-images`.

### Usage

Once built, `saboteur deploy` **auto-detects** the golden image — no extra flags needed:

```bash
uv run saboteur deploy   # automatically uses the golden image
```

You'll see `✓ Found Kali golden image — skipping marketplace` in the output.

> **Without a golden image**, the CLI falls back to the Kali marketplace image
> (with cloud-init tool installation), and if that fails, to an Ubuntu base
> image with the same tools installed via cloud-init.

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
