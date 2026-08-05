locals {
  common_tags = {
    Project     = "Spotify-Big-Data"
    Environment = "production"
    ManagedBy   = "Terraform"
  }

  s3_bucket_name     = var.create_s3_bucket ? one(aws_s3_bucket.script_bucket[*].id) : one(data.aws_s3_bucket.existing[*].id)
  glue_database_name = var.create_glue_database ? one(aws_glue_catalog_database.spotify_db[*].name) : var.glue_database_name
}
