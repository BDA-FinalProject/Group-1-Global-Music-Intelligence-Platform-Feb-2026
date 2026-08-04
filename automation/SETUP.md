# spotify-lake — AWS Medallion Pipeline (Phase 1)

S3 medallion lake (bronze/silver/gold) + Kaggle ingestion EC2 instance,
fully defined in Terraform, deployed via GitHub Actions with OIDC (no
long-lived AWS keys). This is phase 1 only: bootstrap + data lake +
ingestion instance + CI wiring. Glue transforms, Athena, Postgres/RAG
serving are later phases.

## Layout

```
automation/
  terraform/
    bootstrap/        one-time state bucket, local state, applied by hand
    modules/           data_lake, ssm_kaggle_creds, ec2_ingestion, github_oidc
    envs/dev/          root module wiring the above together, remote state
  ingestion/
    ingest.py          Kaggle -> Parquet -> bronze/, runs on the EC2 instance
  terraform-ci.sh      actual fmt/init/validate/plan/apply logic
.github/workflows/
  terraform.yml        thin GitHub Actions entrypoint (OIDC auth, calls the script above)
```

Everything for this pipeline lives under `automation/` on purpose — kept
separate from any app-level code elsewhere in this repo. `.github/workflows/`
is the one exception: GitHub requires workflow files at that exact
repo-root path, they can't be nested.

## Prerequisites

- AWS CLI configured locally with credentials that can create the bootstrap
  resources (S3, IAM) — used once, by hand, for the bootstrap apply only.
- **Terraform >= 1.9.0** installed locally. `use_lockfile = true` (S3 native
  state locking, no DynamoDB table) requires this version — check with
  `terraform version` before running anything below. Install via
  [tfenv](https://github.com/tfutils/tfenv) or the
  [official installer](https://developer.hashicorp.com/terraform/install)
  if you don't have it yet.
- A Kaggle account with an API token (Account -> Create New Token on
  kaggle.com) — you'll need the username + key values for step 3.

## Apply order

1. **Bootstrap the state bucket** (local state, applied once by hand):
   ```
   cd automation/terraform/bootstrap
   terraform init
   terraform apply
   ```
   Confirms creation of `spotify-lake-dev-tfstate`.

2. **Apply the dev environment** (creates the data lake, glue-assets,
   athena-results buckets, the SSM parameter placeholders, the ingestion
   EC2 instance, and the GitHub OIDC role):
   ```
   cd ../../terraform/envs/dev
   terraform init
   terraform apply
   ```
   All variables have defaults matching this project's actual config
   (`spotify-lake` / `dev` / `ap-south-1` / the Kaggle dataset), so no
   `.tfvars` file is required for dev. Note the `github_actions_role_arn`
   output — you'll need it in step 5.

3. **Seed the real Kaggle credentials** (Terraform created the parameters
   with a placeholder value and will never touch `value` again after this):
   ```
   aws ssm put-parameter \
     --name /spotify-lake/dev/kaggle/username \
     --value "<your-kaggle-username>" \
     --type SecureString --overwrite

   aws ssm put-parameter \
     --name /spotify-lake/dev/kaggle/key \
     --value "<your-kaggle-api-key>" \
     --type SecureString --overwrite
   ```

4. **Deploy and run the ingestion script** (no automated trigger yet —
   copy it onto the instance via Session Manager and run it by hand):
   ```
   aws ssm start-session --target <ingestion_instance_id-from-outputs>

   # on the instance:
   source /etc/profile.d/ingestion-env.sh
   # copy ingest.py + requirements.txt over (e.g. via `aws s3 cp` after
   # uploading them to the glue-assets bucket, or `aws ssm send-command`)
   python3 ingest.py
   ```

5. **Wire up GitHub Actions** so pushes to `main` run `terraform apply`
   automatically:
   - In the GitHub repo settings, add a repository **variable** (not
     secret — it's not sensitive) named `AWS_GITHUB_ACTIONS_ROLE_ARN` set
     to the `github_actions_role_arn` output from step 2.
   - No AWS access keys are ever stored in GitHub — the workflow
     (`.github/workflows/terraform.yml`) assumes the role via OIDC.
   - Opening a PR against `main` that touches `automation/terraform/**` runs
     `terraform plan`; merging to `main` runs `terraform apply`.

## Notes

- `automation/terraform/bootstrap` is intentionally excluded from the
  GitHub Actions workflow — it uses local state and is meant to be run by
  a human once.
- Bucket names, the Kaggle dataset slug/target file, and instance sizing
  are all `automation/terraform/envs/dev/variables.tf` defaults — override via
  `-var` or a `.tfvars` file if you need to change them without editing
  code.
