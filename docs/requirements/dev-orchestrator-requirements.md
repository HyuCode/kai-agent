# 要件定義書 — 開発オーケストレーター（システム開発実装の代行）

| 項目             | 内容                                                                                                                                                                               |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 文書名           | 開発オーケストレーター 要件定義書                                                                                                                                                  |
| バージョン       | 1.0                                                                                                                                                                                |
| 作成日           | 2026-06-16                                                                                                                                                                         |
| ステータス       | ドラフト（To-Be 網羅＋実装状況明示）                                                                                                                                               |
| 関連文書         | `docs/design/dev-orchestrator-design.md`（基本設計書）, `docs/plans/2026-06-07-dev-orchestrator.md`, `docs/requirements/streaming-assistant-requirements.md`（`live_coding` 連携） |
| 凡例（実装状況） | ✅ 実装済み / 🟡 部分実装 / ⬜ 計画のみ                                                                                                                                            |
| 凡例（優先度）   | P0 必須 / P1 重要 / P2 任意                                                                                                                                                        |

---

## 1. 目的・背景・ビジョン

Hermes を「**複数リポジトリにまたがる開発作業の受付・進行管理・実行委譲・報告を行う開発オーケストレーター**」にする。ユーザーが（テキストまたは音声で）開発タスクを指示すると、Hermes が対象リポジトリを解決し、タスクごとに**隔離された git worktree** を作成し、外部コーディングエージェント（**Codex CLI / Claude Code**）に one-shot で実装を委譲し、結果（diff・テスト・ログ）を **Kanban DB** に記録し、必要に応じて **GitHub PR** を作成し、進捗・完了・blocked を**音声（TTS）と overlay** で報告する。

設計の核心は、**永続状態の正本（canonical source）を memory ではなく Kanban DB に置く**こと、外部公開アクション（push/PR/Issue 起票）は**承認ゲート**を通すこと、コーディング配信（`live_coding`）と統合して「開発作業そのものを配信コンテンツにできる」ことである。

## 2. スコープ

### 2.1 対象（In Scope）

- リポジトリ登録・管理（repo registry）。
- 開発タスクの投入・追跡（Kanban DB）。
- worktree 隔離下での Codex / Claude Code への実装委譲（バックグラウンド実行）。
- GitHub Issue 連携（list/view、Issue→タスク化）と PR 作成・採用。
- 完了/blocked の音声・overlay 通知。
- TUI slash command（`/dev ...`）と音声/エージェントツール（`dev_*`）からの操作。

### 2.2 対象外（Out of Scope）

- Hermes 自身をワーカーとして実装させる「hermes worker レーン」（現状未実装・将来検討）。
- GitHub Issue の起票（create）（現状未実装・将来検討）。
- コスト/トークン上限の厳密制御（現状なし・将来検討）。
- 開発オーケストレーター専用の dashboard UI（Phase 7、将来）。

## 3. 想定ユーザー・利用シーン

| 区分       | 説明                                                                                                          |
| ---------- | ------------------------------------------------------------------------------------------------------------- |
| 主ユーザー | 本人（seiichi3141）。通常開発時、またはコーディング配信中に Hermes に開発を任せる。                           |
| 入力経路   | TUI の slash command（`/dev ...`）、音声（Deepgram STT → agent turn → `dev_*` ツール）。中心は **TUI/音声**。 |

**典型フロー**: 「kai のこのバグ直して」 → `/dev assign`（Kanban タスク化） → `/dev run`（worktree 隔離＋Codex/Claude が実装、バックグラウンド） → 完了/blocked を TTS 報告 → `/dev pr <task_id> --confirm`（push＋PR 作成）。
**音声問い合わせ例**: 「kai の作業状況を教えて」「PR 作成は終わった？」（→ `dev_status` 相当を読み上げ）。

## 4. 用語定義

