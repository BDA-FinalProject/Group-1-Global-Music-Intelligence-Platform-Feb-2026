# Terraform creates the parameter, never the value. The placeholder value
# below is only ever seen by Terraform's own state on the very first apply;
# `lifecycle.ignore_changes` means a later `aws ssm put-parameter` from you
# is never reverted by a subsequent `terraform apply`.

resource "aws_ssm_parameter" "kaggle_username" {
  name        = "/${var.project_name}/${var.env}/kaggle/username"
  description = "Kaggle API username. Value is seeded manually, not by Terraform."
  type        = "SecureString"
  value       = "REPLACE_ME_MANUALLY"
  tags        = merge(var.tags, { layer = "ingestion" })

  lifecycle {
    ignore_changes = [value]
  }
}

resource "aws_ssm_parameter" "kaggle_key" {
  name        = "/${var.project_name}/${var.env}/kaggle/key"
  description = "Kaggle API key. Value is seeded manually, not by Terraform."
  type        = "SecureString"
  value       = "REPLACE_ME_MANUALLY"
  tags        = merge(var.tags, { layer = "ingestion" })

  lifecycle {
    ignore_changes = [value]
  }
}
