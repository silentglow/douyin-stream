# Installation Guide

This guide is written for a fresh clone. Use Docker for the shortest path, or use local development when you want to edit code.

## Prerequisites

| Tool | Required for | Check |
| --- | --- | --- |
| Git | Clone the repository | `git --version` |
| Docker + Compose | Recommended first run | `docker --version` and `docker compose version` |
| Python 3.11+ | Local backend development | `python3.11 --version` |
| Node.js 20+ and npm | Local frontend development | `node --version` and `npm --version` |
| FFmpeg | Media processing and local transcription | `ffmpeg -version` |

FFmpeg install examples:

| OS | Command |
| --- | --- |
| macOS | `brew install ffmpeg` |
| Ubuntu/Debian | `sudo apt install ffmpeg` |
| Windows | `choco install ffmpeg` or install from <https://ffmpeg.org/download.html> and add it to `PATH` |

## Docker Quickstart

```bash
git clone https://github.com/silentglow/douyin-stream.git
cd douyin-stream
cp config/config.yaml.example config/config.yaml
cd deploy
docker compose up -d --build
```

Open `http://localhost:8000`.

Useful commands:

```bash
cd deploy
docker compose logs -f app
docker compose ps
docker compose down
```

The default configuration stores runtime data under the repository `data/` directory. In Docker this is mounted to `/app/data`, so the default download path `data/downloads` resolves to `/app/data/downloads` inside the container.

## Local Development Setup

```bash
git clone https://github.com/silentglow/douyin-stream.git
cd douyin-stream
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp config/config.yaml.example config/config.yaml
./run.sh
```

Open `http://localhost:5173`.

Other local commands:

```bash
./run.sh backend
./run.sh frontend
./run.sh build
```

The local startup script expects `.venv/bin/python` to exist. Create the virtual environment first; the script will install missing project dependencies inside that environment when possible.

## First-Run Configuration

After the web UI opens:

1. Go to Settings.
2. Add at least one Douyin or Bilibili account cookie for download workflows.
3. Add or rehydrate at least one Qwen account for transcription workflows.
4. Confirm the download directory and transcript output format.
5. Run one small download + transcription task before starting a large batch.

Do not put cookies or Qwen tokens in screenshots, issues, or public logs.

## Runtime Data

| Path | Purpose |
| --- | --- |
| `data/media_tools.db` | SQLite runtime database |
| `data/auth/` | Qwen and account auth state cache |
| `data/downloads/` | Downloaded media files |
| `data/logs/` | Runtime logs |
| `transcripts/` | Transcript output for local development |
| `config/config.yaml` | Local configuration copied from the example |

`data/`, `transcripts/`, and local auth/config files are intentionally ignored by git.

## Diagnostics Checklist

Use this checklist before opening a bug report.

### Environment

```bash
python3.11 --version
node --version
npm --version
ffmpeg -version
docker --version
docker compose version
```

### Docker

```bash
docker compose -f deploy/docker-compose.yml config
cd deploy && docker compose logs --tail=100 app
```

If `docker compose ... config` fails, the Compose file or local Docker installation is the issue. If config succeeds but the app exits, inspect container logs.

### Local App

```bash
test -x .venv/bin/python
.venv/bin/python -c "import media_tools"
curl -fsS http://127.0.0.1:8000/api/health
```

The `curl` command only works after the backend is running.

### Runtime Database

```bash
python scripts/health_check.py
```

This command expects `data/media_tools.db` to exist. On a fresh checkout before first startup, a missing database is expected. If your transcript files live outside the default `transcripts/` directory, pass `--transcripts-dir /path/to/transcripts`.

### Account State

Check these in the Settings page:

- Douyin/Bilibili account is present and not expired.
- Qwen account is authenticated.
- Qwen quota is available.
- Transcript export format is set to the expected value.

## Common Installation Failures

| Symptom | Likely cause | Next action |
| --- | --- | --- |
| `COPY frontend/package*.json` fails during Docker build | Docker context ignored frontend files | Ensure `.dockerignore` does not exclude `frontend/`; v0.2.0 keeps source files and ignores only `frontend/node_modules` and `frontend/dist` |
| `env file ... .env not found` from Docker Compose | Old Compose config required a local `.env` file | Use the current `deploy/docker-compose.yml`, which does not require `.env` |
| `未找到项目 venv` from `./run.sh` | Local virtual environment was not created | Run `python3.11 -m venv .venv && .venv/bin/pip install -e ".[dev]"` |
| `ffmpeg` not found | FFmpeg is missing or not on `PATH` | Install FFmpeg and restart the shell or container |
| Web UI cannot reach backend | Backend failed or port conflict | Check backend logs and whether port `8000` is already in use |
| Download fails with auth errors | Platform cookie expired or missing | Re-add the account in Settings |
| Transcription never starts | Qwen account missing, expired, or no quota | Rehydrate Qwen account and check quota in Settings |
