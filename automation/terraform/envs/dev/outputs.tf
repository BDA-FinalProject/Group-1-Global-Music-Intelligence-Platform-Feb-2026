output "data_lake_bucket_name" {
  value = module.data_lake.data_lake_bucket_name
}

output "glue_assets_bucket_name" {
  value = module.data_lake.glue_assets_bucket_name
}

output "athena_results_bucket_name" {
  value = module.data_lake.athena_results_bucket_name
}

output "ingestion_instance_id" {
  value = module.ec2_ingestion.instance_id
}

output "github_actions_role_arn" {
  value = var.enable_github_oidc ? module.github_oidc[0].github_actions_role_arn : null
}

output "kaggle_username_param_name" {
  value = module.ssm_kaggle_creds.kaggle_username_param_name
}

output "kaggle_key_param_name" {
  value = module.ssm_kaggle_creds.kaggle_key_param_name
}

output "glue_silver_job_name" {
  value = module.glue_silver_song_charts.job_name
}
