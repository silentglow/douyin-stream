# Release Checklist

Use this checklist before publishing a tagged release. Keep the final commands aligned with the current CI workflow and deployment docs.

## 1. Scope

- Confirm the release milestone has a clear goal and no unrelated features.
- Check `ROADMAP.md` and move completed items into the release notes.
- Confirm user-facing behavior changes are reflected in `README.md`, `docs/references/INSTALLATION.md`, or `docs/references/FAQ.md`.
- Confirm no secrets, cookies, account exports, local databases, or transcripts are staged.

## 2. Version And Changelog

- Update `pyproject.toml` version if this is a packaged release.
- Update `CHANGELOG.md` with:
  - added.
  - changed.
  - fixed.
  - known limitations.
- Use a tag name like `v0.2.0`.

## 3. Local Validation

Run from a clean working tree where possible.

```bash
git status --short
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
cd frontend && npm test -- --run
cd frontend && npm run build
docker compose -f deploy/docker-compose.yml config
```

If Docker is available and the release changes deployment, also run:

```bash
cd deploy
docker compose build
docker compose up -d
docker compose logs --tail=100 app
docker compose down
```

If a local runtime database exists, run:

```bash
python scripts/health_check.py
```

`scripts/health_check.py` returns exit code `1` when it finds runtime data anomalies. Treat that as a release blocker for a production data snapshot, but not for a fresh checkout with no database.

## 4. Manual Smoke Test

- Start the app using the documented recommended path.
- Open the web UI.
- Confirm Settings loads.
- Confirm task panel loads.
- Configure or verify one platform account and one Qwen account.
- Process one small video or known local media file.
- Confirm the transcript appears in the reader.
- Confirm logs do not contain secrets.

## 5. GitHub Release

- Push the release commit.
- Create and push the tag.

```bash
git tag v0.2.0
git push origin main
git push origin v0.2.0
```

- Draft the GitHub release with:
  - short positioning.
  - upgrade notes.
  - validation commands that passed.
  - known limitations.
  - rollback notes.

## 6. Rollback Notes

- Document whether the release changes database schema or runtime data layout.
- For documentation-only releases, rollback is a normal git revert.
- For releases with migrations, note whether downgrading requires restoring a database backup.

