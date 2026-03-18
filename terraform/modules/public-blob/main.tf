# Public blob container — intentionally misconfigured with anonymous read access.
# The flag is uploaded as a blob the player can discover via enumeration.

locals {
  # Storage account names: 3-24 chars, lowercase alphanumeric only
  storage_name = replace(substr("st${var.resource_prefix}", 0, 24), "-", "")
}

resource "azurerm_storage_account" "this" {
  name                     = local.storage_name
  location                 = var.region
  resource_group_name      = var.resource_group_name
  account_tier             = "Standard"
  account_replication_type = "LRS"

  allow_nested_items_to_be_public = true

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "public-blob"
  }
}

resource "azurerm_storage_container" "public" {
  name                  = "data"
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "blob"
}

resource "azurerm_storage_blob" "flag" {
  name                   = "backup/config.json"
  storage_account_name   = azurerm_storage_account.this.name
  storage_container_name = azurerm_storage_container.public.name
  type                   = "Block"
  source_content = jsonencode({
    database_connection = "Server=internal-db;Database=app;User=${var.credentials["step_${var.step_index}_username"]};Password=${var.credentials["step_${var.step_index}_password"]}"
    api_key             = var.flag
    environment         = "production"
  })
}

output "storage_account_name" {
  description = "Name of the storage account"
  value       = azurerm_storage_account.this.name
}

output "blob_endpoint" {
  description = "Primary blob endpoint"
  value       = azurerm_storage_account.this.primary_blob_endpoint
}
