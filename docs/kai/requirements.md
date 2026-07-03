# kai 要件定義書

- **ステータス:** ドラフト（v0.2）
- **作成日:** 2026-07-03
- **更新日:** 2026-07-03（オーナーとの方針確認を反映）
- **対象:** hermes-agent（`github.com/NousResearch/hermes-agent` fork）をベースに再実装する AITuber「kai」
- **参照:** プロトタイプ実装 `/Volumes/ExSSD/apps/seiichi3141/kai`（TypeScript/pnpm モノレポ、約24パッケージ）

---

## 1. 概要と背景

### 1.1 kai とは

kai は、**YouTube でライブ配信をしながらライブコーディングを行う AITuber エージェント**である。GitHub の Issue / PR を起点に、自身のソースコードやオーナー（せいさん）が提供するサービスのコードを、実装・検証・レビュー対応・PR 作成まで継続して開発し、その進行を配信コンテンツとして可視化する。

コアバリューは **「開発作業（GitHub 上の実体）」と「視聴体験（配信・字幕・音声・チャット応答）」を同一の運用ループに載せること**にある。最終的には、オーナーの介入なしに「課題発見 → 要件化 → 実装 → 評価 → 改善」を自走する**自律開発**への到達を目指す。

### 1.2 本プロジェクトの位置づけ

これまで独自に TypeScript で実装してきたプロトタイプ（成熟した設計を持つが macOS 依存が強い）を**参考**としつつ、**hermes-agent（Python 製の自己改善型エージェント基盤）を新たなベース**として kai を再実装する。hermes-agent は「同一エージェントコアを CLI / メッセージング Gateway / TUI / Electron で共有する」構成を持ち、LLM プロバイダ抽象・cron・delegation・memory・TTS/STT・computer_use（GUI 操作）・browser 自動化など、kai に必要な基盤機能の多くを既に備えている。

### 1.3 実行環境

- **常駐先:** GCP 上の Linux（Ubuntu）インスタンス。24 時間稼働を前提とする。
- **利用可能な LLM:**
  - OpenAI（Codex）
  - Claude（Claude Code）
  - ローカル LLM（Windows 上に構築、OpenAI 互換エンドポイント）
- **配信で実演する活動:** コーディング、ブラウジング、Figma 操作、OBS 操作、X（Twitter）運用、技術トピックのプレゼンなど、Linux 上のさまざまな操作。
- **アイドル時の活動:** 作業候補がない時間帯は、ゲーム・ネット閲覧・リスナーとの雑談など、視聴者と遊ぶコンテンツを行い、配信の間を持たせる。

### 1.4 配信スタイル（確定方針）

オーナーとの確認により、以下を確定方針とする。

- **配信画面:** 基本的に **Linux（Ubuntu）のデスクトップそのもの**を配信する。kai が実際にデスクトップ上でアプリを操作する様子を見せる。
- **アバター:** **2D の PNG アニメーション**をデスクトップ画面上にオーバーレイする（3D は不採用）。アバター素材は **Codex の画像生成（imagegen）機能**で制作する。
- **アバター＝カーソルの理想像:** アバターは、Linux デスクトップ上を**自由に動くマウスカーソルの代わり**として振る舞えるのがベスト。kai がクリック・操作する対象へアバター自身が移動し、操作主体を視覚的に体現する（＝「カーソルの位置＝kai の居場所」）。
- **音声:** **AquesTalk** でキャラクター音声を開始する。
- **LLM 連携:** Claude は **Anthropic API 利用**（`CLAUDE_CODE_OAUTH_TOKEN` 再利用）で足りる。CLI プロセス駆動の新規 transport は不要。

---

## 2. スコープ

### 2.1 対象（In Scope）

- hermes-agent fork 上での kai エージェント本体の構築
- GitHub Issue / PR 駆動の自律開発ループ
- YouTube ライブ配信・ライブチャット連携
- 音声（TTS）・字幕・アバター等の配信演出
- X 運用、Discord 連携（オーナー通知・運用連絡）
- Linux（GCP Ubuntu）上での画面制御・配信スタック
- upstream hermes-agent の定期的な変更取り込み（fork 運用）

### 2.2 対象外・後回し（Out of Scope / Later）

