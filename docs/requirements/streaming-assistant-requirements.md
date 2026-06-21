# 要件定義書 — ライブ配信ゲーム実況 AI アシスタント

| 項目             | 内容                                                                                                                                                                                                                                                                                       |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 文書名           | ライブ配信ゲーム実況 AI アシスタント 要件定義書                                                                                                                                                                                                                                            |
| バージョン       | 1.0                                                                                                                                                                                                                                                                                        |
| 作成日           | 2026-06-16                                                                                                                                                                                                                                                                                 |
| ステータス       | ドラフト（To-Be 網羅＋実装状況明示）                                                                                                                                                                                                                                                       |
| 関連文書         | `docs/design/streaming-assistant-design.md`（基本設計書）, `docs/plans/2026-05-30-youtube-live-ai-assistant.md`, `docs/plans/2026-05-30-response-latency-optimization.md`, `docs/plans/2026-05-30-voice-conversation-test-script.md`, `docs/plans/2026-06-01-aquestalk-tts-integration.md` |
| 凡例（実装状況） | ✅ 実装済み / 🟡 部分実装 / ⬜ 計画のみ                                                                                                                                                                                                                                                    |
| 凡例（優先度）   | P0 必須 / P1 重要 / P2 任意                                                                                                                                                                                                                                                                |

---

## 1. 目的・背景・ビジョン

Hermes Agent をベースに、YouTube のゲーム実況ライブ配信で配信者と**音声で会話できる「共同司会者（cohost）」型 AI アシスタント**を実現する。配信者の発話を streaming STT で聞き取り、YouTube ライブチャットを読み、必要に応じて TTS で配信に乗る音声を返し、OBS の Browser Source オーバーレイに字幕・選別チャット・攻略パネル等を表示する。

本機能の本質的な狙いは、**アシスタントの音声と掛け合い自体を配信コンテンツにする**ことであり、そのために「自然な掛け合いを成立させる低レイテンシ」「ネタバレ回避・配信事故防止の安全性」を最優先する。配信モードは実況補助の `game` を中核とし、コーディング配信向けの `live_coding`（→ `docs/requirements/dev-orchestrator-requirements.md` と連携）も併せ持つ。

## 2. スコープ

### 2.1 対象（In Scope）

- 配信者の音声入力（streaming STT）と会話ターン終端判定。
- エージェント応答の音声化（TTS）と OBS オーバーレイ表示。
- YouTube ライブチャットの取得・選別・表示。
- ゲーム実況ペルソナ（短い相づち・補足・ネタバレ厳守）。
- 配信モード切替（`/stream game`）と低レイテンシ調整。
- `live_coding` モードとの連携点（詳細は開発オーケストレーター要件定義書）。

### 2.2 対象外（Out of Scope）

- YouTube ライブチャットへの自動投稿（初期版は読み取りのみ。将来検討）。
- OBS の高度な番組演出自動化（scene 切替の全自動制御は将来検討）。
- 配信プラットフォームの YouTube 以外への対応（Twitch 等は将来）。
- 開発タスク実行そのもの（開発オーケストレーター機能で扱う）。

## 3. 想定ユーザー・ペルソナ・利用シーン

| 区分                   | 説明                                                                                                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| 配信者（主ユーザー）   | YouTube でゲーム実況する個人配信者（一次ユーザーは作者 seiichi3141）。マイクで Hermes と掛け合う。                                              |
| 視聴者                 | ライブチャットで質問・指摘・雑談を投稿。選別されたものだけがオーバーレイに表示され、アシスタントが音声反応。Super Chat/メンバーは優先扱い候補。 |
| アシスタント・ペルソナ | 既定 `calm_strategy_cohost`（落ち着いた戦略系共同司会）。短い相づち・ツッコミ・補足を優先し、無理に喋り続けない。                               |

**利用シーン例**: (a) ゲーム実況中に攻略ヒント・雑談・チャット選別を音声で補助。(b) コーディング配信で作業説明・委譲（`live_coding`）。

## 4. 用語定義

