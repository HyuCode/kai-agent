# Loop Engineering 調査・分析＋導入レポート — hermes-agent を `claude -p` で開発する

- 作成日: 2026-06-16
- 目的: Claude を使った **Loop Engineering** を調査し、**このローカル hermes-agent リポジトリの開発（機能開発・バグ修正）を `claude -p`（Claude Code ヘッドレス）で半自律に回す仕組み** を設計・導入する。
- 成果物（本レポートと併せて作成）: `loop/` ハーネス一式、`CLAUDE.md`、`.claude/settings.json`。

> 注: 本レポートは「Hermes という製品に Loop 機能を足す」話ではなく、**「Hermes の開発作業そのものを Loop Engineering で進める」** 開発方法論の話。

---

## 0. エグゼクティブサマリー

- **Loop Engineering とは**、人間が 1 プロンプトずつ手動で AI を操作するのをやめ、**エージェントが自律的にループを回す「仕組み」を設計する**こと。Claude Code を作った Boris Cherny の「My job is to write loops」が発端で、Addy Osmani が体系化。2026 年半ばには Claude Code が `/loop` を同梱。
- 本リポジトリ開発への適用として、**`claude -p` を使った Maker→Checker ループ**を構築した:
  `Maker(claude -p で実装)` → `決定論的ゲート(loop/verify.sh)` → `Checker(別 claude -p で独立検証)` → FAIL ならフィードバックを返して最大 N 回反復。
- このハーネスは Loop Engineering の必須要素を満たす: **アンカーファイル**（CLAUDE.md/VISION.md）、**ディスク状態**（STATE.md）、**Maker–Checker 分離**（自己採点＝Verifier Theater 防止）、**ガードレール**（最大試行回数・`--max-budget-usd`・No-progress 停止）、**限定権限**（acceptEdits ＋ deny で push/秘密/破壊コマンド禁止）。
- 検証ゲートは本リポジトリの CI ブロッキング項目に一致させた: **import smoke / ruff(PLW1514) / windows footguns / `scripts/run_tests.sh`**。fast チェックの実動作も確認済み。

---

## 1. Loop Engineering とは何か

> 「Loop engineering とは、エージェントにプロンプトを入力する人間（=あなた）を置き換えること。代わりにそれを行うシステムをあなたが設計するのだ。」— Addy Osmani

- 従来は「人間がプロンプト → 返答を読む → また書く」。Loop Engineering では **エージェントが自分にプロンプトを与え、作業を発見し、完了するまで反復する**仕組みを人間が組む。
- レバレッジが **「何を聞くか」から「聞く仕組みをどう設計・検証・停止・予算管理するか」** へ移る。役割は「タイピスト → プロンプト操作者 → ループエンジニア」へと**高度が上がる**が、**判断・検証の責任は人間に残る**。

---

## 2. ループの解剖学（構成要素）

### 2.1 Anthropic 公式のエージェントループ（最小モデル）

1. プロンプト＋システムプロンプト＋ツール定義＋履歴を受信 → 2. 評価して text or ツール呼び出し → 3. ツール実行・結果回収（hooks で介入可） → 4. ツール呼び出しが無くなるまで反復（1 周=1 ターン） → 5. 結果（コスト・トークン・session_id）。
   制御: `max_turns` / `max_budget_usd` で上限、Compaction で文脈肥大を抑制、永続ルールは **CLAUDE.md**（毎リクエスト再注入）に置く、Subagent で文脈分離、Hooks で任意点に割り込み。

### 2.2 Addy Osmani の「良いループの 5+1 構成」と、本ハーネスでの実体

| 構成要素      | 役割             | 本リポジトリでの実体                                                  |
| ------------- | ---------------- | --------------------------------------------------------------------- |
| Automations   | 自律実行の鼓動   | `loop/loop.sh`（手動起動）。将来は cron/GitHub Actions 化可           |
| Worktrees     | 並行の安全性     | `git switch -c` でブランチ分離（必要なら `claude -w` worktree）       |
| Skills        | 意図の永続化     | `CLAUDE.md` + `AGENTS.md`/`CONTRIBUTING.md`（規約）, `loop/prompts/*` |
| Connectors    | 環境統合         | （現状なし。将来 GitHub Issue/PR 連携）                               |
| Sub-agents    | 関心の分離       | **Maker と Checker を別 `claude -p` プロセスに分離**                  |
| +State/Memory | ディスク上の背骨 | `loop/STATE.md`（ループ間で持続する作業メモリ）                       |

