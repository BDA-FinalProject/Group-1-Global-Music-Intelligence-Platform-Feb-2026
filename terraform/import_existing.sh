#!/bin/bash

# Initialize variables from Terraform environment variables or fallbacks
BUCKET_NAME=${TF_VAR_script_bucket_name}
SILVER_JOB=${TF_VAR_glue_job_silver_name}
GOLD_JOB=${TF_VAR_glue_job_gold_name}
CRAWLER_NAME=${TF_VAR_glue_crawler_name}
DB_NAME=${TF_VAR_glue_database_name}

# Fallbacks from terraform.tfvars if environment variables are not set
if [ -z "$BUCKET_NAME" ] && [ -f "terraform.tfvars" ]; then
  BUCKET_NAME=$(grep -E '^script_bucket_name' terraform.tfvars | cut -d'"' -f2)
fi
if [ -z "$SILVER_JOB" ] && [ -f "terraform.tfvars" ]; then
  SILVER_JOB=$(grep -E '^glue_job_silver_name' terraform.tfvars | cut -d'"' -f2)
fi
if [ -z "$GOLD_JOB" ] && [ -f "terraform.tfvars" ]; then
  GOLD_JOB=$(grep -E '^glue_job_gold_name' terraform.tfvars | cut -d'"' -f2)
fi
if [ -z "$CRAWLER_NAME" ] && [ -f "terraform.tfvars" ]; then
  CRAWLER_NAME=$(grep -E '^glue_crawler_name' terraform.tfvars | cut -d'"' -f2)
fi
if [ -z "$DB_NAME" ] && [ -f "terraform.tfvars" ]; then
  DB_NAME=$(grep -E '^glue_database_name' terraform.tfvars | cut -d'"' -f2)
fi

echo "=========================================================="
echo " Checking existing AWS resources for Terraform Import..."
echo "=========================================================="

# 1. S3 Bucket
if [ -n "$BUCKET_NAME" ]; then
  echo "Checking S3 Bucket '$BUCKET_NAME'..."
  aws s3api head-bucket --bucket "$BUCKET_NAME" >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "→ S3 Bucket '$BUCKET_NAME' exists in AWS."
    terraform state show 'aws_s3_bucket.script_bucket[0]' >/dev/null 2>&1
    if [ $? -ne 0 ]; then
      echo "→ Importing S3 Bucket '$BUCKET_NAME' into state..."
      terraform import 'aws_s3_bucket.script_bucket[0]' "$BUCKET_NAME"
    else
      echo "→ S3 Bucket '$BUCKET_NAME' is already in state."
    fi
  else
    echo "→ S3 Bucket '$BUCKET_NAME' does not exist in AWS. Will be created."
  fi
fi

# 2. Glue Silver Job
if [ -n "$SILVER_JOB" ]; then
  echo "Checking Glue Job '$SILVER_JOB'..."
  aws glue get-job --job-name "$SILVER_JOB" >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "→ Glue Job '$SILVER_JOB' exists in AWS."
    terraform state show 'aws_glue_job.silver_job[0]' >/dev/null 2>&1
    if [ $? -ne 0 ]; then
      echo "→ Importing Glue Job '$SILVER_JOB' into state..."
      terraform import 'aws_glue_job.silver_job[0]' "$SILVER_JOB"
    else
      echo "→ Glue Job '$SILVER_JOB' is already in state."
    fi
  else
    echo "→ Glue Job '$SILVER_JOB' does not exist in AWS. Will be created."
  fi
fi

# 3. Glue Gold Job
if [ -n "$GOLD_JOB" ]; then
  echo "Checking Glue Job '$GOLD_JOB'..."
  aws glue get-job --job-name "$GOLD_JOB" >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "→ Glue Job '$GOLD_JOB' exists in AWS."
    terraform state show 'aws_glue_job.gold_job[0]' >/dev/null 2>&1
    if [ $? -ne 0 ]; then
      echo "→ Importing Glue Job '$GOLD_JOB' into state..."
      terraform import 'aws_glue_job.gold_job[0]' "$GOLD_JOB"
    else
      echo "→ Glue Job '$GOLD_JOB' is already in state."
    fi
  else
    echo "→ Glue Job '$GOLD_JOB' does not exist in AWS. Will be created."
  fi
fi

# 4. Glue Crawler
if [ -n "$CRAWLER_NAME" ]; then
  echo "Checking Glue Crawler '$CRAWLER_NAME'..."
  aws glue get-crawler --name "$CRAWLER_NAME" >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "→ Glue Crawler '$CRAWLER_NAME' exists in AWS."
    terraform state show 'aws_glue_crawler.spotify_crawler[0]' >/dev/null 2>&1
    if [ $? -ne 0 ]; then
      echo "→ Importing Glue Crawler '$CRAWLER_NAME' into state..."
      terraform import 'aws_glue_crawler.spotify_crawler[0]' "$CRAWLER_NAME"
    else
      echo "→ Glue Crawler '$CRAWLER_NAME' is already in state."
    fi
  else
    echo "→ Glue Crawler '$CRAWLER_NAME' does not exist in AWS. Will be created."
  fi
fi

# 5. Glue Database
if [ -n "$DB_NAME" ]; then
  echo "Checking Glue Database '$DB_NAME'..."
  aws glue get-database --name "$DB_NAME" >/dev/null 2>&1
  if [ $? -eq 0 ]; then
    echo "→ Glue Database '$DB_NAME' exists in AWS."
    terraform state show 'aws_glue_catalog_database.spotify_db[0]' >/dev/null 2>&1
    if [ $? -ne 0 ]; then
      echo "→ Importing Glue Database '$DB_NAME' into state..."
      terraform import 'aws_glue_catalog_database.spotify_db[0]' "$DB_NAME"
    else
      echo "→ Glue Database '$DB_NAME' is already in state."
    fi
  else
    echo "→ Glue Database '$DB_NAME' does not exist in AWS. Will be created."
  fi
fi

echo "=========================================================="
echo " AWS resource checking and import process complete."
echo "=========================================================="
