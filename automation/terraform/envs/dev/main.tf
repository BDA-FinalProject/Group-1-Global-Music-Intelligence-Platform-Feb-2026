locals {
  data_bucket_name           = "${var.project_name}-${var.env}-data"
  glue_assets_bucket_name    = "${var.project_name}-${var.env}-glue-assets"
  athena_results_bucket_name = "${var.project_name}-${var.env}-athena-results"
}

module "data_lake" {
  source = "../../modules/data_lake"

  bucket_name                = local.data_bucket_name
  glue_assets_bucket_name    = local.glue_assets_bucket_name
  athena_results_bucket_name = local.athena_results_bucket_name
}

module "ssm_kaggle_creds" {
  source = "../../modules/ssm_kaggle_creds"

  project_name = var.project_name
  env          = var.env
}

module "ec2_ingestion" {
  source = "../../modules/ec2_ingestion"

  project_name              = var.project_name
  env                       = var.env
  aws_region                = var.aws_region
  instance_type             = var.ingestion_instance_type
  root_volume_size          = var.ingestion_root_volume_size
  use_lab_instance_profile  = var.use_lab_instance_profile
  lab_instance_profile_name = var.lab_instance_profile_name

  data_bucket_name = module.data_lake.data_lake_bucket_name
  data_bucket_arn  = module.data_lake.data_lake_bucket_arn

  kaggle_username_param_name = module.ssm_kaggle_creds.kaggle_username_param_name
  kaggle_username_param_arn  = module.ssm_kaggle_creds.kaggle_username_param_arn
  kaggle_key_param_name      = module.ssm_kaggle_creds.kaggle_key_param_name
  kaggle_key_param_arn       = module.ssm_kaggle_creds.kaggle_key_param_arn

  kaggle_slug = var.kaggle_slug
  target_file = var.target_file
  table_name  = var.table_name
}

# Sandbox accounts (AWS Academy Learner Lab etc.) deny iam:CreateRole and
# iam:CreateOpenIDConnectProvider outright — this module can't apply there
# at all. Toggle it off with enable_github_oidc = false in that case; the
# GitHub Actions OIDC role has to be created from a real (non-lab) AWS
# account instead.
module "github_oidc" {
  count  = var.enable_github_oidc ? 1 : 0
  source = "../../modules/github_oidc"

  project_name = var.project_name
  env          = var.env
  github_repo  = var.github_repo
}
