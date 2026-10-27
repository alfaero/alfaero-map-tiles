# Cartas raster dos EUA (spec 414)

Gera os mbtiles das quatro cartas raster dos EUA a partir dos GeoTIFF da FAA (aeronav), por edição
de 56 dias. Mesmos ids, zooms e formato dos arquivos no ar (512 px, WebP q75, TMS).

| Carta | id | Fonte | Zoom |
|---|---|---|---|
| Sectional (53 cartas, 57 TIFs com insets) | 3447a49e-bcf6-4a02-a033-f726105eb5a0 | `visual/<data>/sectional-files/*.zip` | 1-11 |
| ENR L (ELUS1-36, N e S) | c75884f3-443a-4f1a-aa1a-01f99ad9075f | `enroute/<data>/enr_lNN.zip` | 5-10 |
| ENR H (EHUS1-12) | c3fba2b7-575e-4fb9-bf30-8f75a86520f2 | `enroute/<data>/enr_hNN.zip` | 4-9 |
| Havaí/Pacífico (EPHI1, EPHI2) | 7f17cb4a-88b3-41c7-bf31-67b1f0c48929 | `enroute/<data>/enr_p01.zip`, `enr_p02.zip` | 2-7 |

Nada aqui publica: servidor, S3, CloudFront e Remote Config ficam com o passo a passo da spec 414.

## Arquivos

- `Dockerfile`: GDAL 3.13.3 (tag estável fixada) + Pillow + OpenCV. `docker build -t alfaero-us-charts:gdal3.13.3 .`
- `download.py`: baixa os zips da edição (`MM-DD-AAAA`), confere o Content-Length, pode ser repetido.
- `neatline.py`: detecta a área útil de cada TIF e grava `neatlines.geojson` (EPSG:4326, uma feição
  por TIF, com prioridade de pintura). Com `CROPS=1` salva recortes das saliências para conferência.
- `sec_ajustes.csv`: ajustes revisados a olho na edição 2026-10-29 (ver "Método").
- `enr_exclusions.csv`: caixas dentro da moldura da ENR P01 que não são mapa georreferenciado.
- `build_parts.py`: expande a paleta (Sectional), reprojeta para EPSG:3857 com o recorte e roda o
  `gdal2tiles` por carta; apaga a reprojeção logo depois.
- `merge.py`: junta as partes num mbtiles (tile de uma parte só: bytes sem recomprimir; sobreposição:
  `alpha_composite`, carta-mãe embaixo e inset por cima) e grava os metadados com `faa_edition` e `valid_until`.
- `run_all.sh`: roda partes + junção para as quatro séries.
- `verify.py`: tiles por zoom contra os arquivos de 21/10/2026, tamanho, sha256, amostra de tiles.
- `render_check.py`, `contact_sheet.py`: PNGs de conferência visual.

## Como rodar

```bash
python download.py 10-29-2026 <dl>
docker volume create us414work
# recortes (uns 6 min; conferir as folhas de contato antes de seguir)
docker run --rm -e CROPS=1 -v <dl>:/dl:ro -v <esta pasta>:/scripts -v <check>:/check \
  alfaero-us-charts:gdal3.13.3 python3 /scripts/neatline.py /scripts/neatlines.geojson /check/neatline /dl/*.zip
# tiles + junção (as partes ficam no volume, não na pasta do Windows: 2,5x mais rápido)
# --tmpfs: as reprojeções temporárias ficam em RAM. No volume, cada reprojeção apagada deixa blocos
# novos no disco virtual do Docker (vhdx), que não devolve espaço ao C: (medido: +4,4 GB no C: para
# 1,3 GB de tiles). Se cair no meio, repetir com build_parts.py --resume (pula cartas prontas).
docker run --rm --tmpfs /work/tmp:size=6g -v <dl>:/dl:ro -v <esta pasta>:/scripts:ro -v us414work:/work \
  alfaero-us-charts:gdal3.13.3 bash /scripts/run_all.sh 2026-10-29 2026-12-24
docker run --rm -v us414work:/work -v <out>:/out alfaero-us-charts:gdal3.13.3 cp /work/out/*.mbtiles /out/
python verify.py <out>
```

No `neatline.py` passe os zips por caminho (`/dl/Albuquerque.zip ...`); `zip::nome.tif` processa um TIF só.

## Automação (spec 008)

