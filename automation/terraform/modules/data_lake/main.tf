# Medallion data lake bucket (bronze/silver/gold) plus the two auxiliary
# buckets Glue and Athena need. All three are created empty here; Glue jobs
# and Athena workgroups that populate/read them are a later phase.

resource "aws_s3_bucket" "data_lake" {
  bucket = var.bucket_name
  tags   = merge(var.tags, { Name = var.bucket_name, layer = "lake" })
}

resource "aws_s3_bucket_versioning" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "data_lake" {
  bucket = aws_s3_bucket.data_lake.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "data_lake" {
  bucket                  = aws_s3_bucket.data_lake.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Zero-byte objects so bronze/, silver/, gold/ show up as prefixes even
# before any real data lands in them.
resource "aws_s3_object" "medallion_prefixes" {
  for_each = toset(["bronze/", "silver/", "gold/"])

  bucket  = aws_s3_bucket.data_lake.id
  key     = each.value
  content = ""
}

resource "aws_s3_bucket" "glue_assets" {
  bucket = var.glue_assets_bucket_name
  tags   = merge(var.tags, { Name = var.glue_assets_bucket_name, layer = "etl" })
}

resource "aws_s3_bucket_versioning" "glue_assets" {
  bucket = aws_s3_bucket.glue_assets.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "glue_assets" {
  bucket = aws_s3_bucket.glue_assets.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "glue_assets" {
  bucket                  = aws_s3_bucket.glue_assets.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket" "athena_results" {
  bucket = var.athena_results_bucket_name
  tags   = merge(var.tags, { Name = var.athena_results_bucket_name, layer = "serving" })
}

resource "aws_s3_bucket_versioning" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "athena_results" {
  bucket = aws_s3_bucket.athena_results.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "athena_results" {
  bucket                  = aws_s3_bucket.athena_results.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
