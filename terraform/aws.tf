# Infra AWS pro pipeline semanal:
#   EventBridge cron → Step Functions → EC2 RunInstances spot → user-data roda run-update.sh
#
# Por que EC2 e não Batch/Fargate: precisa ~150 GB de scratch local (mbtiles 80GB + pmtiles 100GB),
# Fargate tem limites mais apertados de disco e setup mais chato. EC2 spot c6i.4xlarge é simples e barato.

data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

# Imagem Ubuntu 22.04 mais recente
data "aws_ami" "ubuntu_2204" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }
}

# VPC default (sem provisionar nada exclusivo — job é curto e sem state)
data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

# Security group: só egress (download OFM + upload R2 + Cloudflare API)
resource "aws_security_group" "pipeline" {
  name        = "alfaero-map-tiles-pipeline"
  description = "Pipeline EC2 spot - egress only"
  vpc_id      = data.aws_vpc.default.id

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Secrets: credenciais R2 + Cloudflare API token
resource "aws_secretsmanager_secret" "pipeline_secrets" {
  name        = "alfaero/map-tiles-pipeline"
  description = "Credenciais R2 + Cloudflare API token pro pipeline semanal"
}

# Valor preenchido manualmente (terraform import ou via CLI):
# aws secretsmanager put-secret-value --secret-id alfaero/map-tiles-pipeline \
#   --secret-string '{"R2_ACCESS_KEY_ID":"...","R2_SECRET_ACCESS_KEY":"...","R2_ENDPOINT":"...","CF_API_TOKEN":"...","CF_ZONE_ID_ALFAERO":"...","SLACK_WEBHOOK_URL":"..."}'

# IAM role: EC2 instance pode ler o secret e se auto-terminar
resource "aws_iam_role" "pipeline" {
  name = "alfaero-map-tiles-pipeline"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "pipeline" {
  name = "alfaero-map-tiles-pipeline"
  role = aws_iam_role.pipeline.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:GetSecretValue"]
        Resource = aws_secretsmanager_secret.pipeline_secrets.arn
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:TerminateInstances"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "ec2:ResourceTag/Project" = "alfaero-map-tiles"
          }
        }
      },
      {
        Effect   = "Allow"
        Action   = ["sns:Publish"]
        Resource = aws_sns_topic.pipeline.arn
      }
    ]
  })
}

resource "aws_iam_instance_profile" "pipeline" {
  name = "alfaero-map-tiles-pipeline"
  role = aws_iam_role.pipeline.name
}

# SNS topic pra notificação de fim de job
resource "aws_sns_topic" "pipeline" {
  name = "alfaero-map-tiles-pipeline"
}

# Launch template do EC2 spot
resource "aws_launch_template" "pipeline" {
  name_prefix   = "alfaero-map-tiles-"
  image_id      = data.aws_ami.ubuntu_2204.id
  instance_type = "c6i.4xlarge"

  iam_instance_profile {
    arn = aws_iam_instance_profile.pipeline.arn
  }

  vpc_security_group_ids = [aws_security_group.pipeline.id]

  block_device_mappings {
    device_name = "/dev/sda1"
    ebs {
      volume_size           = 400
      volume_type           = "gp3"
      iops                  = 6000
      throughput            = 250
      delete_on_termination = true
      encrypted             = true
    }
  }

  instance_market_options {
    market_type = "spot"
    spot_options {
      max_price          = "0.50"
      spot_instance_type = "one-time"
    }
  }

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name    = "alfaero-map-tiles-pipeline"
      Project = "alfaero-map-tiles"
    }
  }

  user_data = base64encode(templatefile("${path.module}/../infrastructure/ec2-job/user-data.sh", {
    secret_arn  = aws_secretsmanager_secret.pipeline_secrets.arn
    aws_region  = data.aws_region.current.name
    sns_topic   = aws_sns_topic.pipeline.arn
    git_repo    = "https://github.com/alfaero/alfaero-map-tiles.git"
    git_branch  = "main"
  }))
}

# Step Functions: launch EC2 + aguarda SNS callback + cleanup
resource "aws_iam_role" "sfn" {
  name = "alfaero-map-tiles-sfn"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "states.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "sfn" {
  role = aws_iam_role.sfn.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ec2:RunInstances", "ec2:CreateTags"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["iam:PassRole"]
        Resource = aws_iam_role.pipeline.arn
      }
    ]
  })
}

resource "aws_sfn_state_machine" "weekly_update" {
  name     = "alfaero-map-tiles-weekly-update"
  role_arn = aws_iam_role.sfn.arn

  definition = jsonencode({
    Comment = "Launch EC2 spot weekly to refresh planet.pmtiles"
    StartAt = "LaunchSpot"
    States = {
      LaunchSpot = {
        Type     = "Task"
        Resource = "arn:aws:states:::aws-sdk:ec2:runInstances"
        Parameters = {
          LaunchTemplate = {
            LaunchTemplateId = aws_launch_template.pipeline.id
            Version          = "$Latest"
          }
          MinCount = 1
          MaxCount = 1
        }
        End = true
      }
    }
  })
}

# EventBridge cron: Domingo 04:00 BRT = 07:00 UTC
resource "aws_cloudwatch_event_rule" "weekly" {
  name                = "alfaero-map-tiles-weekly"
  description         = "Trigger pipeline alfaero-map-tiles every Sunday 07:00 UTC"
  schedule_expression = "cron(0 7 ? * SUN *)"
}

resource "aws_iam_role" "eventbridge" {
  name = "alfaero-map-tiles-eventbridge"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "events.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy" "eventbridge" {
  role = aws_iam_role.eventbridge.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["states:StartExecution"]
      Resource = aws_sfn_state_machine.weekly_update.arn
    }]
  })
}

resource "aws_cloudwatch_event_target" "weekly" {
  rule     = aws_cloudwatch_event_rule.weekly.name
  arn      = aws_sfn_state_machine.weekly_update.arn
  role_arn = aws_iam_role.eventbridge.arn
}

output "sfn_state_machine_arn" {
  value = aws_sfn_state_machine.weekly_update.arn
}

output "manual_trigger_command" {
  value = "aws stepfunctions start-execution --state-machine-arn ${aws_sfn_state_machine.weekly_update.arn}"
}

output "sns_topic_arn" {
  value = aws_sns_topic.pipeline.arn
}