- プロトタイプの macOS 固有実装（yabai / Syphon / afplay / AquesTalk Mac SDK）の移植（→ Linux 相当へ全面置換）
- 廃止済み経路の復活（VSCode 拡張によるコード表示、`packages/web` の `/overlay` route、mirror DB による GitHub 状態同期、worker 間の候補分割、dynamic leader election）
- 複数 AI によるペア開発構想（プロトタイプで既に破棄済み）

### 2.3 fork 運用の大原則（全設計に優先）

hermes-agent の開発ガイド（`AGENTS.md`）が定める2大原則を踏襲する。

1. **会話単位のプロンプトキャッシュは不可侵。** 会話途中で system prompt / toolset / 過去コンテキストを変更しない。
2. **コアは narrow waist、機能はエッジに置く。** kai 固有機能は Footprint Ladder の上位（低フットプリント）から選ぶ：① 既存拡張 → ② CLI コマンド + skill → ③ service-gated tool → ④ plugin → ⑤ MCP サーバ → ⑥ 新コアツール（最終手段）。

**追従コスト最小化のため、kai 固有コードは可能な限り `plugins/` / `skills/` / skin / 独立プロセス / `config.yaml` に閉じ込め、コアファイル（`run_agent.py`, `cli.py`, `gateway/run.py`, `hermes_cli/main.py`, `toolsets.py`, `model_tools.py`）の改変を極小化する。** これにより `git merge upstream/main` のコンフリクトをほぼゼロに保つ。

---

## 3. 用語定義（ユビキタス言語）

プロトタイプで確立された語彙を継承する。命名の「別名禁止」ルールを維持する。

| 用語 | 定義 |
| --- | --- |
| **Owner（オーナー）** | kai システムの所有者（せいさん）。視聴者（Viewer）とは明確に区別する。 |
| **Session（配信 / セッション）** | kai プロセスの1起動分。トレースの最小単位。 |
| **Main Loop（メインループ）** | 作業候補を収集・選択・実行する中核ループ。破壊的変更は最高リスク。 |
| **WorkItem（作業アイテム）** | 1つの処理単位。Issue / conflict / ci_failure / review 等の種別を持つ union。種別＝優先度。 |
| **Narrator（ナレーター）** | Agent の思考・行動を視聴者向けの自然な日本語一人称セリフに変換する **LLM 人格レイヤー専用語**。配送・キュー・表示などの構造責務には使わない。 |
| **Beat** | 1発話 + その期間に表示する演出パーツ束。音声・字幕・演出を同一時間軸で同期する単位。 |
| **OverlayEvent** | 配信画面（overlay）へ送るリアルタイムイベントの union 型。 |
| **streamer / worker** | 配信機能を起動する実行主体（streamer）と、配信せず作業のみ行う実装主体（worker）。同一ループを共有し、起動配線でのみ差分を持つ。 |
| **ops-agent** | PR のレビュー・承認・マージ判断を担う独立主体。 |
| **短期記憶 / 意味記憶** | 状態・lock・スケジュールを扱う短期記憶と、embedding による知識・RAG を扱う意味記憶。混同しない。 |

> **人格の現行方針:** kai の人格は「多脚思考 AI」（攻殻機動隊タチコマにインスパイアされたオリジナルキャラクター、固有名詞は使わない）。一人称「ボク」、オーナーは「せいさん」、視聴者は「みんな」。プロトタイプ初期の「霊夢」路線は破棄済み。

---

## 4. アクターとロール

| アクター | 説明 |
| --- | --- |
| **kai（streamer）** | 配信を行い、視聴者と対話しながらライブコーディングする主役エージェント。 |
| **kai（worker）** | 配信せず、裏で Issue / PR 作業を並行処理する実装主体（hermes の delegation / 追加プロセスで実現）。 |
| **ops-agent** | PR レビュー・auto-merge・エスカレーションを担う独立プロセス。 |
| **Owner（せいさん）** | **要件定義と GitHub Issue の追加**、高リスク変更の承認、方針決定を行う。Discord 経由で kai と対話。 |
| **Viewer（視聴者）** | YouTube ライブチャットでコメント・要望・質問を送る。kai は応答し、要望を Issue 化する。 |

---

## 5. 機能要件

### 5.1 自律開発ループ（中核）

