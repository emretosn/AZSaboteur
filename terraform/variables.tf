variable "scenario_id" {
  description = "Unique identifier for this scenario deployment"
  type        = string
}

variable "region" {
  description = "Azure region for deployment"
  type        = string
  default     = "westeurope"
}

variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "kali_admin_username" {
  description = "Admin username for the Kali box"
  type        = string
  default     = "kali"
}

variable "kali_admin_password" {
  description = "Admin password for the Kali box"
  type        = string
  sensitive   = true
}

variable "kali_vm_size" {
  description = "VM size for the Kali box"
  type        = string
  default     = "Standard_B2s_v2"
}

variable "chain" {
  description = "Attack chain module configuration (passed from scenario engine)"
  type        = any
  default     = []
}

variable "credentials" {
  description = "Generated credentials for the scenario"
  type        = map(string)
  default     = {}
}

variable "flags" {
  description = "Generated flags for the scenario"
  type        = map(string)
  default     = {}
}