### 2.3 「ループ契約（Loop Contract）」— 本ハーネスでの対応

| 要素    | 本ハーネス                                                     |
| ------- | -------------------------------------------------------------- |
| TRIGGER | 手動 `loop/loop.sh <task>`（将来: cron/PR コメント）           |
| SCOPE   | タスクファイル `loop/tasks/*.md` ＋ `TEST_SCOPE:`              |
| ACTION  | Maker プロンプト（最小の正しい実装）                           |
| BUDGET  | `MAX_ATTEMPTS`, `MAKER/CHECKER_BUDGET_USD`, `--max-budget-usd` |
| STOP    | Checker PASS ＋ ゲート green / No-progress / MAX_ATTEMPTS      |

### 2.4 アンカーファイル

毎反復で読む安定した記憶: `CLAUDE.md`（運用ルール・検証コマンド）, `loop/VISION.md`（Done と制約）, `loop/prompts/*`（プロンプト）, テスト（検証層）。進捗は会話文脈ではなく **git／`STATE.md`** に置く（Ralph パターン）。

---

## 3. 実装パターン（自律度・低→高）と本ハーネスの位置づけ

1. `bash while + claude -p`（Ralph パターン最小形）← `loop/README.md` に単一ループ例を同梱
2. `/loop`（セッション内・定期）
3. `/schedule`（クラウド cron で永続）
4. **Maker–Checker（実装者と検証者を分離）← 本ハーネスが採用**
5. Agent SDK（hooks でゲート・監査）
6. GitHub Actions（CI 常駐）

推奨される進め方: まず低リスクで回し、検証手段が整ってから自律度を上げる。本ハーネスは 4 を中核に、1 を簡易版として、将来 3/6 へ拡張できる構成。

---

## 4. ガードレール — 検証・停止・コスト

Loop Engineering の半分は設計、もう半分はガードレール。「フィードバックの無いループは、エージェントが延々と自分に同意し続けるだけ」。

- **検証**: テスト・型・lint が「No と言う存在」。**Maker の自己採点を禁止**し、別プロセスの Checker ＋ 決定論的 `verify.sh` が独立判定（Verifier Theater 対策）。
- **停止**: `MAX_ATTEMPTS`、`/goal` 的な「green になるまで」＝ Checker PASS、**No-progress 検知**（Maker が差分を出さない／ゲートが同一失敗を 2 連続）。
- **コスト**: `--max-budget-usd`（Maker/Checker 個別）＋ 試行回数上限。実測目安（2026/6）: 読むだけ < $0.01／修正＋検証 1 サイクル ≈ $0.7。
- **失敗モード**（Addy Osmani）: 理解の負債（読まない速いコードの出荷）、思考放棄、無人ミス。**だから push/PR は人間が手動**にしている。

---

## 5. 本リポジトリの検証基盤（ゲートの根拠）

`loop/verify.sh` は CI のブロッキング項目に一致させてある（exact コマンド）:

| 段階                             | コマンド                                                                                                    | 由来                          |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------- |
| import smoke                     | `python -c "import cli, run_agent"`                                                                         | 構造破壊の最安検知            |
| lint（ブロッキング）             | `ruff check .`（無ければ `uv tool run ruff`）→ **PLW1514**: `open/read_text/write_text` に `encoding=` 必須 | `.github/workflows/lint.yml`  |
| windows footguns（ブロッキング） | `python scripts/check-windows-footguns.py --all`                                                            | `lint.yml`                    |
| tests（CI パリティ）             | `scripts/run_tests.sh [path]`（per-file 隔離・`TZ=UTC`・`-m 'not integration'`）                            | `.github/workflows/tests.yml` |

開発規約（`AGENTS.md`/`CONTRIBUTING.md`）の要点: Conventional Commits（`type(scope): …`）、ブランチ `type/scope-…`、1 PR=1 論理変更、クロスプラットフォーム必須、`pytest` を直接呼ばない。
**動作確認済み**: fast ゲート（import + ruff via uv + footguns）が `✅ ALL GREEN` を出すことを実機確認。

---

