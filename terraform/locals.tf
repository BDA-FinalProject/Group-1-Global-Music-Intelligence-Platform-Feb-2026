locals {
  common_tags = {
    Project     = "Spotify-Big-Data"
    Environment = "production"
    ManagedBy   = "Terraform"
  }

  s3_bucket_name     = var.create_s3_bucket ? aws_s3_bucket.script_bucket[0].id : data.aws_s3_bucket.existing[0].id
  glue_database_name = var.create_glue_database ? aws_glue_catalog_database.spotify_db[0].name : var.glue_database_name
}