A tarefa agendada "Alfaero cartas EUA" (criada por `register_task.ps1`) roda `python -I auto_edition.py run`
todo dia às 06:40. Quando a FAA publica a próxima edição (ciclo de 56 dias a partir de 2026-10-29), ela
baixa, gera e confere (`check.py`); na data de vigência, a partir de 09:01Z, publica (`publish.py`:
cópia das cartas em uso, envio como `.new` com sha256, troca com volta automática, purga do nginx,
S3 + CloudFront, Remote Config `?v=`, conferência de fora). Avisos por e-mail pelo SNS `ec2-alertas`.

- Estado, log e saídas: `%LOCALAPPDATA%\alfaero-us-charts` (`state.json`, `auto.log`, `out\<edição>`).
- `python -I auto_edition.py status` mostra o estado e a decisão de hoje, sem fazer nada.
- Na rodada automática os recortes da edição nova vão para o volume (`/work/neatlines.geojson`,
  `NEATLINES=` no `run_all.sh`); o `neatlines.geojson` desta pasta continua sendo o da edição 2026-10-29.
- Testes: `python -I -B test_auto_edition.py`.

## Método de recorte

Sem recorte de terceiros: tudo sai do próprio raster e do georreferenciamento da FAA.

- **Sectional** (`sec_flood`): o colar é papel branco; o mapa é colorido e fechado pelo neatline preto.
  Máscara de branco pela paleta (R, G, B >= 245), reduzida 2x pelo mínimo; preenchimento 4-conectado a
  partir da borda (o colar); abertura 7x7 e maior componente. Onde o mapa chega na borda da imagem sem
  neatline (Alasca, neve branca), uma linha-barreira a 2 px da borda impede o preenchimento de entrar.
  Depois, o que a abertura 61x61 solta do contorno (textos "Joins ...", réguas, rótulos de grau
  encostados no neatline) sai, menos o marcado "manter" no `sec_ajustes.csv` (abas legítimas e
  cantos da carta do Havaí, que vem girada). Caixas grandes do colar encostadas no neatline (índice
  do Alasca, faixa do título, avisos) saem pelos retângulos "excluir" do mesmo CSV; mapa com neve até
  a borda que o preenchimento ainda invade entra pelos retângulos "incluir". Cada linha traz a medida
  das bordas; se a FAA mudar o leiaute, o ponto/caixa não bate e o script para ou a folha de contato mostra.
  O neatline fica dentro do recorte: cartas vizinhas se sobrepõem pela largura da linha (sem fresta).
- **ENR L/H/P** (`enr_flood`): o fundo do mapa também é branco, então a barreira é a linha escura
  (min(R,G,B) < 110). Preenche a partir da borda tudo que não é linha escura; o mapa fica fechado pela
  moldura; erosão de 12 px tira a própria moldura. Insets com TIF próprio (ENR_L23_WILM_INSET,
  ENR_L34_BOST_INSET, ENR_P01_GUA) entram por cima. Na P01, a caixa "Guam Area" e a tabela de
  informações saem pelo `enr_exclusions.csv`.
- **Antimeridiano**: longitude desembrulhada em torno do meridiano central da carta e polígono cortado
  em ±180 (Western Aleutian East, Dutch Harbor e ENR P01 viram duas partes).
- **Insets das Sectionals com TIF próprio** (Honolulu, Marianas, Samoa): prioridade 1, por cima.
  Insets impressos dentro da própria carta em outra escala (Jacksonville, Los Angeles, Washington,
  St. Louis, Kodiak etc.) ficam como na carta impressa e como nos tiles de hoje.

## Ordem de grandeza (máquina do Levi, 16 threads)

Medido em 21/10/2026 (edição 2026-10-29): download 3,85 GB em ~5 min; recortes ~6 min; Sectional
partes ~2 h 05 min (57 TIFs, 2 a 4 min cada) + junção 9 min; ENR L 24 min + 2 min; ENR H 9 min;
ENR P 1,5 min. Disco: zips 3,85 GB (apagar conforme processa), partes até ~2,5 GB e mbtiles ~2,7 GB
no volume, mais a cópia final de 2,7 GB.

Cuidado com ENR: o geotransform vem girado (a carta impressa está de lado), por isso a resolução da
fonte é o módulo do vetor do pixel (`hypot(gt[1], gt[4])`), não `gt[1]`.
