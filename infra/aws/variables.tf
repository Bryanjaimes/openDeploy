variable "region" {
  type        = string
  description = "AWS region"
  default     = "us-east-1"
}

variable "instance_type" {
  type        = string
  description = "Instance type"
  default     = "g4dn.xlarge"
}

variable "key_name" {
  type        = string
  description = "AWS key pair name"
}

variable "public_key_path" {
  type        = string
  description = "Path to your SSH public key (e.g., ~/.ssh/id_rsa.pub)"
}

variable "root_volume_size" {
  type        = number
  description = "Root volume size in GB"
  default     = 200
}
