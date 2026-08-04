variable "bucket_name" {
  description = "Name of the medallion data lake S3 bucket (bronze/silver/gold prefixes)."
  type        = string
}

variable "glue_assets_bucket_name" {
  description = "Name of the bucket holding Glue job scripts/assets."
  type        = string
}

variable "athena_results_bucket_name" {
  description = "Name of the bucket holding Athena query results."
  type        = string
}

variable "tags" {
  description = "Extra tags merged into every resource in this module (project/env/managed_by come from provider default_tags)."
  type        = map(string)
  default     = {}
}
