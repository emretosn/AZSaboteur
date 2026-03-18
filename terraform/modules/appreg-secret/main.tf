# App Registration with a leaked client secret.
# The player discovers the client_id + client_secret (e.g. from a .git repo)
# and uses them to authenticate as the application.

data "azurerm_client_config" "current" {}

resource "azuread_application" "this" {
  display_name = "${var.resource_prefix}-app"

  tags = ["azsaboteur", var.scenario_id]
}

resource "azuread_application_password" "leaked" {
  application_id = azuread_application.this.id
  display_name   = "primary-key"
  end_date       = timeadd(timestamp(), "8760h")
}

resource "azuread_service_principal" "this" {
  client_id = azuread_application.this.client_id
}

# Give the SP a role so it can actually do something once the player authenticates.
# Reader on the resource group lets the player enumerate resources.
resource "azurerm_role_assignment" "reader" {
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
  role_definition_name = "Reader"
  principal_id         = azuread_service_principal.this.object_id
}

# Store the flag in the application's notes — accessible via MS Graph once
# authenticated as the app.
resource "azuread_application" "flag_holder" {
  display_name = "${var.resource_prefix}-internal"
  notes        = "Service configuration — API_KEY=${var.flag}"

  tags = ["azsaboteur", var.scenario_id, "internal"]
}

output "client_id" {
  description = "Application (client) ID"
  value       = azuread_application.this.client_id
}

output "client_secret" {
  description = "Leaked client secret"
  value       = azuread_application_password.leaked.value
  sensitive   = true
}

output "tenant_id" {
  description = "Azure AD tenant ID"
  value       = data.azurerm_client_config.current.tenant_id
}
