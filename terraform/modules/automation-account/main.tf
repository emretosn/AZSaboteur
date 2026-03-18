# Automation Account with a runbook that runs as a high-privilege managed identity.
# The player discovers the Automation Account and modifies/executes a runbook.

resource "azurerm_automation_account" "this" {
  name                = "aa-${var.resource_prefix}"
  location            = var.region
  resource_group_name = var.resource_group_name
  sku_name            = "Basic"

  identity {
    type = "SystemAssigned"
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "automation-account"
  }
}

# Give the automation account's managed identity Contributor on the RG
data "azurerm_client_config" "current" {}

resource "azurerm_role_assignment" "contributor" {
  scope                = "/subscriptions/${data.azurerm_client_config.current.subscription_id}/resourceGroups/${var.resource_group_name}"
  role_definition_name = "Contributor"
  principal_id         = azurerm_automation_account.this.identity[0].principal_id
}

resource "azurerm_automation_runbook" "this" {
  name                    = "Get-ServerStatus"
  location                = var.region
  resource_group_name     = var.resource_group_name
  automation_account_name = azurerm_automation_account.this.name
  runbook_type            = "PowerShell"
  log_progress            = false
  log_verbose             = false

  content = <<-PS
    # Server health check runbook
    # Flag: ${var.flag}
    Connect-AzAccount -Identity
    $vms = Get-AzVM -ResourceGroupName '${var.resource_group_name}'
    foreach ($vm in $vms) {
        Write-Output "VM: $($vm.Name) - Status: Running"
    }
  PS
}

output "automation_account_name" {
  description = "Name of the Automation Account"
  value       = azurerm_automation_account.this.name
}

output "runbook_name" {
  description = "Name of the runbook"
  value       = azurerm_automation_runbook.this.name
}
