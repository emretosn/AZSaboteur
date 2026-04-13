variable "scenario_id" {
  description = "Unique scenario identifier"
  type        = string
}

variable "region" {
  description = "Azure region"
  type        = string
}

variable "resource_group_name" {
  description = "Shared resource group name"
  type        = string
}

variable "lab_subnet_id" {
  description = "Lab subnet ID for VMs"
  type        = string
}

variable "resource_prefix" {
  description = "Unique prefix for resource names in this step"
  type        = string
}

variable "step_index" {
  description = "Position of this step in the attack chain"
  type        = number
}

variable "flag" {
  description = "Flag to hide in this step"
  type        = string
  sensitive   = true
}

variable "credentials" {
  description = "All generated credentials for the scenario"
  type        = map(string)
  sensitive   = true
}

variable "reader_principal_ids" {
  description = "Principal IDs that should have Get+List access to Key Vault secrets (e.g. managed identities from preceding attack-chain steps)"
  type        = list(string)
  default     = []
}
