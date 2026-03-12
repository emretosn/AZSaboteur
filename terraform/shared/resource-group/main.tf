variable "scenario_id" {
  type = string
}

variable "region" {
  type = string
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${var.scenario_id}"
  location = var.region

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
  }
}

output "name" {
  value = azurerm_resource_group.this.name
}

output "id" {
  value = azurerm_resource_group.this.id
}
