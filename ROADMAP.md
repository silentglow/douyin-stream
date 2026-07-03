# Media Tools Roadmap

This roadmap is intentionally practical. The project already has a working local media workflow; the next releases focus on making it easier to run, diagnose, and contribute to before expanding the product surface.

## v0.2.0: Open Source Readiness

Goal: a new user can clone the repository, start the app, configure accounts, and complete one download -> transcription -> reading flow in about 10 minutes.

### P0: Adoption Basics

- README first screen explains who the project is for, what workflow it supports, and the recommended setup path.
- Docker quickstart works from a fresh clone.
- Installation docs include a diagnostics checklist for Python, Node, ffmpeg, Docker, data directories, SQLite, platform cookies, Qwen accounts, and transcript output.
- FAQ covers the most common setup and runtime failures with symptoms, causes, and next actions.
- GitHub issue templates collect enough environment, logs, and reproduction detail to make reports actionable.
- Pull request template asks for tests, screenshots when relevant, risk notes, and linked issues.
- Release checklist documents repeatable validation and release steps.

### P1: First-Run Confidence

- Add browser E2E coverage for the main first-run path: Settings -> add account -> submit a small task -> inspect task state -> open transcript.
- Add a lightweight UI diagnostics panel or endpoint if repeated issue reports show users cannot find required status information.
- Surface Qwen transcription settings currently documented but not configurable:
  - speaker mode.
  - export content type.
  - with speaker.
  - with timestamp.
  - language and translation options.
- Improve screenshots and demo media with sanitized, reproducible examples.

### P2: Product Extensibility

- Define a transcription-provider interface before adding non-Qwen providers.
- Research additional platform support as prototypes before committing to production support.
- Improve packaging options after Docker and local development paths are stable.
- Consider GitHub Container Registry publishing once the release process is repeatable.

## Good First Issue Candidates

- Documentation: add platform-specific ffmpeg installation screenshots or commands.
- Documentation: improve FAQ entries with logs from real setup failures.
- Tests: add frontend unit tests around task status formatting and retry controls.
- Tests: add API contract tests for public Settings and task routes.
- UI polish: improve empty states in Settings, Library, and Transcripts.
- Dev tooling: add a docs link checker or markdown lint command.
- Research: document requirements for one potential new platform without implementing it.

## Explicit Non-Goals For Now

- Multi-user accounts.
- Hosted SaaS deployment.
- Payment, licensing gates, or cloud billing.
- Plugin marketplace.
- Replacing SQLite for the default single-machine workflow.
- Large transcription pipeline rewrites without a separate design.

