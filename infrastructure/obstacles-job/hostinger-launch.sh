#!/bin/bash
# Roda a base de obstáculos (spec 006) na VPS da Hostinger, desacoplado do SSH.
# Lê a chave do R2 no Secrets Manager desta máquina e passa só pelo ambiente
# do processo remoto. Acompanhar: ssh ... tail -f /root/obstacles-job/obstacles-<STAMP>.log
#
# Uso: bash infrastructure/obstacles-job/hostinger-launch.sh [AAAAMMDD]
set -euo pipefail
STAMP="${1:-$(date -u +%Y%m%d)}"
DIR="$(cd "$(dirname "$0")" && pwd)"
HOST="root@2.25.136.129"
KEY="$HOME/.ssh/alfaero_hostinger"

SECRETS=$(aws secretsmanager get-secret-value --secret-id alfaero/map-tiles-pipeline \
  --region us-east-1 --query SecretString --output text)
field() {
  printf '%s' "$SECRETS" | python -c "import json,sys; print(json.load(sys.stdin).get('$1') or '')"
}
# Sem chave o upload falharia no fim e o job apagaria a base: aborta antes.
for k in R2_ENDPOINT R2_ACCESS_KEY_ID R2_SECRET_ACCESS_KEY; do
  [[ -n "$(field "$k")" ]] || { echo "segredo sem $k" >&2; exit 1; }
done

ssh -i "$KEY" "$HOST" 'mkdir -p /root/obstacles-job && cat > /root/obstacles-job/job.sh && chmod 700 /root/obstacles-job/job.sh' \
  < "$DIR/hostinger-job.sh"
# Aerogeradores da ANEEL baixados daqui: o SIGEL não aceita conexão da VPS.
ANEEL_JSON="$(mktemp)"
(cd "$DIR" && python -m obstacles.aneel "$ANEEL_JSON")
python -c "import json,sys; n=len(json.load(open(sys.argv[1]))); assert n > 12000, n" "$ANEEL_JSON"
ssh -i "$KEY" "$HOST" 'cat > /root/obstacles-job/aneel-input.json' < "$ANEEL_JSON"
rm -f "$ANEEL_JSON"

# Pacote Python (sem testes): o job roda `python -m obstacles.build` dentro da pasta.
tar -C "$DIR" -czf - --exclude='__pycache__' obstacles \
  | ssh -i "$KEY" "$HOST" 'rm -rf /root/obstacles-job/obstacles && tar -C /root/obstacles-job -xzf -'

# As chaves vão pela entrada padrão, nunca pela linha de comando (ps).
{
  printf 'export STAMP=%q\n' "$STAMP"
  # A chave do R2 não cria bucket: sem NO_CHECK_BUCKET o rclone tenta e leva 403.
  printf 'export RCLONE_CONFIG_ALFAERO_TYPE=s3 RCLONE_CONFIG_ALFAERO_PROVIDER=Cloudflare RCLONE_CONFIG_ALFAERO_NO_CHECK_BUCKET=true\n'
  printf 'export RCLONE_CONFIG_ALFAERO_ENDPOINT=%q\n' "$(field R2_ENDPOINT)"
  printf 'export RCLONE_CONFIG_ALFAERO_ACCESS_KEY_ID=%q\n' "$(field R2_ACCESS_KEY_ID)"
  printf 'export RCLONE_CONFIG_ALFAERO_SECRET_ACCESS_KEY=%q\n' "$(field R2_SECRET_ACCESS_KEY)"
  printf 'setsid nohup /root/obstacles-job/job.sh </dev/null >/dev/null 2>&1 &\n'
  printf 'echo "job iniciado, pid $!"\n'
} | ssh -i "$KEY" "$HOST" bash -s
unset SECRETS