## 6. 導入した `claude -p` 開発ループ（成果物）

```text
Maker (claude -p) ─▶ 決定論的ゲート (loop/verify.sh) ─▶ Checker (claude -p)
     ▲                                                          │
     └──────────── FAIL 時フィードバック（最大 MAX_ATTEMPTS）─────┘
```

| ファイル                        | 役割                                                                                  |
| ------------------------------- | ------------------------------------------------------------------------------------- |
| `CLAUDE.md`                     | Claude Code が自動ロードするアンカー（規約＋検証コマンド＋ループ運用）                |
| `.claude/settings.json`         | 権限。allow=テスト/lint/git、deny=`git push`・秘密読取・`rm -rf`/`sudo`/`curl`/`wget` |
| `loop/verify.sh`                | 決定論的ゲート（上表）                                                                |
| `loop/loop.sh`                  | Maker→Checker オーケストレーション（No-progress 停止・予算上限内蔵）                  |
| `loop/prompts/maker.md`         | 実装プロンプト（スコープ厳守・自己検証・STATE 更新・Conventional Commit）             |
| `loop/prompts/checker.md`       | 独立検証プロンプト（実装禁止・差分とゲートを再検証・PASS/FAIL 出力）                  |
| `loop/VISION.md`                | 全タスク共通の Done と制約                                                            |
| `loop/STATE.md`                 | ループ間で持続する作業メモリ                                                          |
| `loop/tasks/EXAMPLE-fix-bug.md` | タスク雛形（1 ファイル=1 タスク、`TEST_SCOPE:` 指定）                                 |

### 使い方

```bash
cp loop/tasks/EXAMPLE-fix-bug.md loop/tasks/my-task.md   # ゴール・受け入れ条件・TEST_SCOPE を記入
git switch -c fix/scope-short-desc                        # ループは push しない
loop/loop.sh loop/tasks/my-task.md                        # 回す
git diff main...HEAD                                      # 確認して手動で push/PR
```

調整は環境変数（`MAX_ATTEMPTS` / `LOOP_TEST_SCOPE` / `MAKER_BUDGET_USD` / `CHECKER_BUDGET_USD` / `MODEL` / `PERMISSION_MODE`）。詳細は `loop/README.md`。

---

## 7. 段階的ロードマップ

| フェーズ | 内容                                                                                                              | 状態                      |
| -------- | ----------------------------------------------------------------------------------------------------------------- | ------------------------- |
| **P0**   | アンカー＋決定論ゲート＋ Maker→Checker ＋ガードレール                                                             | ✅ 導入済み（本コミット） |
| P1       | 実タスクで試走し、プロンプト/`TEST_SCOPE`/予算を調整。`STATE.md` 運用を定着                                       | 次の一歩                  |
| P2       | worktree 並行（`claude -w`）で複数タスクを同時に回す                                                              |                           |
| P3       | `/schedule`（cron）で「読むだけ Daily Triage（CI 失敗/Issue を要約通知）」を 1 本。検証が固まったら自動修正へ昇格 |                           |
| P4       | GitHub Actions 化（PR コメント駆動、`--max-budget-usd` でコスト統制）                                             |                           |

最初の一歩は **小さく狭い `TEST_SCOPE` の実バグ修正タスクを 1 本** ループに通し、Maker/Checker プロンプトを実地調整すること。

---

## 参考リンク

- The New Stack — _Loop Engineering_: <https://thenewstack.io/loop-engineering/>
- Addy Osmani — _Loop Engineering_: <https://addyosmani.com/blog/loop-engineering/>
- Addy Osmani — _Self-Improving Coding Agents_: <https://addyosmani.com/blog/self-improving-agents/>
- explainx.ai — _Loop Engineering (2026 Guide)_: <https://explainx.ai/blog/loop-engineering-coding-agents-claude-code-guide-2026>
- Claude Code Docs — _How the agent loop works_: <https://code.claude.com/docs/en/agent-sdk/agent-loop>
- クラスメソッド — _Claude で実践する Loop Engineering_: <https://dev.classmethod.jp/articles/claude-loop-engineering-practice/>
- データサイエンスDOJO — _Agentic Loops: From ReAct to Loop Engineering (2026)_: <https://datasciencedojo.com/blog/agentic-loops-explained-from-react-to-loop-engineering-2026-guide/>
