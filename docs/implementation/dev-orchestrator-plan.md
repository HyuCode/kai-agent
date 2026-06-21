# 実装計画 — 開発オーケストレーター（システム開発実装の代行）

| 項目           | 内容                                                                                           |
| -------------- | ---------------------------------------------------------------------------------------------- |
| 文書名         | 開発オーケストレーター 実装計画（WBS）                                                         |
| バージョン     | 1.0                                                                                            |
| 作成日         | 2026-06-16                                                                                     |
| 関連文書       | `docs/requirements/dev-orchestrator-requirements.md`, `docs/design/dev-orchestrator-design.md` |
| 凡例（状態）   | ✅ 完了 / 🟡 部分実装（要追加） / ⬜ 未着手                                                    |
| 凡例（規模）   | S（〜0.5日） / M（1〜2日） / L（3日以上）                                                      |
| 凡例（ループ） | 🤖 `loop/loop.sh`（claude -p）に乗せやすい / 👤 人手中心（外部CLI/実機検証が必要）             |

---

## 1. 概要・前提

Phase 1–6 の中核（repo registry／タスク投入／worktree 隔離／Codex・Claude delegate ワーカー／PR 作成・採用／音声通知）は実装済み。残課題は **品質ゲート・ガードレール・通知調停・Issue 起票・dashboard・hermes worker レーン**。各タスクは要件 ID（`DO-FR-xx`/`DO-NFR-xx`）に対応。

**検証基盤**: 既存 `tests/hermes_cli/test_dev_orchestrator.py` / `test_dev_tools.py` / `test_dev_notify.py` を `loop/verify.sh`（`TEST_SCOPE=tests/hermes_cli/`）で回す。`gh`/Codex/Claude CLI 実行を伴う検証は 👤。

---

## 2. マイルストーン

| MS  | 名称              | ゴール                                           | 状態    |
| --- | ----------------- | ------------------------------------------------ | ------- |
| M0  | コア（Phase 1–6） | 指示→worktree隔離→委譲→PR→音声通知が動く         | ✅ 完了 |
| M1  | 品質ゲート        | 自己申告でなくテスト検証で done 判定（DO-FR-11） | ⬜      |
| M2  | ガードレール      | 同時実行/コスト上限・No-progress（DO-NFR-01/04） | ⬜      |
| M3  | 通知・連携強化    | 通知調停・Issue起票・`/dev open`強化             | 🟡      |
| M4  | 可視化・拡張      | dev専用 overlay/dashboard・hermes worker レーン  | ⬜      |
| M5  | 運用整備          | 設定ドキュメント・registry 別ファイル化検討      | ⬜      |

---

## 3. 作業項目（WBS）

### M0 — コア（実装済み、Phase 1–6）

| ID      | 作業                                                                             | 関連FR   | 状態 | 主要ファイル                                           |
| ------- | -------------------------------------------------------------------------------- | -------- | ---- | ------------------------------------------------------ |
| DO-T-01 | リポジトリ登録/管理（registry・推定・`/dev repos`/`repo`）                       | DO-FR-01 | ✅   | `hermes_cli/dev_orchestrator.py`                       |
| DO-T-02 | タスク投入（`/dev assign`/`tasks`/`status`、`dev_assign`）                       | DO-FR-02 | ✅   | `hermes_cli/dev_orchestrator.py`, `tools/dev_tools.py` |
| DO-T-03 | worktree 隔離（`dev/<task_id>`、再利用/再アタッチ）                              | DO-FR-03 | ✅   | `hermes_cli/dev_orchestrator.py`                       |
| DO-T-04 | コーディングワーカー委譲（Codex/Claude、`/dev run` background/`--wait`）         | DO-FR-04 | ✅   | `hermes_cli/live_coding.py`, `dev_orchestrator.py`     |
| DO-T-05 | PR 作成・採用（auto-commit→push→`gh pr create`、`--confirm`、冪等採用、PR_BODY） | DO-FR-05 | ✅   | `hermes_cli/dev_orchestrator.py`                       |
| DO-T-06 | タスク追跡（Kanban 正本、claim/complete/block、run メタ、`/dev stop`）           | DO-FR-07 | ✅   | `hermes_cli/kanban_db.py`, `dev_orchestrator.py`       |
| DO-T-07 | 音声通知（cursor ポーリング、cooldown、TTS＋overlay、watcher）                   | DO-FR-08 | ✅   | `hermes_cli/dev_notify.py`, `tui_gateway/server.py`    |
| DO-T-08 | エージェントツール（dev_status/assign/run/stop）                                 | DO-FR-12 | ✅   | `tools/dev_tools.py`                                   |
| DO-T-09 | Issue 連携（list/view、Issue→task）                                              | DO-FR-06 | 🟡   | `hermes_cli/dev_orchestrator.py`                       |
| DO-T-10 | `/dev open`（VS Code、macOS fallback）                                           | DO-FR-09 | 🟡   | `hermes_cli/dev_orchestrator.py`                       |

### M1 — 品質ゲート（最重要残課題）

| ID      | 作業                                                                | 関連     | 状態 | 規模 | ループ | 依存       | 受け入れ                                                                      |
| ------- | ------------------------------------------------------------------- | -------- | ---- | ---- | ------ | ---------- | ----------------------------------------------------------------------------- |
| DO-T-20 | worktree 内テスト実行による done 判定（worker 完了後に検証）        | DO-FR-11 | ⬜   | M    | 🤖     | DO-T-03,04 | テスト green を done 条件に。失敗時は blocked（自己申告だけで done にしない） |
| DO-T-21 | Maker→Checker 型の二段検証（別 delegate に diff/test を検証させる） | DO-FR-11 | ⬜   | M    | 🤖     | DO-T-20    | 実装と検証を分離（`loop/` のパターンを dev worker に適用）                    |
| DO-T-22 | change_summary に検証結果（test/lint 結果）を含める                 | DO-FR-11 | ⬜   | S    | 🤖     | DO-T-20    | Kanban run メタにテスト合否が残る                                             |

