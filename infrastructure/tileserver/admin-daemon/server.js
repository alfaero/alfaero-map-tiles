#!/usr/bin/env node
/**
 * TileServer GL admin daemon
 *
 * Endpoints (todos protegidos por Bearer token via env ADMIN_TOKEN):
 *   GET  /health                       → ping
 *   POST /register   { uuid, file_name } → baixa S3 → adiciona ao config.json → restart container
 *   POST /unregister { uuid }             → remove do config.json → deleta arquivo local → restart
 *   POST /sync                            → reload config.json (sem deletar arquivos)
 *
 * Roda em 127.0.0.1:8007. Exposto via nginx em https://raster.alfaero.com/admin/*
 *   (autenticação por Bearer ADMIN_TOKEN — também usada no Laravel TileServerService).
 *
 * Diretórios esperados:
 *   /opt/alfaero-tileserver/config.json
 *   /opt/alfaero-tileserver/mbtiles/<uuid>.mbtiles
 *
 * Variáveis de ambiente:
 *   ADMIN_TOKEN              — token compartilhado com Laravel
 *   TILESERVER_DIR           — /opt/alfaero-tileserver (default)
 *   S3_BUCKET                — alfaero
 *   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION
 */

const express = require('express');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const { promisify } = require('util');
const { pipeline } = require('stream/promises');
const { S3Client, GetObjectCommand, HeadObjectCommand } = require('@aws-sdk/client-s3');

const PORT = parseInt(process.env.PORT || '8007', 10);
const ADMIN_TOKEN = process.env.ADMIN_TOKEN || '';
const TILESERVER_DIR = process.env.TILESERVER_DIR || '/opt/alfaero-tileserver';
const MBTILES_DIR = path.join(TILESERVER_DIR, 'mbtiles');
const CONFIG_PATH = path.join(TILESERVER_DIR, 'config.json');
const S3_BUCKET = process.env.S3_BUCKET || 'alfaero';

if (!ADMIN_TOKEN) {
    console.error('FATAL: ADMIN_TOKEN env var não definida');
    process.exit(1);
}

const s3 = new S3Client({
    region: process.env.AWS_REGION || 'us-east-1',
    // Credenciais lidas automaticamente de env/IAM
});

const app = express();
app.use(express.json({ limit: '1mb' }));

// Bearer auth
app.use((req, res, next) => {
    const auth = req.headers.authorization || '';
    if (auth !== `Bearer ${ADMIN_TOKEN}`) {
        return res.status(401).json({ error: 'unauthorized' });
    }
    next();
});

app.get('/health', (req, res) => {
    const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
    res.json({
        ok: true,
        data_sources: Object.keys(config.data || {}).length,
        styles: Object.keys(config.styles || {}).length,
    });
});

app.post('/register', async (req, res) => {
    const { uuid, file_name } = req.body || {};
    if (!uuid || !file_name) return res.status(400).json({ error: 'uuid and file_name required' });

    try {
        const localPath = path.join(MBTILES_DIR, file_name);

        // 1. Download S3 → local (se ainda não tiver)
        if (!fs.existsSync(localPath)) {
            console.log(`Downloading s3://${S3_BUCKET}/${file_name} → ${localPath}`);
            await downloadFromS3(file_name, localPath);
        } else {
            console.log(`File ${localPath} já existe localmente; sobrescrevendo do S3`);
            await downloadFromS3(file_name, localPath);
        }

        // 2. Atualiza config.json
        const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
        config.data = config.data || {};
        config.data[uuid] = { mbtiles: file_name };
        fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));

        // 3. Restart container (preserva mbtiles via bind mount)
        console.log('Restarting TileServer container…');
        execSync('docker compose restart', { cwd: TILESERVER_DIR, stdio: 'inherit' });

        // 4. Aguarda healthcheck (até 30s)
        await waitForHealth(30);

        // 5. Detecta formato real do mbtiles via TileServer
        const format = await detectFormat(uuid);

        res.json({ ok: true, uuid, file_name, format });
    } catch (err) {
        console.error('Register error:', err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/unregister', async (req, res) => {
    const { uuid, delete_local = true } = req.body || {};
    if (!uuid) return res.status(400).json({ error: 'uuid required' });

    try {
        const config = JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf8'));
        const entry = (config.data || {})[uuid];
        if (entry) {
            delete config.data[uuid];
            fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
        }

        if (delete_local && entry?.mbtiles) {
            const local = path.join(MBTILES_DIR, entry.mbtiles);
            if (fs.existsSync(local)) {
                fs.unlinkSync(local);
                console.log(`Deleted local ${local}`);
            }
        }

        console.log('Restarting TileServer (unregister)…');
        execSync('docker compose restart', { cwd: TILESERVER_DIR, stdio: 'inherit' });
        await waitForHealth(30);

        res.json({ ok: true, uuid });
    } catch (err) {
        console.error('Unregister error:', err);
        res.status(500).json({ error: err.message });
    }
});

app.post('/sync', async (req, res) => {
    try {
        execSync('docker compose restart', { cwd: TILESERVER_DIR, stdio: 'inherit' });
        await waitForHealth(30);
        res.json({ ok: true });
    } catch (err) {
        res.status(500).json({ error: err.message });
    }
});

async function downloadFromS3(key, localPath) {
    // Verifica tamanho
    const head = await s3.send(new HeadObjectCommand({ Bucket: S3_BUCKET, Key: key }));
    const sizeMB = Math.round((head.ContentLength || 0) / 1024 / 1024);
    console.log(`Size: ${sizeMB} MB`);

    const get = await s3.send(new GetObjectCommand({ Bucket: S3_BUCKET, Key: key }));
    const out = fs.createWriteStream(localPath);
    await pipeline(get.Body, out);

    const actualSize = fs.statSync(localPath).size;
    if (head.ContentLength && actualSize !== head.ContentLength) {
        throw new Error(`Size mismatch: expected ${head.ContentLength}, got ${actualSize}`);
    }
    console.log(`Downloaded ${key} (${actualSize} bytes)`);
}

async function waitForHealth(maxSeconds) {
    const http = require('http');
    const start = Date.now();
    while ((Date.now() - start) / 1000 < maxSeconds) {
        try {
            const ok = await new Promise(resolve => {
                const r = http.get('http://localhost:8006/health', res => {
                    resolve(res.statusCode === 200);
                });
                r.on('error', () => resolve(false));
                r.setTimeout(2000, () => { r.destroy(); resolve(false); });
            });
            if (ok) return;
        } catch (_) {}
        await new Promise(r => setTimeout(r, 1000));
    }
    throw new Error(`TileServer não respondeu /health em ${maxSeconds}s`);
}

async function detectFormat(uuid) {
    try {
        const http = require('http');
        return await new Promise((resolve) => {
            const r = http.get(`http://localhost:8006/data/${uuid}.json`, res => {
                let data = '';
                res.on('data', c => data += c);
                res.on('end', () => {
                    try {
                        const json = JSON.parse(data);
                        resolve(json.format || null);
                    } catch (_) { resolve(null); }
                });
            });
            r.on('error', () => resolve(null));
            r.setTimeout(3000, () => { r.destroy(); resolve(null); });
        });
    } catch (_) { return null; }
}

app.listen(PORT, '127.0.0.1', () => {
    console.log(`alfaero-tileserver-admin-daemon listening on 127.0.0.1:${PORT}`);
});
