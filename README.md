# 🎵 Global Music Intelligence Platform

A cloud-native end-to-end Data Engineering project that transforms large-scale Spotify streaming data into business-ready analytics using the AWS ecosystem and Medallion Architecture. The project demonstrates modern data engineering practices including scalable data ingestion, ETL pipelines, data cataloging, serverless querying, and interactive business intelligence dashboards.

---

# 📌 Project Overview

The Global Music Intelligence Platform is designed to process and analyze large-scale Spotify streaming datasets containing millions of records across songs, artists, albums, and countries. The platform ingests raw data into Amazon S3, processes it through a Medallion Architecture using AWS Glue and Apache Spark, catalogs datasets with AWS Glue Crawlers, and enables serverless SQL analytics through Amazon Athena. The curated data is finally visualized using Power BI or Tableau to deliver actionable business insights.

This project showcases a production-inspired cloud data engineering pipeline built using AWS services and Infrastructure as Code (Terraform).

---

# 🎯 Business Problem

The rapid growth of music streaming platforms has generated enormous amounts of data across countries, artists, albums, and record labels. However, stakeholders often lack a centralized analytics platform to monitor global music consumption, evaluate artist performance, and identify emerging market trends.

This project addresses the following business challenges:

- Cross-Country Music Consumption Analytics
- Artist Performance Analytics
- Album Performance Analytics
- Record Label Performance Analytics
- Streaming Trend Analysis
- Business KPI Reporting

---

# 🎯 Project Objectives

- Build a scalable cloud-native data lake on AWS.
- Implement Medallion Architecture (Bronze, Silver, Gold).
- Automate ETL pipelines using AWS Glue and Apache Spark.
- Perform scalable data transformation and cleansing.
- Generate business-ready analytical datasets.
- Enable serverless SQL analytics using Amazon Athena.
- Visualize KPIs through interactive dashboards.
- Demonstrate industry-standard Data Engineering practices.

---

# 🏗️ Solution Architecture

```text
                        Kaggle Dataset
                              │
                              ▼
                      EC2 Data Ingestion
                              │
                              ▼
                     Amazon S3 (Bronze Layer)
                              │
                              ▼
                  AWS Glue ETL (Bronze → Silver)
                              │
                              ▼
                     Amazon S3 (Silver Layer)
                              │
                              ▼
                  AWS Glue ETL (Silver → Gold)
                              │
                              ▼
                      Amazon S3 (Gold Layer)
                              │
                              ▼
                      AWS Glue Crawler
                              │
                              ▼
                    AWS Glue Data Catalog
                              │
                              ▼
                       Amazon Athena
                              │
                     ODBC / JDBC Driver
                              │
                              ▼
                           Tableau
```

---

# ☁️ AWS Services Used

| Service | Purpose |
|----------|----------|
| Amazon EC2 | Dataset ingestion from Kaggle |
| Amazon S3 | Data Lake Storage |
| AWS Glue | ETL Processing |
| AWS Glue Crawler | Schema Discovery |
| AWS Glue Data Catalog | Metadata Management |
| Amazon Athena | Serverless SQL Query Engine |
| IAM | Access Management |
---

# 💻 Technology Stack

- Python
- Apache Spark
- AWS Glue
- Amazon S3
- Amazon Athena
- AWS Glue Data Catalog
- AWS Glue Crawlers
- Terraform
- GitHub
- GitHub Actions
- Tableau

---

# 📂 Dataset

**Source:** Spotify Charts Dataset (Kaggle)

The dataset includes:

- Songs
- Albums
- Artists
- Weekly Album Charts
- Daily Artist Charts
- Daily Song Charts
- Artwork Metadata

The project processes millions of streaming records collected from Spotify across multiple countries.

---

# 🏅 Medallion Architecture

## Bronze Layer

- Raw data ingestion
- Immutable source files
- Original schema preserved
- Landing zone for incoming datasets

---

## Silver Layer

- Data cleansing
- Null value handling
- Duplicate removal
- Data standardization
- Country mapping
- Business transformations

---

## Gold Layer

- Business-ready datasets
- Aggregated KPIs
- Reporting tables
- Analytics-ready schema
- Optimized for BI tools

---

# 🔄 ETL Pipeline

1. Download Spotify datasets from Kaggle.
2. Upload raw files to Amazon S3 Bronze Layer.
3. Transform raw data using AWS Glue (Apache Spark).
4. Store cleaned datasets in the Silver Layer.
5. Perform business transformations.
6. Store curated datasets in the Gold Layer.
7. Run AWS Glue Crawler to create metadata tables.
8. Register datasets in the AWS Glue Data Catalog.
9. Query curated datasets using Amazon Athena.
10. Connect Tableau using the Athena ODBC/JDBC connector.
11. Build interactive dashboards and business KPIs.

---

# 📊 Key Business Analytics

The platform enables analysis of:

- Global Music Consumption Trends
- Country-wise Streaming Analysis
- Artist Popularity Rankings
- Album Performance
- Record Label Performance
- Daily & Weekly Chart Analysis
- Top Performing Songs
- Historical Streaming Trends
- Market Growth Analysis

---

# 📁 Repository Structure

```
Global-Music-Intelligence-Platform/
│
├── ingestion/
│   ├── downloader.py
│   ├── extractor.py
│   ├── uploader.py
│   ├── helper.py
│   ├── logger.py
│   ├── config.py
│   ├── requirements.txt
│   └── main.py
│
├── terraform/
│
├── glue_jobs/
│   ├── bronze_to_silver.py
│   ├── silver_to_gold.py
│   └── utility/
│
│
├── dashboards/
│
├── architecture/
│
├── images/
│
├── docs/
│
└── README.md
```

---

# 🚀 Future Enhancements

- Real-time streaming using Amazon Kinesis
- Workflow orchestration using Apache Airflow
- Automated Data Quality Validation
- CI/CD Deployment Pipeline
- Predictive Analytics using Machine Learning
- Automated Dashboard Refresh
- Data Governance and Lineage

---

# 👥 Contributors

This project is being developed as a cloud-native data engineering solution demonstrating modern AWS Data Lake architecture, scalable ETL pipelines, serverless analytics, and business intelligence reporting.

---

# ⭐ Project Highlights

- End-to-End AWS Data Engineering Pipeline
- Medallion Architecture Implementation
- Apache Spark ETL with AWS Glue
- Infrastructure as Code using Terraform
- Serverless SQL Analytics using Amazon Athena
- Interactive Power BI & Tableau Dashboards
- Scalable Cloud Data Lake Architecture
- Production-Inspired Data Engineering Workflow
- GitHub-Based Version Control and Collaboration
