# Storage account with an overly permissive SAS token.
# The player discovers the SAS token (e.g. from env vars) and uses it
# to access blobs containing the flag.

locals {
  storage_name = replace(substr("st${var.resource_prefix}", 0, 24), "-", "")
}

resource "azurerm_storage_account" "this" {
  name                     = local.storage_name
  location                 = var.region
  resource_group_name      = var.resource_group_name
  account_tier             = "Standard"
  account_replication_type = "LRS"

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "sas-overperm"
  }
}

resource "azurerm_storage_container" "data" {
  name                  = "internal-data"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_blob" "flag" {
  name                   = "admin/credentials.txt"
  storage_account_name   = azurerm_storage_account.this.name
  storage_container_name = azurerm_storage_container.data.name
  type                   = "Block"
  source_content         = "ADMIN_API_KEY=${var.flag}"
}

data "azurerm_storage_account_sas" "overperm" {
  connection_string = azurerm_storage_account.this.primary_connection_string

  resource_types {
    service   = true
    container = true
    object    = true
  }

  services {
    blob  = true
    queue = true
    table = true
    file  = true
  }

  # Intentionally over-permissive: full read/write/list/delete
  permissions {
    read    = true
    write   = true
    delete  = true
    list    = true
    add     = true
    create  = true
    update  = true
    process = true
    tag     = false
    filter  = false
  }

  start  = timestamp()
  expiry = timeadd(timestamp(), "8760h") # 1 year — intentionally long
}

output "storage_account_name" {
  description = "Storage account name"
  value       = azurerm_storage_account.this.name
}

output "sas_token" {
  description = "Overly permissive SAS token (intentionally leaked)"
  value       = data.azurerm_storage_account_sas.overperm.sas
  sensitive   = true
}
