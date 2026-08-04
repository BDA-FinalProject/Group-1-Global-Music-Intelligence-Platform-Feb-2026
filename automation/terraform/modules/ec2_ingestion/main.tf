# Ingestion EC2 instance: pulls one Kaggle file, converts to Parquet,
# writes to the bronze/ prefix of the data lake bucket. No SSH surface —
# operator access is via SSM Session Manager only.

data "aws_ssm_parameter" "al2023_ami" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-x86_64"
}

data "aws_vpc" "default" {
  count   = var.vpc_id == null ? 1 : 0
  default = true
}

data "aws_subnets" "default" {
  count = var.subnet_id == null ? 1 : 0

  filter {
    name   = "vpc-id"
    values = [var.vpc_id != null ? var.vpc_id : data.aws_vpc.default[0].id]
  }
}

locals {
  vpc_id    = var.vpc_id != null ? var.vpc_id : data.aws_vpc.default[0].id
  subnet_id = var.subnet_id != null ? var.subnet_id : data.aws_subnets.default[0].ids[0]
}

# var.use_lab_instance_profile exists because sandbox AWS accounts (e.g.
# AWS Academy Learner Lab) deny iam:CreateRole entirely — the only role
# available to attach to an EC2 instance is the pre-existing
# LabInstanceProfile. In a normal AWS account, leave this false and get a
# purpose-built, least-privilege role instead.

data "aws_iam_policy_document" "assume_ec2" {
  count = var.use_lab_instance_profile ? 0 : 1

  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ingestion" {
  count = var.use_lab_instance_profile ? 0 : 1

  name               = "${var.project_name}-${var.env}-ingestion"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2[0].json
  tags               = merge(var.tags, { layer = "bronze" })
}

# Session Manager only — no key pair, no inbound port 22.
resource "aws_iam_role_policy_attachment" "ssm_core" {
  count = var.use_lab_instance_profile ? 0 : 1

  role       = aws_iam_role.ingestion[0].name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Least privilege: read exactly the two Kaggle SSM params, and touch
# exactly the bronze/ prefix of the data bucket. Nothing else.
data "aws_iam_policy_document" "ingestion_scoped" {
  count = var.use_lab_instance_profile ? 0 : 1

  statement {
    sid       = "ReadKaggleCreds"
    actions   = ["ssm:GetParameter"]
    resources = [var.kaggle_username_param_arn, var.kaggle_key_param_arn]
  }

  statement {
    sid       = "ListBronzePrefix"
    actions   = ["s3:ListBucket"]
    resources = [var.data_bucket_arn]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["bronze/*"]
    }
  }

  statement {
    sid       = "WriteBronzeOnly"
    actions   = ["s3:PutObject"]
    resources = ["${var.data_bucket_arn}/bronze/*"]
  }
}

resource "aws_iam_role_policy" "ingestion_scoped" {
  count = var.use_lab_instance_profile ? 0 : 1

  name   = "${var.project_name}-${var.env}-ingestion-scoped"
  role   = aws_iam_role.ingestion[0].id
  policy = data.aws_iam_policy_document.ingestion_scoped[0].json
}

resource "aws_iam_instance_profile" "ingestion" {
  count = var.use_lab_instance_profile ? 0 : 1

  name = "${var.project_name}-${var.env}-ingestion"
  role = aws_iam_role.ingestion[0].name
}

data "aws_iam_instance_profile" "lab" {
  count = var.use_lab_instance_profile ? 1 : 0
  name  = var.lab_instance_profile_name
}

locals {
  instance_profile_name = var.use_lab_instance_profile ? data.aws_iam_instance_profile.lab[0].name : aws_iam_instance_profile.ingestion[0].name
}

resource "aws_security_group" "ingestion" {
  name        = "${var.project_name}-${var.env}-ingestion"
  description = "Ingestion EC2 instance. No inbound rules; access via SSM Session Manager only."
  vpc_id      = local.vpc_id

  egress {
    description = "Outbound HTTPS/etc. needed to reach Kaggle, S3, and SSM endpoints."
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(var.tags, { layer = "bronze" })
}

resource "aws_instance" "ingestion" {
  ami                    = data.aws_ssm_parameter.al2023_ami.value
  instance_type          = var.instance_type
  subnet_id              = local.subnet_id
  vpc_security_group_ids = [aws_security_group.ingestion.id]
  iam_instance_profile   = local.instance_profile_name

  root_block_device {
    volume_size = var.root_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  # IMDSv2 only.
  metadata_options {
    http_tokens = "required"
  }

  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    aws_region            = var.aws_region
    data_bucket           = var.data_bucket_name
    kaggle_username_param = var.kaggle_username_param_name
    kaggle_key_param      = var.kaggle_key_param_name
    kaggle_slug           = var.kaggle_slug
    target_file           = var.target_file
    table_name            = var.table_name
  })

  tags = merge(var.tags, {
    Name  = "${var.project_name}-${var.env}-ingestion"
    layer = "bronze"
  })
}
