# Setup Guide — Spotify Medallion Data Lake on AWS

This guide walks you through standing up the entire pipeline from
scratch, and then running it day-to-day, **even if you've never used
Terraform or AWS Glue before.** Every step explains *what* you're doing
and *why*, not just the command to paste. It's long on purpose — read it
once fully, then you'll only need the command boxes on future runs.

If you get stuck, jump to **§7 Troubleshooting** — it covers every real
error we've actually hit while building and running this.

---

## 0. What you're building, in plain English

By the end of this guide, you'll have:

1. Some **storage** in AWS (S3 "buckets" — think of them as folders that
   live in the cloud) to hold data at three stages of cleanliness:
   raw ("bronze"), cleaned ("silver"), and business-ready ("gold").
2. A small **virtual computer** (an EC2 instance) that downloads a dataset
   from Kaggle and drops it into the "bronze" storage.
3. Two **automated data-cleaning jobs** (AWS Glue jobs, which just run our
   Python/PySpark scripts on AWS's infrastructure) that turn bronze data
   into silver, then silver into gold.

All of this is described as **code** (Terraform files, ending in `.tf`)
instead of being clicked together by hand in the AWS website. That means
anyone on the team can read exactly what infrastructure exists, and
recreate it identically by running one command.

**Key concepts you'll see repeated below** (skip if you already know these):

| Term | What it means here |
|---|---|
| **Terraform** | A tool that reads `.tf` files describing "what AWS resources should exist" and creates/updates/deletes real AWS resources to match. Running it is called an "apply." |
| **S3 bucket** | Cloud file storage. A "prefix" inside a bucket is just a folder path, e.g. `bronze/` |
| **EC2 instance** | A virtual machine running in AWS |
| **AWS Glue job** | A managed way to run a PySpark (big-data Python) script without managing servers yourself |
| **SSM (Systems Manager)** | The AWS service we use to (a) securely store secrets like Kaggle credentials, and (b) remotely run commands on the EC2 instance without ever using SSH |
| **State** (Terraform state) | Terraform's memory of what it already created, so it knows what to change on the next apply instead of creating duplicates |

---

## 1. Prerequisites — install and verify each one

Do these once, before anything else. Each has a command to confirm it
worked.

### 1.1 AWS CLI, configured with working credentials

Install: <https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html>

Verify it's installed **and** that you're logged in:
```bash
aws sts get-caller-identity
```
You should see JSON back with an `Account` and `Arn` field — no output or
an error here means you're not authenticated yet (in an AWS Academy
Learner Lab, this usually means copying fresh temporary credentials from
the lab's "AWS Details" page into `~/.aws/credentials`).

### 1.2 Terraform, version 1.9 or newer

Install via [tfenv](https://github.com/tfutils/tfenv) or the
[official installer](https://developer.hashicorp.com/terraform/install).

Verify:
```bash
terraform version
```
The version **must be >= 1.9.0** — this project's remote state locking
(`use_lockfile = true`) is a Terraform 1.9+ feature and won't work on
older versions.

### 1.3 Session Manager plugin (for running commands on EC2 without SSH)

Install: <https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html>
(on Mac: `brew install --cask session-manager-plugin`)

Verify:
```bash
session-manager-plugin --version
```

### 1.4 A Kaggle account with an API token

1. Log into <https://www.kaggle.com>
2. Click your profile picture (top right) → **Settings**
3. Scroll to the **API** section → click **Create New Token**
4. This downloads a `kaggle.json` file containing your `username` and
   `key` — keep both values handy, you'll paste them in manually in
   §3 below (they never go into any file in this repo, and never get
   committed to git).

---

## 2. Build the infrastructure

**If someone on your team has already run this and the AWS account
already has everything deployed, skip to §4 — you don't need to redo
this part.** You can check first with:
```bash
cd automation/terraform/envs/dev
terraform init
terraform plan
```
If this prints `No changes. Your infrastructure matches the
configuration.`, everything already exists and you can skip straight to
running the pipeline (§4).

Otherwise, build it fresh:

### 2.1 Step 1 — Bootstrap the Terraform state bucket (one-time, by hand)

This creates a single S3 bucket whose only job is to store Terraform's
own memory of what it built (see the "State" row in the concepts table
above). This step deliberately does **not** use that remote state itself
— it's the thing that creates the remote state bucket in the first
place, so it has to keep its own state locally.

```bash
cd automation/terraform/bootstrap
terraform init
terraform apply
```

Terraform will print a plan (what it's about to create) and ask you to
type `yes` to confirm. After it finishes, confirm the bucket exists:
```bash
aws s3 ls | grep tfstate
```
You should see `spotify-lake-dev-tfstate` in the output.

**You only ever run this once per AWS account.** Every future
`terraform apply` for the actual pipeline (§2.2) will read/write its
state into this bucket automatically.

### 2.2 Step 2 — Apply the main stack (creates everything else)

```bash
cd ../../terraform/envs/dev
terraform init
terraform apply
```

Again, review the plan and type `yes`. This single command creates:
- The 3 data-lake S3 buckets
- The Kaggle-credential SSM parameter slots (empty for now — see §3)
- The EC2 ingestion instance
- Both Glue jobs (Silver and Gold)

This takes a few minutes (EC2 instances aren't instant). When it
finishes, Terraform prints an **outputs** block — save this, you'll need
the `ingestion_instance_id` value in §4.

**You don't need to create or edit a `.tfvars` file.** Every setting has
a sensible default already matching this project (bucket names, the
Kaggle dataset, instance size). If you ever do need to override something
— e.g. running this in a real (non-sandbox) AWS account — see
`README.md` in this folder for what to change and why.

### 2.3 Step 3 — Seed your real Kaggle credentials

Terraform created two *empty* SSM parameters in step 2.2 (it deliberately
never writes real secret values — see `README.md` §2.3 for why). Fill
them in now:

```bash
aws ssm put-parameter \
  --name /spotify-lake/dev/kaggle/username \
  --value "<your-kaggle-username>" \
  --type SecureString --overwrite

aws ssm put-parameter \
  --name /spotify-lake/dev/kaggle/key \
  --value "<your-kaggle-api-key>" \
  --type SecureString --overwrite
```
Use the username/key from the `kaggle.json` you downloaded in §1.4.

**Infrastructure is now fully built.** Everything from here on is
*using* it, not building it — and this is the part you'll come back to
repeatedly.

---

## 3. Understand what happens when you "run the pipeline"

Before diving into commands, here's the mental model: the pipeline has
**three separate stages**, and each one has to be triggered manually
today (there's no automatic scheduler yet — see `README.md` §3 for why).
You always run them **in this order**, because each stage reads the
previous one's output:

```
1. Ingestion  (Kaggle -> Bronze)     — you trigger this by running a script on the EC2 instance
2. Silver job (Bronze -> Silver)     — you trigger this with one AWS CLI command
3. Gold job   (Silver -> Gold)       — you trigger this with one AWS CLI command, after Silver finishes
```

---

## 4. Run Stage 1 — Ingestion (Kaggle → Bronze)

The EC2 instance boots with Python and its dependencies pre-installed,
but the actual `ingest.py` script is **not** baked into it — you deploy
the current version fresh each time, from your own machine.

### 4.1 Upload the current script to S3

```bash
# IMPORTANT: run this from the repo root. If you run it from any other
# directory, "automation/ingestion/ingest.py" silently resolves to a
# DIFFERENT file (or fails), and you won't get an error telling you so.
cd /path/to/spotify-lake-infra
pwd   # sanity check — should end in .../spotify-lake-infra

aws s3 cp automation/ingestion/ingest.py s3://spotify-lake-dev-glue-assets/scripts/ingest.py
```
You should see `Completed ... with 1 file(s)` — if the file size looks
suspiciously different from what you expect (`wc -c automation/ingestion/ingest.py`
locally, compare), you're probably in the wrong directory.

### 4.2 Get your EC2 instance's ID

If you don't already have it from the `terraform apply` output:
```bash
cd automation/terraform/envs/dev
terraform output ingestion_instance_id
```

### 4.3 Open an interactive session on the instance

```bash
INSTANCE_ID=<paste-the-id-from-4.2>
aws ssm start-session --region us-east-1 --target $INSTANCE_ID
```
This opens a remote shell **directly in your terminal** — no SSH key,
no port to open, fully audit-logged on the AWS side. You'll know it
worked when your prompt changes to something like `sh-5.2$`.

### 4.4 Inside the session — become root, download, and run

```bash
sudo -i
```
This switches you to a root **login** shell — which matters because a
login shell automatically loads the environment variables the instance
needs (Kaggle dataset name, S3 bucket name, etc.) from
`/etc/profile.d/ingestion-env.sh`. Confirm they loaded:
```bash
echo $KAGGLE_SLUG $DATA_BUCKET
```
You should see real values printed, not blank lines.

Now pull the script you uploaded in 4.1, and run it:
```bash
python3 -c "import boto3; boto3.client('s3', region_name='us-east-1').download_file('spotify-lake-dev-glue-assets', 'scripts/ingest.py', '/opt/ingest.py')"

python3 /opt/ingest.py --work-dir /opt/ingest/work --target-file charts_songs_daily.csv
```

This downloads the ~10GB Kaggle file (takes 1-2 minutes) and uploads it
to S3 bronze/ (takes a couple more minutes). You'll see progress bars and
then a final `INFO ingestion complete: raw=s3://...` line — that's your
success signal.

When done, type `exit` twice to leave the root shell and then the SSM
session, back to your own terminal.

**⚠️ Two things that WILL trip you up here — read before you run this:**

- **Never put `sudo` in front of `python3` once you're already inside a
  `sudo -i` root shell.** Even though you're already root, `sudo` resets
  the shell's environment variables by default — so `KAGGLE_SLUG` etc.,
  which were loaded when the login shell started, disappear, and the
  script fails with `missing required config`. If you're already root
  (check with `whoami`), just run `python3 ...` directly, no `sudo`.
- **Always type `--target-file charts_songs_daily.csv` explicitly**, like
  the command above does. The instance has a stale environment variable
  baked in from when it first launched (it thinks the file is
  `charts_songs_daily.csv.gz`, which doesn't exist on Kaggle — Kaggle
  serves it uncompressed). Passing `--target-file` on the command line
  overrides that stale value.

---

## 5. Run Stage 2 & 3 — Silver and Gold Glue jobs

Back on your own machine (not inside the SSM session):

```bash
aws glue start-job-run --region us-east-1 --job-name spotify-lake-dev-silver-song-charts
```
This returns immediately with a `JobRunId` — the job itself keeps
running in the background on AWS, it doesn't block your terminal. Check
on it:
```bash
aws glue get-job-runs --region us-east-1 --job-name spotify-lake-dev-silver-song-charts --max-results 1 --query "JobRuns[0].JobRunState" --output text
```
Wait until this prints `SUCCEEDED` (it usually takes about 10 minutes)
before moving on — **Gold reads Silver's output, so running it too early
means it'll work off stale/incomplete data.**

Once Silver says `SUCCEEDED`:
```bash
aws glue start-job-run --region us-east-1 --job-name spotify-lake-dev-gold-layer
```
Same pattern to check status:
```bash
aws glue get-job-runs --region us-east-1 --job-name spotify-lake-dev-gold-layer --max-results 1 --query "JobRuns[0].JobRunState" --output text
```

**Why Silver doesn't need a `--target-file`-style override:** it's smart
about finding new data on its own — it automatically looks at what's the
newest dated folder in Bronze, and only processes rows it hasn't already
put into Silver. So re-running it after every ingestion is normal and
cheap; it never reprocesses the same data twice.

---

## 6. Verify everything landed correctly

```bash
aws s3 ls s3://spotify-lake-dev-data/bronze/charts_songs_daily/ --recursive --human-readable
aws s3 ls s3://spotify-lake-dev-data/silver/song_charts/ --recursive --summarize
aws s3 ls s3://spotify-lake-dev-data/gold/ --recursive --summarize
```
You're looking for: a new dated folder under `bronze/`, more files under
`silver/` than before (or a log message saying "already up to date" if
you re-ran without new Bronze data), and all 5 tables present under
`gold/` (`kpi_song`, `kpi_artist`, `country_performance`,
`monthly_trends`, `label_performance_enhanced`).

Also worth running after any infrastructure change:
```bash
cd automation/terraform/envs/dev
terraform plan
```
`No changes. Your infrastructure matches the configuration.` means
everything is healthy and matches the code — no manual changes have
drifted the real AWS account away from what's in git.

---

## 7. Clean up — stop paying for the EC2 instance

The EC2 instance only needs to exist while ingestion is actively running.
Leaving it running 24/7 costs money for no benefit. Tear it down when
you're done:

```bash
cd automation/terraform/envs/dev
terraform destroy -target=module.ec2_ingestion
```

This removes **only** the EC2 instance and its security group — none of
your S3 data (bronze/silver/gold) is touched, and nothing else in the
stack is affected. Next time you need to ingest, just re-run
`terraform apply` (§2.2) — it recreates the instance in under a minute,
and §4 works exactly the same way afterward.

---

## 8. Troubleshooting — errors we've actually hit

| Symptom | Cause | Fix |
|---|---|---|
| `ingest.py: error: missing required config` even though env vars look set | You ran `sudo python3 ...` while already in a root shell | Drop the `sudo` — you're already root, and `sudo` wipes the environment |
| Kaggle download gets `404 - Not Found` for a `.csv.gz` file | Stale `$TARGET_FILE` baked into the instance from an old Terraform config | Pass `--target-file charts_songs_daily.csv` explicitly on the command line |
| `aws` CLI crashes on the EC2 instance with a `botocore`/`dateutil` import traceback | `pip3 install boto3` at boot clobbered the system AWS CLI's bundled `botocore` | Don't use the `aws` CLI *inside* the instance — use a one-line `python3 -c "import boto3; ..."` instead (boto3 the library still works fine, only the CLI wrapper is broken) |
| `AccessDeniedException` on `ssm:SendCommand` / `glue:GetJobRuns` mentioning a region you didn't expect in the error's resource ARN | Your local AWS CLI's default region doesn't match `us-east-1` (where everything actually lives) | Add `--region us-east-1` explicitly to every `aws ssm` / `aws glue` command |
| `aws s3 cp automation/ingestion/ingest.py ...` "succeeds" but the wrong content ends up on S3 | You ran the command from the wrong working directory (e.g. your home folder), and a stale/unrelated file happened to exist at that relative path | Always `cd` to the repo root first; sanity-check with `pwd` before uploading |
| `terraform plan` inside `envs/dev` fails immediately, complaining about the backend | You skipped the bootstrap step (§2.1), so the state bucket it's trying to read from doesn't exist yet | Run §2.1 first, exactly once, before ever touching `envs/dev` |
| A multi-line command pasted into your terminal breaks into several "unknown command" errors | Your shell (especially `fish`) didn't receive the line-continuation backslashes correctly, often from copy-paste reformatting | Re-paste ensuring each line except the last ends in `\`, or paste it as a single unbroken line |

If you hit something not listed here, check `README.md` §5 (design
choices) for context on *why* things are built the way they are — most
surprises trace back to a deliberate tradeoff explained there.

---

## 9. Optional — wire up GitHub Actions (real AWS account only)

This step **does not work in an AWS Academy Learner Lab sandbox** (it
denies `iam:CreateOpenIDConnectProvider`). Only do this from a real,
non-sandbox AWS account:

1. In `automation/terraform/envs/dev/variables.tf`, set
   `enable_github_oidc = true`, then re-run `terraform apply` (§2.2).
2. Copy the `github_actions_role_arn` value from the apply output.
3. In the GitHub repo's **Settings → Secrets and variables → Actions →
   Variables** tab, add a repository **variable** (not a secret — it's
   not sensitive, it's just a role ARN) named `AWS_GITHUB_ACTIONS_ROLE_ARN`
   set to that value.
4. From now on: opening a PR that touches `automation/terraform/**` runs
   `terraform plan` automatically; merging to `main` runs
   `terraform apply` automatically. No AWS access keys are ever stored in
   GitHub — the workflow authenticates via the short-lived OIDC token.

---

Questions this guide didn't answer? Check `README.md` in this folder for
deeper technical detail on every module and script, or the top-level
`README.md` for the full team-facing architecture overview.
