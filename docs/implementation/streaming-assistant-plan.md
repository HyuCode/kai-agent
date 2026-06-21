# 実装計画 — ライブ配信ゲーム実況 AI アシスタント

| 項目           | 内容                                                                                                 |
| -------------- | ---------------------------------------------------------------------------------------------------- |
| 文書名         | ライブ配信ゲーム実況 AI アシスタント 実装計画（WBS）                                                 |
| バージョン     | 1.0                                                                                                  |
| 作成日         | 2026-06-16                                                                                           |
| 関連文書       | `docs/requirements/streaming-assistant-requirements.md`, `docs/design/streaming-assistant-design.md` |
| 凡例（状態）   | ✅ 完了 / 🟡 部分実装（要追加） / ⬜ 未着手                                                          |
| 凡例（規模）   | S（〜0.5日） / M（1〜2日） / L（3日以上）                                                            |
| 凡例（ループ） | 🤖 `loop/loop.sh`（claude -p）に乗せやすい / 👤 人手中心（外部API/OBS/配信実機が必要）               |

---

## 1. 概要・前提

実装済みコア（STT セッション、ターン pipeline、Fish Audio/AquesTalk TTS、YouTube チャット ingestion・選別、overlay server、persona skill、`/stream game`）の上に、レイテンシ最適化・表示制御の道具化・安全制御を積み上げる。各タスクは要件 ID（`SA-FR-xx`/`SA-NFR-xx`）に対応。

**検証基盤**: 単体テストは `loop/verify.sh`（`scripts/run_tests.sh tests/hermes_cli/ tests/tools/` 等）で回す。配信実機・外部 API・OBS が要るものは 👤。

---

## 2. マイルストーン

| MS  | 名称                 | ゴール                                               | 状態    |
| --- | -------------------- | ---------------------------------------------------- | ------- |
| M0  | コア基盤             | 音声→agent→TTS/overlay/チャットの一連が動く          | ✅ 完了 |
| M1  | レイテンシ最適化     | 体感初声 1.0–2.0s（SA-NFR-01〜04）                   | 🟡 進行 |
| M2  | 表示制御の道具化     | overlay/OBS をエージェントツール化、応答ルーティング | ⬜      |
| M3  | 高度ターン制御       | turn classifier 本番化、投機生成（安全制御込み）     | ⬜      |
| M4  | プラットフォーム拡張 | OBS 操作、YouTube 投稿、platform plugin 化           | ⬜      |
| M5  | 運用整備             | env/skill/ドキュメント整備                           | 🟡      |

---

## 3. 作業項目（WBS）

### M0 — コア基盤（実装済み）

| ID      | 作業                                                           | 関連FR            | 状態 | 主要ファイル                                                                     |
| ------- | -------------------------------------------------------------- | ----------------- | ---- | -------------------------------------------------------------------------------- |
| SA-T-01 | Deepgram streaming STT セッション                              | SA-FR-01/02       | ✅   | `hermes_cli/streaming_stt.py`                                                    |
| SA-T-02 | ターン pipeline（pending submit / commit / cancel / rebuffer） | SA-FR-03          | ✅   | `tui_gateway/server.py`                                                          |
| SA-T-03 | Fish Audio REST/WebSocket TTS（ffplay 再生）                   | SA-FR-11/12       | ✅   | `hermes_cli/streaming_tts.py`, `tools/tts_tool.py`                               |
| SA-T-04 | AquesTalk ローカル TTS＋正規化＋読み辞書                       | SA-FR-13/14/15/16 | ✅   | `tools/tts_tool.py`, `hermes_cli/tts_terms.py`                                   |
| SA-T-05 | YouTube チャット ingestion（InnerTube/DataAPI）＋選別          | SA-FR-17/18/19    | ✅   | `hermes_cli/youtube_chat.py`, `scripts/youtube-chat-innertube-bridge.mjs`        |
| SA-T-06 | overlay server（caption/SSE/state）                            | SA-FR-24/25       | ✅   | `hermes_cli/live_overlay.py`                                                     |
| SA-T-07 | persona skill ＋ `/stream game` プリセット                     | SA-FR-29/30       | ✅   | `skills/media/youtube-live-assistant/SKILL.md`, `hermes_cli/stream_assistant.py` |
| SA-T-08 | `live_coding` 連携（委譲・サニタイズ・coding overlay）         | SA-FR-31〜34      | ✅   | `hermes_cli/live_coding.py`, `tools/live_coding_tool.py`                         |

