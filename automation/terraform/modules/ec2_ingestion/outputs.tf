output "instance_id" {
  value = aws_instance.ingestion.id
}

output "instance_profile_name" {
  value = local.instance_profile_name
}

output "security_group_id" {
  value = aws_security_group.ingestion.id
}
