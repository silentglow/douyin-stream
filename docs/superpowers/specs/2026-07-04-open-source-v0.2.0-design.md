# Media Tools Open Source v0.2.0 Design

## Purpose

Media Tools is already open source and has a working product core: creator management, video download, Qwen transcription, a task system, a React workbench, and Docker deployment. The next development step is to make the project understandable, runnable, and contributable for people who did not build it.

The goal for `v0.2.0` is to move the project from "published source code" to "usable open source product."

Success means a new user can start from the repository, run the app with Docker, configure the required accounts, and complete one download -> transcription -> reading flow in about 10 minutes.

## Target Users

- Individual users who want a local video-to-transcript workflow.
- Technical users who can provide cookies or account credentials but do not know this codebase.
- Early contributors who need clear setup instructions, issue templates, contribution boundaries, and small tasks they can safely pick up.

## Scope

`v0.2.0` focuses on adoption, diagnosis, and contribution readiness. It does not expand the product into a cloud service or add major new business workflows.

Deliverables:

- Rewrite the README first viewport so it explains the product, audience, core flow, and quickest setup path.
- Add a 5-minute or 10-minute quickstart that walks through one complete successful flow:
  1. Start the app.
  2. Configure platform and Qwen accounts.
  3. Add or discover one creator or video.
  4. Download one video.
  5. Transcribe it.
  6. Read the transcript.
- Add `ROADMAP.md` with clear priorities:
  - P0: install, documentation, diagnostics, release hygiene.
  - P1: first-run experience, E2E coverage, Qwen transcription settings surfaced in UI.
  - P2: provider abstraction, additional platform research, packaging polish.
- Add `RELEASE_CHECKLIST.md` covering version bump, backend tests, frontend build, Docker validation, changelog update, tag, release notes, and rollback notes.
- Add GitHub issue templates:
  - Bug report.
  - Feature request.
  - Question or help request.
- Add a pull request template that asks for summary, screenshots when relevant, tests run, risks, and linked issues.
- Add a contributor-facing task list with `good first issue` candidates grouped by documentation, tests, UI polish, and platform research.
- Add an installation and runtime diagnostics checklist for:
  - Python version.
  - Node/npm version.
  - ffmpeg availability.
  - Docker availability.
  - writable data directories.
  - SQLite database initialization.
  - Douyin/Bilibili cookie presence.
  - Qwen account status.
  - transcript output path.

## Non-Goals

This release will not add:

- Multi-user accounts.
- SaaS hosting.
- Payment or licensing gates.
- Plugin marketplace.
- Major transcription pipeline rewrites.
- A database migration away from SQLite.
- New platform support as production functionality.

These may become later work, but they are not required for open source adoption at this stage.

## Repository Changes

The implementation should be documentation and project-process heavy. Expected repository-level changes:

- `README.md`: clearer product positioning, screenshots placeholders or references, quickstart, common failure links, and contribution links.
- `ROADMAP.md`: public development priorities.
- `RELEASE_CHECKLIST.md`: repeatable release process.
- `.github/ISSUE_TEMPLATE/bug_report.yml`: structured bug reports.
- `.github/ISSUE_TEMPLATE/feature_request.yml`: scoped feature requests.
- `.github/ISSUE_TEMPLATE/question.yml`: support questions.
- `.github/pull_request_template.md`: contribution checklist.
- `docs/references/INSTALLATION.md`: update or link to the quickstart and diagnostics checklist.
- `docs/references/FAQ.md`: ensure common setup and account failures are covered.

No backend or frontend production behavior is required for this design. If implementation finds a small missing diagnostic endpoint or script that materially improves first-run support, it should be proposed separately before being added.

## User Flow

The README and linked docs should guide a new user through one path:

1. Confirm prerequisites.
2. Clone the repository.
3. Start with Docker Compose, or use local development startup if Docker is unavailable.
4. Open the web UI.
5. Add platform cookies and Qwen accounts in Settings.
6. Use the app to process one small video.
7. Confirm the transcript appears in the reader.
8. Use the troubleshooting section if any step fails.

The docs should avoid presenting every possible workflow equally. The default path should be obvious.

## Error Handling and Diagnostics

Open source users will fail at setup in predictable places. The docs should convert these failures into actionable checks:

- ffmpeg missing or not on `PATH`.
- Docker build or port conflict.
- missing writable `data/` directory.
- invalid or expired platform cookies.
- Qwen account not authenticated.
- Qwen quota unavailable.
- transcript path outside the allowed workspace.
- download blocked by platform-side rate limits or auth state.

Each common failure should include:

- Symptom.
- Likely cause.
- Command or UI location to check.
- Next action.

## Testing and Verification

Before shipping `v0.2.0`, verify:

- README quickstart can be followed from a fresh clone.
- Docker Compose path starts the app and serves the UI.
- Local development path still works.
- Backend tests pass.
- Frontend build passes.
- Issue and PR templates render correctly on GitHub.
- Release checklist has no project-specific gaps.
- Roadmap items are specific enough to become issues.

Recommended commands:

```bash
uv run pytest
cd frontend && npm run build
cd deploy && docker compose up -d --build
python scripts/health_check.py
```

The exact Docker validation command may change if implementation updates deployment docs. The release checklist should contain the final command set.

## Milestone Definition

`v0.2.0` is complete when:

- A new user has a single obvious setup path.
- A contributor has clear templates and small tasks.
- The maintainer has a repeatable release checklist.
- The roadmap explains what is next without implying unsupported SaaS or multi-user functionality.
- No new major product surface has been added without separate design approval.

