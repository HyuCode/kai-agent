#!/usr/bin/env bash
# loop/loop.sh — Maker→Checker development loop for hermes-agent, driven by `claude -p`.
#
#   Maker (claude -p)  ->  deterministic gate (loop/verify.sh)  ->  Checker (claude -p)
#        ^                                                                  |
#        └──────────────── feedback (on FAIL, up to MAX_ATTEMPTS) ─────────┘
#
# State lives on disk (loop/STATE.md + loop/.artifacts/), not in context. The loop
# never pushes or opens PRs — review & push stay manual.
#
# Usage:
#   loop/loop.sh loop/tasks/my-task.md
#   MAX_ATTEMPTS=3 MODEL=opus LOOP_TEST_SCOPE=tests/tools/ loop/loop.sh loop/tasks/my-task.md
#
# Guardrails (env-overridable):
#   MAX_ATTEMPTS        max Maker→Checker rounds                (default 5)
#   MAKER_BUDGET_USD    --max-budget-usd per Maker invocation   (default 3.00)
#   CHECKER_BUDGET_USD  --max-budget-usd per Checker invocation (default 1.00)
#   MODEL               claude model alias                      (default: account default)
#   PERMISSION_MODE     claude --permission-mode                (default acceptEdits)
#   LOOP_TEST_SCOPE     test path passed to verify.sh           (default: task TEST_SCOPE or tests/)
#
# No-progress stop: if the Maker produces no new diff in a round, or the same gate
# failure repeats, the loop stops instead of burning budget.

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

TASK="${1:-}"
if [ -z "$TASK" ] || [ ! -f "$TASK" ]; then
  echo "usage: loop/loop.sh <task-file.md>   (e.g. loop/tasks/EXAMPLE-fix-bug.md)" >&2
  exit 64
fi

command -v claude >/dev/null 2>&1 || { echo "error: 'claude' CLI not found in PATH" >&2; exit 69; }

MAX_ATTEMPTS="${MAX_ATTEMPTS:-5}"
MAKER_BUDGET_USD="${MAKER_BUDGET_USD:-3.00}"
CHECKER_BUDGET_USD="${CHECKER_BUDGET_USD:-1.00}"
PERMISSION_MODE="${PERMISSION_MODE:-acceptEdits}"

# TEST_SCOPE precedence: env > "TEST_SCOPE:" line in the task file > tests/
TEST_SCOPE="${LOOP_TEST_SCOPE:-}"
if [ -z "$TEST_SCOPE" ]; then
  TEST_SCOPE="$(grep -iE '^TEST_SCOPE:' "$TASK" | head -1 | sed -E 's/^TEST_SCOPE:[[:space:]]*//')"
fi
TEST_SCOPE="${TEST_SCOPE:-tests/}"

MODEL_ARGS=()
[ -n "${MODEL:-}" ] && MODEL_ARGS=(--model "$MODEL")

ART="loop/.artifacts"
mkdir -p "$ART"
FEEDBACK_FILE="$ART/checker-feedback.md"
VERDICT_FILE="$ART/verdict.txt"
RUN_LOG="$ART/loop.log"
: > "$FEEDBACK_FILE"
: > "$RUN_LOG"

say() { printf '\n\033[1;36m[loop]\033[0m %s\n' "$*" | tee -a "$RUN_LOG"; }

diff_hash() { git add -A -N >/dev/null 2>&1; git diff HEAD 2>/dev/null | shasum | awk '{print $1}'; }

say "TASK=$TASK  TEST_SCOPE=$TEST_SCOPE  MAX_ATTEMPTS=$MAX_ATTEMPTS  MODEL=${MODEL:-<default>}"

prev_diff_hash=""
prev_gate_fail=""

for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  say "===== Attempt $attempt / $MAX_ATTEMPTS ====="

  # ---- MAKER -------------------------------------------------------------
  say "Maker: implementing…"
  MAKER_PROMPT="$(cat loop/prompts/maker.md)
