# Over-privileged Service Principal — has Owner on the resource group.
# The player discovers SP credentials from a previous step and uses them
# to escalate privileges.

data "azurerm_client_config" "current" {}

resource "azuread_application" "this" {
  display_name = "${var.resource_prefix}-svc"

  tags = ["azsaboteur", var.scenario_id]
}

resource "azuread_application_password" "this" {
  application_id = azuread_application.this.id
  display_name   = "automation-key"
  end_date       = timeadd(timestamp(), "8760h")
}

resource "azuread_service_principal" "this" {
  client_id = azuread_application.this.client_id
}

# Intentional misconfiguration: Owner on the resource group
resource "azurerm_role_assignment" "owner" {
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
  role_definition_name = "Owner"
  principal_id         = azuread_service_principal.this.object_id
}

# The flag is in a tag on the role assignment's scope (resource group)
# accessible once the player has Owner.
resource "azurerm_resource_group_template_deployment" "flag_tag" {
  name                = "flag-${var.resource_prefix}"
  resource_group_name = var.resource_group_name
  deployment_mode     = "Incremental"

  template_content = jsonencode({
    "$schema"      = "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#"
    contentVersion = "1.0.0.0"
    resources      = []
    outputs = {
      flag = {
        type  = "string"
        value = var.flag
      }
    }
  })
}

output "service_principal_id" {
  description = "Service Principal object ID"
  value       = azuread_service_principal.this.object_id
}

output "client_id" {
  description = "Application (client) ID"
  value       = azuread_application.this.client_id
}
