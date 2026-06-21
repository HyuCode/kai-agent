#!/usr/bin/env bash
# loop/verify.sh — deterministic verification gate for the dev loop.
#
# This is the single source of truth for "is the change green". The Maker
# agent runs it to self-check; loop.sh runs it as the objective gate before
# the Checker review. It mirrors the blocking CI checks (lint.yml, tests.yml).
#
# Usage:
#   loop/verify.sh                      # fast checks + full test suite (tests/)
#   loop/verify.sh tests/tools/         # fast checks + targeted tests
#   LOOP_TEST_SCOPE=tests/agent/ loop/verify.sh
#   LOOP_SKIP_TESTS=1 loop/verify.sh    # fast checks only (lint + footguns + import)
#
# Exit code 0 = all green. Non-zero = a stage failed (see the printed log).
# A machine-readable log is written to loop/.artifacts/verify.log.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ART_DIR="loop/.artifacts"
mkdir -p "$ART_DIR"
LOG="$ART_DIR/verify.log"
: > "$LOG"

TEST_SCOPE="${1:-${LOOP_TEST_SCOPE:-tests/}}"

log()  { printf '%s\n' "$*" | tee -a "$LOG"; }
fail() { log "❌ FAIL: $*"; exit 1; }

log "== verify.sh @ $(git rev-parse --short HEAD 2>/dev/null || echo nogit) =="

# Resolve a python that has the project deps (prefer the project venv).
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif [ -x "venv/bin/python" ]; then
  PY="venv/bin/python"
else
  PY="python"
fi
log "python: $PY"

# 1) Import smoke — cheapest signal that nothing is structurally broken.
log "-- [1/4] import smoke --"
if ! "$PY" -c "import cli, run_agent" >>"$LOG" 2>&1; then
  fail "import smoke (python -c 'import cli, run_agent')"
fi
log "ok: imports"

# 2) Lint — ruff PLW1514 is blocking in CI (lint.yml).
log "-- [2/4] ruff check --"
if command -v ruff >/dev/null 2>&1; then RUFF="ruff"; else RUFF="uv tool run ruff"; fi
if ! $RUFF check . >>"$LOG" 2>&1; then
  fail "ruff check . (likely PLW1514: missing encoding= on open/read_text/write_text)"
fi
log "ok: ruff"

# 3) Windows footguns — blocking in CI (lint.yml).
log "-- [3/4] windows footguns --"
if ! "$PY" scripts/check-windows-footguns.py --all >>"$LOG" 2>&1; then
  fail "scripts/check-windows-footguns.py --all"
fi
log "ok: footguns"

# 4) Tests — CI-parity runner (per-file isolation, deterministic env).
if [ "${LOOP_SKIP_TESTS:-0}" = "1" ]; then
  log "-- [4/4] tests SKIPPED (LOOP_SKIP_TESTS=1) --"
else
  log "-- [4/4] tests: $TEST_SCOPE --"
  if ! scripts/run_tests.sh "$TEST_SCOPE" >>"$LOG" 2>&1; then
    fail "scripts/run_tests.sh $TEST_SCOPE"
  fi
  log "ok: tests ($TEST_SCOPE)"
fi

log "✅ ALL GREEN"
exit 0
