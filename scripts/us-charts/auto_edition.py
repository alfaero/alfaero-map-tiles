#!/usr/bin/env python3
"""Orquestrador das cartas raster dos EUA (spec 008). Roda todo dia pela tarefa agendada.

Decide entre: publicar a edição já gerada (a partir de 09:01Z da vigência), gerar a próxima edição
(quando a FAA já publicou os arquivos) ou não fazer nada. Avisa por e-mail (SNS `ec2-alertas`)
quando gera, publica ou falha.

Uso:
    python -I auto_edition.py run            # o que a tarefa agendada chama
    python -I auto_edition.py status         # mostra o estado e a decisão de hoje, sem fazer nada
    python -I auto_edition.py seed <edição> <pasta_com_os_mbtiles>   # registra a edição publicada
"""
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
import urllib.request
from datetime import date, datetime, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import edition as ed  # noqa: E402
from check import CHARTS, check_edition, summarize  # noqa: E402

ROOT = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "alfaero-us-charts")
STATE = os.path.join(ROOT, "state.json")
LOCK = os.path.join(ROOT, "lock")
LOG = os.path.join(ROOT, "auto.log")
TOPIC = "arn:aws:sns:us-east-1:954222311704:ec2-alertas"
IMAGE = "alfaero-us-charts:gdal3.13.3"
VOLUME = "us414work"
MIN_FREE_GB = 20
LOCK_MAX_AGE_S = 8 * 3600
DOCKER_DESKTOP = r"C:\Program Files\Docker\Docker\Docker Desktop.exe"


# ---------------------------------------------------------------------------
# Decisão (pura, testável)

def decide(state: dict, now: datetime, faa_has) -> tuple:
    """('publish', edição) | ('generate', edição) | ('none', motivo)."""
    published = ed.parse(state["published"]["edition"])
    gen = state.get("generated")
    if gen:
        g = ed.parse(gen["edition"])
        if g > published:
            if now >= ed.effective_utc(g):
                return ("publish", g.isoformat())
            return ("none", f"edição {g} gerada, aguardando a vigência {ed.effective_utc(g).isoformat()}")
    nxt = ed.edition_after(published)
    if faa_has(nxt):
        return ("generate", nxt.isoformat())
    return ("none", f"FAA ainda sem os arquivos de {nxt}")


# ---------------------------------------------------------------------------
# Infra

def log(msg):
    line = f"{datetime.now().isoformat(timespec='seconds')} {msg}"
    print(line, flush=True)
    os.makedirs(ROOT, exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def notify(subject, body):
    log(f"aviso: {subject}")
    try:
        subprocess.run(["aws", "sns", "publish", "--topic-arn", TOPIC, "--subject", subject[:99],
                        "--message", body], capture_output=True, timeout=60, check=True)
    except Exception as e:  # o aviso não pode derrubar a rodada; fica no log
        log(f"falha ao avisar: {e}")


def load_state():
    with open(STATE, encoding="utf-8") as f:
        return json.load(f)


def save_state(state):
    os.makedirs(ROOT, exist_ok=True)
    tmp = STATE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=1)
    os.replace(tmp, STATE)


def acquire_lock():
    os.makedirs(ROOT, exist_ok=True)
    if os.path.exists(LOCK) and time.time() - os.path.getmtime(LOCK) < LOCK_MAX_AGE_S:
        return False
    with open(LOCK, "w") as f:
        f.write(str(os.getpid()))
    return True


def release_lock():
    try:
        os.remove(LOCK)
    except FileNotFoundError:
        pass


def faa_has(edition: date) -> bool:
    """A FAA já publicou a edição? (HEAD da Sectional de Washington e da ENR L01)"""
    folder = ed.faa_folder(edition)
    for url in (f"https://aeronav.faa.gov/visual/{folder}/sectional-files/Washington.zip",
                f"https://aeronav.faa.gov/enroute/{folder}/enr_l01.zip"):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "Mozilla/5.0 (alfaero-us-charts)"})
            if urllib.request.urlopen(req, timeout=30).status != 200:
                return False
        except Exception:
            return False
    return True


def ensure_docker():
    def up():
        return subprocess.run(["docker", "info"], capture_output=True, timeout=60).returncode == 0
    if up():
        return
    log("Docker parado: abrindo o Docker Desktop")
    subprocess.Popen([DOCKER_DESKTOP], creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    for _ in range(30):
        time.sleep(10)
        if up():
            return
    raise RuntimeError("Docker não subiu em 5 min")


def sh(step, cmd, timeout):
    log(f"{step}: {' '.join(cmd)[:200]}")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                       env={**os.environ, "MSYS_NO_PATHCONV": "1"})
    if r.returncode != 0:
        raise RuntimeError(f"{step}: {(r.stderr or r.stdout).strip()[-1500:]}")
    return r.stdout


# ---------------------------------------------------------------------------
# Geração