## This run
TASK_FILE: $TASK
TEST_SCOPE: $TEST_SCOPE

--- TASK CONTENT ---
$(cat "$TASK")
--- END TASK ---

--- CHECKER_FEEDBACK (empty on first round) ---
$(cat "$FEEDBACK_FILE")
--- END CHECKER_FEEDBACK ---"

  claude -p "$MAKER_PROMPT" \
    --permission-mode "$PERMISSION_MODE" \
    --max-budget-usd "$MAKER_BUDGET_USD" \
    "${MODEL_ARGS[@]}" 2>&1 | tee -a "$RUN_LOG"

  # ---- No-progress detection --------------------------------------------
  cur_diff_hash="$(diff_hash)"
  if [ "$attempt" -gt 1 ] && [ "$cur_diff_hash" = "$prev_diff_hash" ]; then
    say "No-progress: Maker produced no new changes since last round. Stopping."
    exit 3
  fi
  prev_diff_hash="$cur_diff_hash"

  # ---- OBJECTIVE GATE (deterministic) -----------------------------------
  say "Gate: running loop/verify.sh ($TEST_SCOPE)…"
  if LOOP_TEST_SCOPE="$TEST_SCOPE" bash loop/verify.sh >/dev/null 2>&1; then
    gate_ok=1
    say "Gate: ✅ green"
  else
    gate_ok=0
    gate_fail_sig="$(tail -5 "$ART/verify.log" | shasum | awk '{print $1}')"
    say "Gate: ❌ failed (see loop/.artifacts/verify.log)"
    if [ "$gate_fail_sig" = "$prev_gate_fail" ]; then
      say "No-progress: identical gate failure two rounds in a row. Stopping."
      printf 'Gate failed identically two rounds. Tail of verify.log:\n\n' > "$FEEDBACK_FILE"
      tail -40 "$ART/verify.log" >> "$FEEDBACK_FILE"
      exit 4
    fi
    prev_gate_fail="$gate_fail_sig"
  fi

  # ---- CHECKER (independent review) -------------------------------------
  say "Checker: reviewing…"
  : > "$VERDICT_FILE"
  CHECKER_PROMPT="$(cat loop/prompts/checker.md)
## This run
TASK_FILE: $TASK
TEST_SCOPE: $TEST_SCOPE
VERDICT_FILE: $VERDICT_FILE
FEEDBACK_FILE: $FEEDBACK_FILE

--- TASK CONTENT ---
$(cat "$TASK")
--- END TASK ---

Note from the deterministic gate this round: $([ "$gate_ok" = 1 ] && echo 'gate is GREEN' || echo 'gate FAILED — see loop/.artifacts/verify.log; you must verdict FAIL')."

  claude -p "$CHECKER_PROMPT" \
    --permission-mode default \
    --allowedTools "Read Grep Glob Bash(git *) Bash(loop/verify.sh:*) Bash(bash loop/verify.sh:*) Bash(scripts/run_tests.sh:*) Bash(ruff:*) Bash(python *)" \
    --max-budget-usd "$CHECKER_BUDGET_USD" \
    "${MODEL_ARGS[@]}" 2>&1 | tee -a "$RUN_LOG"

  verdict="$(tr -d '[:space:]' < "$VERDICT_FILE" 2>/dev/null | tr '[:lower:]' '[:upper:]')"
  say "Checker verdict: ${verdict:-<none>}"

  if [ "$gate_ok" = 1 ] && [ "$verdict" = "PASS" ]; then
    say "✅ DONE — gate green and Checker PASSED on attempt $attempt."
    say "Review the commit, then push/open a PR manually. State: loop/STATE.md"
    exit 0
  fi

  say "Round $attempt did not pass. Feeding Checker feedback back to the Maker."
done

say "⛔ Reached MAX_ATTEMPTS ($MAX_ATTEMPTS) without a PASS. See loop/STATE.md and loop/.artifacts/."
exit 2
