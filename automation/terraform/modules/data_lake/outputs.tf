output "data_lake_bucket_name" {
  value = aws_s3_bucket.data_lake.id
}

output "data_lake_bucket_arn" {
  value = aws_s3_bucket.data_lake.arn
}

output "glue_assets_bucket_name" {
  value = aws_s3_bucket.glue_assets.id
}

output "athena_results_bucket_name" {
  value = aws_s3_bucket.athena_results.id
}
