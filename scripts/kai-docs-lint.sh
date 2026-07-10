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

check_kai_doc_numbering() {
  local failed=0 path name

  # stream-review/ は .gitignore 対象のローカル作業記録なので、正式文書の規則から除外する。
  while IFS= read -r -d '' path; do
    name="${path##*/}"
    if [[ ! "$name" =~ ^[0-9]{2}- ]]; then
      echo "番号なしの kai 文書パス: $path" >&2
      failed=1
    fi
  done < <(
    find docs/kai \
      -path docs/kai/stream-review -prune -o \
      -mindepth 1 \( -type d -o -type f \) -print0
  )

  if ((failed)); then
    echo "docs/kai の正式文書は NN- で始まる名前にしてください。" >&2
    return 1
  fi
}

check_kai_doc_numbering

if [[ "${1:-}" == "--fix" ]]; then
  npx --yes "$PRETTIER" --write "${GLOBS[@]}"
  npx --yes "$MARKDOWNLINT" --fix
else
  npx --yes "$PRETTIER" --check "${GLOBS[@]}"
  npx --yes "$MARKDOWNLINT"
fi
