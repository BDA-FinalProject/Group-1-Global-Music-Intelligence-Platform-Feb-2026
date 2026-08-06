# automation branch — Spotify Medallion Data Lake on AWS

This branch builds a fully Infrastructure-as-Code AWS pipeline that takes
the Kaggle `charts_songs_daily` dataset (~10GB, daily-updated) and lands it
in S3 as a medallion-architecture data lake — **Bronze → Silver → Gold** —
with **zero manual AWS Console clicks**. Everything is provisioned by
Terraform and every transform is a PySpark Glue job.

It's kept intentionally self-contained under `automation/` (plus one
GitHub-mandated exception, noted below) so it merges cleanly without
touching anyone else's work on `main`.

---

## 1. Architecture

```
Kaggle (charts_songs_daily, ~10GB, daily-updated snapshot dataset)
        │  ingest.py runs on an EC2 instance, credentials pulled from SSM
        ▼
S3 bronze/charts_songs_daily/ingest_date=YYYY-MM-DD/
        raw CSV, exactly as Kaggle serves it — no cleaning, no conversion
        │
        │  AWS Glue (PySpark): silver_song_charts.py
        │  auto-detects latest ingest_date, incremental load
        ▼
S3 silver/song_charts/  (Parquet, partitioned by year/month)
        cleaned, deduped, country-standardized, feature-engineered
        │
        │  AWS Glue (PySpark): gold_layer_etl.py
        ▼
S3 gold/  — 5 business-ready tables:
        kpi_song, kpi_artist, country_performance,
        monthly_trends, label_performance_enhanced
```

**A note on "incremental" and why Kaggle limits how far this can go:**
Kaggle's dataset API does **not support delta/incremental downloads**.
Every `kaggle datasets download` call returns the **entire current
snapshot** of the file — there is no API to ask "give me only the rows
added since my last download." This is a Kaggle platform limitation, not
a design choice on our end. Because of that:

- **Bronze ingestion** always pulls the full ~10GB file. The only thing we
  control is *when* to pull it and *where it lands* (a new dated
  partition each time, so old pulls are never overwritten).
- **Silver is where real incrementality starts**, and it *is* implemented:
  the Glue job reads the latest Bronze snapshot but only processes rows
  with `date > max(date already in Silver)`, so re-running it after a new
  Bronze pull is cheap — it doesn't reprocess history it already has.
- **Gold** currently recomputes from the full Silver dataset on every run
  (aggregation tables can't just be appended to without risking
  double-counting). This is a known, deliberate scope boundary for this
  phase, not an oversight.

---

## 2. Repository layout — what every file/folder does

```
README.md                          this file
.gitignore                         standard Terraform/Python/OS ignores
.github/workflows/terraform.yml    CI entrypoint (see §2.1 — the one file outside automation/)

automation/
├── README.md                      technical reference: layout, sandbox toggles, real bugs hit + fixed
├── SETUP.md                       step-by-step commands to stand this up from zero
├── terraform-ci.sh                the actual fmt/init/validate/plan/apply logic, shared by CI and local runs
│
├── ingestion/
│   ├── ingest.py                  Kaggle -> S3 bronze/, runs on the EC2 instance
│   └── requirements.txt           Python deps for ingest.py (boto3, kaggle)
│
├── glue_jobs/
│   ├── silver_song_charts.py      PySpark: bronze -> silver (cleaning + incremental load)
│   └── gold_layer_etl.py          PySpark: silver -> 5 gold business tables
│
└── terraform/
    ├── bootstrap/                 one-time state bucket, applied by hand, local state
    │   ├── main.tf                 the S3 bucket + versioning/encryption/lifecycle config
    │   └── variables.tf            project_name/env/aws_region — just naming/region inputs
    │
    ├── envs/dev/                  ROOT MODULE — one `terraform apply` here builds everything
    │   ├── main.tf                 wires all 6 modules together (see §2.2)
    │   ├── variables.tf            every configurable value for this environment, with defaults
    │   ├── outputs.tf              exposes bucket names, instance ID, Glue job names, etc.
    │   └── backend.tf              points remote state at the bootstrap bucket (S3-native locking)
    │
    └── modules/                   6 reusable building blocks (see §2.3 for what each provisions)
        ├── data_lake/
        ├── ssm_kaggle_creds/
        ├── ec2_ingestion/
        │   └── templates/user_data.sh.tpl   EC2 boot script (installs deps, does NOT run ingest.py)
        ├── glue_job/               generic module, instantiated twice (Silver job + Gold job)
        └── github_oidc/            GitHub Actions -> AWS trust, no stored AWS keys
```

### 2.1 Why `.github/workflows/terraform.yml` lives outside `automation/`

