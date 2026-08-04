variable "project_name" {
  type    = string
  default = "spotify-lake"
}

variable "env" {
  type    = string
  default = "dev"
}

variable "aws_region" {
  description = "us-east-1 is required while running in the AWS Academy Learner Lab sandbox — EC2 is not accessible from other regions there."
  type        = string
  default     = "us-east-1"
}

variable "github_repo" {
  description = "GitHub repo (org-or-user/repo-name) allowed to assume the CI role."
  type        = string
  default     = "BDA-FinalProject/Group-1-Global-Music-Intelligence-Platform-Feb-2026"
}

variable "kaggle_slug" {
  type    = string
  default = "gonzalopezgil/spotify-charts-daily-updated"
}

variable "target_file" {
  type    = string
  default = "charts_songs_daily.csv.gz"
}

variable "table_name" {
  type    = string
  default = "charts_songs_daily"
}

variable "ingestion_instance_type" {
  description = "m5.large avoids t3.*'s CPU-credit throttling for the sustained CSV->Parquet conversion workload."
  type        = string
  default     = "m5.large"
}

variable "ingestion_root_volume_size" {
  description = "Root EBS volume size (GB) for the ingestion instance."
  type        = number
  default     = 40
}

variable "use_lab_instance_profile" {
  description = "true in the AWS Academy Learner Lab sandbox (can't create IAM roles), false in a real AWS account."
  type        = bool
  default     = true
}

variable "lab_instance_profile_name" {
  type    = string
  default = "LabInstanceProfile"
}

variable "enable_github_oidc" {
  description = "false in the AWS Academy Learner Lab sandbox (can't create an OIDC provider/IAM role there). Set true from a real AWS account to wire up GitHub Actions CI."
  type        = bool
  default     = false
}
