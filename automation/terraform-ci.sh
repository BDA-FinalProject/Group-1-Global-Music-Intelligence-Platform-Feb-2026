#!/usr/bin/env bash
# Actual Terraform CI/CD logic, kept out of the workflow YAML on purpose so
# it's testable locally (`./automation/terraform-ci.sh plan`) and the
# workflow file stays a thin entrypoint.
set -euo pipefail

action="${1:?usage: terraform-ci.sh <plan|apply>}"

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
env_dir="$script_dir/terraform/envs/dev"

cd "$env_dir"

terraform fmt -check -recursive "$script_dir/terraform"
terraform init -input=false
terraform validate

case "$action" in
  plan)
    terraform plan -input=false -no-color
    ;;
  apply)
    terraform apply -input=false -auto-approve
    ;;
  *)
    echo "unknown action: $action (expected plan|apply)" >&2
    exit 1
    ;;
esac
