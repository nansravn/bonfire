variable "resource_group_name" { type = string }
variable "location" { type = string }
variable "admin_cidr" {
  type        = string
  description = "CIDR allowed to SSH (the owner's public IP, e.g. 203.0.113.7/32)."
}
variable "ports" {
  type        = list(object({ port = number, proto = string }))
  description = "Game ports to open to the internet, from games/<game>/adapter.json."
}
