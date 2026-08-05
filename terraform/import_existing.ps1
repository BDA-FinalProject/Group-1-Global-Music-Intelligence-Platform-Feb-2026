$BucketName = $env:TF_VAR_script_bucket_name
$SilverJob = $env:TF_VAR_glue_job_silver_name
$GoldJob = $env:TF_VAR_glue_job_gold_name
$CrawlerName = $env:TF_VAR_glue_crawler_name
$DbName = $env:TF_VAR_glue_database_name

# Fallbacks from terraform.tfvars if environment variables are not set
if ([string]::IsNullOrEmpty($BucketName) -and (Test-Path "terraform.tfvars")) {
    $tfvars = Get-Content "terraform.tfvars"
    foreach ($line in $tfvars) {
        if ($line -match '^script_bucket_name\s*=\s*"([^"]+)"') {
            $BucketName = $Matches[1]
        }
        if ($line -match '^glue_job_silver_name\s*=\s*"([^"]+)"') {
            $SilverJob = $Matches[1]
        }
        if ($line -match '^glue_job_gold_name\s*=\s*"([^"]+)"') {
            $GoldJob = $Matches[1]
        }
        if ($line -match '^glue_crawler_name\s*=\s*"([^"]+)"') {
            $CrawlerName = $Matches[1]
        }
        if ($line -match '^glue_database_name\s*=\s*"([^"]+)"') {
            $DbName = $Matches[1]
        }
    }
}

Write-Host "=========================================================="
Write-Host " Checking existing AWS resources for Terraform Import..."
Write-Host "=========================================================="

# 1. S3 Bucket
if (![string]::IsNullOrEmpty($BucketName)) {
    Write-Host "Checking S3 Bucket '$BucketName'..."
    aws s3api head-bucket --bucket $BucketName 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "→ S3 Bucket '$BucketName' exists in AWS."
        terraform state show 'aws_s3_bucket.script_bucket[0]' 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "→ Importing S3 Bucket '$BucketName' into state..."
            terraform import 'aws_s3_bucket.script_bucket[0]' $BucketName
        } else {
            Write-Host "→ S3 Bucket '$BucketName' is already in state."
        }
    } else {
        Write-Host "→ S3 Bucket '$BucketName' does not exist in AWS. Will be created."
    }
}

# 2. Glue Silver Job
if (![string]::IsNullOrEmpty($SilverJob)) {
    Write-Host "Checking Glue Job '$SilverJob'..."
    aws glue get-job --job-name $SilverJob 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "→ Glue Job '$SilverJob' exists in AWS."
        terraform state show 'aws_glue_job.silver_job[0]' 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "→ Importing Glue Job '$SilverJob' into state..."
            terraform import 'aws_glue_job.silver_job[0]' $SilverJob
        } else {
            Write-Host "→ Glue Job '$SilverJob' is already in state."
        }
    } else {
        Write-Host "→ Glue Job '$SilverJob' does not exist in AWS. Will be created."
    }
}

# 3. Glue Gold Job
if (![string]::IsNullOrEmpty($GoldJob)) {
    Write-Host "Checking Glue Job '$GoldJob'..."
    aws glue get-job --job-name $GoldJob 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "→ Glue Job '$GoldJob' exists in AWS."
        terraform state show 'aws_glue_job.gold_job[0]' 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "→ Importing Glue Job '$GoldJob' into state..."
            terraform import 'aws_glue_job.gold_job[0]' $GoldJob
        } else {
            Write-Host "→ Glue Job '$GoldJob' is already in state."
        }
    } else {
        Write-Host "→ Glue Job '$GoldJob' does not exist in AWS. Will be created."
    }
}

# 4. Glue Crawler
if (![string]::IsNullOrEmpty($CrawlerName)) {
    Write-Host "Checking Glue Crawler '$CrawlerName'..."
    aws glue get-crawler --name $CrawlerName 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "→ Glue Crawler '$CrawlerName' exists in AWS."
        terraform state show 'aws_glue_crawler.spotify_crawler[0]' 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "→ Importing Glue Crawler '$CrawlerName' into state..."
            terraform import 'aws_glue_crawler.spotify_crawler[0]' $CrawlerName
        } else {
            Write-Host "→ Glue Crawler '$CrawlerName' is already in state."
        }
    } else {
        Write-Host "→ Glue Crawler '$CrawlerName' does not exist in AWS. Will be created."
    }
}

# 5. Glue Database
if (![string]::IsNullOrEmpty($DbName)) {
    Write-Host "Checking Glue Database '$DbName'..."
    aws glue get-database --name $DbName 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "→ Glue Database '$DbName' exists in AWS."
        terraform state show 'aws_glue_catalog_database.spotify_db[0]' 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Host "→ Importing Glue Database '$DbName' into state..."
            terraform import 'aws_glue_catalog_database.spotify_db[0]' $DbName
        } else {
            Write-Host "→ Glue Database '$DbName' is already in state."
        }
    } else {
        Write-Host "→ Glue Database '$DbName' does not exist in AWS. Will be created."
    }
}

Write-Host "=========================================================="
Write-Host " AWS resource checking and import process complete."
Write-Host "=========================================================="
