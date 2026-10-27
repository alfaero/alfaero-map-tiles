# Imagem de trabalho das cartas dos EUA: GDAL estável fixado + Pillow (junção dos tiles)
# + OpenCV headless (detecção do neatline das Sectionals).
# Build: docker build -t alfaero-us-charts:gdal3.13.3 .
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.13.3
RUN apt-get update && apt-get install -y --no-install-recommends python3-pil python3-pip sqlite3 \
    && pip3 install --no-cache-dir --break-system-packages opencv-python-headless==4.10.0.84 \
    && apt-get purge -y python3-pip && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
