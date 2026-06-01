# AquesTalk TTS 組み込み調査と計画

作成日: 2026-06-01

## 目的

Hermes の配信用 AI アシスタントで、Fish Audio とは別のローカル TTS 選択肢として AquesTalk10 を使えるようにする。

特に以下を満たす。

- ライセンスキー、AquesTalk SDK 本体、再配布制限のある dylib/header をリポジトリに入れない。
- 配信で使える程度に低遅延で安定して発話できる。
- 日本語、英数字、技術語、記号、Markdown 混入に強くする。
- 既存の STT -> LLM -> TTS -> OBS 字幕/音声の構成を壊さない。

## 調査対象

- Hermes 側ローカル配置: `aquestalk/`
- 参考実装: `/Volumes/ExSSD/apps/seiichi3141/kai`

## Hermes 側に現在あるもの

`aquestalk/` には以下がある。

- `aquestalk_cli`
  - Mach-O arm64 実行ファイル。
  - 引数: `"text" [voice_type] [speed]`
  - stdout に WAV を出力する。
- `aquestalk_cli.c`
  - AquesTalk10 を呼び出す C ラッパー。
  - 現状はライセンスキーをコード内に直接書いている。
- `lib/libAquesTalk10.dylib`
- `AquesTalk10.h`
- `licence.txt`
- AquesTalk 公式 PDF

実行確認:

- `DYLD_LIBRARY_PATH=... ./aquestalk/aquestalk_cli 'こんにちは、テストです。' F1 130 > /tmp/aquestalk_test.wav`
- 出力は `RIFF WAVE`, 16-bit mono, 16000 Hz。

注意:

- 英字を含む入力では CLI が失敗するケースがある。
- AquesTalk に渡す前に日本語読み、英数字タグ、記号除去などの前処理が必要。
- SDK 本体、dylib、header、ライセンスキーはリポジトリに入れない方針にする。

## kai 参考実装の要点

### 配布・ライセンス方針

`kai/packages/aquestalk/README.md` では以下の方針。

- `AquesTalk10.h` と `libAquesTalk10.dylib` は再配布禁止対象なのでリポジトリに含めない。
- ライセンスキーは `AQUESTALK_DEV_KEY` / `AQUESTALK_USR_KEY` 環境変数から読む。
- CLI ソースと薄いラッパーバイナリだけを repo 管理する。
- SDK 位置は `AQUESTALK_SDK_DIR` / `AQUESTALK_DIR` / `AQUESTALK_LIB_DIR` / `AQUESTALK_CLI_PATH` で指定する。

Hermes でも同じ方針を採用する。

### CLI ラッパー

kai の `packages/aquestalk/aquestalk_cli.c` は Hermes 側の現状より安全で高機能。

- ライセンスキーを env から読む。
- 声種: `F1`, `F2`, `F3`, `M1`, `M2`, `R1`, `R2`
- 速度: 50-300
- 声質パラメータ:
  - `--vol=N`
  - `--pit=N`
  - `--acc=N`
  - `--lmd=N`
  - `--fsc=N`
- stdout に WAV を出力する。
- stderr にエラーを出し、非ゼロ終了する。

Hermes 側では kai 版の方針に合わせて、ライセンスキー直書き版を廃止する。

### テキスト変換

kai の `packages/tts/src/converter.ts` は、通常テキストを AquesTalk10 音声記号列へ変換する。

主要処理:

- `kuromoji` で漢字かな交じり文をカナ化。
- 技術用語辞書で `GitHub`, `OBS`, `LLM`, `TTS`, `PR` などを読みへ置換。
- 数字を `<NUMK VAL=...>` に変換。
- 英字を `<ALPHA VAL=...>` に変換する段階があるが、kai の LLM koe 生成では英字をひらがな読みへ寄せる方針。
- 絵文字、制御文字、三点リーダーを除去。
- 句読点を AquesTalk 向けに正規化。
- 助詞「は」を kuromoji の係助詞判定で「わ」に補正。
- 括弧、Markdown 系の危険文字、未閉じタグ、禁則文字を除去。

Hermes にそのまま TypeScript を持ち込むのではなく、Python 実装として必要部分を移植する。

### LLM による音声記号列生成

kai の `text-to-speech-provider.ts` は、AquesTalk10 音声記号列生成を LLM に任せる経路を持つ。

特徴:

- OpenAI / local OpenAI-compatible / llama の順で試す。
- 失敗時は kuromoji 変換にフォールバック。
- `KOE_LOCAL_LLM_URL`, `TTS_KOE_MODEL`, `KOE_LLM_BACKENDS`, `KOE_REMOTE_TIMEOUT_MS` などで制御。
- LLM 出力を `sanitizeLlmKoe()` で強くサニタイズする。
- `applyParticleCorrection()` で「は→わ」を補正する。

