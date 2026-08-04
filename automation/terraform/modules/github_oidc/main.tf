# GitHub Actions authenticates to AWS via OIDC — no long-lived access keys
# stored as GitHub secrets. The role is only assumable from this exact repo
# on pushes to main.

data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com/.well-known/openid-configuration"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]

  tags = merge(var.tags, { layer = "cicd" })
}

data "aws_iam_policy_document" "github_trust" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:ref:refs/heads/main"]
    }
  }
}

resource "aws_iam_role" "github_actions" {
  name               = "${var.project_name}-${var.env}-github-actions"
  assume_role_policy = data.aws_iam_policy_document.github_trust.json
  tags               = merge(var.tags, { layer = "cicd" })
}

# NOTE on scoping: aws:ResourceTag conditions only constrain actions on
# resources that already exist and are already tagged project=<project_name>.
# They do NOT constrain *creation* of new resources (that needs
# aws:RequestTag, per-action, which gets unwieldy fast for a Terraform CI
# role that has to create/update/destroy a moving set of resource types).
# This is provisioning-level access, deliberately broad within s3/ec2/iam/ssm
# so `terraform apply` can manage the whole stack — tighten to per-action
# RequestTag/ResourceTag pairs once the resource set stabilizes.
data "aws_iam_policy_document" "github_actions_permissions" {
  statement {
    sid       = "ManageExistingTaggedResources"
    effect    = "Allow"
    actions   = ["s3:*", "ec2:*", "iam:*", "ssm:*"]
    resources = ["*"]

    condition {
      test     = "StringEquals"
      variable = "aws:ResourceTag/project"
      values   = [var.project_name]
    }
  }

  statement {
    sid    = "CreateAndDescribeResources"
    effect = "Allow"
    actions = [
      "s3:CreateBucket",
      "s3:ListAllMyBuckets",
      "ec2:Describe*",
      "ec2:CreateSecurityGroup",
      "ec2:RunInstances",
      "ec2:CreateTags",
      "iam:CreateRole",
      "iam:CreateInstanceProfile",
      "iam:CreateOpenIDConnectProvider",
      "iam:TagRole",
      "iam:TagInstanceProfile",
      "iam:TagOpenIDConnectProvider",
      "ssm:PutParameter",
      "ssm:AddTagsToResource",
      "ssm:GetParameters",
    ]
    resources = ["*"]
  }

  statement {
    sid     = "TerraformStateAccess"
    effect  = "Allow"
    actions = ["s3:GetObject", "s3:PutObject", "s3:ListBucket", "s3:DeleteObject"]
    resources = [
      "arn:aws:s3:::${var.project_name}-${var.env}-tfstate",
      "arn:aws:s3:::${var.project_name}-${var.env}-tfstate/*",
    ]
  }

  statement {
    sid       = "ReadCallerIdentity"
    effect    = "Allow"
    actions   = ["sts:GetCallerIdentity"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "github_actions" {
  name   = "${var.project_name}-${var.env}-github-actions"
  role   = aws_iam_role.github_actions.id
  policy = data.aws_iam_policy_document.github_actions_permissions.json
}
