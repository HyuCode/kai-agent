#!/usr/bin/env bash
# kai 所有ドキュメントの lint / format。
# 対象は .markdownlint-cli2.jsonc の globs と .prettierignore の allowlist で定義
# （upstream hermes-agent のファイルは対象外 — fork 追従のため触らない）。
#
# 使い方:
#   scripts/kai-docs-lint.sh          # チェックのみ（CI 向け）
#   scripts/kai-docs-lint.sh --fix    # 自動修正
set -euo pipefail
cd "$(dirname "$0")/.."

MARKDOWNLINT=markdownlint-cli2@0.18.1
PRETTIER=prettier@3.6.2

GLOBS=("docs/kai/**/*.md" "kai-services/**/*.md" "CLAUDE.md" ".claude/agents/*.md")

if [[ "${1:-}" == "--fix" ]]; then
  npx --yes "$PRETTIER" --write "${GLOBS[@]}"
  npx --yes "$MARKDOWNLINT" --fix
else
  npx --yes "$PRETTIER" --check "${GLOBS[@]}"
  npx --yes "$MARKDOWNLINT"
fi
