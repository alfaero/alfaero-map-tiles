#!/bin/bash
# user-data do EC2 do pipeline alfaero-map-tiles.
# Vars substituídas via templatefile():
#   $${secret_arn}, $${aws_region}, $${sns_topic}, $${git_repo}, $${git_branch}

set -uo pipefail
# NOTA: -e removido propositalmente — controle de erro feito via STATUS e cleanup via trap

exec > >(tee /var/log/alfaero-pipeline.log | logger -t alfaero-pipeline -s 2>/dev/console) 2>&1

STATUS="UNKNOWN"
INSTANCE_ID="unknown"

cleanup() {
    local exit_code=$?
    set +x
    echo "=== CLEANUP (exit_code=$${exit_code}, STATUS=$${STATUS}) ==="

    INSTANCE_ID=$(curl -sS http://169.254.169.254/latest/meta-data/instance-id 2>/dev/null || echo "unknown")
    local log_name="logs/$(date -u +%Y%m%dT%H%M%SZ)-$${INSTANCE_ID}-$${STATUS}.log"

    # Upload do log pro R2 (best effort)
    if command -v rclone >/dev/null && [[ -f /root/.config/rclone/rclone.conf ]]; then
        rclone copyto /var/log/alfaero-pipeline.log "alfaero:alfaero-map-tiles/$${log_name}" \
            --header-upload "Content-Type: text/plain" 2>/dev/null || \
            echo "WARN: rclone upload failed"
    else
        echo "WARN: rclone not configured, log NOT uploaded"
    fi

    # SNS notification (best effort)
    aws sns publish \
        --topic-arn "${sns_topic}" \
        --region "${aws_region}" \
        --subject "alfaero-map-tiles pipeline $${STATUS}" \
        --message "Pipeline $${STATUS} (exit=$${exit_code}) on $${INSTANCE_ID}. Log: s3://alfaero-map-tiles/$${log_name}" \
        2>/dev/null || echo "WARN: SNS publish failed"

    # Aguarda 60s antes de terminar (pra capturar console output AWS)
    echo "Sleeping 60s before terminate..."
    sleep 60

    aws ec2 terminate-instances \
        --instance-ids "$${INSTANCE_ID}" \
        --region "${aws_region}" \
        2>/dev/null || shutdown -h now
}
trap cleanup EXIT

set -x

# ----- deps -----
apt-get update
apt-get install -y --no-install-recommends \
    curl ca-certificates jq unzip git rclone awscli

# go-pmtiles
PMTILES_VERSION="v1.22.0"
PMTILES_VERSION_NUM="$${PMTILES_VERSION#v}"
curl -L "https://github.com/protomaps/go-pmtiles/releases/download/$${PMTILES_VERSION}/go-pmtiles_$${PMTILES_VERSION_NUM}_Linux_x86_64.tar.gz" \
    | tar xz -C /usr/local/bin pmtiles
chmod +x /usr/local/bin/pmtiles

# ----- credenciais via Secrets Manager (trace OFF) -----
set +x
SECRETS=$(aws secretsmanager get-secret-value \
    --secret-id "${secret_arn}" \
    --region "${aws_region}" \
    --query SecretString --output text) || { STATUS="FAILED_SECRETS"; exit 10; }

export R2_ACCESS_KEY_ID=$(echo "$${SECRETS}" | jq -r .R2_ACCESS_KEY_ID)
export R2_SECRET_ACCESS_KEY=$(echo "$${SECRETS}" | jq -r .R2_SECRET_ACCESS_KEY)
export R2_ENDPOINT=$(echo "$${SECRETS}" | jq -r .R2_ENDPOINT)
export R2_BUCKET=$(echo "$${SECRETS}" | jq -r .R2_BUCKET)
export CF_API_TOKEN=$(echo "$${SECRETS}" | jq -r .CF_API_TOKEN)
export CF_ZONE_ID_ALFAERO=$(echo "$${SECRETS}" | jq -r .CF_ZONE_ID_ALFAERO)
export TILES_DOMAIN=$(echo "$${SECRETS}" | jq -r .TILES_DOMAIN)
export SLACK_WEBHOOK_URL=$(echo "$${SECRETS}" | jq -r '.SLACK_WEBHOOK_URL // ""')
GITHUB_PAT=$(echo "$${SECRETS}" | jq -r '.GITHUB_PAT // ""')
unset SECRETS

# Configurar rclone CEDO pra log upload funcionar mesmo se pipeline falhar
mkdir -p /root/.config/rclone
cat > /root/.config/rclone/rclone.conf <<RCLONE_EOF
[alfaero]
type = s3
provider = Cloudflare
endpoint = $${R2_ENDPOINT}
access_key_id = $${R2_ACCESS_KEY_ID}
secret_access_key = $${R2_SECRET_ACCESS_KEY}

[ofm]
type = s3
provider = Cloudflare
endpoint = https://4ddd8b88c1ea4b4ba84c33b8b30b62ac.r2.cloudflarestorage.com
no_auth = true
RCLONE_EOF
chmod 600 /root/.config/rclone/rclone.conf

set -x

# ----- clone do repo (público — sem PAT) -----
cd /opt
git clone --depth 1 --branch "${git_branch}" "${git_repo}" alfaero-map-tiles || { STATUS="FAILED_CLONE"; exit 20; }
unset GITHUB_PAT

# ----- prepara workdir -----
mkdir -p /work
chmod 755 /work

# ----- executa pipeline -----
cd /opt/alfaero-map-tiles
chmod +x pipeline/*.sh

if WORKDIR=/work HOME=/root bash pipeline/run-update.sh; then
    STATUS="SUCCESS"
else
    STATUS="FAILED_PIPELINE"
fi
