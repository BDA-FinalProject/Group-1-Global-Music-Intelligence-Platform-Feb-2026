data "aws_iam_role" "lab" {
  count = var.use_lab_role ? 1 : 0
  name  = var.lab_role_name
}

locals {
  role_arn = var.use_lab_role ? data.aws_iam_role.lab[0].arn : var.role_arn
}

resource "aws_s3_object" "script" {
  bucket = var.script_s3_bucket
  key    = var.script_s3_key
  source = var.script_local_path
  etag   = filemd5(var.script_local_path)
}

resource "aws_glue_job" "this" {
  name              = var.job_name
  role_arn          = local.role_arn
  glue_version      = var.glue_version
  worker_type       = var.worker_type
  number_of_workers = var.number_of_workers
  timeout           = var.timeout
  max_retries       = var.max_retries

  command {
    name            = "glueetl"
    script_location = "s3://${var.script_s3_bucket}/${aws_s3_object.script.key}"
    python_version  = "3"
  }

  default_arguments = merge({
    "--job-language"                     = "python"
    "--job-bookmark-option"              = "job-bookmark-disable"
    "--enable-metrics"                   = "true"
    "--enable-continuous-cloudwatch-log" = "true"
    "--TempDir"                          = "s3://${var.script_s3_bucket}/temporary/"
  }, var.default_arguments)

  tags = var.tags
}
