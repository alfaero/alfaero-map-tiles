#!/bin/bash
# Roda o recorte do terreno (spec 005) na VPS da Hostinger, desacoplado do SSH.
# Lê a chave do R2 no Secrets Manager desta máquina e passa só pelo ambiente
# do processo remoto. Acompanhar: ssh ... tail -f /root/terrain-job/terrain-<STAMP>.log
#
# Uso: bash infrastructure/terrain-job/hostinger-launch.sh [AAAAMMDD]
set -euo pipefail
STAMP="${1:-20261018}"
DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="root@2.25.136.129"
KEY="$HOME/.ssh/alfaero_hostinger"

SECRETS=$(aws secretsmanager get-secret-value --secret-id alfaero/map-tiles-pipeline \
  --region us-east-1 --query SecretString --output text)
field() {
  printf '%s' "$SECRETS" | python -c "import json,sys; print(json.load(sys.stdin).get('$1') or '')"
}
# Sem chave o upload falharia no fim e o job apagaria o recorte: aborta antes.
for k in R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
  [[ -n "$(field "$k")" ]] || { echo "segredo sem $k" >&2; exit 1; }
done

ssh -i "$KEY" "$HOST" 'mkdir -p /root/terrain-job && cat > /root/terrain-job/job.sh && chmod 700 /root/terrain-job/job.sh' \
  < "$DIR/hostinger-job.sh"

# As chaves vão pela entrada padrão, nunca pela linha de comando (ps).
{
  printf 'export STAMP=%q\n' "$STAMP"
  # A chave do R2 não cria bucket: sem NO_CHECK_BUCKET o rclone tenta e leva 403.
  printf 'export RCLONE_CONFIG_ALFAERO_TYPE=s3 RCLONE_CONFIG_ALFAERO_PROVIDER=Cloudflare RCLONE_CONFIG_ALFAERO_NO_CHECK_BUCKET=true\n'
  printf 'export RCLONE_CONFIG_ALFAERO_ENDPOINT=%q\n' "$(field R2_ENDPOINT)"
  printf 'export RCLONE_CONFIG_ALFAERO_ACCESS_KEY_ID=%q\n' "$(field R2_ACCESS_KEY_ID)"
  printf 'export RCLONE_CONFIG_ALFAERO_SECRET_ACCESS_KEY=%q\n' "$(field R2_SECRET_ACCESS_KEY)"
  printf 'setsid nohup /root/terrain-job/job.sh </dev/null >/dev/null 2>&1 &\n'
  printf 'echo "job iniciado, pid $!"\n'
} | ssh -i "$KEY" "$HOST" bash -s
unset SECRETS
