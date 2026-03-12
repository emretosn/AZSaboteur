output "resource_group_name" {
  description = "Name of the resource group"
  value       = module.resource_group.name
}

output "kali_public_ip" {
  description = "Public IP of the Kali box (RDP target for the player)"
  value       = module.kalibox.public_ip
}

output "kali_rdp_command" {
  description = "RDP connection command for the player"
  value       = "xfreerdp /v:${module.kalibox.public_ip} /u:${var.kali_admin_username} /p:<password> /cert:ignore"
}

output "kali_admin_username" {
  description = "Kali box admin username"
  value       = var.kali_admin_username
}

output "lab_subnet_id" {
  description = "Subnet ID for lab resources"
  value       = module.networking.lab_subnet_id
}

output "vnet_id" {
  description = "VNet ID"
  value       = module.networking.vnet_id
}
