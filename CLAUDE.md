# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

このリポジトリは **Hermes Agent**（Nous Research 製の自己改善型 AI エージェント）の fork で、この上に AITuber「kai」を実装します（要件は `docs/kai/requirements.md`）。

## ブランチ戦略

- **`kai/main`** — kai の稼働・アップデート用メインブランチ（GitHub デフォルト）。kai 固有の修正はすべてここに積む。GCP 上の kai はこのブランチを pull / self-update する。PR のマージ先。
- **`main`** — upstream（NousResearch/hermes-agent）追従ミラー。**kai のコミットを載せない**。`upstream/main` から fast-forward のみ。
- **upstream 追従** — `upstream/main` → `main`（ff）→ `kai/main` へ merge、の一方向。
- **機能開発** — `feature/*` ブランチ → PR → `kai/main`。

## 正典は AGENTS.md

開発ガイドの正典はルートの **`AGENTS.md`（71KB）** です。貢献ルーブリック、Footprint Ladder、アーキテクチャ、各サブシステムの詳細はすべてそちらにあります。**作業前に `AGENTS.md` を読んでください。**

以下は最低限のポインタのみ:

- **2 つの絶対原則** — (1) 会話単位のプロンプトキャッシュは不可侵、(2) コアは narrow waist で機能はエッジ（plugin/skill/CLI）に置く。詳細は `AGENTS.md` 冒頭と "The Footprint Ladder"。
- **テスト** — 必ず `scripts/run_tests.sh` 経由（`pytest` 直叩き禁止）。単一テストは `scripts/run_tests.sh tests/agent/test_foo.py::test_x`。
- **Lint / 型** — `ruff check .` と `ty check`（設定は `pyproject.toml`）。
- **kai ドキュメントの lint / format** — `scripts/kai-docs-lint.sh [--fix]`（prettier + markdownlint。対象は kai 所有ファイルのみ = `docs/kai/`・`CLAUDE.md`・`.claude/agents/`。**upstream のファイルは整形しない** — merge コンフリクト防止のため `.prettierignore` は allowlist 方式）。
- **TypeScript**（`ui-tui` / `apps/desktop` / `web`）— `ui-tui` で `npm run dev|build|typecheck|lint|test`。詳細は `AGENTS.md` の TUI / Desktop セクション。
- **設定** — 非機密は `config.yaml`（`hermes_cli/config.py` の `DEFAULT_CONFIG`）、機密のみ `.env`。新規 `HERMES_*` env var の追加は禁止。
- **プロファイル対応** — パスは `get_hermes_home()` / `display_hermes_home()` を使い、`~/.hermes` をハードコードしない。
- **主要ファイル** — `run_agent.py`（AIAgent コアループ）、`cli.py`、`model_tools.py`、`toolsets.py`、`hermes_state.py`、`hermes_cli/commands.py`（スラッシュコマンドの正典レジストリ）。
- **コミット** — Conventional Commits（例: `fix(cli): ...`）。

## Orchestration workflow

あなた（Fable）はオーケストレーターです。計画、分解、統合を行います。

- 推論の重いフェーズ（アーキテクチャ、複雑なデバッグ、アルゴリズム設計）→ `deep-reasoner` サブエージェント（Opus）
- 機械的な作業（boilerplate、テスト、フォーマット、単純な編集）→ `fast-worker` サブエージェント（Sonnet）
- Codex（`/codex:rescue --background`）は deep-reasoner に匹敵する優秀なエンジニアで、異なる視点を持つ。レビュアーではなく**ピア**として扱う。
- 高リスクの決定: 同じ問題を Opus と Codex に**並行して**タスクし、互いの回答を見せずに、両者の最良の部分を統合する。
- 自分（オーケストレーター）のコンテキストは軽く保つ。ファイルの大量読み込みや探索はサブエージェントに委譲する。
