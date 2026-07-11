# FAQ

This FAQ focuses on setup, account state, download/transcription failures, and runtime diagnostics.

## Setup And Startup

### Docker build fails while copying frontend files

- Symptom: Docker reports that `frontend/package*.json` or `frontend/` cannot be found.
- Likely cause: the Docker build context is excluding frontend source files.
- Next action: use the current `.dockerignore`, which ignores `frontend/node_modules`, `frontend/dist`, and `frontend/.vite`, but not the `frontend/` source directory.

### Docker Compose reports `.env` is missing

- Symptom: `docker compose up` or `docker compose config` fails before building the app.
- Likely cause: an older Compose file required `../.env`.
- Next action: use the current `deploy/docker-compose.yml`. Runtime configuration is handled by `config/config.yaml`, Settings, and explicit environment variables when needed.

### `./run.sh` says the project virtual environment is missing

- Symptom: `未找到项目 venv: .../.venv/bin/python`.
- Likely cause: local development setup was skipped.
- Next action:

```bash
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
./run.sh
```

### The frontend opens but data does not load

- Symptom: empty pages, network errors, or stale task state.
- Likely cause: backend is not running, backend health check failed, or WebSocket connection dropped.
- Next action:

```bash
curl -fsS http://127.0.0.1:8000/api/health
cd deploy && docker compose logs --tail=100 app
```

Refresh the page after confirming the backend is healthy.

## Accounts And Authentication

### Download says the platform cookie is missing or expired

- Symptom: download task fails with auth or cookie errors.
- Likely cause: no Douyin/Bilibili account is configured, or the cookie expired.
- Next action: open Settings, delete the expired account if needed, and add the account again.

### Qwen transcription cannot start

- Symptom: transcription task fails before upload or stays blocked at account selection.
- Likely cause: no active Qwen account, expired Qwen auth state, or unavailable quota.
- Next action: open Settings, rehydrate the Qwen account, then check quota status.

### Are cookies written to logs?

- Cookies and tokens should not be posted publicly. The app has redaction paths for known sensitive fields, but users should still review logs before opening issues.
- Runtime account data is stored in the SQLite `Accounts_Pool` table and Qwen auth cache under `data/auth/`.
- Do not include `config/config.yaml`, `data/auth/`, database files, or raw cookies in issues.

## Media And Transcription

### FFmpeg is not found

- Symptom: local media processing or transcription preparation fails.
- Likely cause: FFmpeg is not installed or is not available on `PATH`.
- Next action:
  - macOS: `brew install ffmpeg`
  - Ubuntu/Debian: `sudo apt install ffmpeg`
  - Windows: `choco install ffmpeg` or install from the official FFmpeg site and update `PATH`

### Some videos are skipped

- Likely causes:
  - the video already exists locally and incremental sync skipped it.
  - the video is private or deleted.
  - the platform temporarily rate-limited the account.
  - the cookie cannot view that content.
- Next action: open the creator page in a browser with the same account, confirm the video is visible, then retry later if rate-limited.

### Where are downloads and transcripts stored?

- Local development downloads default to `data/downloads/`.
- Docker downloads default to `/app/data/downloads`, persisted as repository `data/downloads/`.
- Transcript output defaults to `transcripts/` in local development.
- Settings can change export format; deployment-level paths are controlled by `config/config.yaml`.

### Which transcript formats are supported?

Supported export formats:

- `md`
- `docx`
- `pdf`
- `srt`
- `txt`

Change the format in Settings before submitting new transcription tasks.

### Will transcription delete my original media file?

- Pipeline downloads can delete source video after successful transcription when auto-delete is enabled.
- Local file transcription does not delete the user's original source file; it only cleans temporary files.

### I moved transcript files out of the project. Will auto-sync re-download everything?

- No. Incremental sync and auto-follow use the database (`last_fetch_time`, `video_metadata` aweme IDs), not “is the file still on disk?”.
- Moved/archived files remain “known history”. Only **new** videos after the last sync are fetched.
- **全量重拉 (full sync)** is different: it re-downloads everything and ignores that archive workflow. Avoid it after you have archived content.

### Where did the transcripts page go?

- The dedicated 文稿库 page was removed. Open **内容库 → creator → completed item** to read.
- Old `/transcripts` URLs redirect to the content library.

### How do I stop following a creator but keep transcripts?

- In the content library, open **⋯ → 移除创作者…** (or multi-select → **停跟并保留**).
- Choose **停跟，保留文稿**: `auto_sync` off, status `unfollowed`, assets and files kept.
- Choose **彻底删除** only when you want creator + DB assets + local files gone.

### Why does pause then continue re-run the whole task?

- Workers do not persist execution checkpoints. Pause stops the current coroutine; resume restarts the workflow with original parameters.
- The UI labels this as “继续（从头）” intentionally.

## Task Recovery

### What happens after a service restart?

- In-memory background tasks are lost.
- On startup, stale `RUNNING` or `PENDING` tasks are marked failed so they can be retried.
- Transcription retries use `transcribe_runs` data where possible to resume from uploaded or remote records instead of starting from scratch.

### Why does a Qwen polling timeout not re-upload immediately?

- `QWEN_TRANSCRIBE_POLL_TIMEOUT_SECONDS` controls how long the local app waits for Qwen completion in one attempt.
- Timeout does not prove the remote record failed.
- The app keeps `record_id` and `gen_record_id` so a later retry can resume from the remote record.

## Diagnostics

### How do I check local runtime consistency?

```bash
python scripts/health_check.py
```

This scans the local database and file system for missing transcript files, stuck tasks, and stale Qwen runs. It expects an initialized `data/media_tools.db`.

If transcript files live outside the default `transcripts/` directory, run:

```bash
python scripts/health_check.py --transcripts-dir /path/to/transcripts
```

### What should I include in a bug report?

- Version or commit SHA.
- Startup mode: Docker or local.
- OS, Python, Node, npm, Docker, and FFmpeg versions.
- Exact reproduction steps.
- Backend logs or browser errors with secrets removed.
- Whether `python scripts/health_check.py` found anomalies.
