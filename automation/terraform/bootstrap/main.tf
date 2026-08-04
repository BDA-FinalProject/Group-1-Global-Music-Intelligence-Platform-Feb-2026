# One-time bootstrap: the S3 bucket that holds Terraform state for
# everything under terraform/envs/*. This folder uses local state and is
# applied by hand, once, before any envs/* backend can initialize.

resource "aws_s3_bucket" "tfstate" {
  bucket = "${var.project_name}-${var.env}-tfstate"

  tags = {
    Name       = "${var.project_name}-${var.env}-tfstate"
    project    = var.project_name
    env        = var.env
    layer      = "cicd"
    managed_by = "terraform"
  }
}

resource "aws_s3_bucket_versioning" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "tfstate" {
  bucket = aws_s3_bucket.tfstate.id

  rule {
    id     = "expire-noncurrent-versions"
    status = "Enabled"

    filter {}

    noncurrent_version_expiration {
      noncurrent_days = 90
    }
  }
}
