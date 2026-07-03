# Media Tools

> Local video capture -> cloud transcription -> focused reading, in one web workbench.

![React](https://img.shields.io/badge/Frontend-React%2019-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/Backend-FastAPI-009688?logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.11%2B-brightgreen?logo=python&logoColor=white)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Media Tools is a local-first content operations workbench for people who collect, transcribe, and read video material. It currently supports Douyin/Bilibili creator workflows, Qwen cloud transcription, background task tracking, transcript export, and browser-based reading.

The project is designed as a single-machine tool. It is not a hosted SaaS service, does not include multi-user accounts, and keeps runtime data on your own machine by default.

## What It Does

- Manage Douyin/Bilibili creators and sync their public video metadata.
- Preview videos before downloading so you can avoid blind full-batch downloads.
- Download selected videos and optionally trigger transcription.
- Transcribe local audio/video files through Qwen.
- Track background tasks with retry, cancellation, partial failure states, and WebSocket progress.
- Read and manage transcripts in the web UI.
- Export transcripts as `md`, `docx`, `pdf`, `srt`, or `txt`.

## Recommended Quickstart: Docker

Use Docker first if you want to try the app from a fresh clone.

Requirements:

- Git
- Docker with Docker Compose

```bash
git clone https://github.com/silentglow/douyin-stream.git
cd douyin-stream
cp config/config.yaml.example config/config.yaml
cd deploy
docker compose up -d --build
```

Open `http://localhost:8000`.

Runtime data is stored under the repository `data/` directory through the Compose volume. The default `config/config.yaml.example` already points downloads to `data/downloads`, which maps to `/app/data/downloads` inside the container.

Useful Docker commands:

```bash
cd deploy
docker compose logs -f app
docker compose down
docker compose up -d --build
```

## Local Development

Use local development when you want to edit backend or frontend code.

Requirements:

- Python 3.11+
- Node.js 20+
- npm
- FFmpeg

```bash
git clone https://github.com/silentglow/douyin-stream.git
cd douyin-stream
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp config/config.yaml.example config/config.yaml
./run.sh
```

Open `http://localhost:5173`.

Other startup commands:

```bash
./run.sh backend
./run.sh frontend
./run.sh build
```

## 10-Minute Validation Flow

After the app starts:

1. Open Settings.
2. Add a Douyin or Bilibili account cookie.
3. Add or rehydrate at least one Qwen account.
4. Add one creator or use a direct video/creator link.
5. Select one small video and run download + transcription.
6. Watch task progress in the task panel.
7. Open the transcript reader and confirm the transcript is available.

If a step fails, check [Installation](docs/references/INSTALLATION.md) and [FAQ](docs/references/FAQ.md). They list common symptoms, causes, and diagnostics.

## Diagnostics

Basic environment checks:

```bash
python --version
node --version
npm --version
ffmpeg -version
docker --version
```

Runtime data check:

```bash
python scripts/health_check.py
```

`scripts/health_check.py` scans the local SQLite database and file system for task/transcript consistency issues. It expects an initialized runtime database.

## Documentation

- [Installation guide](docs/references/INSTALLATION.md)
- [FAQ](docs/references/FAQ.md)
- [API and architecture notes](docs/references/API.md)
- [Configuration architecture](docs/architecture/config.md)
- [Roadmap](ROADMAP.md)
- [Release checklist](RELEASE_CHECKLIST.md)
- [Contributing guide](CONTRIBUTING.md)

Public screenshots are not bundled with personal runtime data. Sanitized screenshots and demo media should be added as release assets or under `docs/ui/` when available.

## Technology

| Layer | Stack |
| --- | --- |
| Frontend | React 19, Vite, TypeScript, Tailwind CSS v4, shadcn/ui, Zustand, Framer Motion |
| Backend | Python 3.11+, FastAPI, SQLite WAL, APScheduler |
| Media | f2 for Douyin, yt-dlp for Bilibili, FFmpeg |
| Transcription | Qwen HTTP API and OSS upload flow |

## Repository Layout

```text
media-tools/
├── frontend/                  # React SPA
├── src/media_tools/           # FastAPI app and domain modules
├── config/                    # Configuration templates and auth rules
├── data/                      # Runtime database, auth state, downloads, logs
├── deploy/                    # Dockerfile and docker-compose.yml
├── docs/                      # Architecture and reference docs
├── scripts/                   # Startup and operational scripts
├── tests/                     # Backend tests
└── run.sh                     # Local development startup entrypoint
```

## Contributing

Issues and pull requests are welcome. Start with:

- [ROADMAP.md](ROADMAP.md) for priorities.
- [CONTRIBUTING.md](CONTRIBUTING.md) for development workflow.
- GitHub issue templates for bug reports, feature requests, and questions.

Please remove cookies, account tokens, private media names, and local file paths before posting logs or screenshots.

## License

[MIT License](LICENSE)
