resource "aws_glue_catalog_database" "spotify_db" {
  count = var.create_glue_database ? 1 : 0
  name  = var.glue_database_name
}

resource "aws_glue_crawler" "spotify_crawler" {
  count         = var.create_glue_crawler ? 1 : 0
  database_name = local.glue_database_name
  name          = var.glue_crawler_name
  role          = data.aws_iam_role.glue_role.arn

  s3_target {
    path = "s3://${local.s3_bucket_name}/silver/"
  }

  s3_target {
    path = "s3://${local.s3_bucket_name}/gold/"
  }

  tags = local.common_tags
}
