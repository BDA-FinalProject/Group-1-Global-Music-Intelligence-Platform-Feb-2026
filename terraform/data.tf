data "aws_iam_role" "glue_role" {
  name = var.glue_role_name
}

data "aws_s3_bucket" "existing" {
  count  = var.create_s3_bucket ? 0 : 1
  bucket = var.script_bucket_name
}