- **F-1: Issue 駆動実装。** 対象リポジトリ群（`config/repositories.json` 相当。kai 自身を含む）の open Issue を収集・優先順位付けし、最優先の1件をブランチ作成 → TDD 実装 → 検証 → commit → PR 作成まで実行する。
- **F-2: PR 作業。** conflict / CI failure / review 指摘 / merge 判断を WorkItem 化して処理する。**PR 作業は新規 Issue より優先**する。
- **F-3: 統一スケジューラ。** 全リポジトリから作業候補を収集・ソートし最優先を返す。排他は lock（Redis 相当。hermes では state ストア）で行い、worker 間で候補を分割しない。
- **F-4: 未完作業の分割。** max_turns 到達時は draft PR で救済せず、残作業を sub-issue として起票する。
- **F-5: ops-agent による PR ゲート。** open PR をポーリングしてレビュー、changes requested / approve を判定、green かつ approve で auto-merge。上限超過で人間へエスカレーション。kai は自動マージしない（ops-agent が担う）。

### 5.2 配信・演出・発話

- **F-6: ライブ配信管理。** YouTube ライブ配信の作成・開始・終了・メタデータ更新（hermes: YouTube Data API 連携を新規プラグイン/skill 化）。
- **F-7: ナレーション。** Agent の thought / tool_call / tool_result を、視聴者向けの自然な日本語実況セリフに変換する（kickoff / work / summary モード）。
- **F-8: 音声合成（TTS）。** 発話テキストを日本語音声（**AquesTalk** キャラクター音声）に合成し再生する。字幕・口パク用メタデータを生成する。Linux 上での AquesTalk 動作は要検証（§9.2）。
- **F-9: 字幕表示。** 配信画面下部に日本語字幕を1件表示（履歴なし）。コード・コマンド・識別子・GitHub キーワードは英語のまま表示する。TTS 無効時も字幕は発火する。
- **F-10: Beat 同期。** 音声・字幕・演出パーツを同一時間軸で同期する（`speech_started` で字幕表示、`speech_ended` で解放。残留防止の duration fallback）。
- **F-11: アバター・表情・リアクション。** **2D PNG アニメーション**のアバターをデスクトップ画面上にオーバーレイ表示し、発話・作業イベントに同期した表情（7種）と短いリアクションを見せる。アバター素材は Codex の画像生成で制作する。
- **F-11b: アバター＝カーソル追従。** アバターは Linux デスクトップ上を自由に移動し、**マウスカーソルの代わり**として振る舞う。kai が操作する対象（クリック位置・入力欄・ウィンドウ）へアバターが移動し、操作主体を視覚的に体現する。
- **F-12: 技術トピックのプレゼン。** 短い外部入力（X 投稿等）から台本 + スライドを生成して実演する（初期は human-in-the-loop）。
- **F-13: BGM。** 配信中の無音低減のため lo-fi / instrumental BGM を再生する。

### 5.3 視聴者インタラクション

- **F-14: ライブチャット読取・返信。** YouTube ライブチャットのコメントを読み取り、応答する。
- **F-15: 要望インテイク。** 視聴者・オーナーの要望を多ターン確認で具体化し、GitHub Issue（またはオーナーレビュー待ち proposal）に変換する。オーナーの低リスク要望は自動受入、その他はオーナーレビューを経る。
- **F-16: 意図分類。** チャットメッセージを閉じた intent（issue_request / status_question / research_question / casual_chat / unsafe / ignore 等）に分類する（ローカル LLM 活用）。
- **F-17: 視聴者プロファイル。** 視聴者を記憶する（訪問回数・関係・会話履歴・メモ）。
- **F-18: 公開リスナー向け Web。** 「今／過去／次に何を作るか」、質問・要望の扱いを公開する視聴者向け Web（運用者向け画面とは分離、秘匿情報をサニタイズ）。

### 5.4 外部発信・運用連絡

- **F-19: X 運用。** 配信開始 / 作業完了 / idle / リリース告知 / mention 返信を投稿する。人格・作業文脈・コスト制約を反映（固定テンプレートにしない）。
- **F-20: Discord 連携。** 作業ログ・日報・異常・配信開始終了をオーナーへ通知し、オーナーからの指示を受信・解釈する。
- **F-21: ニュース収集。** X のキュレーテッドリストからニュース差分を取得し、興味カテゴリを判定して意味記憶へ蓄積する（投稿はしない）。

### 5.5 自己観測・自己改善・保守

