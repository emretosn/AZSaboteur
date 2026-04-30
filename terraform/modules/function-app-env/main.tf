# Function App with secrets in environment variables.
# The player discovers the Function App (e.g. via SP credentials) and reads
# its app settings to find the flag and other secrets.

locals {
  storage_name = replace(substr("stfn${var.resource_prefix}", 0, 24), "-", "")
  func_name    = "func-${var.resource_prefix}"
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
  }
}

resource "azurerm_service_plan" "this" {
  name                = "plan-${var.resource_prefix}"
  location            = var.region
  resource_group_name = var.resource_group_name
  os_type             = "Linux"
  sku_name            = "Y1" # Consumption plan

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
  }
}

resource "azurerm_linux_function_app" "this" {
  name                = local.func_name
  location            = var.region
  resource_group_name = var.resource_group_name
  service_plan_id     = azurerm_service_plan.this.id

  # Use managed identity for storage instead of shared key (shared key may be
  # disabled by tenant policy on managed subscriptions).
  storage_account_name          = azurerm_storage_account.this.name
  storage_uses_managed_identity = true

  identity {
    type = "SystemAssigned"
  }

  site_config {
    application_stack {
      python_version = "3.11"
    }
  }

  # Intentionally leaking secrets through app settings
  app_settings = {
    "SP_CLIENT_ID"     = "will-be-set-by-ansible"
    "SP_CLIENT_SECRET" = var.flag
    "SP_TENANT_ID"     = "will-be-set-by-ansible"
    "DATABASE_URL"     = "postgresql://${var.credentials["step_${var.step_index}_username"]}:${var.credentials["step_${var.step_index}_password"]}@internal-db:5432/app"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "function-app-env"
  }
}

# Grant the Function App's managed identity access to its storage account
resource "azurerm_role_assignment" "func_storage" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Owner"
  principal_id         = azurerm_linux_function_app.this.identity[0].principal_id
}

resource "azurerm_role_assignment" "func_storage_file" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage File Data Privileged Contributor"
  principal_id         = azurerm_linux_function_app.this.identity[0].principal_id
}

output "function_app_name" {
  description = "Name of the Function App"
  value       = azurerm_linux_function_app.this.name
}

output "default_hostname" {
  description = "Default hostname of the Function App"
  value       = azurerm_linux_function_app.this.default_hostname
}
