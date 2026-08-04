output "job_name" {
  value = aws_glue_job.this.name
}

output "script_s3_uri" {
  value = "s3://${var.script_s3_bucket}/${aws_s3_object.script.key}"
}
