# Cosmos DB with leaked primary key — the player uses a discovered connection string
# to connect and read all data, finding the flag in a document.

resource "azurerm_cosmosdb_account" "this" {
  name                = "cosmos-${var.resource_prefix}"
  location            = var.region
  resource_group_name = var.resource_group_name
  offer_type          = "Standard"

  # Disable zone redundancy — avoids capacity limits in popular regions
  is_virtual_network_filter_enabled = false

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = var.region
    failover_priority = 0
    zone_redundant    = false
  }

  tags = {
    project  = "azsaboteur"
    scenario = var.scenario_id
    step     = var.step_index
    role     = "cosmosdb-leaked-key"
  }
}

resource "azurerm_cosmosdb_sql_database" "this" {
  name                = "appdata"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name
}

resource "azurerm_cosmosdb_sql_container" "this" {
  name                = "secrets"
  resource_group_name = var.resource_group_name
  account_name        = azurerm_cosmosdb_account.this.name
  database_name       = azurerm_cosmosdb_sql_database.this.name
  partition_key_paths = ["/category"]
}

output "cosmosdb_endpoint" {
  description = "Cosmos DB endpoint"
  value       = azurerm_cosmosdb_account.this.endpoint
}

output "cosmosdb_connection_string" {
  description = "Primary connection string (intentionally exposed)"
  value       = azurerm_cosmosdb_account.this.primary_sql_connection_string
  sensitive   = true
}
