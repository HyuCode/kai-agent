# CLAUDE.md — hermes-agent

This file is auto-loaded by Claude Code. It is the **anchor** for every
`claude -p` development loop run (see `loop/`). Keep it short and stable.

## What this repo is

Hermes Agent — a self-improving AI agent (Python, large codebase). Entry points:
`cli.py`, `run_agent.py`, `hermes_cli/`, `agent/`, `tools/`, `gateway/`.

## Authoritative conventions (read these, don't re-derive)

- `AGENTS.md` — architecture, testing strategy, code style, PR review checklist.
- `CONTRIBUTING.md` — commit format, branch naming, PR standards.
  When `AGENTS.md`/`CONTRIBUTING.md` and this file disagree, those two win.

## Verification gate — the single source of truth for "is it green"

Run `loop/verify.sh` (fast checks always; tests scoped by `LOOP_TEST_SCOPE`):

1. Import smoke: `python -c "import cli, run_agent"` (must succeed).
2. Lint (blocking in CI): `ruff check .` — enforces `PLW1514` (no bare `open()`/
   `read_text()`/`write_text()`; always pass `encoding=`).
3. Windows footguns (blocking in CI): `python scripts/check-windows-footguns.py --all`.
4. Tests (CI-parity runner): `scripts/run_tests.sh [path]`. Default discovery is
   `tests/`; `addopts = -m 'not integration'` skips external-service tests.
   Run a **targeted subset** while iterating, e.g. `scripts/run_tests.sh tests/tools/`.

Never call `pytest` directly — `scripts/run_tests.sh` enforces CI parity
(per-file isolation, `TZ=UTC`, `LANG=C.UTF-8`, `PYTHONHASHSEED=0`, blanked env).

## Must-follow rules for any change

- **Cross-platform always.** Never assume Unix. If you touch file I/O, processes,
  or terminals, consider macOS / Linux / WSL2 / Windows. The footgun check is blocking.
- **Encoding always.** Every `open()`/`read_text()`/`write_text()` needs `encoding="utf-8"`.
- **Focused changes.** One logical change per branch/PR. No mixing fix + refactor + feature.
- **Tested.** Add/adjust tests near the changed subsystem; the gate must pass before "done".
- **Conventional Commits.** `type(scope): description` (types: fix, feat, docs, test,
  refactor, chore). Branch: `type/scope-short-desc`.
- Comments only for non-obvious intent/trade-offs, not narration. Log unexpected
  errors with `logger.error(..., exc_info=True)`.

## Loop workflow

Autonomous/assisted development runs through `loop/loop.sh` (Maker → deterministic
verify → independent Checker). Working state lives on disk in `loop/STATE.md`,
not in conversation context. Product direction / Definition-of-Done: `loop/VISION.md`.
Do **not** `git push` from a loop run; pushing/PRs stay manual.
