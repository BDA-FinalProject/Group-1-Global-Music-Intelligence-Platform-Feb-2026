variable "job_name" {
  type = string
}

variable "script_local_path" {
  description = "Local path to the PySpark script to upload."
  type        = string
}

variable "script_s3_bucket" {
  type = string
}

variable "script_s3_key" {
  type = string
}

variable "glue_version" {
  type    = string
  default = "5.0"
}

variable "worker_type" {
  type    = string
  default = "G.1X"
}

variable "number_of_workers" {
  type    = number
  default = 2
}

variable "timeout" {
  description = "Job timeout in minutes."
  type        = number
  default     = 30
}

variable "max_retries" {
  type    = number
  default = 0
}

variable "default_arguments" {
  type    = map(string)
  default = {}
}

variable "tags" {
  type    = map(string)
  default = {}
}

# Same lab-account pattern as ec2_ingestion: sandbox accounts (AWS Academy
# Learner Lab etc.) deny iam:CreateRole, but a pre-existing LabRole is
# usable directly by name.
variable "use_lab_role" {
  type    = bool
  default = false
}

variable "lab_role_name" {
  type    = string
  default = "LabRole"
}

variable "role_arn" {
  description = "IAM role ARN for the Glue job. Required when use_lab_role is false."
  type        = string
  default     = null
}