def generate(state, edition_iso):
    free_gb = shutil.disk_usage(ROOT).free / 1e9
    if free_gb < MIN_FREE_GB:
        raise RuntimeError(f"disco: {free_gb:.1f} GB livres no C: (mínimo {MIN_FREE_GB})")
    edition = ed.parse(edition_iso)
    dl = os.path.join(ROOT, "dl", edition_iso)
    out = os.path.join(ROOT, "out", edition_iso)
    os.makedirs(dl, exist_ok=True)
    os.makedirs(out, exist_ok=True)
    ensure_docker()
    sh("download", [sys.executable, "-I", os.path.join(HERE, "download.py"), ed.faa_folder(edition), dl], 3 * 3600)
    if subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True).returncode != 0:
        sh("imagem", ["docker", "build", "-t", IMAGE, HERE], 3600)
    sh("volume", ["docker", "volume", "create", VOLUME], 120)
    # Recortes com as tabelas de ajuste da edição revisada: se a FAA mudou o leiaute, o
    # neatline.py para (ponto ou caixa que não bate) e a rodada falha com aviso. Os recortes da
    # edição nova ficam no volume; o neatlines.geojson da pasta (edição 2026-10-29) não é tocado.
    zips = sorted(f"/dl/{n}" for n in os.listdir(dl) if n.lower().endswith(".zip"))
    sh("recortes", ["docker", "run", "--rm", "-v", f"{dl}:/dl:ro", "-v", f"{HERE}:/scripts:ro",
                    "-v", f"{VOLUME}:/work", IMAGE, "python3", "/scripts/neatline.py",
                    "/work/neatlines.geojson", "/tmp/check", *zips], 3600)
    sh("tiles", ["docker", "run", "--rm", "--tmpfs", "/work/tmp:size=6g", "-e", "NEATLINES=/work/neatlines.geojson",
                 "-v", f"{dl}:/dl:ro",
                 "-v", f"{HERE}:/scripts:ro", "-v", f"{VOLUME}:/work", IMAGE, "bash", "/scripts/run_all.sh",
                 edition_iso, ed.valid_until(edition).isoformat()], 12 * 3600)
    sh("cópia", ["docker", "run", "--rm", "-v", f"{VOLUME}:/work", "-v", f"{out}:/out", IMAGE,
                 "bash", "-c", "cp /work/out/*.mbtiles /out/ && rm -rf /work/out /work/parts"], 3600)
    problems, summaries = check_edition(out, state["published"]["charts"], edition_iso)
    if problems:
        raise RuntimeError("conferência reprovou:\n" + "\n".join(problems))
    state["generated"] = {"edition": edition_iso, "out": out, "charts": summaries,
                          "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    save_state(state)
    shutil.rmtree(dl, ignore_errors=True)
    notify(f"Cartas EUA: edição {edition_iso} gerada",
           f"Edição {edition_iso} gerada e conferida em {out}.\n"
           f"Publicação automática a partir de {ed.effective_utc(edition).isoformat()}.")


def do_publish(state, edition_iso):
    from publish import publish
    gen = state["generated"]
    prev = state["published"]["edition"]
    publish(gen["out"], edition_iso, prev, os.path.join(ROOT, "rc"), log=log)
    old_out = state["published"].get("out")
    state["published"] = {"edition": edition_iso, "charts": gen["charts"], "out": gen["out"],
                          "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    state.pop("generated", None)
    save_state(state)
    if old_out and os.path.isdir(old_out) and old_out != gen["out"]:
        shutil.rmtree(old_out, ignore_errors=True)
    notify(f"Cartas EUA: edição {edition_iso} publicada",
           f"Edição {edition_iso} publicada (servidor, S3, CloudFront, Remote Config ?v={edition_iso.replace('-', '')}).\n"
           f"Cópia da edição {prev} guardada em s3://alfaero/backup/us-charts/{prev}/ e /opt/us-charts/{prev}/.")


# ---------------------------------------------------------------------------

def run():
    if not acquire_lock():
        log("outra execução em andamento: saindo")
        return 0
    action = None
    try:
        state = load_state()
        action, arg = decide(state, datetime.now(timezone.utc), faa_has)
        log(f"decisão: {action} {arg}")
        if action == "generate":
            generate(state, arg)
        elif action == "publish":
            do_publish(state, arg)
        return 0
    except Exception as e:
        log(traceback.format_exc())
        notify(f"Cartas EUA: falha ({action or 'decisão'})", f"{e}\n\nLog: {LOG}")
        return 1
    finally:
        release_lock()


def seed(edition_iso, out_dir):
    charts = {}
    for chart in CHARTS:
        s = summarize(os.path.join(out_dir, chart + ".mbtiles"), sample=50)
        charts[chart] = {"zooms": s["zooms"], "size": s["size"]}
    save_state({"published": {"edition": edition_iso, "charts": charts, "out": out_dir,
                              "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}})
    print(json.dumps(load_state(), indent=1)[:1500])


def status():
    state = load_state()
    print(json.dumps({k: v for k, v in state.items()}, indent=1)[:2000])
    print("decisão de agora:", decide(state, datetime.now(timezone.utc), faa_has))


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "run":
        sys.exit(run())
    if cmd == "seed":
        seed(sys.argv[2], sys.argv[3])
    else:
        status()
