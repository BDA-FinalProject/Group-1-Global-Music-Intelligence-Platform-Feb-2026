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
   (`spotify-lake` / `dev` / `us-east-1` / the Kaggle dataset), so no
   `.tfvars` file is required for dev. Defaults also assume a sandbox
   account (`use_lab_instance_profile = true`, `enable_github_oidc =
   false`) — see `README.md` in this folder for what to flip for a real
   AWS account, which also gets you the `github_actions_role_arn` output
   used in step 5.

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

5. **Wire up GitHub Actions** (real AWS account only — set
   `enable_github_oidc = true` and re-apply first; sandbox accounts can't
   create the OIDC provider) so pushes to `main` run `terraform apply`
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

## Day-to-day operations (once the stack is already deployed)

You don't need to re-apply Terraform for routine use — infra only changes
when the `.tf` files do. This section covers running the pipeline itself:
pulling new Kaggle data, transforming it, and cleaning up afterward.

### Run ingestion (Kaggle -> Bronze)

`ingest.py` is not baked into the EC2 instance's boot image — it has to be
uploaded to S3 and pulled onto the box fresh each time you want to run the
latest version of it.

```bash
# Always run this from the repo root — a relative path from the wrong
# directory will silently upload some other file that happens to exist
# at that path instead of erroring.
cd /path/to/spotify-lake-infra
aws s3 cp automation/ingestion/ingest.py s3://spotify-lake-dev-glue-assets/scripts/ingest.py

# Use an interactive session, not send-command — far easier to see errors
# live instead of round-tripping through get-command-invocation each time.
aws ssm start-session --region us-east-1 --target <instance-id>
```

On the instance:

```bash
sudo -i    # root login shell — /etc/profile.d/ingestion-env.sh auto-sources here

python3 -c "import boto3; boto3.client('s3', region_name='us-east-1').download_file('spotify-lake-dev-glue-assets', 'scripts/ingest.py', '/opt/ingest.py')"

python3 /opt/ingest.py --work-dir /opt/ingest/work --target-file charts_songs_daily.csv
```

**Known gotchas (hit during real runs, worth knowing before you hit them again):**

- **Don't prefix commands with `sudo` once you're already in a `sudo -i`
  root shell.** `sudo` resets the environment by default even when you're
  already root, which wipes out the Kaggle/bucket env vars that were
  sourced from `/etc/profile.d/ingestion-env.sh` — `ingest.py` then fails
  with "missing required config" even though the vars are visibly set in
  your shell.
- **Always pass `--target-file charts_songs_daily.csv` explicitly.** The
  `$TARGET_FILE` env var baked into this instance at launch time is stale
  (`charts_songs_daily.csv.gz`, which 404s — Kaggle serves this file
  uncompressed). The instance's `/etc/profile.d/ingestion-env.sh` only
  reflects whatever `target_file` value was current in Terraform *at the
  moment the instance was launched*; changing the variable later and
  re-applying does not retroactively update it on an already-running box.
- **Use `--work-dir /opt/ingest/work`, never the default `/tmp`.** On
  Amazon Linux 2023, `/tmp` is RAM-backed (tmpfs) and too small for a
  ~10GB download.
- If your local AWS CLI's default region isn't `us-east-1`, **pass
  `--region us-east-1` explicitly** on every `aws ssm` / `aws glue`
  command — the ingestion instance and both Glue jobs live there
  regardless of what your shell's default region is set to.

### Run the transform jobs (Bronze -> Silver -> Gold)

```bash
aws glue start-job-run --region us-east-1 --job-name spotify-lake-dev-silver-song-charts
# wait for it to succeed, then:
aws glue start-job-run --region us-east-1 --job-name spotify-lake-dev-gold-layer
```

Run Silver before Gold — Gold reads the full Silver dataset, so it needs
Silver's latest output to exist first. Silver itself is incremental: it
auto-detects the newest Bronze `ingest_date` partition and only processes
rows newer than what's already in Silver, so it's cheap to re-run.

Check status:
```bash
aws glue get-job-runs --region us-east-1 --job-name <job-name> --max-results 3
```

### Verify

```bash
aws s3 ls s3://spotify-lake-dev-data/bronze/charts_songs_daily/ --recursive --human-readable
aws s3 ls s3://spotify-lake-dev-data/silver/song_charts/ --recursive --summarize
aws s3 ls s3://spotify-lake-dev-data/gold/ --recursive --summarize

cd automation/terraform/envs/dev && terraform plan   # "No changes" = infra matches code, no drift
```

### Clean up (stop paying for the EC2 instance)

The ingestion EC2 instance only needs to exist while ingestion is
actually running — tear it down afterward:

```bash
cd automation/terraform/envs/dev
terraform destroy -target=module.ec2_ingestion
```

This only removes the EC2 instance and its security group — the S3
buckets and all data in them are untouched. Run `terraform apply` again
next time you need to ingest; it recreates the instance from scratch in
under a minute.
