# Key Vault with lax access policy — any identity with the right policy can read secrets.
# The flag is stored as a Key Vault secret the player can retrieve with a stolen token.

data "azurerm_client_config" "current" {}

resource "azurerm_key_vault" "this" {
  name                       = "kv-${var.resource_prefix}"
  location                   = var.region
  resource_group_name        = var.resource_group_name
  tenant_id                  = data.azurerm_client_config.current.tenant_id
  sku_name                   = "standard"
  soft_delete_retention_days = 7
  purge_protection_enabled   = false

  # Intentionally lax: allow the deployer to set secrets,
  # and any authenticated identity to read them.
  access_policy {
    tenant_id = data.azurerm_client_config.current.tenant_id
    object_id = data.azurerm_client_config.current.object_id

    secret_permissions = ["Get", "List", "Set", "Delete", "Purge"]
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "keyvault-lax"
  }
}

resource "azurerm_key_vault_secret" "flag" {
  name         = "DatabaseConnectionString"
  value        = var.flag
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "decoy_1" {
  name         = "AppInsightsKey"
  value        = "ai-00000000-0000-0000-0000-000000000000"
  key_vault_id = azurerm_key_vault.this.id
}

resource "azurerm_key_vault_secret" "decoy_2" {
  name         = "StorageAccountKey"
  value        = "ZGVjb3kta2V5LW5vdC1yZWFs"
  key_vault_id = azurerm_key_vault.this.id
}

output "key_vault_name" {
  description = "Name of the Key Vault"
  value       = azurerm_key_vault.this.name
}

output "key_vault_uri" {
  description = "URI of the Key Vault"
  value       = azurerm_key_vault.this.vault_uri
}