| 用語                                  | 定義                                                                                       |
| ------------------------------------- | ------------------------------------------------------------------------------------------ |
| STT                                   | Speech-to-Text（音声認識）。本機能では Deepgram streaming を主に使用。                     |
| partial / final transcript            | STT の暫定結果 / 確定結果。                                                                |
| 会話ターン終端判定（turn detection）  | 配信者の発話が一区切りしたかを判定し、エージェントへ submit すべきタイミングを決める処理。 |
| barge-in                              | アシスタントの発話中に配信者が話し始めたら、TTS 再生・生成を中断すること。                 |
| 投機的生成（speculative）             | final 確定前に裏で LLM を先行実行し、確定後に採用/破棄する最適化。                         |
| overlay                               | OBS の Browser Source に読み込ませるローカル HTTP オーバーレイ（字幕・パネル等）。         |
| barge-in / commit / cancel / rebuffer | ターン pipeline の状態遷移（提出前バッファの確定・取消・再バッファ）。                     |

## 5. 機能要件（FR）

優先度は配信成立に必要な度合い。状態は 2026-06-16 時点のコード実態に基づく。

### 5.1 音声入力（STT）

| ID       | 要件                                                                                                                              | 優先 | 状態                             |
| -------- | --------------------------------------------------------------------------------------------------------------------------------- | ---- | -------------------------------- |
| SA-FR-01 | Deepgram streaming STT でマイク音声を継続取得し、partial/final transcript を生成する                                              | P0   | ✅                               |
| SA-FR-02 | `always_on`（`/voice on`〜`/voice off` 常時ストリーミング）と push-to-talk の両方式に対応                                         | P0   | ✅                               |
| SA-FR-03 | final を即送信せず短時間バッファし、会話ターン終端（debounce / min_chars / max_wait / speech_final / partial 活動）で submit する | P0   | ✅                               |
| SA-FR-04 | ローカル LLM の turn classifier（`submit/wait/ignore/backchannel` を JSON 返却、hybrid 判定）を任意で利用                         | P1   | 🟡（config あり・既定 disabled） |
| SA-FR-05 | 既存 faster-whisper（`transcribe_audio(path)`）を非ライブ用途の fallback として温存                                               | P2   | ✅                               |
| SA-FR-06 | 投機的 hidden draft 生成（確定前に裏で LLM 実行 → commit/reveal、または cancel/discard）                                          | P1   | ⬜                               |

### 5.2 エージェント応答・レイテンシ

| ID       | 要件                                                                        | 優先 | 状態                         |
| -------- | --------------------------------------------------------------------------- | ---- | ---------------------------- |
| SA-FR-07 | final transcript を通常の `prompt.submit` として Hermes agent に渡す        | P0   | ✅                           |
| SA-FR-08 | sentence-level TTS（`message.delta` を文単位で先行 TTS 投入）で初声を早める | P1   | 🟡                           |
| SA-FR-09 | barge-in（配信者が話し始めたら TTS 再生・生成を停止）                       | P1   | ⬜                           |
| SA-FR-10 | 応答の2系統分離（短い音声＝公開発話／詳細＝オーバーレイ表示）               | P1   | 🟡（prompt convention 運用） |

### 5.3 音声出力（TTS）

| ID       | 要件                                                                                              | 優先 | 状態                |
| -------- | ------------------------------------------------------------------------------------------------- | ---- | ------------------- |
| SA-FR-11 | Fish Audio REST TTS provider（`reference_id`/model/format/latency）                               | P1   | ✅                  |
| SA-FR-12 | Fish Audio WebSocket streaming TTS（MessagePack、`ffplay` 再生、REST fallback）                   | P1   | ✅                  |
| SA-FR-13 | AquesTalk ローカル TTS provider（CLI subprocess、WAV→MP3、声種/速度/声質）                        | P0   | ✅                  |
| SA-FR-14 | AquesTalk 向けテキスト正規化（Markdown/URL/絵文字除去、句読点正規化、読み辞書置換、失敗時 retry） | P1   | ✅                  |
| SA-FR-15 | AquesTalk 読み変換ローカル LLM（`koe_generation`、OpenAI 互換、失敗時 deterministic fallback）    | P2   | ✅（既定 disabled） |
| SA-FR-16 | TTS 用語読み辞書ストア（SQLite、関連語のみ注入）                                                  | P2   | ✅                  |

