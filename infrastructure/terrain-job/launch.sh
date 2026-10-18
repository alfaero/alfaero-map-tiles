#!/bin/bash
# Lança a EC2 de uso único que recorta o terreno do Mapterhorn e sobe para o R2
# (spec 005). Usa o launch template do pipeline (papel IAM e segredo do R2) e
# troca só o tamanho, o disco e o script. A instância se desliga sozinha ao
# terminar (shutdown = terminate) e nunca passa de 6 horas.
#
# Uso: bash infrastructure/terrain-job/launch.sh [AAAAMMDD]
set -euo pipefail
STAMP="${1:-20261018}"
DIR="$(cd "$(dirname "$0")" && pwd)"
UD="$(mktemp)"
sed "s/__STAMP__/${STAMP}/" "$DIR/user-data.sh" > "$UD"
# No Git Bash do Windows o aws.exe não enxerga o /tmp do bash: passa o caminho
# do Windows.
UD_ARG="$UD"
if command -v cygpath >/dev/null 2>&1; then UD_ARG="$(cygpath -m "$UD")"; fi
aws ec2 run-instances --region us-east-1 \
  --launch-template "LaunchTemplateId=lt-0f9cb92ff7ad49eaf,Version=\$Latest" \
  --instance-type c6i.xlarge \
  --instance-initiated-shutdown-behavior terminate \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":80,"VolumeType":"gp3","DeleteOnTermination":true,"Encrypted":true}}]' \
  --user-data "file://$UD_ARG" \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=alfaero-terrain-job},{Key=Project,Value=alfaero-map-tiles}]' \
  --query "Instances[0].[InstanceId,State.Name]" --output text
rm -f "$UD"
