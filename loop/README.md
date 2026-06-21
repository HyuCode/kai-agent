# loop/ — `claude -p` による開発ループ（Loop Engineering ハーネス）

このリポジトリ自身の **機能開発・バグ修正** を、Claude Code のヘッドレスモード（`claude -p`）で
半自律に回すための仕組み。設計の背景は [`docs/loop-engineering-analysis.md`](../docs/loop-engineering-analysis.md)。

```text
Maker (claude -p)  ──▶  決定論的ゲート (loop/verify.sh)  ──▶  Checker (claude -p)
     ▲                                                              │
     └──────────────── FAIL 時はフィードバックを返す（最大 MAX_ATTEMPTS）──┘
```

- **Maker**: 実装する `claude -p`。最小の正しい変更を入れ、`verify.sh` で自己検証し、`STATE.md` を更新してコミット。
- **ゲート**: `verify.sh`（import / ruff / footguns / 対象テスト）。LLM ではなくスクリプトが客観判定（自己採点＝Verifier Theater を防ぐ）。
- **Checker**: 別プロセスの `claude -p`。差分とゲートを独立に再検証し、テストでは拾えない観点（スコープ・意図・移植性）をレビューして `PASS`/`FAIL` を出す。実装はしない。

## 使い方

```bash
# 1) タスクを書く（雛形をコピー）
cp loop/tasks/EXAMPLE-fix-bug.md loop/tasks/my-task.md
$EDITOR loop/tasks/my-task.md          # ゴール・受け入れ条件・TEST_SCOPE を埋める

# 2) 専用ブランチを切る（ループは push しない。レビューと push は手動）
git switch -c fix/scope-short-desc

# 3) 回す
loop/loop.sh loop/tasks/my-task.md

# 4) 結果を確認して手動で push / PR
git log --oneline -5
git diff main...HEAD
```

### よく使う調整（環境変数）

| 変数                 | 既定                                         | 説明                                   |
| -------------------- | -------------------------------------------- | -------------------------------------- |
| `MAX_ATTEMPTS`       | `5`                                          | Maker→Checker の最大ラウンド数         |
| `LOOP_TEST_SCOPE`    | task の `TEST_SCOPE:` 行 → なければ `tests/` | ゲートで回すテストパス（狭いほど速い） |
| `MAKER_BUDGET_USD`   | `3.00`                                       | Maker 1回の `--max-budget-usd`         |
| `CHECKER_BUDGET_USD` | `1.00`                                       | Checker 1回の `--max-budget-usd`       |
| `MODEL`              | アカウント既定                               | `opus` / `sonnet` などのエイリアス可   |
| `PERMISSION_MODE`    | `acceptEdits`                                | Maker の権限モード                     |

例: `MAX_ATTEMPTS=3 MODEL=opus LOOP_TEST_SCOPE=tests/tools/ loop/loop.sh loop/tasks/my-task.md`

## ガードレール（暴走・課金事故の防止）

- **最大試行回数** `MAX_ATTEMPTS`。
- **コスト上限** `--max-budget-usd`（Maker / Checker 個別）。
- **No-progress 停止**: Maker が新しい差分を出さない／ゲートが同一失敗を 2 連続したら停止。
- **権限**: `acceptEdits`（編集と限定 Bash のみ自動承認）。`.claude/settings.json` の `deny` で
  `git push` / 秘密ファイル読取 / 破壊的コマンドをブロック。

## 単一ループ（Checker なし）で素早く回したい場合

最小構成は素の bash ループでも可（Ralph パターン）。Checker を省く分コストは下がるが、
独立検証が無くなるので「動くもの」を出す用途に留める:

```bash
for i in $(seq 1 5); do
  claude -p "$(cat loop/prompts/maker.md)
## This run
TASK_FILE: loop/tasks/my-task.md
TEST_SCOPE: tests/tools/
$(cat loop/tasks/my-task.md)" --permission-mode acceptEdits --max-budget-usd 3
  LOOP_TEST_SCOPE=tests/tools/ loop/verify.sh && break
done
```

## ファイル構成

- `verify.sh` — 決定論的ゲート（CI のブロッキング項目に対応）。
- `loop.sh` — Maker→Checker オーケストレーション本体。
- `prompts/maker.md`, `prompts/checker.md` — それぞれの安定プロンプト（アンカー）。
- `VISION.md` — 全タスク共通の Done と制約。
- `STATE.md` — ループ間で持続する作業メモリ。
- `tasks/` — 1ファイル=1タスク。
- `.artifacts/` — 実行ログ・verify ログ・verdict（gitignore 済み）。