Hermes ではすでにローカル LLM を使っているため、軽量な音声記号列生成モデルとして流用できる。
実際の TUI 動作確認で、AquesTalk CLI に漢字かな交じりの文章が渡ると `Failed to synthesize speech` で失敗することを確認した。
そのため、初期実装の deterministic な辞書/正規化に加えて、kai と同じ方向のローカル LLM 読み生成経路を追加する。

Hermes 側の方針:

- `tts.aquestalk.koe_generation.enabled` が `true` のときだけ有効にする。
- OpenAI 互換 API の `/v1/chat/completions` を使う。
- 既定モデルは `gemma-4-e4b`。
- 既定URLは `http://127.0.0.1:8001/v1`。
- この環境では `http://100.94.173.74:8001/v1` を設定して試す。
- LLM 出力はそのまま信用せず、AquesTalk に渡せる読み文字へサニタイズする。
- LLM 変換が失敗した場合は既存の deterministic 正規化へフォールバックする。
- ライセンスキーやAPIキーは `.env` / 環境変数に置き、リポジトリには入れない。

## Hermes への組み込み方針

### 1. SDK/キーを repo に入れない

`aquestalk/` の現状は未追跡だが、このままコミットしない。

repo に入れるもの:

- Python wrapper 実装
- 設定項目
- テスト
- ドキュメント
- 必要なら AquesTalk CLI の自前ソース。ただしライセンスキー直書きは禁止。

repo に入れないもの:

- `libAquesTalk10.dylib`
- `AquesTalk10.h`
- AquesTalk SDK 由来の PDF
- `licence.txt`
- `AQUESTALK_DEV_KEY`
- `AQUESTALK_USR_KEY`
- SDK 由来ファイルを含んだビルド成果物

### 2. Hermes の TTS provider として追加

`tools/tts_tool.py` に `aquestalk` provider を追加する。

設定例:

```yaml
tts:
  provider: aquestalk
  aquestalk:
    cli_path: /Users/seiichiro/apps/seiichi3141/hermes-agent/aquestalk/aquestalk_cli
    lib_dir: /Users/seiichiro/apps/seiichi3141/hermes-agent/aquestalk/lib
    voice: F1
    speed: 130
    output_format: mp3
    volume: 100
    pitch: 110
    accent: 100
    intonation: 100
    sampling_freq: 100
    timeout_seconds: 10
```

秘密情報は `~/.hermes/.env`:

```env
AQUESTALK_DEV_KEY=...
AQUESTALK_USR_KEY=...
```

`hermes_cli/config.py` の `OPTIONAL_ENV_VARS` に上記2つを追加する。

### 3. CLI 実行方式

初期実装では AquesTalk CLI を subprocess で実行する。

入力:

- Hermes の assistant final text
- Markdown 除去済みテキスト
- AquesTalk 用に正規化した koe/text

出力:

- CLI stdout の WAV
- Hermes の通常 TTS 再生経路に合わせるため、必要なら ffmpeg で MP3 に変換

理由:

- `hermes_cli.voice.speak_text()` は現在 `mp3_path` を期待している。
- 既存の command provider は WAV 出力には対応できるが、`speak_text()` が返却された実出力パスを見ず、指定した mp3 path だけを確認するため、そのままでは voice TTS に使いにくい。
- AquesTalk provider 側で、指定された出力拡張子に合わせて WAV または MP3 を書くのが安全。

### 4. テキスト品質改善

初期段階で入れる deterministic 処理:

- Markdown 除去
- URL 除去
- 絵文字/制御文字除去
- 明示的に与えられた読み辞書の適用
- `！` -> `。`
- `?` -> `？`
- `...`, `…` 除去
- 括弧・引用記号除去
- `づ` -> `ず`, `ぢ` -> `じ`, `ゔ` 系の置換
- 長音・促音・句読点の連続を圧縮
- 失敗時は再サニタイズして1回だけ retry

技術用語辞書はコード内の巨大な固定辞書にしない。
数が多く、配信・ゲーム・開発文脈で継続的に増えるため、最終的にはDB/RAGで管理する。

短期:

- `tts.aquestalk.terms` または `tts.aquestalk.terms_path` で小さな手動辞書だけを注入する。
- provider 本体には大きなデフォルト辞書を持たせない。
- 2026-06-02 初期実装:
  - `hermes_cli.tts_terms` に SQLite ベースの読み辞書ストアを追加。
  - 既定DBは `~/.hermes/tts_terms.db`。
  - `add_tts_term()`, `delete_tts_term()`, `list_tts_terms()`, `find_relevant_tts_terms()`, `import_tts_terms_json()` を提供。
  - AquesTalk provider は入力文に出現する関連語だけを取得し、`term -> reading` 置換に使う。
  - `tts.aquestalk.terms_db_enabled`, `terms_db_path`, `terms_limit`, `terms_min_confidence` で制御する。