### 5.4 YouTube ライブチャット

| ID       | 要件                                                                                                            | 優先 | 状態                                 |
| -------- | --------------------------------------------------------------------------------------------------------------- | ---- | ------------------------------------ |
| SA-FR-17 | InnerTube（`youtubei.js`）経由でライブチャットを読み取り（Node subprocess → NDJSON ブリッジ）                   | P0   | ✅                                   |
| SA-FR-18 | YouTube Data API fallback（`videos.list`→`activeLiveChatId`→`liveChatMessages.list` polling）                   | P1   | ✅                                   |
| SA-FR-19 | チャット選別フィルタ（スポイラー語 `spoiler_terms`、NG ワード `blocked_terms`、min/max chars、`selected_only`） | P0   | ✅                                   |
| SA-FR-20 | 選別チャットを OBS オーバーレイに表示                                                                           | P1   | 🟡（config/server あり・配線要確認） |
| SA-FR-21 | 重複抑制・cooldown・rate limit                                                                                  | P1   | 🟡                                   |
| SA-FR-22 | YouTube ライブチャットへの投稿（`liveChatMessages.insert`）                                                     | P2   | ⬜（初期版は投稿しない方針）         |
| SA-FR-23 | first-class platform plugin 化（`plugins/platforms/youtube_live/`）                                             | P2   | ⬜                                   |

### 5.5 OBS オーバーレイ・表示

| ID       | 要件                                                                                                                                               | 優先 | 状態                              |
| -------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ---- | --------------------------------- |
| SA-FR-24 | ローカル overlay server（`http://127.0.0.1:8765/overlay`、SSE `/events` ＋ `/state.json` polling fallback、HTML/CSS）                              | P0   | ✅                                |
| SA-FR-25 | partial→caption、final→確定 caption 置換、assistant delta caption                                                                                  | P0   | ✅                                |
| SA-FR-26 | エージェント向け `overlay_*` ツール群（`overlay_set_caption`/`overlay_set_panel`/`overlay_show_selected_chat`/`overlay_clear`/`overlay_set_mode`） | P1   | ⬜（内部ヘルパのみ・tool 未登録） |
| SA-FR-27 | obs-websocket による OBS 操作ツール（`obs_switch_scene`/`obs_set_source_visible`/`obs_set_text_source`/`obs_get_scene_list`）                      | P2   | ⬜                                |

### 5.6 応答ルーティング・ペルソナ

| ID       | 要件                                                                                                                                       | 優先 | 状態                                                 |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ---- | ---------------------------------------------------- |
| SA-FR-28 | stream response router（`public_tts`/`overlay_caption`/`overlay_selected_chat`/`overlay_panel`/`obs_action`/`internal_note` への振り分け） | P1   | ⬜                                                   |
| SA-FR-29 | ゲーム実況 persona skill（短い発話、ネタバレ厳守、game-state memory、選別チャット表示手順、OBS scene 条件）                                | P0   | ✅（`skills/media/youtube-live-assistant/SKILL.md`） |
| SA-FR-30 | `/stream game`（`/stream status`）でゲーム実況用設定を一括有効化                                                                           | P0   | ✅                                                   |

### 5.7 ライブコーディング連携（`live_coding`）