- **F-22: 実行トレース。** セッション / WorkItem / イベント / 発話 / 配信 / チャット / 視聴者 / BGM を永続化し、運用ダッシュボードで閲覧する。保存前に秘匿情報をマスクする。
- **F-23: 自己観測 MCP。** kai 自身の状態を read-only ツール群として公開する（秘匿情報・接続文字列は返さない）。
- **F-24: 合議制（multi-agent-deliberation）。** 診断・自己提案・新機能探索・リファクタ提案を、役割分離した合議体で行う。参加 Agent は副作用なしの意見提供者、**Issue 起票は kai（オーナー役）だけ**が行う。
- **F-25: 会話からの学習。** 実会話とオーナー訂正から、kai の人格・事実・口調・失敗知識を継続更新する（hermes の memory / skill 学習ループを活用）。
- **F-26: セキュリティスキャン。** リポジトリ群を定期スキャンし、秘密漏洩・危険な実行・脆弱依存を検出、Issue 化・通知・限定的な auto-fix を行う（既定は無効）。
- **F-27: self-update（upstream 追従）。** upstream hermes-agent の変更、および kai 自身のリリースを検知して取り込み、ローリング再起動する。

### 5.6 アイドル時のエンタメ

- **F-28: アイドル時の遊び。** 作業候補がない時間帯は、配信の間を持たせるため、視聴者と遊べるコンテンツを行う。具体例：
  - ゲーム（ブラウザゲーム・CLI ゲームなど）をプレイする。
  - ネット閲覧（技術記事・ニュース・話題のサイト）を実演する。
  - リスナーとの雑談・参加型のやり取りをする。
- **F-29: 遊びと作業の切替。** 新たな作業候補（Issue / PR）が発生したら、遊びを中断して自律開発ループへ戻る。遊びの範囲・安全境界（アクセスするサイト・実行するゲーム）は許可リストで制御する。

> **注:** アイドル時の「遊び」の具体的な範囲・実現手段は §9.2 の残る論点。

---

## 6. 非機能要件

### 6.1 セキュリティ

- 秘密情報（API キー・OAuth トークン・Webhook URL・`.env` 値・完全な endpoint URL）を、ログ・字幕・トレース・仕様書・Issue・PR・配信映像に**一切載せない**。多層のマスキング／サニタイズを行う。
- 外部入力（Issue 本文・PR コメント・チャット・レビュー・X mention）を信頼しない。LLM プロンプトでは文脈境界（見出し・コードフェンス・XML 風タグ）で囲み、prompt injection と SSRF / DNS リバインドを考慮する（untrusted 入力経路で `WebFetch` を禁止、`WebSearch` は許可、等）。
- **高リスク変更**（認証・権限、外部通信、シェルコマンド、依存追加、CI/CD、self-update、Agent system prompt、設定スキーマ、main loop、lock）は理由・影響範囲・検証結果を明記し、**オーナーの明示承認**を待つ。
- CLI 実行は配列引数で行い、`shell: true` や外部入力の文字列連結を禁止する（コマンドインジェクション対策）。

### 6.2 可用性・常駐

- optional feature（Discord / YouTube / X / OBS / TTS / narrator / 提案系）の失敗はメインループを止めず、warn ログ + 縮退で継続する。
- 長時間稼働を前提に、保守タスクは interval / cooldown / leader guard / rate limit を尊重する。
- プロセス障害はプロセスマネージャの自動再起動で回復する（leader は role で静的決定、dynamic election は使わない）。

### 6.3 品質

- TDD（Red → Green → Refactor）を必須とする。
- PR は小さく保つ（本体変更ファイル5以下・差分300行以下を目安、超過時は sub-issue 分割）。
- 外部連携・CLI・UI・DB・OBS・認証が絡む変更は、**runtime acceptance / smoke evidence**（実機検証の証跡）なしに完了扱いにしない。検証不能時は理由と follow-up Issue を明記する。
- コミットは Conventional Commits（本文は日本語）。`--no-verify` 等の検証バイパスを禁止する。
- 自己改善の LLM 経路は権限を最小化する（静的シグナル経路は `allowedTools: []`・軽量モデル、検証ループ経路は read-only ツール + パス allowlist + 外部ネットワーク禁止）。

### 6.4 運用性

- 起動モード・role・トレース・記憶・OBS・YouTube・Discord・X・LLM backend の設定は、`config.yaml`（非機密）と `.env`（機密のみ）で管理し、運用ドキュメントで説明する。
- worker / streamer / ops-agent の状態を、ログ・Discord・トレース・キュースナップショットから切り分けられるようにする。

---