### M1 — レイテンシ最適化

| ID      | 作業                                                               | 関連          | 状態 | 規模 | ループ | 依存       | 受け入れ                                                                           |
| ------- | ------------------------------------------------------------------ | ------------- | ---- | ---- | ------ | ---------- | ---------------------------------------------------------------------------------- |
| SA-T-10 | sentence-level TTS（`message.delta` を文単位で先行投入）           | SA-FR-08      | 🟡   | M    | 🤖     | SA-T-03    | 文確定ごとに TTS 投入され first audio が短縮。単体テストで文分割・キュー投入を検証 |
| SA-T-11 | barge-in（配信者発話で TTS 再生・生成を停止）                      | SA-FR-09      | ⬜   | M    | 👤     | SA-T-01,03 | 再生中に partial 検知→再生/生成を中断（実機確認）                                  |
| SA-T-12 | 既定レイテンシ値の収束（実コード/テスト台本/レイテンシ計画の統一） | SA-NFR-01〜04 | 🟡   | S    | 🤖     | —          | 根拠ある単一既定に統一（design §11-2）。`/stream game` プリセットと整合            |
| SA-T-13 | レイテンシ計測メトリクス（発話終端予測/first token/first audio）   | SA-NFR-01〜04 | ⬜   | M    | 🤖     | SA-T-02,03 | 各区間の ms をログ収集し予算と比較できる                                           |

### M2 — 表示制御の道具化

| ID      | 作業                                                                                              | 関連        | 状態 | 規模 | ループ | 依存       | 受け入れ                                                            |
| ------- | ------------------------------------------------------------------------------------------------- | ----------- | ---- | ---- | ------ | ---------- | ------------------------------------------------------------------- |
| SA-T-20 | `overlay_*` エージェントツール群（set_caption/set_panel/show_selected_chat/clear/set_mode）       | SA-FR-26    | ⬜   | M    | 🤖     | SA-T-06    | エージェントが overlay を能動操作。配信モード時のみ有効な別 toolset |
| SA-T-21 | 選別チャット overlay 表示の配線完了                                                               | SA-FR-20/21 | 🟡   | S    | 🤖     | SA-T-05,06 | 選別済チャットが overlay に出る。重複抑制・cooldown を単体検証      |
| SA-T-22 | stream response router（public_tts/overlay_caption/selected_chat/panel/obs_action/internal_note） | SA-FR-28    | ⬜   | M    | 🤖     | SA-T-20    | 応答が用途別経路に振り分く。prompt convention 依存を脱却            |
| SA-T-23 | 応答2系統分離の structured output 化（短音声＋詳細overlay）                                       | SA-FR-10    | 🟡   | M    | 🤖     | SA-T-22    | speech と overlay が構造的に分離（強制）                            |

### M3 — 高度ターン制御

| ID      | 作業                                                                       | 関連      | 状態 | 規模 | ループ | 依存       | 受け入れ                                                                       |
| ------- | -------------------------------------------------------------------------- | --------- | ---- | ---- | ------ | ---------- | ------------------------------------------------------------------------------ |
| SA-T-30 | turn classifier 本番有効化・チューニング（submit/wait/ignore/backchannel） | SA-FR-04  | 🟡   | M    | 🤖+👤  | SA-T-02    | classifier 有効時に誤 submit/取りこぼしが baseline 以下。timeout fallback 検証 |
| SA-T-31 | 投機的 hidden draft 生成（先行 LLM → commit/reveal/cancel）                | SA-FR-06  | ⬜   | L    | 👤     | SA-T-02,30 | 確定前に先行生成、cancel/reveal が安全に動作（配信事故防止の制御込み）         |
| SA-T-32 | STT フィードバックループ対策（自分の TTS をマイクが拾わない）              | SA-NFR-10 | ⬜   | M    | 👤     | SA-T-01,03 | TTS 再生中の自己発話が誤認識されない                                           |