### M2 — ガードレール

| ID      | 作業                                                            | 関連      | 状態 | 規模 | ループ | 依存    | 受け入れ                                       |
| ------- | --------------------------------------------------------------- | --------- | ---- | ---- | ------ | ------- | ---------------------------------------------- |
| DO-T-30 | 同時実行スレッド数の上限                                        | DO-NFR-01 | ⬜   | S    | 🤖     | DO-T-04 | 上限超の run はキューイング/拒否され暴走しない |
| DO-T-31 | worker コスト/トークン上限（`claude -p --max-budget-usd` 活用） | DO-NFR-04 | ⬜   | S    | 🤖     | DO-T-04 | run ごとに予算上限が効き、超過で停止           |
| DO-T-32 | No-progress 検知（同一失敗の連続・差分なしで停止）              | DO-NFR-04 | ⬜   | M    | 🤖     | DO-T-04 | 進捗のない run を早期に blocked 化             |

### M3 — 通知・連携強化

| ID      | 作業                                                           | 関連      | 状態 | 規模 | ループ | 依存    | 受け入れ                                 |
| ------- | -------------------------------------------------------------- | --------- | ---- | ---- | ------ | ------- | ---------------------------------------- |
| DO-T-40 | 音声通知の調停（streaming TTS/STT 録音中の保留・割り込み制御） | DO-NFR-06 | 🟡   | M    | 👤     | DO-T-07 | 配信中も通知が TTS/STT と衝突しない      |
| DO-T-41 | Issue 起票（`gh issue create`、承認ゲート付き）                | DO-FR-06  | ⬜   | S    | 👤     | DO-T-09 | 承認付きで Issue を作成できる            |
| DO-T-42 | `/dev open <task_id>/current`（task worktree を開く導線）      | DO-FR-09  | 🟡   | S    | 🤖     | DO-T-10 | task 指定で worktree を VS Code で開ける |

### M4 — 可視化・拡張

| ID      | 作業                                                      | 関連     | 状態 | 規模 | ループ | 依存    | 受け入れ                                                              |
| ------- | --------------------------------------------------------- | -------- | ---- | ---- | ------ | ------- | --------------------------------------------------------------------- |
| DO-T-50 | dev 専用 overlay state（active repo/task/PR/test status） | DO-FR-10 | ⬜   | M    | 🤖     | DO-T-06 | dev 状況が overlay に表示される（既存 caption 流用から専用 state へ） |
| DO-T-51 | dashboard 導線（kanban v1 spec 連携）                     | DO-FR-10 | ⬜   | L    | 🤖     | DO-T-50 | 開発状況を一覧できる                                                  |
| DO-T-52 | hermes worker レーン（サンドボックス前提）                | DO-FR-04 | ⬜   | L    | 👤     | DO-T-04 | Codex/Claude 以外に Hermes 自身がワーカーになれる                     |

### M5 — 運用整備

| ID      | 作業                                                                            | 関連 | 状態 | 規模 | ループ | 依存    | 受け入れ                          |
| ------- | ------------------------------------------------------------------------------- | ---- | ---- | ---- | ------ | ------- | --------------------------------- |
| DO-T-60 | 設定ドキュメント整備（`dev_orchestrator.*`/`stream_assistant.coding.*` の説明） | —    | ⬜   | S    | 🤖     | —       | 設定キーが文書化される            |
| DO-T-61 | repo registry の別ファイル化検討（`~/.hermes/repositories.yaml`）               | —    | ⬜   | M    | 🤖     | DO-T-01 | registry の保存先方針を確定・実装 |

---

## 4. 推奨実装順序（クリティカルパス）

1. **DO-T-20 → DO-T-22 → DO-T-21**（品質ゲート。「自己申告で done」のリスクを最優先で解消。`loop/` の Maker→Checker と同じ思想で 🤖 ループ化しやすい）
2. **DO-T-30 → DO-T-31 → DO-T-32**（ガードレール。暴走・課金事故の防止。小粒で並行可）
3. **DO-T-42 / DO-T-41 / DO-T-60 / DO-T-61**（連携・運用の小改善。ループ化しやすい）
4. **DO-T-40**（通知調停。配信実機での検証が要る 👤）
5. **DO-T-50 → DO-T-51**（可視化）
6. **DO-T-52**（hermes worker レーン。サンドボックス設計が前提の大物）

---

## 5. ループ運用メモ

- 本機能は **`loop/` ハーネスと思想が一致**（Maker→Checker、worktree 隔離、承認ゲート）。DO-T-20/21 はまさに `loop/verify.sh`＋Checker の考え方を dev worker に内蔵する作業。
- 🤖 タスク（DO-T-20/21/22/30/31/32/42/50/51/60/61）は `loop/tasks/*.md` 化し `TEST_SCOPE=tests/hermes_cli/` で `loop/loop.sh` に通せる。
- 👤 タスク（DO-T-40 通知調停・DO-T-41 Issue 起票・DO-T-52 hermes worker）は `gh`/実機/サンドボックスが要るため人手＋実機検証中心。