## 7. アーキテクチャ方針（hermes-agent 上での実現）

### 7.1 全体構造

GitHub を唯一の作業ソース・オブ・トゥルースとし、状態ストアを共有状態、配信 UI を観測面とする**複数プロセス構成**を維持する。hermes-agent の `AIAgent` コアをエージェント実行エンジンとして用い、kai 固有機能を周辺に配置する。

### 7.2 コンポーネント配置戦略（Footprint Ladder 準拠）

| kai 機能 | hermes 上の配置 | コア改変 |
| --- | --- | --- |
| YouTube ライブチャット連携 | `plugins/platforms/youtube_live/`（プラットフォームアダプタ。`ADDING_A_PLATFORM.md` 準拠） | 無 |
| X 運用 | 既存 `skills/social-media/xurl/` を利用（必要なら拡張） | 無 |
| 定期タスク（X 投稿 / self-update / 日報） | cron ジョブ + skill | 無 |
| OBS 制御 / 配信起動・停止 | plugin tool または CLI コマンド + skill | 無 |
| デスクトップ配信 / RTMP / 画面キャプチャ | **独立プロセス（配信スタック）**。OBS で Linux デスクトップをキャプチャし RTMP 配信。kai が local terminal / skill から制御 | 無 |
| 2D PNG アバター（カーソル追従）・字幕オーバーレイ | 独立プロセス。OBS ブラウザソース等でデスクトップ映像に合成。カーソル位置と同期 | 無 |
| Figma 操作 | computer_use（GUI）または Figma REST を skill / MCP 化 | 無 |
| GUI / デスクトップ操作全般（クリック・入力・カーソル移動） | 既存 `tools/computer_use/`（cua-driver, Linux X11） | 無 |
| ブラウジング実演・アイドル時のネット/ゲーム | 既存 `tools/browser_tool.py`（headed / CDP アタッチ）または computer_use | 無 |
| LLM 切替（codex / claude / local） | 既存 provider profile を `config.yaml` で利用。kai 専用は `plugins/model-providers/kai/` | 無 |
| AquesTalk キャラクター音声 | plugin tool（`tools/tts_tool.py` 直改変は避ける。neutts / piper が前例）。Linux 版 AquesTalk が前提 | 避ける |
| 視聴者多人数記憶（要件化時） | standalone memory-provider plugin（in-tree 追加は方針上不可） | 無 |
| kai の人格・配信ブランディング | skin（YAML データ） | 無 |
| 並行作業（配信中に裏で Issue 対応） | 既存 delegation / Kanban | 無 |
| 思考・ツール実行の可視化画面 | 既存 TUI / dashboard を1配信ソースとして OBS に取り込む | 無 |

### 7.3 hermes-agent で流用できる既存機能

- **Gateway / platforms:** プラグイン経路でのプラットフォーム追加が正式サポートされており、YouTube ライブチャットをコア無改変で追加できる。
- **LLM プロバイダ抽象:** OpenAI Codex（`codex_responses` / `codex app-server`）、Claude（Anthropic API、`CLAUDE_CODE_OAUTH_TOKEN` 再利用可）、ローカル LLM（`custom` provider + OpenAI 互換 base_url）を**すべて設定で切替可能**。
- **Terminal backend:** GCP Ubuntu 常駐は `local` backend で設定変更なしに対応。
- **cron / delegation / Kanban / memory / session（FTS5）/ TTS・STT / computer_use / browser** が既存資産として利用可能。

### 7.4 Linux 移植で新規実装が必要な領域

プロトタイプの以下は macOS 依存が強く、Linux で全面再設計・新規実装する。

- **画面制御・配信スタック（最大の課題、Linux 新規実装）:**
  - **デスクトップ配信:** OBS で Linux（Ubuntu）デスクトップをキャプチャし、YouTube へ RTMP 配信する。プロトタイプの Electron + R3F + Syphon による 3D 合成は**不要**（2D PNG アバター採用のため、移植負荷が大きく下がる）。
  - **2D アバターオーバーレイ（カーソル追従）:** 2D PNG アニメーションのアバターと字幕を OBS のオーバーレイ（ブラウザソース等）としてデスクトップ映像に重ねる。アバターは**マウスカーソル位置に追従**して動く軽量オーバーレイを新規実装する（発話・表情・操作対象に同期）。実装方式（透過ウィンドウ / OBS ブラウザソース + カーソル座標フィード等）は設計時に決定。
  - **ウィンドウ操作:** `window-manager`（yabai / `open -b` / macOS バンドル ID）→ Linux の WM 操作（wmctrl / xdotool / gtk-launch / WM_CLASS）へ置換。kai がデスクトップ上でアプリを起動・配置・操作する。
  - **ヘッドレス対策:** GCP VM には実ディスプレイがないため、Xvfb / Xorg + 軽量 WM で仮想ディスプレイを用意する。
