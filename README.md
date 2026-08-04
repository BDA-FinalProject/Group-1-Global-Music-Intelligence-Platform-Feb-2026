# automation branch

This branch adds a Terraform-managed AWS pipeline for the Spotify medallion
data lake — infrastructure-as-code, ingestion, and CI/CD. It's kept
intentionally separate from the rest of the project: everything this
branch adds lives under `automation/` (plus one GitHub-mandated exception,
noted below), so it merges cleanly without touching anyone else's work.

## What this branch does

Takes one raw Kaggle dataset and gets it into S3, medallion-style, entirely
through code — no manual console clicking:

```
Kaggle (charts_songs_daily, ~10GB)
        │  kaggle CLI, credentials pulled from SSM
        ▼
EC2 ingestion instance
        │  chunked CSV -> Parquet conversion (bounded memory,
        │  works regardless of file size)
        ▼
S3 bronze/ prefix (raw csv + parquet, both partitioned by ingest_date)
        │  AWS Glue (PySpark) job
        │  clean, dedupe, country-standardize, feature-engineer
        ▼
S3 silver/song_charts/ (Parquet, partitioned by year/month)
        │  AWS Glue (PySpark) job
        │  aggregate + window functions (top artist/label, growth %,
        │  market share, catalog hit rate)
        ▼
S3 gold/ — 5 business-ready tables:
        dashboard_summary, country_performance, monthly_trends,
        label_performance, artist_performance
```

Everything that provisions this — the S3 buckets, the EC2 instance, the
Glue job, the IAM/SSM wiring, the CI pipeline — is Terraform, reviewable
and repeatable instead of one-off console setup.

## What's in this branch

| Path | What it is |
|---|---|
| `automation/terraform/bootstrap/` | One-time S3 bucket for Terraform state |
| `automation/terraform/modules/` | 5 building blocks: `data_lake`, `ssm_kaggle_creds`, `ec2_ingestion`, `glue_job`, `github_oidc` |
| `automation/terraform/envs/dev/` | Root module — wires everything together, one `apply` builds the whole stack |
| `automation/ingestion/ingest.py` | The ingestion script that runs on the EC2 instance (bronze) |
| `automation/glue_jobs/silver_song_charts.py` | PySpark job: bronze → silver (cleaning, country names, hit-category/chart-strength features) |
| `automation/glue_jobs/gold_layer_etl.py` | PySpark job: silver → 5 gold tables (dashboard/country/monthly/label/artist) |
| `automation/terraform-ci.sh` | fmt/init/validate/plan/apply, identical in CI and local runs |
| `.github/workflows/terraform.yml` | GitHub Actions entrypoint — PR gets `plan`, merge to `main` gets `apply`, authenticated via OIDC (no AWS keys stored in GitHub) |
| `automation/README.md` | Technical reference: layout, sandbox-account toggles, bugs hit and fixed |
| `automation/SETUP.md` | Step-by-step: exact commands, in order, to stand this up from scratch |

## Design choices worth knowing about

- **No long-lived AWS credentials anywhere.** GitHub Actions authenticates
  via OIDC (`github_oidc` module) — a short-lived token per run, nothing
  stored as a repo secret.
- **Kaggle credentials never touch git.** Terraform creates the SSM
  parameter *slots*; the real username/key are seeded by hand with
  `aws ssm put-parameter` and Terraform is told to never touch `value`
  again (`lifecycle.ignore_changes`).
- **No SSH.** The ingestion instance has zero inbound security group
  rules — access is exclusively via SSM Session Manager.
- **Memory-safe by construction.** `ingest.py` streams the CSV→Parquet
  conversion in 250k-row chunks, so it works the same whether the source
  file is 1GB or 100GB — memory use doesn't scale with file size.
- **Works in both a real AWS account and a classroom sandbox.** AWS
  Academy Learner Lab / Vocareum-style accounts deny `iam:CreateRole` and
  lock EC2 to one region. Two Terraform variables
  (`use_lab_instance_profile`, `enable_github_oidc`) switch between
  "create a proper least-privilege role" and "use the sandbox's
  pre-existing `LabInstanceProfile` / skip OIDC entirely" — same codebase,
  no forked config. Details in `automation/README.md`.

## Proof it actually works

This isn't just code that *should* work — it was run against a real AWS
account end to end:

1. `terraform apply` — built the state bucket, data lake bucket, SSM
   parameters, and EC2 instance with zero manual AWS console steps
2. Connected via SSM Session Manager, ran `ingest.py`
3. Hit and fixed three real bugs along the way (wrong assumed filename,
   `/tmp` being a too-small RAM disk on Amazon Linux 2023, `t3.small`
   throttling under sustained CPU load — full writeup in
   `automation/README.md`)
4. **42,869,655 rows** landed in S3 as Parquet, confirmed via `aws s3 ls`
5. Tore the EC2 instance down again once confirmed (`terraform destroy
   -target=module.ec2_ingestion`) so nothing keeps billing
6. Applied the `glue_job` module, triggered a real run
   (`aws glue start-job-run`), and it **SUCCEEDED in 612 seconds** —
   `silver/song_charts/` now has cleaned, year/month-partitioned data with
   the new analytical columns. Unlike EC2, a Glue job only costs money
   while a run is actively executing — nothing to tear down once it
   finishes.
7. Reused the same `glue_job` module for a second job, silver→gold. Fixed
   a real bug in the source script first — it referenced
   `col("artist_uri")` but the actual silver column is `artist_uris`
   (plural), which would have failed with `AnalysisException` on every
   run. Triggered it — **SUCCEEDED in 336 seconds**, produced all 5 gold
   tables, spot-checked (`active_artists` counts are real, non-null;
   `dashboard_summary` and `monthly_trends` agree on their overlapping
   columns).

## Where to go next

- Want to run this yourself? Start with `automation/SETUP.md` — exact
  commands, in order.
- Want the technical details (toggles, known gotchas, architecture)?
  `automation/README.md`.
- Bronze→silver→gold (this branch) is done, end to end. Athena and the
  Postgres/RAG serving layer are separate, later work.