中期:

- term store の管理UI/CLIを追加する。
- `term`, `reading`, `source`, `confidence`, `last_used_at`, `created_at`, `usage_count` を活用して、よく使う用語や修正済み用語を優先する。
- 誤読を見つけた時に、TUIから読みを登録できるようにする。

長期:

- transcript、チャット、ゲーム名、攻略情報、過去の修正履歴から候補語を抽出する。
- ローカルLLMで読み候補を生成し、低 confidence のものは確認待ちにする。
- RAGで現在のゲーム/配信文脈に関連する読みだけを取り出し、TTS変換に注入する。

第2段階で検討:

- Python 版 kuromoji 相当として `SudachiPy` または `fugashi` を導入する。
- 依存追加は upper bound 付きで `pyproject.toml` に入れる。
- まずは辞書ベース/正規化のみで始め、必要性が明確になってから形態素解析を足す。

第2段階として実装:

- ローカル LLM による AquesTalk 読み生成。
- OpenAI-compatible endpoint を利用する。
- 発話ごとにLLMを挟むため、配信用リアルタイム会話ではレイテンシを継続計測する。
- 失敗時は deterministic 正規化に戻す。

### 5. ストリーミング可否

AquesTalk CLI は短いテキストなら十分高速だが、基本は「テキスト全体 -> WAV 全体」の同期生成。

Fish Audio WebSocket のような token streaming TTS ではない。

低遅延化の方針:

- LLM出力を句点・読点・短い文節で分割する。
- セグメント単位で AquesTalk 合成し、再生キューへ投入する。
- 次セグメントを合成しながら前セグメントを再生する。
- バージイン時は再生プロセスと合成キューを止める。

これは Hermes の現在の streaming Fish worker とは別 worker として設計する。

### 6. バージイン対応

既存の Fish Audio streaming TTS と同様に、AquesTalk 再生 worker も active worker として登録する。

STT partial/final が来たら:

- active AquesTalk playback を停止
- 未再生キューを破棄
- 生成中 agent turn を interrupt
- OBS字幕に割り込み表示は出さない

### 7. テスト計画

単体テスト:

- provider alias: `aquestalk`
- missing `cli_path`
- missing executable
- invalid speed/voice
- env key が command line/log に出ない
- CLI stdout WAV を出力ファイルへ保存
- MP3出力時に ffmpeg を呼ぶ
- CLI失敗時にサニタイズ retry
- Markdown/英数字/技術用語/記号の正規化

手動テスト:

- `こんにちは、テストです。`
- `OBSとYouTubeチャットを見ながら、LLMで判断します。`
- `PR #123 の GitHub Actions が失敗しています。`
- `**まずは** \`右\` へ行きます。`
- 長めのアシスタント回答
- 発話中のバージイン

## 実装ステップ

1. `aquestalk/` を `.gitignore` で除外するか、少なくともSDK由来ファイルがコミットされない状態を明示する。
2. `hermes_cli/config.py`
   - `tts.provider` の説明に `aquestalk` を追加。
   - `tts.aquestalk` default block を追加。
   - `OPTIONAL_ENV_VARS` に `AQUESTALK_DEV_KEY` / `AQUESTALK_USR_KEY` を追加。
3. `tools/tts_tool.py`
   - `BUILTIN_TTS_PROVIDERS` に `aquestalk` を追加。
   - `_generate_aquestalk_tts()` を追加。
   - `_check_aquestalk_available()` を追加。
   - dispatcher と `check_tts_requirements()` に接続。
4. `tools/aquestalk_text.py` または `hermes_cli/aquestalk_text.py`
   - AquesTalk向け正規化関数を分離。
   - kai の converter/sanitize 方針を Python に移植。
5. TTS term store を設計する。
   - 初期実装では `terms_path` JSON で逃がす。
   - DB/RAG化は AquesTalk provider の次の改善タスクにする。
6. 非ストリーミング voice TTS で動作確認。
7. 必要なら AquesTalk worker を追加し、分割合成・再生キュー・バージイン停止を実装。
8. ドキュメントにローカルセットアップ手順とライセンス注意を追記。

## 初期結論

AquesTalk は Hermes に組み込み可能。

ただし、今の `aquestalk/` ディレクトリをそのままコミットするのは避けるべき。
特に SDK由来ファイルとライセンスキー直書きの CLI ソースは repo 管理に向かない。

品質面では、単に CLI を呼ぶだけでは英字・記号・Markdown で失敗しやすい。
kai の価値は AquesTalk CLI よりも、`converter.ts` / `text-to-speech-provider.ts` / 技術用語辞書 / サニタイズ設計にある。

Hermes ではまず「安全な local provider」として実装し、その後、必要に応じて「短文分割 + 再生キュー + バージイン」の低遅延化へ進む。
