# Remote state in the bucket created by terraform/bootstrap. S3 native
# locking (use_lockfile) needs Terraform >= 1.9 and no DynamoDB table.
terraform {
  backend "s3" {
    bucket       = "spotify-lake-dev-tfstate"
    key          = "envs/dev/terraform.tfstate"
    region       = "us-east-1"
    use_lockfile = true
    encrypt      = true
  }
}