| 用語               | 定義                                                                                                                  |
| ------------------ | --------------------------------------------------------------------------------------------------------------------- |
| repo registry      | 対象リポジトリの登録情報（repo_id → local_path/github/default_branch/worktree_root/worker）。                         |
| worktree 隔離      | タスクごとに `dev/<task_id>` ブランチと専用ディレクトリを `git worktree add` し、共有チェックアウトを汚さない仕組み。 |
| worker（delegate） | 実装を行う外部 CLI エージェント（Codex CLI / Claude Code）。one-shot で起動。                                         |
| Kanban DB          | タスクの正本ストア（`hermes_cli.kanban_db`）。dev タスクは `kind=dev_task` ＋ `dev-task-meta` JSON を持つ。           |
| 承認ゲート         | push/PR 作成/Issue 起票など外部公開アクションを実行前に承認させる仕組み（`--confirm`、`require_approval_for_*`）。    |

## 5. 機能要件（FR）

| ID       | 要件                                                                                                                                                                                                                                        | 優先 | 状態                                                                                  |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | ------------------------------------------------------------------------------------- |
| DO-FR-01 | リポジトリ登録/管理（`repositories` config、git remote から github/default branch 推定、`/dev repos`・`/dev repo show\|add\|remove`）                                                                                                       | P0   | ✅                                                                                    |
| DO-FR-02 | タスク投入（`/dev assign <repo_id> <task>`〔`--worker`/`--issue`〕、`/dev tasks`〔`--repo`/`--all`〕、`/dev status`、`dev_assign` ツール）                                                                                                  | P0   | ✅                                                                                    |
| DO-FR-03 | worktree 隔離（`dev/<task_id>` ブランチ＋専用ディレクトリ、再利用・再アタッチ対応、dirty checkout を汚さない）                                                                                                                              | P0   | ✅                                                                                    |
| DO-FR-04 | コーディングワーカー委譲（Codex `codex exec`／Claude `claude -p [--model][--permission-mode acceptEdits][--allowedTools]`、`/dev run`〔既定 background、`--wait` 同期〕、worker prompt でシークレット/ push/PR/Issue 禁止・テスト実行指示） | P0   | ✅                                                                                    |
| DO-FR-05 | PR 作成・採用（done/review タスクで auto-commit〔commit 承認 off 時〕→push→`gh pr create`、`--confirm` 必須、既存 PR の冪等採用、`PR_BODY.md` or delegate 生成本文、`auto_create_pr` で自動化）                                             | P0   | ✅                                                                                    |
| DO-FR-06 | Issue 連携（`/dev issue <repo_id> [list\|<number>]`、`--issue <n>` で Issue→タスク化）                                                                                                                                                      | P1   | 🟡（view/list/Issue→task は実装。**Issue 起票 create は未実装**）                     |
| DO-FR-07 | タスク追跡（Kanban DB 正本、`claim`→`complete`/`block`、run メタ〔returncode/duration/change_summary/log_path〕保存、`/dev tasks` は done を `tasks_recent_hours` で非表示・blocked は残す、`/dev stop`・`dev_stop` ツール）                | P0   | ✅                                                                                    |
| DO-FR-08 | 完了通知（音声等）（Kanban イベントを cursor でポーリング、repo ごと cooldown＋max_chars 切詰めで TTS、overlay へ caption、`/voice on` で watcher 起動）                                                                                    | P1   | ✅                                                                                    |
| DO-FR-09 | VS Code で開く（`/dev open <repo_id>`、`code` CLI、macOS fallback `open -a`）                                                                                                                                                               | P2   | 🟡（repo_id は可。task_id/current は限定的）                                          |
| DO-FR-10 | 開発専用 overlay/dashboard state（active repo/task/PR/test status）                                                                                                                                                                         | P2   | ⬜（Phase 7、通知は既存 caption 流用）                                                |
| DO-FR-11 | テスト検証による done 判定（Hermes が diff/tests を確認してから done）                                                                                                                                                                      | P1   | 🟡（change summary 記録・worker への指示まで。**Hermes 側のテスト実行検証は未実装**） |
| DO-FR-12 | エージェントツール公開（`dev_status`/`dev_assign`/`dev_run`/`dev_stop` を LLM ツール化、音声 turn から呼べる）                                                                                                                              | P0   | ✅                                                                                    |

