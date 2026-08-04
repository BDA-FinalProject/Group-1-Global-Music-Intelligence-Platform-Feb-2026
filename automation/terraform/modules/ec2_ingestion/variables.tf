variable "project_name" {
  type = string
}

variable "env" {
  type = string
}

variable "aws_region" {
  type = string
}

variable "instance_type" {
  type    = string
  default = "t3.small"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GB."
  type        = number
  default     = 40
}

variable "vpc_id" {
  description = "VPC to launch the ingestion instance in. Defaults to the account's default VPC."
  type        = string
  default     = null
}

variable "subnet_id" {
  description = "Subnet to launch the ingestion instance in. Defaults to the first subnet in the default VPC."
  type        = string
  default     = null
}

variable "data_bucket_name" {
  type = string
}

variable "data_bucket_arn" {
  type = string
}

variable "kaggle_username_param_name" {
  type = string
}

variable "kaggle_username_param_arn" {
  type = string
}

variable "kaggle_key_param_name" {
  type = string
}

variable "kaggle_key_param_arn" {
  type = string
}

variable "kaggle_slug" {
  type = string
}

variable "target_file" {
  type = string
}

variable "table_name" {
  type = string
}

variable "tags" {
  type    = map(string)
  default = {}
}

variable "use_lab_instance_profile" {
  description = "Set true in sandbox accounts (e.g. AWS Academy Learner Lab) that deny iam:CreateRole. Attaches the pre-existing lab_instance_profile_name instead of creating a purpose-built role."
  type        = bool
  default     = false
}

variable "lab_instance_profile_name" {
  description = "Name of the pre-existing instance profile to use when use_lab_instance_profile is true."
  type        = string
  default     = "LabInstanceProfile"
}