| ID       | 要件                                                                                                             | 優先 | 状態                                         |
| -------- | ---------------------------------------------------------------------------------------------------------------- | ---- | -------------------------------------------- |
| SA-FR-31 | `stream_assistant.mode: live_coding` ＋ Codex/Claude Code 委譲 coordinator                                       | P1   | ✅（詳細は開発オーケストレーター要件定義書） |
| SA-FR-32 | `live_coding_delegate` ツール / `live_coding` toolset（core に混ぜない）                                         | P1   | ✅                                           |
| SA-FR-33 | 秘密情報フィルタ（`.env`/API key/token/private path を TTS・overlay から伏せる）                                 | P0   | ✅                                           |
| SA-FR-34 | ライブコーディング用 overlay state（current_task/codex_status/build_status/test_status/error_summary/next_step） | P1   | ✅                                           |

## 6. 非機能要件（NFR）

### 6.1 レイテンシ（最重要・`response-latency-optimization.md` の予算表）

| ID        | 区間                         | 現状              | 目標                                              |
| --------- | ---------------------------- | ----------------- | ------------------------------------------------- |
| SA-NFR-01 | 発話終了予測                 | 約 800–3000 ms    | **300–800 ms**                                    |
| SA-NFR-02 | LLM first token              | model 依存        | **300–900 ms**                                    |
| SA-NFR-03 | TTS first audio              | final response 後 | LLM first sentence 後 **300–800 ms**              |
| SA-NFR-04 | 体感 first voice（短い一言） | 数秒              | **1.0–2.0 秒以内**（短い相づちは 1 秒台を最優先） |

参考実測: Fish Audio WebSocket `first_audio_ms=894`。turn detection は `endpointing:800` が turn 数とのバランス最良（テスト台本の結論）。

### 6.2 その他 NFR

| ID        | 分類             | 要件                                                                                                                                                                                                                       |
| --------- | ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| SA-NFR-05 | 可用性           | Deepgram 接続断でアシスタントが落ちない（再接続・無音/終端対応）。OBS/obs-websocket 接続エラーでも overlay は疎結合で動く。                                                                                                |
| SA-NFR-06 | 堅牢性           | classifier timeout/failure 時は baseline へ fallback。`max_wait_ms` で無限待機を防止。長時間（数時間）配信で安定動作。                                                                                                     |
| SA-NFR-07 | コスト           | ライブ用途は Deepgram（partial 必要）。本番 LLM はローカル中心＋tool-call 失敗対策に安価なクラウド fallback を併用。context を過大にしない。                                                                               |
| SA-NFR-08 | 言語             | **日本語中心**（Deepgram `language: ja`、TTS は Fish Audio / AquesTalk〔日本語ローカル〕）。                                                                                                                               |
| SA-NFR-09 | プラットフォーム | linux / macOS / windows。ローカル LLM は OpenAI 互換（LM Studio 等）。                                                                                                                                                     |
| SA-NFR-10 | 安全性           | ネタバレ回避必須（`spoiler_policy: strict`）。危険チャットを読み上げない。scene 切替は明示意図＋cooldown。投機生成・投機中の tool call は配信事故防止のため厳格制御。STT が自分の TTS を拾うフィードバックループを避ける。 |

## 7. 制約・前提

- Hermes Agent の既存アーキテクチャ（agent loop / toolset / config）を踏襲する。
- AquesTalk10 の SDK/dylib/ライセンスキーはリポジトリ外（`AQUESTALK_DEV_KEY`/`AQUESTALK_USR_KEY`）。
- YouTube Data API は quota / OAuth の制約があるため、ライブチャットは InnerTube を primary とする。
- ローカル LLM の tool-call 信頼性に限界があるため、重要経路はクラウド fallback を許容する。
- OBS 連携は Browser Source（overlay HTTP/SSE）を primary とし、obs-websocket は将来拡張。

## 8. 外部依存・インターフェース

| 依存                | 用途                                                     | 認証                                    |
| ------------------- | -------------------------------------------------------- | --------------------------------------- |
| Deepgram            | streaming STT（WebSocket、nova-3）                       | `DEEPGRAM_API_KEY`                      |
| Fish Audio          | TTS（REST ＋ WebSocket msgpack）                         | `FISH_AUDIO_API_KEY`                    |
| AquesTalk10         | ローカル日本語 TTS（CLI subprocess）                     | `AQUESTALK_DEV_KEY`/`AQUESTALK_USR_KEY` |
| YouTube InnerTube   | ライブチャット読み取り（Node `youtubei.js`）             | 不要                                    |
| YouTube Data API v3 | チャット fallback                                        | `YOUTUBE_API_KEY`                       |
| OBS                 | Browser Source overlay（primary）/ obs-websocket（将来） | —                                       |
| ローカル LLM        | turn classifier / AquesTalk 読み生成（OpenAI 互換）      | —                                       |
| ffplay              | streaming TTS 再生                                       | —                                       |

