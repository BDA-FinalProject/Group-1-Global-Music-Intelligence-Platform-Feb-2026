resource "aws_s3_bucket" "script_bucket" {
  count         = var.create_s3_bucket ? 1 : 0
  bucket        = var.script_bucket_name
  force_destroy = false

  tags = local.common_tags
}

resource "aws_s3_bucket_public_access_block" "script_bucket_public_access_block" {
  count  = var.create_s3_bucket ? 1 : 0
  bucket = aws_s3_bucket.script_bucket[0].id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