- **OBS 制御:** obs-websocket 連携は hermes に存在しないため新規（obs-websocket 自体はクロスプラットフォーム）。
- **RTMP / YouTube 配信:** ffmpeg / OBS を local terminal からシェルアウトする新規実装。
- **AquesTalk キャラクター音声:** hermes 標準 TTS プロバイダに AquesTalk はない。AquesTalk を plugin tool として実装する（`tools/tts_tool.py` 直改変は避け、neutts / piper を前例とする）。プロトタイプは AquesTalk10 の macOS Mac SDK 依存のため、**Linux 版 AquesTalk の入手・動作検証が前提**（§9.2）。

### 7.5 データストア

- プロトタイプは PostgreSQL（+ pgvector）中心（トレース・意味記憶・PR ジョブキュー）と Redis（短期記憶・lock・pub/sub）を用いる。
- hermes はセッションを SQLite（FTS5）で持つ。kai の実装では、**hermes の既存記憶・セッション機構をまず利用し**、視聴者多人数記憶・意味検索・実行トレースなど要件が固まった領域についてのみ、外部ストア（PostgreSQL + pgvector / Redis）を独立プロセス側で導入する。ストア選定は §9 の意思決定ポイントとする。

---

## 8. 外部依存・連携

| 外部 | 役割 | 境界・注意 |
| --- | --- | --- |
| **GitHub** | Issue / PR / Actions / Release のソース・オブ・トゥルース | `gh` / `git` CLI を正規境界に、配列引数で。GitHub App token または `gh auth`。mirror DB は持たない。 |
| **YouTube** | ライブチャット（読取 = API key / InnerTube、投稿 = OAuth）、配信管理（Data API v3）、指標（Analytics API v2） | チャットは外部入力。OAuth 失効・quota 管理に注意。 |
| **Discord** | オーナー通知・運用連絡（Webhook + Bot） | 秘匿情報を出さない。未設定は縮退。 |
| **X（Twitter）** | 告知・返信・mention・ニュース収集 | OAuth 1.0a。認証不足時は機能無効化。料金プラン管理。 |
| **OBS Studio** | 配信映像取込（WebSocket 制御） | ローカル運用前提。接続失敗で縮退。 |
| **Figma** | サムネイル生成 / デザイン操作 | GUI（computer_use）または REST / MCP。 |
| **LLM backend** | Claude / OpenAI Codex / ローカル LLM（OpenAI 互換） | prompt injection・秘匿情報混入を考慮。role ごとに backend 選択。 |
| **データストア** | PostgreSQL + pgvector（トレース・意味記憶）、Redis（短期記憶・lock） | 接続値は秘匿。導入範囲は §9 で決定。 |

---

## 9. 確定事項と残る論点

### 9.1 確定した方針（2026-07-03、オーナー確認済み）

- **Claude Code 連携:** Anthropic API 利用（`CLAUDE_CODE_OAUTH_TOKEN` 再利用）。CLI プロセス駆動の新規 transport は不要。
- **配信画面:** Linux（Ubuntu）デスクトップそのものを配信する。
- **アバター:** 2D PNG アニメーション（Codex imagegen で制作）。3D は不採用。**マウスカーソルの代わりとしてデスクトップ上を動く**のを理想とする。
- **キャラクター音声:** AquesTalk で開始する。
- **配信スタック:** OBS / RTMP / 画面キャプチャ / アバター・字幕オーバーレイは **hermes 外の独立コンポーネント**として設計し、kai は local terminal / skill から制御する。
- **役割分担:** **要件定義と Issue 追加はオーナーが行う。** kai は実装・PR・自己アップデートに集中する（視聴者要望の自動 Issue 化＝F-15、合議制での起票＝F-24 は当面の優先度が低い）。
- **当面のゴール:** GitHub Issue を自分で拾って自身のコードを開発し、アップデートする**自律開発**の成立（フェーズ 1）。加えて、アイドル時に視聴者と遊べること。

### 9.2 残る論点

