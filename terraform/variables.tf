variable "aws_region" {
  description = "AWS Region where resources exist"
  type        = string
}

variable "script_bucket_name" {
  description = "Name of the S3 bucket containing Glue scripts"
  type        = string
}

variable "glue_job_silver_name" {
  description = "Name of the Bronze to Silver Glue Job"
  type        = string
}

variable "glue_job_gold_name" {
  description = "Name of the Silver to Gold Glue Job"
  type        = string
}

variable "glue_crawler_name" {
  description = "Name of the Glue Crawler"
  type        = string
}

variable "glue_database_name" {
  description = "Name of the Glue Catalog Database"
  type        = string
}

variable "glue_role_name" {
  description = "Existing Glue IAM Role Name"
  type        = string
}

variable "silver_script_key" {
  description = "S3 key of the Bronze to Silver Glue script"
  type        = string
  default     = "etl/final_silver_etl.py"
}

variable "gold_script_key" {
  description = "S3 key of the Silver to Gold Glue script"
  type        = string
  default     = "etl/gold_etl.py"
}

# Conditional creation flags
variable "create_s3_bucket" {
  description = "Whether to create the script S3 bucket. If false, references existing bucket via data source."
  type        = bool
  default     = true
}

variable "create_glue_database" {
  description = "Whether to create the Glue database. If false, references existing database via data source."
  type        = bool
  default     = false
}

variable "create_glue_job_silver" {
  description = "Whether to create the Silver Glue job. If false, references existing job via data source."
  type        = bool
  default     = true
}

variable "create_glue_job_gold" {
  description = "Whether to create the Gold Glue job. If false, references existing job via data source."
  type        = bool
  default     = true
}

variable "create_glue_crawler" {
  description = "Whether to create the Glue crawler. If false, references existing crawler via data source."
  type        = bool
  default     = true
}