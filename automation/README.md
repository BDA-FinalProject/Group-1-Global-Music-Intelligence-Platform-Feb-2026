# automation/

Terraform + ingestion pipeline for the Spotify medallion data lake on AWS
(phase 1). Kept as a self-contained folder, separate from the rest of the
repo — see `SETUP.md` in this folder for full step-by-step apply
instructions.

## What's here

```
terraform/
  bootstrap/     one-time state bucket (local state, applied by hand)
  modules/       data_lake, ssm_kaggle_creds, ec2_ingestion, github_oidc
  envs/dev/      wires the modules together, remote state
ingestion/
  ingest.py      Kaggle -> chunked Parquet conversion -> S3 bronze/
terraform-ci.sh  fmt/init/validate/plan/apply, run identically in CI and locally
README.md        this file
SETUP.md         full apply order, prerequisites, exact commands
```

`.github/workflows/terraform.yml` is the one file that lives outside this
folder — GitHub requires workflow files at that exact repo-root path. It's
a thin entrypoint: authenticates via OIDC, then calls `terraform-ci.sh`.

## Status: tested end-to-end, ingestion confirmed working

This has been run against a real AWS account (an AWS Academy Learner Lab
sandbox) start to finish:

- `terraform apply` created the data lake bucket, SSM parameters, and the
  ingestion EC2 instance without errors
- `ingest.py` downloaded the Kaggle `charts_songs_daily` dataset, converted
  it to Parquet in memory-bounded chunks, and uploaded both the raw and
  Parquet files to `bronze/`
- **42,869,655 rows** landed in S3 successfully
- The EC2 instance was destroyed afterward (`terraform destroy
  -target=module.ec2_ingestion`) to stop billing; the data lake buckets and
  their contents were kept

## Sandbox-account support

Sandbox AWS accounts (AWS Academy Learner Lab, Vocareum, etc.) commonly
deny `iam:CreateRole` / `iam:CreateOpenIDConnectProvider` and lock EC2 to a
single region. Two `envs/dev` variables handle this without touching a
real AWS account's behavior:

| Variable | Sandbox value | Real AWS account |
|---|---|---|
| `use_lab_instance_profile` | `true` — attaches the pre-existing `LabInstanceProfile` | `false` — Terraform creates a purpose-built, least-privilege role |
| `enable_github_oidc` | `false` — OIDC module skipped entirely | `true` — creates the OIDC provider + CI role |

`aws_region` also defaults to `us-east-1` (the only region reachable in the
tested sandbox account) — override it for a real deployment.

## Known real-world gotchas (hit and fixed during testing)

- **Kaggle's actual filename didn't match the assumed one.** The dataset
  ships `charts_songs_daily.csv` (10GB, uncompressed), not
  `charts_songs_daily.csv.gz`. `ingest.py` handles either (branches on the
  `.gz` suffix), but the Terraform `target_file` default needs to match
  whatever Kaggle is actually serving — check with
  `kaggle datasets files -d <slug>` before assuming.
- **`/tmp` on Amazon Linux 2023 is tmpfs (RAM-backed), not disk.** It's
  sized off available RAM and was too small (3.9GB) for a 10GB download.
  Point `WORK_DIR` at a real disk path (e.g. `/opt/ingest/work`) instead of
  the `/tmp` default when working with large files.
- **`t3.*` burstable instances throttle under sustained CPU load.** The
  chunked CSV→Parquet conversion is CPU-bound long enough to exhaust
  `t3.small`'s burst credits. `m5.large` (non-burstable) is the default for
  this reason — resizing is a one-line Terraform variable change, and
  Terraform resizes the existing instance in place (same instance ID, same
  disk) rather than recreating it.