GitHub requires workflow files at the exact repo-root path
`.github/workflows/`; they cannot be nested under a subfolder. It's kept
deliberately thin — all real logic lives in `automation/terraform-ci.sh`,
which is directly runnable and testable locally (`./automation/terraform-ci.sh plan`).
The workflow just authenticates via OIDC and calls that script.

### 2.2 `envs/dev/main.tf` — how the 6 modules fit together

```
terraform apply
        │
        ├── module.data_lake              → 3 S3 buckets (bronze/silver/gold, glue-assets, athena-results)
        ├── module.ssm_kaggle_creds       → 2 SSM parameter slots for Kaggle creds
        ├── module.ec2_ingestion          → depends on the two above (needs bucket ARN + param ARNs)
        ├── module.glue_silver_song_charts → instance of glue_job, depends on data_lake (glue-assets bucket)
        ├── module.glue_gold_layer         → same, second instance of glue_job
        └── module.github_oidc             → count = enable_github_oidc ? 1 : 0 (off in sandbox)
```

Terraform resolves this dependency order automatically from module
outputs referenced in each module's inputs — nothing here is manually
sequenced.

### 2.3 What each Terraform module actually provisions

| Module | Resources created | Why it exists |
|---|---|---|
| `data_lake` | 3 S3 buckets (data lake with bronze/silver/gold zero-byte prefix markers, glue-assets, athena-results), each with versioning, SSE-AES256 encryption, and public-access block | The physical storage layer everything else writes to/reads from |
| `ssm_kaggle_creds` | 2 `SecureString` SSM parameters (`.../kaggle/username`, `.../kaggle/key`), created with a placeholder value and `lifecycle.ignore_changes = [value]` | Terraform creates the *slot*, never the *secret* — real credentials are seeded once by hand via `aws ssm put-parameter` and Terraform is told to never touch the value again. Keeps Kaggle credentials out of git and out of Terraform state diffs entirely |
| `ec2_ingestion` | EC2 instance (Amazon Linux 2023, latest AMI via SSM parameter lookup), security group with **zero inbound rules**, IAM role/instance-profile (or the sandbox's `LabInstanceProfile`), boots via `user_data.sh.tpl` | Runs `ingest.py`. No SSH surface at all — the security group only has an egress rule; the only way onto the box is SSM Session Manager, which is IAM-authenticated and fully audit-logged |
| `glue_job` | One `aws_glue_job` resource + uploads its PySpark script to S3 (`aws_s3_object`, keyed by `filemd5()` so it re-uploads only when the script content changes) | Generic/reusable — the same module code creates both the Silver job and the Gold job, just with different script paths and job names |
| `github_oidc` | OIDC identity provider trusting `token.actions.githubusercontent.com`, plus an IAM role GitHub Actions can assume (scoped to this exact repo, `refs/heads/main` only) | Lets CI authenticate to AWS with a short-lived federated token per run — **no AWS access keys are ever stored as GitHub secrets** |

### 2.4 The two Python pipeline scripts, in detail

**`ingestion/ingest.py`** (runs on the EC2 instance):
1. Reads Kaggle username/key from SSM (`ssm:GetParameter`, decrypted)
2. Runs `kaggle datasets download` for the target file
3. Uploads it **as-is** (raw CSV, no conversion) to
   `s3://.../bronze/charts_songs_daily/ingest_date=<today>/<filename>`
4. Idempotent — re-running for the same `--ingest-date` overwrites that
   exact partition rather than duplicating

Deliberately does **no cleaning and no format conversion** — Bronze's job
is to be a faithful, untouched copy of what Kaggle actually served that
day. All transformation happens downstream in Glue, where it's versioned,
reviewable PySpark code instead of an ad-hoc script running on a box.

**`glue_jobs/silver_song_charts.py`** (AWS Glue, PySpark):
1. Auto-detects the most recent `ingest_date` partition in Bronze
2. Finds `max(date)` already present in Silver, filters the Bronze
   snapshot to only rows newer than that (first run processes everything)
3. Cleans: dedupes on `(date, country, uri)`, maps country codes to full
   names, drops the "Global" aggregate rows, fills nulls, trims whitespace
4. Feature-engineers: `hit_category` (rank-based tiering), `chart_strength_score`
   (weighted composite of rank/peak_rank/days_on_chart/consecutive_days),
   `standardized_label`, `year`/`month`/`quarter`
5. Appends the result to `silver/song_charts/`, partitioned by year/month

**`glue_jobs/gold_layer_etl.py`** (AWS Glue, PySpark):
Reads the full Silver dataset and produces 5 overwrite-mode business
tables: `kpi_song` (per-song monthly streams + hit flag), `kpi_artist`
(distinct active artists per month/country), `country_performance` (top
song/artist, growth %, active artists — via window functions),
`monthly_trends`, and `label_performance_enhanced` (with a hardcoded
label-standardization mapping, e.g. consolidating label name variants
under their parent label).

---

## 3. How much of this is actually automated

**Automated end-to-end, by code, with zero manual AWS Console steps:**
- All infrastructure provisioning — every S3 bucket, the EC2 instance, both
  Glue jobs, IAM roles/instance profiles, SSM parameter slots, the security
  group — is defined in Terraform. `terraform apply` builds the entire
  stack from nothing.
- The full **data transformation logic**, Bronze through Gold, is written
  as code (`ingest.py` + 2 PySpark scripts) — nothing about *what happens
  to the data* is manual or done by hand in a notebook/console.
- Silver's incremental-load logic (detect latest partition, filter to only
  new rows, append) is fully automatic once the job is triggered.