## 9. リスク・未解決事項

### 9.1 未解決事項（計画書 Open Questions）

- public TTS / 字幕の音量・頻度の最適値。
- チャット選別ルール（mention/質問/Super Chat/NG）の詳細仕様。
- YouTube チャット投稿を将来入れるか（完全自動 vs 配信者承認）。
- 初期ターゲットゲーム未定。
- Deepgram final を直接渡すか wake-word/intent filter を挟むか。
- partial 字幕の見せ方（ちらつき抑制）。
- Fish Audio: full-file か chunked streaming か、既定 `reference_id`/voice。
- overlay/OBS の配置（core / bundled plugin / 別 repo）。

### 9.2 主要リスク

- 投機生成の配信事故（cancel 不能リスク）・投機中 tool call の副作用 → 厳格制御が前提（現状未実装ゆえ顕在化せず）。
- partial 字幕のちらつき・誤認識露出（例「火属性」→「秘属性」等のゲーム用語誤認識）。
- 長時間 network 依存（Deepgram/Fish Audio/YouTube）。
- TTS latency による不自然さ、STT フィードバックループ。
- 危険チャット読み上げ、scene 誤操作、ライブコーディングの秘密情報漏洩。

## 10. 受け入れ基準（主要シナリオ）

| ID       | シナリオ                                     | 合格条件                                                                                                   |
| -------- | -------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| SA-AC-01 | `/voice on` → 配信者が一言話す               | partial が overlay に出て、ターン終端後にエージェントが応答し、TTS の初声が体感 1–2 秒以内（SA-NFR-04）    |
| SA-AC-02 | 視聴者が通常チャットと NG/スポイラー語を投稿 | NG/スポイラーは overlay 非表示・読み上げ無し。通常チャットのみ選別表示（SA-FR-19/20）                      |
| SA-AC-03 | `/stream game` 実行                          | STT/overlay/youtube_chat/TTS のゲーム用プリセットが一括適用され、`/stream status` で確認できる（SA-FR-30） |
| SA-AC-04 | Deepgram 接続が一時切断                      | アシスタントが落ちず再接続し、配信継続（SA-NFR-05/06）                                                     |
| SA-AC-05 | `live_coding` で秘密情報を含む出力が発生     | `.env`/key/token/private path が TTS・overlay から伏せられる（SA-FR-33）                                   |

## 11. ロードマップ（残課題）

実装済みコア（STT セッション / ターン pipeline / Fish Audio・AquesTalk TTS / YouTube チャット ingestion・選別 / overlay server / persona skill / `/stream game`）を前提に、未達要件を以下の順で実装する。

| フェーズ | 内容                                                                                                      | 関連 FR                    |
| -------- | --------------------------------------------------------------------------------------------------------- | -------------------------- |
| P-A      | レイテンシ詰め（sentence-level TTS、barge-in、既定値の調整）                                              | SA-FR-08/09, SA-NFR-01〜04 |
| P-B      | エージェント向け表示制御の道具化（`overlay_*` ツール、stream response router、選別チャット overlay 配線） | SA-FR-26/28/20             |
| P-C      | turn classifier の本番有効化・チューニング、投機的生成（安全制御込み）                                    | SA-FR-04/06                |
| P-D      | OBS 操作（obs-websocket）、YouTube 投稿、platform plugin 化                                               | SA-FR-27/22/23             |
| P-E      | 運用整備（`.env.example` への新環境変数追記、`live-coding-assistant` skill 作成）                         | —                          |
