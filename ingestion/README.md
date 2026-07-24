## Important Notes

- Tested on Amazon Linux 2023
- Python 3.9.25
- Kaggle API 1.6.17
- AWS EC2 t3.large
- Uses IAM Role authentication for S3 (no AWS credentials required)

Known Issue:
Kaggle API v1.7.4.5 caused Out-Of-Memory (OOM) errors while downloading the Spotify dataset (~4 GB). Downgrading to Kaggle 1.6.17 resolved the issue.