### M4 — プラットフォーム拡張

| ID      | 作業                                                                                       | 関連     | 状態 | 規模 | ループ | 依存    | 受け入れ                                                           |
| ------- | ------------------------------------------------------------------------------------------ | -------- | ---- | ---- | ------ | ------- | ------------------------------------------------------------------ |
| SA-T-40 | obs-websocket 操作ツール（switch_scene/set_source_visible/set_text_source/get_scene_list） | SA-FR-27 | ⬜   | L    | 👤     | SA-T-20 | エージェントが OBS scene/source を制御（cooldown・明示意図ガード） |
| SA-T-41 | YouTube ライブチャット投稿（`liveChatMessages.insert`、承認制）                            | SA-FR-22 | ⬜   | M    | 👤     | SA-T-05 | 承認付きでチャット返信できる                                       |
| SA-T-42 | YouTube first-class platform plugin 化                                                     | SA-FR-23 | ⬜   | L    | 🤖     | SA-T-05 | `plugins/platforms/youtube_live/` として登録                       |

### M5 — 運用整備

| ID      | 作業                                                                           | 関連         | 状態 | 規模 | ループ | 依存    | 受け入れ                                                           |
| ------- | ------------------------------------------------------------------------------ | ------------ | ---- | ---- | ------ | ------- | ------------------------------------------------------------------ |
| SA-T-50 | `.env.example` に新環境変数追記（DEEPGRAM/YOUTUBE/FISH_AUDIO/AQUESTALK keys）  | —            | ⬜   | S    | 🤖     | —       | 新キーが `.env.example` に記載                                     |
| SA-T-51 | `skills/media/live-coding-assistant/SKILL.md` 作成                             | —            | ⬜   | S    | 🤖     | SA-T-08 | ライブコーディング persona skill が存在                            |
| SA-T-52 | 主 TTS の正式決定（Fish Audio vs AquesTalk）と config 明文化                   | SA-FR-11〜16 | ⬜   | S    | 👤     | —       | `game` モードの既定 provider を文書・config に確定（design §11-1） |
| SA-T-53 | `stream_assistant.*` config の正規化（ペルソナ系キーの config/skill 責務分離） | —            | ⬜   | M    | 🤖     | —       | 計画書 §6 の古い config 例と実装の乖離を解消（design §11-5）       |

---

## 4. 推奨実装順序（クリティカルパス）

1. **SA-T-12 → SA-T-13 → SA-T-10**（レイテンシの土台と計測。掛け合いの質に直結、🤖でループ化しやすい）
2. **SA-T-21 → SA-T-20 → SA-T-22 → SA-T-23**（表示制御を道具化。エージェントが配信画面を主体的に操作できる基盤）
3. **SA-T-50 / SA-T-51 / SA-T-52 / SA-T-53**（運用整備。小粒で並行可、ループ化しやすい）
4. **SA-T-11 / SA-T-32 / SA-T-30**（実機検証が要るレイテンシ・安全性。配信実機で詰める）
5. **SA-T-31**（投機生成。最も難しく配信事故リスクが高い。安全制御が固まってから）
6. **SA-T-40 / SA-T-41 / SA-T-42**（OBS/投稿/plugin 化。拡張）

---

## 5. ループ運用メモ

- 🤖 タスク（SA-T-10/12/13/20/21/22/23/42/50/51/53 等）は `loop/tasks/*.md` 化し、`TEST_SCOPE` を `tests/hermes_cli/` や `tests/tools/` に絞って `loop/loop.sh` で回せる。
- 👤 タスク（barge-in・OBS・配信実機・外部 API キー必須）は人手＋実機確認が中心。ループは下準備（スキャフォールド・単体テスト）まで。
