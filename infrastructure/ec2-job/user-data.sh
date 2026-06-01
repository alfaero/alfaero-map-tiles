#!/bin/bash
# user-data do EC2 spot do pipeline.
# Vars substituídas via templatefile():
#   $${secret_arn}, $${aws_region}, $${sns_topic}, $${git_repo}, $${git_branch}
# (mostrado escapado pro comentário não confundir o parser do Terraform)

set -euo pipefail

exec > >(tee /var/log/alfaero-pipeline.log | logger -t alfaero-pipeline -s 2>/dev/console) 2>&1

# trace habilitado SÓ pra operações sem credenciais (apt, downloads públicos)
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

# ----- credenciais via Secrets Manager (trace OFF pra não logar) -----
set +x
SECRETS=$(aws secretsmanager get-secret-value \
    --secret-id "${secret_arn}" \
    --region "${aws_region}" \
    --query SecretString --output text)

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

# Configurar rclone pra log upload funcionar mesmo em failure precoce
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

# ----- clone do repo (com ou sem PAT) -----
cd /opt
if [[ -n "$${GITHUB_PAT}" && "$${GITHUB_PAT}" != "null" ]]; then
    # private repo: usa credential helper temporário (não loga o PAT)
    GIT_ASKPASS_FILE=$(mktemp)
    chmod 700 "$${GIT_ASKPASS_FILE}"
    cat > "$${GIT_ASKPASS_FILE}" <<EOF
#!/bin/bash
echo "$${GITHUB_PAT}"
EOF
    chmod +x "$${GIT_ASKPASS_FILE}"
    GIT_ASKPASS="$${GIT_ASKPASS_FILE}" GIT_TERMINAL_PROMPT=0 \
        git clone --depth 1 --branch "${git_branch}" \
        "$$(echo '${git_repo}' | sed 's|https://|https://x-access-token@|')" alfaero-map-tiles
    rm -f "$${GIT_ASKPASS_FILE}"
else
    # public repo
    git clone --depth 1 --branch "${git_branch}" "${git_repo}" alfaero-map-tiles
fi
unset GITHUB_PAT
set -x

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

# ----- upload do log pro R2 (debug) -----
INSTANCE_ID=$(curl -s http://169.254.169.254/latest/meta-data/instance-id)
LOG_NAME="logs/$(date -u +%Y%m%dT%H%M%SZ)-$${INSTANCE_ID}-$${STATUS:-UNKNOWN}.log"
# rclone pode não estar configurado se falhou cedo demais, então usar aws cli direto via curl pra R2
# fallback safe: sempre tenta upload, mas não bloqueia se falhar
if command -v rclone >/dev/null && [[ -n "$${R2_ACCESS_KEY_ID:-}" ]]; then
    rclone copyto /var/log/alfaero-pipeline.log "alfaero:$${R2_BUCKET}/$${LOG_NAME}" \
        --header-upload "Content-Type: text/plain" || true
fi

# ----- notifica via SNS -----
aws sns publish \
    --topic-arn "${sns_topic}" \
    --region "${aws_region}" \
    --subject "alfaero-map-tiles pipeline $${STATUS:-UNKNOWN}" \
    --message "Pipeline $${STATUS:-UNKNOWN} on $${INSTANCE_ID}.

Log uploaded to: s3://$${R2_BUCKET:-alfaero-map-tiles}/$${LOG_NAME}
(Access via: rclone cat alfaero:$${R2_BUCKET:-alfaero-map-tiles}/$${LOG_NAME})

Or browse Cloudflare R2 dashboard: alfaero-map-tiles → $${LOG_NAME}" \
    || true

# ----- self-destruct (60s pra capturar console output AWS) -----
sleep 60
aws ec2 terminate-instances \
    --instance-ids "$${INSTANCE_ID}" \
    --region "${aws_region}" \
    || shutdown -h now
