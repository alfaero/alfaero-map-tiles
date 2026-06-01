#!/bin/bash
# user-data do EC2 spot do pipeline.
# Vars substituídas via templatefile():
#   $${secret_arn}, $${aws_region}, $${sns_topic}, $${git_repo}, $${git_branch}
# (mostrado escapado pro comentário não confundir o parser do Terraform)

set -euxo pipefail

exec > >(tee /var/log/alfaero-pipeline.log | logger -t alfaero-pipeline -s 2>/dev/console) 2>&1

# ----- deps -----
apt-get update
apt-get install -y --no-install-recommends \
    curl ca-certificates jq unzip git rclone awscli

# go-pmtiles
PMTILES_VERSION="v1.22.0"
PMTILES_VERSION_NUM="$${PMTILES_VERSION#v}"
curl -L "https://github.com/protomaps/go-pmtiles/releases/download/$$PMTILES_VERSION/go-pmtiles_$${PMTILES_VERSION_NUM}_Linux_x86_64.tar.gz" \
    | tar xz -C /usr/local/bin pmtiles
chmod +x /usr/local/bin/pmtiles

# ----- credenciais via Secrets Manager -----
SECRETS=$(aws secretsmanager get-secret-value \
    --secret-id "${secret_arn}" \
    --region "${aws_region}" \
    --query SecretString --output text)

export R2_ACCESS_KEY_ID=$(echo "$$SECRETS" | jq -r .R2_ACCESS_KEY_ID)
export R2_SECRET_ACCESS_KEY=$(echo "$$SECRETS" | jq -r .R2_SECRET_ACCESS_KEY)
export R2_ENDPOINT=$(echo "$$SECRETS" | jq -r .R2_ENDPOINT)
export R2_BUCKET=$(echo "$$SECRETS" | jq -r .R2_BUCKET)
export CF_API_TOKEN=$(echo "$$SECRETS" | jq -r .CF_API_TOKEN)
export CF_ZONE_ID_ALFAERO=$(echo "$$SECRETS" | jq -r .CF_ZONE_ID_ALFAERO)
export TILES_DOMAIN=$(echo "$$SECRETS" | jq -r .TILES_DOMAIN)
export SLACK_WEBHOOK_URL=$(echo "$$SECRETS" | jq -r '.SLACK_WEBHOOK_URL // ""')
GITHUB_PAT=$(echo "$$SECRETS" | jq -r .GITHUB_PAT)

# ----- clone do repo (private — usa PAT) -----
cd /opt
GIT_URL_WITH_AUTH=$(echo "${git_repo}" | sed "s|https://|https://x-access-token:$$GITHUB_PAT@|")
git clone --depth 1 --branch "${git_branch}" "$$GIT_URL_WITH_AUTH" alfaero-map-tiles
unset GITHUB_PAT GIT_URL_WITH_AUTH

# ----- prepara workdir -----
mkdir -p /work
chmod 755 /work

# ----- executa pipeline -----
cd /opt/alfaero-map-tiles
chmod +x pipeline/*.sh

if WORKDIR=/work bash pipeline/run-update.sh; then
    STATUS="SUCCESS"
else
    STATUS="FAILED"
fi

# ----- notifica via SNS -----
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
aws sns publish \
    --topic-arn "${sns_topic}" \
    --region "${aws_region}" \
    --subject "alfaero-map-tiles pipeline $${STATUS}" \
    --message "Pipeline $${STATUS} on $$INSTANCE_ID. See /var/log/alfaero-pipeline.log on the instance." \
    || true

# ----- self-destruct -----
sleep 30
aws ec2 terminate-instances \
    --instance-ids "$$INSTANCE_ID" \
    --region "${aws_region}" \
    || shutdown -h now
