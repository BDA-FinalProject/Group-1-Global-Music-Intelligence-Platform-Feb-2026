output "script_bucket_name" {
  description = "Name of the script bucket"
  value       = local.s3_bucket_name
}

output "glue_database_name" {
  description = "Name of the Glue database"
  value       = local.glue_database_name
}

output "glue_job_silver_name" {
  description = "Name of the Silver Glue job"
  value       = var.glue_job_silver_name
}

output "glue_job_gold_name" {
  description = "Name of the Gold Glue job"
  value       = var.glue_job_gold_name
}

output "glue_crawler_name" {
  description = "Name of the Glue Crawler"
  value       = var.glue_crawler_name
}