1. **AquesTalk の Linux 動作** — プロトタイプは macOS Mac SDK 依存。Linux 版 AquesTalk の入手・動作可否を検証する。不可の場合の代替（他の日本語 TTS）も要検討。
2. **アバター＝カーソルの実現方式** — 2D アバターをカーソルに追従／置換する具体手段（透過ウィンドウ、OBS ブラウザソース + カーソル座標フィード、実カーソル自体の差し替え等）と、GUI 操作（computer_use）との座標連携。
3. **アイドル時の「遊び」の範囲** — どのゲーム・サイト・遊びを、どこまで自動で行うか。安全境界（許可リスト）の設計。
4. **視聴者記憶の規模** — hermes built-in memory（少人数向け）で開始するか、多人数視聴者向け外部 memory provider を用意するか。
5. **データストアの導入範囲・タイミング** — PostgreSQL + pgvector / Redis をどの機能からどの段階で導入するか。
6. **worker / ops-agent の実現手段** — hermes の delegation / Kanban / 追加プロセスのいずれで並行作業と PR ゲートを構成するか。

---

## 10. 段階的ロードマップ（案）

各段階の詳細要件は別途 spec 化する。**当面の優先フォーカス（オーナー指定）はフェーズ 1 の自律開発の成立まで。** 要件定義と Issue 追加はオーナーが行い、kai は「Issue を拾う → 実装 → PR → マージ → 自己アップデート」に集中する。

- **フェーズ 0: 基盤確立**
  - hermes fork の kai 化（skin による人格「多脚思考 AI」・ブランディング、`config.yaml` 整備、LLM 3 backend の設定確認：codex / Claude API / ローカル LLM）。
  - upstream 追従フロー（cron + skill による self-update）の確立。
- **フェーズ 1: 自律開発ループ（当面のゴール）**
  - GitHub Issue / PR 駆動の実装ループ（F-1〜F-5, F-27）を hermes 上で構築。まず**配信なしの worker モード**で成立させる。
  - kai がオーナーの追加した Issue を自分で拾い、実装・PR・ops-agent ゲート・マージ・自己アップデートまで回せる状態を目指す。
- **フェーズ 2: 配信基盤（Linux）**
  - Linux 画面制御スタック（Xvfb + WM + デスクトップキャプチャ + OBS 連携）、RTMP / YouTube 配信、2D PNG アバター（カーソル追従）・字幕オーバーレイ、AquesTalk 音声の新規実装（F-6, F-8〜F-11b）。
- **フェーズ 3: 発話・演出**
  - ナレーション・Beat 同期・表情・リアクション・BGM・プレゼン（F-7, F-10, F-12, F-13）。
- **フェーズ 4: 視聴者インタラクション & アイドル時の遊び**
  - YouTube ライブチャット連携、意図分類、視聴者プロファイル、アイドル時のゲーム・ネット・雑談（F-14, F-16〜F-18, F-28, F-29）。
- **フェーズ 5: 外部発信・自己改善**
  - X 運用、Discord、ニュース収集、合議制、会話学習、セキュリティスキャン、実行トレース（F-19〜F-26）。要望の自動 Issue 化（F-15）はこの段階以降で検討。
- **フェーズ 6: 自律開発の深化**
  - 課題発見・提案の自走度を高める。高リスク変更のオーナー承認は全フェーズで維持。

---

## 付録: プロトタイプから継承すべき設計判断

再実装においても以下を踏襲する（プロトタイプで確立済み）。

1. GitHub を唯一の作業ソース・オブ・トゥルースにする（自前 mirror DB を持たない）。
2. worker 間で候補を分割しない（全 worker が同じ候補集合を見て、lock で競合を防ぐ）。
3. dynamic leader election を使わない（leader は role で静的決定）。
4. role 差分を起動配線に閉じる（streamer / worker は同一ループを共有）。
5. 人格語彙（Narrator）と構造責務（配送・キュー・実行）の命名を分離する。
6. 短期記憶と意味記憶を混同しない。
7. Beat モデルで音声・字幕・演出を同一時間軸で同期する。
8. 字幕は下部1件のみ・履歴なし、技術トークンは英語のまま。
9. 廃止済み経路（VSCode 拡張、`/overlay` route、incomplete_pr 救済、mirror DB、worker 分割）を復活させない。
10. ユビキタス言語辞書を維持し、新概念導入時に必ず更新する。
