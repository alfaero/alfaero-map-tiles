# Operations runbook

## Setup inicial (one-time)

### Pré-requisitos
- Acesso ao Cloudflare account Alfaero (R2 + DNS de alfaero.com)
- Acesso à conta AWS 954222311704 (`alfaero` profile)
- `gh` autenticado no org `alfaero`
- Terraform >= 1.6 local

### Passos

1. **Criar token Cloudflare** com escopos:
   - `Zone:Edit` no zone alfaero.com
   - `R2:Edit` (Workers R2 Storage)
   - `Cache Purge` no zone alfaero.com

2. **Criar API token R2** (dashboard R2 → Manage R2 API Tokens → Create):
   - Permission: Object Read & Write
   - Bucket: `alfaero-map-tiles` (criado pelo Terraform na próxima etapa)
   - Anota Access Key ID + Secret Access Key

3. **Preparar `terraform.tfvars`**:
   ```bash
   cd terraform
   cp terraform.tfvars.example terraform.tfvars
   # preencher com os valores reais
   ```

4. **Aplicar Terraform**:
   ```bash
   terraform init
   terraform plan
   terraform apply
   ```
   Cria:
   - R2 bucket `alfaero-map-tiles`
   - DNS CNAME `tiles.alfaero.com`
   - Cache Rules no zone alfaero.com
   - Step Functions + EventBridge cron na AWS
   - SNS topic pra notificações
   - IAM roles, launch template, security group

5. **Configurar R2 custom domain** (manual no dashboard CF):
   - R2 → alfaero-map-tiles → Settings → Custom Domains
   - Add `tiles.alfaero.com` (Terraform já criou o CNAME)

6. **Configurar CORS no R2** (manual no dashboard CF):
   ```json
   [{
     "AllowedOrigins": [
       "https://app.alfaero.com",
       "https://b2b.alfaero.com",
       "https://alfaerovip.com",
       "https://*.alfaero.com",
       "http://localhost:*"
     ],
     "AllowedMethods": ["GET", "HEAD"],
     "AllowedHeaders": ["Range", "If-Modified-Since", "If-None-Match"],
     "ExposeHeaders": ["Content-Length", "Content-Range", "Content-Type", "ETag"],
     "MaxAgeSeconds": 3600
   }]
   ```

7. **Popular Secrets Manager** com credenciais do pipeline:
   ```bash
   aws secretsmanager put-secret-value \
     --profile alfaero --region us-east-1 \
     --secret-id alfaero/map-tiles-pipeline \
     --secret-string '{
       "R2_ACCESS_KEY_ID":"...",
       "R2_SECRET_ACCESS_KEY":"...",
       "R2_ENDPOINT":"https://<account_id>.r2.cloudflarestorage.com",
       "R2_BUCKET":"alfaero-map-tiles",
       "CF_API_TOKEN":"...",
       "CF_ZONE_ID_ALFAERO":"...",
       "TILES_DOMAIN":"tiles.alfaero.com",
       "SLACK_WEBHOOK_URL":""
     }'
   ```

8. **Subir styles, sprites, fonts iniciais** (do seu laptop):
   ```bash
   rclone copy styles/ alfaero:alfaero-map-tiles/styles/ --header-upload "Cache-Control: public, max-age=300"
   # sprites + fonts seguem instruções nos respectivos READMEs
   ```

9. **Trigger manual do pipeline** (primeira geração do .pmtiles):
   ```bash
   aws stepfunctions start-execution \
     --profile alfaero --region us-east-1 \
     --state-machine-arn $(terraform -chdir=terraform output -raw sfn_state_machine_arn)
   ```
   Ou usar o workflow GitHub Actions `manual-trigger.yml`.

   Job leva ~3–5h. Acompanhar via console SFN ou logs EC2 (CloudWatch).

10. **Validar com benchmark** (após pmtiles publicado):
    ```bash
    cd benchmark
    ./benchmark.sh 200 https://tiles.alfaero.com/planet-2026w22.pmtiles
    ```

## Update semanal (automático)

EventBridge cron `cron(0 7 ? * SUN *)` (Dom 04:00 BRT / 07:00 UTC) dispara o SFN automaticamente.

Resultado: novo `planet-{YYYY}w{WW}.pmtiles` no R2, styles atualizados, cache purgado, versão antiga deletada.

Acompanhar:
- SNS topic `alfaero-map-tiles-pipeline` → assinar email/Slack
- CloudWatch Logs `/aws/ec2/alfaero-map-tiles` (precisa configurar CW Agent no user-data se quiser persistência)

## Rollback

Se uma versão tiver problema:

```bash
# 1. Identificar versão estável anterior no R2
rclone lsf alfaero:alfaero-map-tiles/ --include 'planet-*.pmtiles' | sort

# 2. Editar styles localmente apontando pra versão antiga (substituir PLACEHOLDER pelo nome do .pmtiles)
# 3. Re-upload styles
rclone copy styles/ alfaero:alfaero-map-tiles/styles/ --header-upload "Cache-Control: public, max-age=300"

# 4. Purgar cache styles
./pipeline/05-purge-cdn.sh
```

## Troubleshooting

| Sintoma | Causa provável | Ação |
|---|---|---|
| 404 em `tiles.alfaero.com/...` | Custom domain não ativado no R2 | Verificar R2 → Settings → Custom Domains |
| 403 em styles/* | CORS não configurado | Aplicar CORS policy no R2 |
| Latência alta (P95 > 500ms) | Cache Reserve off | Ligar nas Cache Rules do Terraform |
| Job falha em `01-download.sh` | OFM R2 mudou endpoint | Atualizar `OFM_R2_ENDPOINT` no secret |
| Job falha em `02-convert.sh` (OOM) | Disco cheio | Aumentar volume EBS no launch template |
| Pipeline não dispara | EventBridge rule desabilitada | `aws events enable-rule --name alfaero-map-tiles-weekly` |

## Custo monitoring

Mensal:
- Dashboard R2: `Cloudflare → R2 → alfaero-map-tiles → Metrics`
- AWS Cost Explorer filtrado por tag `Project=alfaero-map-tiles`
- Esperado: ~$40/mês total. Acima de $60 investigar.
