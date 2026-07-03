# Contributing

Thanks for considering a contribution to Media Tools. The project is currently focused on becoming easy to run, diagnose, and improve as an open source local media workbench.

## Before You Start

- Read [README.md](README.md) to understand the supported workflow.
- Check [ROADMAP.md](ROADMAP.md) for current priorities.
- Search existing issues before opening a new one.
- Do not post cookies, Qwen tokens, local databases, private media names, or account exports.

## Development Setup

```bash
git clone https://github.com/silentglow/douyin-stream.git
cd douyin-stream
python3.11 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp config/config.yaml.example config/config.yaml
```

Frontend dependencies are installed from `frontend/`:

```bash
cd frontend
npm install
```

Start the local app:

```bash
./run.sh
```

## Branches And Commits

Create a topic branch:

```bash
git switch -c fix/short-description
```

Use conventional commit prefixes when practical:

- `feat`: user-facing feature.
- `fix`: bug fix.
- `docs`: documentation.
- `test`: tests.
- `refactor`: internal restructuring without intended behavior change.
- `chore`: tooling, release, or maintenance.

Example:

```text
fix(transcribe): preserve retry state after export failure
```

## Tests And Checks

Run the checks that match your change. For backend changes:

```bash
uv run ruff check src tests
uv run ruff format --check src tests
uv run pytest
```

For frontend changes:

```bash
cd frontend
npm test -- --run
npm run build
```

For Docker or deployment changes:

```bash
docker compose -f deploy/docker-compose.yml config
cd deploy && docker compose build
```

For runtime data consistency checks:

```bash
python scripts/health_check.py
```

`scripts/health_check.py` expects an initialized local database. A missing database in a fresh checkout is not a code failure.

## Pull Requests

A good pull request includes:

- Clear summary of the problem and solution.
- Linked issue when one exists.
- Tests or checks run.
- Screenshots for UI changes.
- Risk notes for migrations, account state, file deletion, retry behavior, or Docker changes.
- Documentation updates for user-facing behavior.

Keep pull requests focused. Large product changes should start with an issue or design discussion.

## Issue Reports

Use the GitHub issue templates:

- Bug report: include version, startup mode, environment, reproduction steps, logs, and diagnostics.
- Feature request: describe the blocked workflow and the smallest useful solution.
- Question: include startup mode, OS, relevant command or page, and what you already checked.

Before posting logs, remove:

- cookies.
- Qwen tokens.
- account IDs if private.
- local absolute paths when they identify private folders.
- private media titles or transcript content.

## Good First Issue Areas

- Documentation: improve setup steps for a specific OS.
- Documentation: add FAQ entries from real issue reports.
- Tests: add frontend tests around task status display.
- Tests: add API contract tests for Settings or task routes.
- UI polish: improve empty states and loading states.
- Tooling: add docs link checking or markdown linting.
- Research: document a new platform's requirements without adding production support.

## Coding Guidelines

- Follow existing module boundaries and local patterns.
- Keep SQLite as the default runtime database unless a separate design says otherwise.
- Keep comments short and useful.
- Prefer typed Python interfaces where they clarify behavior.
- Keep backend formatting aligned with `pyproject.toml` (`line-length = 120`).
- Do not add network-dependent tests unless they are explicitly isolated or skipped by default.

## Documentation Guidelines

Update docs when a change affects:

- startup or installation.
- Docker behavior.
- account setup.
- task retry or cancellation behavior.
- transcript output location or format.
- public API response shape.

Relevant files:

- [README.md](README.md)
- [docs/references/INSTALLATION.md](docs/references/INSTALLATION.md)
- [docs/references/FAQ.md](docs/references/FAQ.md)
- [docs/references/API.md](docs/references/API.md)
- [CHANGELOG.md](CHANGELOG.md)

## License

By contributing, you agree that your contribution is released under the repository's [MIT License](LICENSE).
