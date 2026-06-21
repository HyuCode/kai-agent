# VISION — 開発ループの「Definition of Done」と制約

毎ループで読まれる安定したアンカー。タスク個別ではなく、**全タスク共通の合格基準と制約**を書く。
（プロダクトの方向性が変わったらここを更新する。長くしすぎない。）

## Definition of Done（1タスクが「完了」と言える条件）

- `loop/verify.sh`（import smoke / ruff / footguns / 対象テスト）が `✅ ALL GREEN`。
- 変更がタスクの意図を**過不足なく**満たし、スコープ外の差分が無い。
- 変更箇所のサブシステムにテストが追加/更新され、振る舞いを実際に検証している。
- Conventional Commits 形式でコミット済み（push/PR は人間が手動）。

## 制約（このリポジトリで常に守る）

- **クロスプラットフォーム**: Unix 前提禁止。macOS/Linux/WSL2/Windows を考慮。footgun check は CI ブロッキング。
- **エンコーディング**: `open()/read_text()/write_text()` は必ず `encoding="utf-8"`（ruff PLW1514 がブロッキング）。
- **CI パリティ**: テストは `scripts/run_tests.sh` のみ（直接 `pytest` を呼ばない）。
- **フォーカス**: 1ブランチ＝1論理変更。修正・リファクタ・機能追加を混ぜない。
- 秘密情報（`.env` 等）を読まない・コミットしない。`git push` をループから実行しない。

## 非ゴール（ループにやらせないこと）

- 大規模リファクタ、依存の大幅更新、`uv.lock` の手動編集。
- upstream（NousResearch）の設計方針に反する変更。
