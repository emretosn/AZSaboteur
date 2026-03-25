terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    azuread = {
      source  = "hashicorp/azuread"
      version = "~> 3.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id        = var.subscription_id
  storage_use_azuread    = true
}

provider "azuread" {}

module "resource_group" {
  source = "./shared/resource-group"

  scenario_id = var.scenario_id
  region      = var.region
}

module "networking" {
  source = "./shared/networking"

  scenario_id         = var.scenario_id
  region              = var.region
  resource_group_name = module.resource_group.name
}

module "kalibox" {
  source = "./shared/kalibox"

  scenario_id         = var.scenario_id
  region              = var.region
  resource_group_name = module.resource_group.name
  subnet_id           = module.networking.kali_subnet_id
  admin_username      = var.kali_admin_username
  admin_password      = var.kali_admin_password
  vm_size             = var.kali_vm_size
  custom_image_id     = var.kali_custom_image_id
}
