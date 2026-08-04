output "kaggle_username_param_name" {
  value = aws_ssm_parameter.kaggle_username.name
}

output "kaggle_username_param_arn" {
  value = aws_ssm_parameter.kaggle_username.arn
}

output "kaggle_key_param_name" {
  value = aws_ssm_parameter.kaggle_key.name
}

output "kaggle_key_param_arn" {
  value = aws_ssm_parameter.kaggle_key.arn
}
