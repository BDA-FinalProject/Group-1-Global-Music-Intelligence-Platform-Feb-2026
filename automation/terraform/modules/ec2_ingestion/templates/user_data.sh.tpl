#!/bin/bash
# Prepares the instance to run ingestion/ingest.py. Does NOT run it
# automatically — deploy the script via SSM Session Manager and run it
# by hand (an automated trigger is a later phase).
set -euo pipefail

dnf install -y python3 python3-pip

pip3 install --no-cache-dir \
  kaggle==1.6.17 \
  pandas==2.2.2 \
  pyarrow==17.0.0 \
  boto3==1.34.144

cat <<EOF > /etc/profile.d/ingestion-env.sh
export AWS_REGION="${aws_region}"
export DATA_BUCKET="${data_bucket}"
export KAGGLE_USERNAME_PARAM="${kaggle_username_param}"
export KAGGLE_KEY_PARAM="${kaggle_key_param}"
export KAGGLE_SLUG="${kaggle_slug}"
export TARGET_FILE="${target_file}"
export TABLE_NAME="${table_name}"
EOF
chmod 644 /etc/profile.d/ingestion-env.sh

echo "Ingestion instance ready. Copy ingestion/ingest.py + requirements.txt onto this box via SSM Session Manager (aws ssm start-session) and run it manually." > /etc/motd