- CI/CD scaffolding (`terraform-ci.sh` + the GitHub Actions workflow) is
  code-complete and will run `plan` on PRs / `apply` on merge to `main`
  automatically — currently inactive only because this specific AWS
  account is an AWS Academy Learner Lab sandbox that denies
  `iam:CreateOpenIDConnectProvider`, so `enable_github_oidc = false` for
  now. No code changes needed to activate it on a real AWS account.

**Manual today — deliberately deferred, not a limitation of the code:**
- *Triggering* each pipeline stage. Ingestion runs via SSM (copy the
  script over, run it by hand); the Silver and Gold Glue jobs are started
  with `aws glue start-job-run`. There is currently no scheduler or
  chaining between stages — this is the main piece of orchestration work
  still to do (candidates: `aws_glue_trigger` for Silver→Gold chaining on
  job success, EventBridge + a scheduled trigger for periodic ingestion).
- Tearing down the EC2 instance after an ingestion run
  (`terraform destroy -target=module.ec2_ingestion`) to stop billing.
- Registering the Gold tables with Athena (no crawler configured yet) —
  needed before anyone can query Gold with SQL.

**Bottom line:** the automation covers everything that's *possible* to
automate for the ingestion→transform pipeline itself — infra, cleaning,
feature engineering, incremental Silver loading. What's left is
*orchestration* (chaining/scheduling the already-automated stages) and the
*serving layer* (Athena + a dashboard/RAG interface), both of which are
explicitly out of scope for this phase.

---

## 4. Proof this actually works (run against a real AWS account)

1. `terraform apply` built the state bucket, data lake bucket, SSM
   parameters, and EC2 instance with zero manual AWS console steps.
2. Connected via SSM Session Manager, ran `ingest.py` — **42,869,655 rows**
   landed in S3 as the Bronze snapshot, confirmed via `aws s3 ls`.
3. Hit and fixed three real bugs along the way (documented in
   `automation/README.md`): a wrong assumed Kaggle filename, `/tmp` being
   a too-small RAM disk on Amazon Linux 2023, and `t3.small` throttling
   under sustained CPU load.
4. Triggered the Silver Glue job (`aws glue start-job-run`) —
   **succeeded in 612 seconds**, `silver/song_charts/` now has cleaned,
   year/month-partitioned data with the new analytical columns.
5. Triggered the Gold Glue job — **succeeded in 336 seconds**, produced
   all 5 gold tables, spot-checked for sane non-null values.
6. Re-ran ingestion again on a later date (a second `ingest_date`
   partition landed in Bronze without disturbing the first, or touching
   Silver/Gold) — confirms the pipeline is repeatable, not a one-off.

---

## 5. Design choices worth knowing about

- **No long-lived AWS credentials anywhere.** GitHub Actions authenticates
  via OIDC (`github_oidc` module) — a short-lived token per run, nothing
  stored as a repo secret.
- **Kaggle credentials never touch git.** Terraform creates the SSM
  parameter *slots*; the real username/key are seeded by hand with
  `aws ssm put-parameter`, and `lifecycle.ignore_changes` means Terraform
  never reverts that value on a later apply.
- **No SSH.** The ingestion instance has zero inbound security group
  rules — access is exclusively via SSM Session Manager.
- **Works in both a real AWS account and a classroom sandbox.** AWS
  Academy Learner Lab / Vocareum-style accounts deny `iam:CreateRole` and
  lock EC2 to one region. Two Terraform variables
  (`use_lab_instance_profile`, `enable_github_oidc`) switch between
  "create a proper least-privilege role" and "use the sandbox's
  pre-existing `LabInstanceProfile` / skip OIDC entirely" — same codebase,
  no forked config. Details in `automation/README.md`.

---

## 6. Where to go next

- Want to run this yourself? Start with `automation/SETUP.md` — exact
  commands, in order.
- Want deeper technical detail (variable-by-variable, known gotchas,
  IAM scoping notes)? `automation/README.md`.
- Bronze→Silver→Gold (this branch) is done, end to end. Pipeline
  orchestration (auto-chaining the stages), Athena table registration, and
  the Postgres/RAG serving layer are separate, later work.