## 6. 非機能要件（NFR）

| ID        | 分類         | 要件                                                                                                                                                                                                                                                                                                        |
| --------- | ------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DO-NFR-01 | 並行性       | `/dev run` はタスクごとにデーモンスレッド（`start_dev_task`）でバックグラウンド実行。worktree が task_id ごとに隔離され複数 repo/タスクを並行可能（明示的な同時実行上限は無し）。                                                                                                                           |
| DO-NFR-02 | タイムアウト | dev worker `worker_timeout_seconds` 既定 **3600 秒（60分）**（最低10秒）。delegate 基盤 `stream_assistant.coding.timeout_seconds` 既定 900。`gh` 呼び出しは 60 秒。                                                                                                                                         |
| DO-NFR-03 | 安全性・隔離 | worktree 隔離で共有チェックアウトを汚さない。worker prompt がシークレット/.env/token 読込・push・PR/Issue 作成・（commit 承認時は）commit を禁止。外部公開アクションは承認ゲート（既定 push/PR/Issue create は承認必須、commit は auto 許可）。`/dev pr` は `--confirm` 必須。stop されたタスクは blocked。 |
| DO-NFR-04 | コスト       | 明示的なコスト/トークン上限は無し（将来課題）。出力は 4000 字、PR diff は上限で切詰め。                                                                                                                                                                                                                     |
| DO-NFR-05 | 対応モデル   | `stream_assistant.coding.claude_model`（既定 ""＝CLI デフォルト、alias fable/opus/sonnet 可）。Claude permission mode 既定 `acceptEdits`、`claude_allowed_tools`（headless でテスト実行を許可するルール、例 `Bash(uv run pytest:*)`）。                                                                     |
| DO-NFR-06 | 通知品質     | `max_chars` 既定120、`cooldown_seconds` 既定10、repo ごと cooldown、バッチ内は repo ごと最新のみ・cooldown 中は drop、overlay ttl 8s。TTS 再生中は classic voice の `_tts_playing` を待機（streaming TTS/STT 録音中の調停は未対応）。                                                                       |
| DO-NFR-07 | 可用性       | worker 失敗/timeout/stop は `block_task` で記録し、配信・TUI を落とさない。`gh` 認証エラーは出力をそのまま提示。                                                                                                                                                                                            |

## 7. 制約・前提

- 永続状態の正本は **Kanban DB**（memory ではない）。
- ワーカーは **Codex CLI / Claude Code** の delegate のみ（hermes worker レーンは未実装、明示エラー）。
- 外部公開アクション（push/PR/Issue 起票）は承認制を既定とする。
- `gh` CLI（GitHub 認証済み）が PR/Issue 操作の前提。
- repo registry は現状 `config.yaml`（config デフォルト経由）に保持（別ファイル化は未決）。
- `live_coding` の delegate 基盤（`hermes_cli/live_coding.py`）を dev worker と共用する。

## 8. 外部依存・インターフェース

| 依存                                                               | 用途                                              |
| ------------------------------------------------------------------ | ------------------------------------------------- |
| Claude Code CLI（`claude -p` headless）/ Codex CLI（`codex exec`） | コーディングワーカー。`shutil.which` で存在確認。 |
| git（`worktree`/`status`/`diff`/`rev-list`/`commit`/`push`）       | ローカル操作・worktree 隔離。                     |
| GitHub `gh` CLI（`issue list/view`, `pr create`、`-R owner/repo`） | Issue/PR 操作。`_require_gh` で前提確認。         |
| Kanban DB（`hermes_cli.kanban_db`）                                | タスク永続化（正本）。                            |
| Voice/Overlay（Deepgram STT、TTS、`live_overlay.publish_caption`） | 通知・問い合わせ応答。                            |
| VS Code（`code` CLI / macOS `open -a`）                            | リポジトリを開く。                                |

