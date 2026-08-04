# automation/

CI/CD logic for the Terraform stack. `terraform/` and `ingestion/` live
alongside this script inside `automation/`, kept separate from the rest of
the repo. The one exception is `.github/workflows/`, which GitHub requires
to physically live at that exact repo-root path — it can't be moved here.

- `terraform-ci.sh` — the actual `fmt` / `init` / `validate` / `plan` /
  `apply` sequence. Runs identically in CI and locally:
  ```
  ./automation/terraform-ci.sh plan
  ./automation/terraform-ci.sh apply
  ```
- `.github/workflows/terraform.yml` is a thin entrypoint: it authenticates
  to AWS via OIDC (no stored access keys) and then just calls this script.

Keeping the logic here instead of inline in the workflow YAML means it's
testable without pushing a commit, and the workflow file stays small.
