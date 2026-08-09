resource "aws_glue_job" "silver_job" {
  count        = var.create_glue_job_silver ? 1 : 0
  name         = var.glue_job_silver_name
  role_arn     = data.aws_iam_role.glue_role.arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    script_location = "s3://${local.s3_bucket_name}/${var.silver_script_key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${local.s3_bucket_name}/temporary/"
    "--spark-event-logs-path"            = "s3://${local.s3_bucket_name}/sparkHistoryLogs/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "true"
  }

  tags = local.common_tags
}

resource "aws_glue_job" "gold_job" {
  count        = var.create_glue_job_gold ? 1 : 0
  name         = var.glue_job_gold_name
  role_arn     = data.aws_iam_role.glue_role.arn
  glue_version = "4.0"

  command {
    name            = "glueetl"
    script_location = "s3://${local.s3_bucket_name}/${var.gold_script_key}"
    python_version  = "3"
  }

  default_arguments = {
    "--job-language"                     = "python"
    "--TempDir"                          = "s3://${local.s3_bucket_name}/temporary/"
    "--spark-event-logs-path"            = "s3://${local.s3_bucket_name}/sparkHistoryLogs/"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--enable-glue-datacatalog"          = "true"
  }

  tags = local.common_tags
}
