#!/bin/bash

set -e

echo "Installing Kaggle..."
python3 -m pip install --user kaggle

echo "Adding Kaggle to PATH..."
export PATH=$HOME/.local/bin:$PATH

echo "Checking Kaggle installation..."
kaggle --version

echo "Creating Kaggle configuration..."
mkdir -p ~/.kaggle

cat > ~/.kaggle/kaggle.json <<EOF
{
  "username": "YOUR_KAGGLE_USERNAME",
  "key": "YOUR_KAGGLE_API_KEY"
}
EOF

chmod 600 ~/.kaggle/kaggle.json

echo "Creating working directory..."
mkdir -p /mnt/tmp/spotify_data
cd /mnt/tmp/spotify_data

echo "Downloading Spotify dataset..."
kaggle datasets download -d gonzalopezgil/spotify-charts-daily-updated

echo "Downloaded files:"
ls -lh

echo "Extracting dataset..."
unzip -o spotify-charts-daily-updated.zip

echo "Extracted files:"
ls -lh

echo "Checking S3 bucket..."
aws s3 ls s3://bronze-script/

echo "Uploading files to S3..."
aws s3 cp . s3://bronze-script/bronze/raw_data/ --recursive

echo "Verifying upload..."
aws s3 ls s3://bronze-script/bronze/raw_data/

echo "Data ingestion completed successfully!"