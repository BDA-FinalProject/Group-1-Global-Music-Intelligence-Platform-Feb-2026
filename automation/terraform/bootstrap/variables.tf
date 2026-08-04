variable "project_name" {
  description = "Short project identifier used as a prefix for all resource names."
  type        = string
  default     = "spotify-lake"
}

variable "env" {
  description = "Environment name (e.g. dev, prod)."
  type        = string
  default     = "dev"
}

variable "aws_region" {
  description = "AWS region to bootstrap the Terraform state bucket in. us-east-1 is required in the AWS Academy Learner Lab sandbox."
  type        = string
  default     = "us-east-1"
}