## 9. リスク・未解決事項

### 9.1 未解決事項（計画書）

- repo registry を `config.yaml` か別ファイル（`~/.hermes/repositories.yaml`）か（現状 config）。
- worker を Hermes 主体か Codex/Claude lane 主体か（現状 delegate のみ）。
- commit 自動許可の是非（push/PR は承認制で確定）。
- voice notification を TUI gateway 内か Kanban dispatcher 側か（現状 dev_notify＋TUI gateway 起動）。
- GitHub 連携を `gh`/REST/connector のどれを primary に（現状 `gh`）。

### 9.2 主要リスク

- **品質ゲート不足**: worker の自己申告（exit code）で done 判定しており、計画方針「Codex 自己申告だけで done にしない／Hermes が diff/tests を確認」を完全には満たさない（DO-FR-11 未達）。
- **音声通知の調停不足**: streaming TTS worker との調停・STT 録音中の保留が未対応（割り込み制御が classic voice 前提）。
- **コスト無制限**: 同時実行数・トークン上限の制御なし → 暴走・課金リスク。
- worker の過剰権限による意図しない変更（`acceptEdits` ＋ worktree 隔離で緩和するが、長時間実行は配信テンポを崩す）。

## 10. 受け入れ基準（主要シナリオ）

| ID       | シナリオ                                          | 合格条件                                                                                                                       |
| -------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| DO-AC-01 | `/dev repo add` で repo 登録 → `/dev repos`       | github/default_branch が git remote から推定され一覧表示（DO-FR-01）                                                           |
| DO-AC-02 | `/dev assign <repo> "..."` → `/dev run <task_id>` | `dev/<task_id>` worktree が作られ、worker が実装、成功で done・失敗で blocked、ログ/exit が Kanban に保存（DO-FR-03/04/07）    |
| DO-AC-03 | 2 リポジトリ・2 タスクを並行 run                  | worktree 隔離で互いに干渉せず両方完了（DO-NFR-01）                                                                             |
| DO-AC-04 | `/dev pr <task_id>`（`--confirm` なし→あり）      | `--confirm` なしはプレビューのみ、ありで push＋`gh pr create`、既存 PR は冪等採用、URL を metadata 保存（DO-FR-05、DO-NFR-03） |
| DO-AC-05 | run 完了 → `/voice on` 中                         | TTS で完了/blocked を cooldown・max_chars 内で読み上げ、overlay に caption（DO-FR-08、DO-NFR-06）                              |
| DO-AC-06 | worker が `.env`/secret を読もうとする            | worker prompt が禁止、出力サニタイズで漏洩しない（DO-NFR-03）                                                                  |

## 11. ロードマップ（残課題）

Phase 1–6 の中核（registry／タスク投入／worktree 隔離／Codex・Claude delegate ワーカー／PR 作成・採用／音声通知）は実装済み。残課題を以下の順で実装する。

| フェーズ | 内容                                                                                            | 関連 FR/NFR  |
| -------- | ----------------------------------------------------------------------------------------------- | ------------ |
| D-A      | **品質ゲート**: Hermes 側でテスト/diff を検証してから done 判定（自己申告のみで done にしない） | DO-FR-11     |
| D-B      | **ガードレール**: 同時実行数上限・コスト/トークン上限・No-progress 検知                         | DO-NFR-01/04 |
| D-C      | 音声通知の調停（streaming TTS/STT 録音中の保留・割り込み制御）                                  | DO-NFR-06    |
| D-D      | Issue 起票（create）、`/dev open <task_id>/current` 強化                                        | DO-FR-06/09  |
| D-E      | Phase 7 開発専用 overlay/dashboard、hermes worker レーン                                        | DO-FR-10     |
| D-F      | 運用整備（`.env.example`/設定ドキュメント、repo registry の別ファイル化検討）                   | —            |
