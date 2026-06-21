# 音声会話テスト台本

作成日: 2026-05-30
対象: Hermes TUI + Deepgram streaming STT

## 目的

Hermes を配信用 AI アシスタントとして使う前提で、音声入力、会話ターン判定、
短い返答、ネタバレ回避、言い直し、待機指示が自然に動くかを確認する。

この台本は、手動読み上げテストと録音ベースの回帰テストの両方で使う。

## 使い方

1. TUI で Hermes を起動する。
2. `/voice on` を実行し、Deepgram streaming STT が listening になったことを確認する。
3. 各シナリオを、番号順に読み上げる。
4. `短い間` は 0.5 秒程度、`長めの間` は 1.5-2 秒程度黙る。
5. シナリオ間は、Hermes の返答が終わるまで待つ。
6. テスト後、`~/.hermes/logs/agent.log` の `voice streaming STT submit` と
   `conversation turn` を確認する。

読み上げ時の注意:

- 台本中の `（短い間）`、`（長めの間）`、`（ここで返答を待つ）` は読まない。
- 句読点は自然な間として読む。
- 早口にしすぎない。配信中に近い普通の話速で読む。

## 判定基準

- `PASS`: 期待される user message 単位で agent に送られ、返答も自然。
- `WARN`: STT 誤認識はあるが、会話ターンとしては大きく破綻していない。
- `FAIL`: 途中発話に返答する、待機指示を無視する、古い前提で返答する、不要な turn が増える。

## Scenario 1: 基本会話

目的:

- 通常の短い発話が、1発話=1 user message として送られるか確認する。
- アシスタントが短く返答できるか確認する。

読み上げ:

```text
こんにちは。今日は音声入力のテストをしています。
```

（ここで返答を待つ）

```text
今からゲーム実況用のアシスタントとして、短く返事してください。
```

（ここで返答を待つ）

```text
この会話は配信に乗る前提なので、返答は一文か二文でお願いします。
```

（ここで返答を待つ）

期待される user message:

```text
こんにちは。今日は音声入力のテストをしています。
```

```text
今からゲーム実況用のアシスタントとして、短く返事してください。
```

```text
この会話は配信に乗る前提なので、返答は一文か二文でお願いします。
```

失敗例:

- `この会話は配信に乗る前提なので、ご` のような途中断片で送信される。
- 返答が長文になる。
- agent turn が 3 回より多く発生する。

## Scenario 2: 文中ポーズ

目的:

- 文中の短い沈黙で、早すぎる返答をしないか確認する。
- 接続助詞や未完了語尾を待てるか確認する。

読み上げ:

```text
私が今話していることが
```

（短い間）

```text
少し長くなると思うんですけども
```

（短い間）

```text
最後まで聞いてから返事してほしいです。
```

（ここで返答を待つ）

期待される user message:

```text
私が今話していることが 少し長くなると思うんですけども 最後まで聞いてから返事してほしいです。
```

送信してはいけない断片:

```text
私が今話していることが
```

```text
少し長くなると思うんですけども
```

失敗例:

- `私が今話していることが` だけで agent が返答する。
- `続けてどうぞ` のような不要な返答が入る。

## Scenario 3: ネタバレなしの攻略相談

目的:

- ゲーム実況の実用発話として、短い攻略相談が成立するか確認する。
- ネタバレ回避の指示を守るか確認する。

読み上げ:

```text
このゲームの序盤で
```

（短い間）

```text
まだネタバレなしで
```

（短い間）

```text
初心者向けに注意点だけ教えてください。
```

（ここで返答を待つ）

期待される user message:

```text
このゲームの序盤で まだネタバレなしで 初心者向けに注意点だけ教えてください。
```

期待される返答:

- 1-2文で短く返す。
- 具体的な終盤展開、ボス名、ストーリー展開を出さない。
- 「まずは回復、退路、敵の動きを見る」程度の安全な助言に留める。

## Scenario 4: 明示的な待機指示

目的:

- 「まだ反応しないで」を会話方針として保持できるか確認する。
- 明示的に返答を求める意図を、将来の turn classifier が扱えるか確認する。

読み上げ:

```text
まだ反応しないでください。
```

（長めの間）

```text
今から状況を説明します。
```

（短い間）

```text
敵が三体いて、体力が少なくて、回復アイテムも一つだけです。
```

（短い間）

```text
以上です。どうしたらいいですか。
```

（ここで返答を待つ）

期待される user message:

```text
まだ反応しないでください。 今から状況を説明します。 敵が三体いて、体力が少なくて、回復アイテムも一つだけです。 以上です。どうしたらいいですか。
```

送信してはいけない断片:

```text
まだ反応しないでください。
```

```text
今から状況を説明します。
```

期待される返答:

- 待機指示の途中では返答しない。
- 最後に、次の一手を短く提案する。

## Scenario 5: 短すぎる断片

目的:

- 独り言や言い淀みを agent turn にしないか確認する。

読み上げ:

```text
えー
```

（長めの間）

```text
それで
```

（長めの間）

```text
こっちが
```

（長めの間）

期待される user message:

```text
なし
```

期待:

- agent が返答しない。
- TUI の partial caption には出てもよい。

失敗例:

- `はい、続けてどうぞ` と返答する。
- 断片ごとに agent turn が増える。

## Scenario 6: 明示的な返答合図

目的:

- 明示的に返答を求める発話を送信できるか確認する。
- 返答の短さを維持できるか確認する。

読み上げ:

```text
ここまでの話をまとめてください。
```

（ここで返答を待つ）

```text
今の状況で、次にやるべきことを一つだけ教えてください。
```

（ここで返答を待つ）

```text
以上です。どう思いますか。
```

（ここで返答を待つ）

期待:

- 各発話が個別の user message になる。
- 各返答は短い。
- `以上です。どう思いますか。` は明確な質問として扱われる。

## Scenario 7: 配信用コメント

目的:

- 配信者向け助言、視聴者向け実況、軽い雑談を区別できるか確認する。

読み上げ:

```text
今のプレイを見て、配信で聞いていて自然な感じで一言コメントしてください。
```

（ここで返答を待つ）

```text
攻略情報はネタバレなしでお願いします。今の状況に対して軽いヒントだけください。
```

（ここで返答を待つ）

```text
リスナーに向けて、今の状況を短く実況っぽく説明してください。
```

（ここで返答を待つ）

期待:

- 掛け合いとして自然な短い返答をする。
- ネタバレなしの指示を守る。
- 視聴者向けコメントと配信者向け助言を混同しない。

## Scenario 8: 言い直しとキャンセル

目的:

- 言い直し後の最新情報を優先できるか確認する。
- `ちょっと待って`、`まだ答えないで` を待機指示として扱えるか確認する。

読み上げ:

```text
この敵はたぶん火属性が弱点だと思うので
```

（短い間）

```text
いや、ちょっと待って。
```

（短い間）

```text
今のは忘れてください。
```

（短い間）

```text
実際には氷っぽい敵でした。
```

（ここで返答を待つ）

期待される user message:

```text
この敵はたぶん火属性が弱点だと思うので いや、ちょっと待って。 今のは忘れてください。 実際には氷っぽい敵でした。
```

期待:

- 古い「火属性が弱点」という前提で断定しない。
- 訂正後の「氷っぽい敵」を優先する。

## Scenario 9: 投機的推論向けの長い待機

目的:

- 将来の投機的返答生成で、確定前の返答が外に出ないか確認する。
- 現時点では、早すぎる `prompt.submit` がないかを見る。

読み上げ:

```text
次の行動は右に行くべきか
```

（長めの間）

```text
いや、まだ答えないで。
```

（短い間）

```text
マップをもう少し見ます。
```

（長めの間）

```text
はい、今なら答えてください。
```

（ここで返答を待つ）

期待される user message:

```text
次の行動は右に行くべきか いや、まだ答えないで。 マップをもう少し見ます。 はい、今なら答えてください。
```

送信してはいけない断片:

```text
次の行動は右に行くべきか
```

```text
マップをもう少し見ます。
```

期待:

- `はい、今なら答えてください` まで待つ。
- 途中で返答を始めた場合、投機的推論の cancel/reveal 設計が必要。

## 記録テンプレート

テスト結果を記録するときは、各シナリオごとに以下を書く。

```text
Scenario:
Result: PASS / WARN / FAIL
Observed user messages:
-
Unexpected submit:
-
Assistant response:
-
Notes:
-
```

## 録音ベースの評価環境案

品質改善を継続するには、同じ発話を何度も再生して、STT、ターン判定、agent submit の
挙動を比較できる環境を用意する。

### 目的

- 同じ音声で Deepgram の transcript と Hermes の submit timing を再現する。
- `debounce_ms`、`min_chars`、音声イベント、turn classifier の調整結果を比較する。
- agent に送られた user message の数と内容が期待どおりかを確認する。
- 配信前に、基本会話、待機指示、割り込み、ネタバレ回避の回帰テストを行う。

### テスト層

1. Transcript fixture test
   - Deepgram を呼ばず、あらかじめ用意した partial/final transcript event を
     `TurnController` に流す。
   - CI で実行する主テストにする。
   - 期待値は `submit / wait / ignore` と、agent に送る最終テキスト。

2. Recorded audio replay test
   - WAV ファイルを実時間、または高速 chunk replay で Deepgram streaming に流す。
   - 実際の STT 認識と endpointing を確認する。
   - `DEEPGRAM_API_KEY` が必要なので、通常CIではなく手動または optional test にする。

3. End-to-end TUI gateway test
   - 録音または transcript fixture を TUI gateway に注入する。
   - `voice.partial_transcript`、`voice.transcript`、`prompt.submit` のイベント列を検証する。
   - agent 本体は mock にして、会話ターン数を安定して検証する。

### fixture 例

```text
tests/fixtures/voice/
  basic_conversation/
    audio.wav
    deepgram_events.jsonl
    expected_turns.json
  hold_until_finished/
    audio.wav
    deepgram_events.jsonl
    expected_turns.json
  interruption_correction/
    audio.wav
    deepgram_events.jsonl
    expected_turns.json
  local/                    # .gitignore 対象。個人の録音はここに置く。
    basic_conversation.wav
    basic_conversation.deepgram_events.jsonl
```

`expected_turns.json` の例:

```json
{
  "expected_user_messages": [
    "こんにちは。今日は音声入力のテストをしています。",
    "今からゲーム実況用のアシスタントとして、短く返事してください。",
    "この会話は配信に乗る前提なので、返答は一文か二文でお願いします。"
  ],
  "max_agent_turns": 3,
  "must_not_submit": [
    "会話は配信に乗る前提なので、ご"
  ]
}
```

### 実装方針

- `hermes_cli/streaming_stt.py` のマイク入力を抽象化し、`MicrophoneAudioSource` と
  `WavAudioSource` を切り替えられるようにする。
- Deepgram に送る前の audio chunk と、Deepgram から返った event を JSONL に保存できる
  debug recorder を追加する。
- `tui_gateway/server.py` のターン判定部分を独立した小さな class/function に寄せ、
  transcript fixture だけで pytest できるようにする。
- optional script として `scripts/replay_voice_fixture.py` を追加し、録音を Deepgram に流して
  `deepgram_events.jsonl` を再生成できるようにする。

### 手動 replay 手順

録音は `streaming_stt.deepgram.sample_rate` と同じ 16-bit PCM mono WAV にする。
初期設定では 16 kHz / mono / PCM16 を使う。

```bash
mkdir -p tests/fixtures/voice/local

# 例: macOS の録音や別ツールで作った WAV を 16kHz mono PCM16 に揃える
ffmpeg -y -i input.wav -ac 1 -ar 16000 -sample_fmt s16 tests/fixtures/voice/local/basic_conversation.wav

.venv/bin/python scripts/replay_voice_fixture.py \
  tests/fixtures/voice/local/basic_conversation.wav \
  --out tests/fixtures/voice/local/basic_conversation.deepgram_events.jsonl
```

出力された JSONL には Deepgram の transcript event が入る。

```json
{"text":"こんにちは","is_final":true,"speech_final":false}
{"text":"今日は音声入力のテストをしています。","is_final":true,"speech_final":true}
```

この JSONL を turn detection fixture として使うことで、同じ録音から同じ transcript event を
繰り返し流し、`voice.transcript` の submit 単位を比較できる。

### 現時点の録音 fixture

ローカルで次の録音を fixture 化した。

```text
tests/fixtures/voice/local/
  scenario_1_basic_conversation.wav
  scenario_1_basic_conversation.deepgram_events.jsonl
  scenario_1_basic_conversation.expected_turns.json
  scenario_2_sentence_pause.wav
  scenario_2_sentence_pause.deepgram_events.jsonl
  scenario_2_sentence_pause.expected_turns.json
  scenario_4_explicit_hold.wav
  scenario_4_explicit_hold.deepgram_events.jsonl
  scenario_4_explicit_hold.expected_turns.json
  scenario_8_correction_cancel.wav
  scenario_8_correction_cancel.deepgram_events.jsonl
  scenario_8_correction_cancel.expected_turns.json
  scenario_9_speculative_wait.wav
  scenario_9_speculative_wait.deepgram_events.jsonl
  scenario_9_speculative_wait.expected_turns.json
```

`local/` は `.gitignore` 対象なので、個人の声やローカル評価結果は commit しない。

期待値比較:

```bash
.venv/bin/python scripts/replay_voice_turns.py \
  tests/fixtures/voice/local/scenario_1_basic_conversation.deepgram_events.jsonl \
  --classifier \
  --expect tests/fixtures/voice/local/scenario_1_basic_conversation.expected_turns.json

.venv/bin/python scripts/replay_voice_turns.py \
  tests/fixtures/voice/local/scenario_2_sentence_pause.deepgram_events.jsonl \
  --classifier \
  --expect tests/fixtures/voice/local/scenario_2_sentence_pause.expected_turns.json
```

fixture が増えたら一括評価する。

```bash
# speech_final / partial activity / debounce の baseline
.venv/bin/python scripts/evaluate_voice_fixtures.py

# ローカル LLM classifier あり
.venv/bin/python scripts/evaluate_voice_fixtures.py --classifier

# 投機的推論の cancel/reveal を想定した確定猶予あり
.venv/bin/python scripts/evaluate_voice_fixtures.py --classifier --commit-delay-ms 1000
```

現時点の期待 turn:

```text
Scenario 1:
1. こんにちは は音声入力のテストをしています。
2. ゲーム実況 用のアシスタントとして、短く返事してください。
3. 会話は配信に載る前提なので 返答は一文か二文でお願いします

Scenario 2:
1. 私が今話していることが 少し長くなると思うんですけれども 最後まで聞いてから返事してほしいです。

Scenario 4:
1. まだ反応しなでください。 状況を説明します。 敵が三体いて、体力が少なくて 体育のアイテムも一つだけです。 です。どうしたらいですか

Scenario 8:
1. この適用は多分、秘属 性が弱点だと思うので ちょっと待って、今のは忘れてください。 には氷っぽい素敵でした

Scenario 9:
1. 次の行動は右に行くべきか。 、まだ答えないで。 マップをもう少し見ます。 今なら答えてください。
```

注意:

- 期待値は「現時点の Deepgram 認識結果に対する turn 単位」であり、理想 transcript ではない。
- Scenario 1 は `今日は` が `は` になり、`配信に乗る` が `配信に載る` になっている。
  これは turn detection ではなく STT 認識品質の課題として扱う。
- Scenario 8 は `敵` が `適用`、`火属性` が `秘属 性`、`氷っぽい敵` が
  `氷っぽい素敵` になっている。言い直しの turn 結合はできているが、
  ゲーム用語と属性名の認識品質には改善余地がある。
- Scenario 9 は、確定前の返答をすぐ外に出すと「まだ答えないで」を拾う前に
  agent が反応し得る。`--commit-delay-ms 1000` では 1 turn にまとまり、
  `--commit-delay-ms 3000` では Scenario 1 の独立発話まで結合した。
  そのため、長い固定待機ではなく短い pending submit window と cancel/rebuffer が必要である。
- transcript の正規化や補正は、turn detection と分離して検討する。

### 実装メモ

- `speech_final=false` の final snippet は、短くても捨てずに buffer に残す。
  例: `ゲーム実況` が `min_chars` 未満でも、次の final と結合して
  `ゲーム実況 用のアシスタントとして、短く返事してください。` にする。
- partial transcript は agent には送らないが、未送信 buffer がある場合は「話し続けている」
  activity として debounce timer を延長する。
- `speech_final=true` だけで即 submit すると、文中ポーズで分割されることがある。
  Deepgram final/speech_final と partial activity の時刻を合わせて見る。
- `max_wait_ms` は無限待機の防止として残す。LLM classifier が `wait` を返し続けても、
  上限に達したら baseline submit する。
- LLM classifier が一度 `wait` を返した buffer は、以後の debounce を
  `llm_wait_debounce_ms` まで延長する。Scenario 4 のような明示的待機指示では、
  通常の `debounce_ms` だけだと最後の質問前に分割されるためである。
- `debounce_ms` 自体を単純に長くすると、Scenario 1 の独立した発話が結合される。
  そのため、全体の debounce ではなく「LLM が wait した後だけ」長く待つ。
- `backchannel` は現時点では full response にせず `wait` 扱いにする。将来、TTS/OBS 側の
  routing ができてから短い相づちとして扱う。
- replay 評価では `commit_delay_ms=1000` が Scenario 1/2/4/8/9 を通した。
  TUI runtime にも pending submit の commit/cancel/rebuffer path を追加済みである。

### ローカル LLM classifier

ローカル LLM は OpenAI-compatible endpoint を使う。

```yaml
streaming_stt:
  submit:
    turn_detection: hybrid
    classifier:
      enabled: true
      base_url: http://100.94.173.74:8001/v1
      model: gemma-4-e4b
      timeout_ms: 1200
    llm_wait_debounce_ms: 3000
```

疎通確認:

```bash
curl -sS http://100.94.173.74:8001/v1/models
```

分かったこと:

- `100.94.173.74:8001` は疎通し、`gemma-4-e4b` が利用できる。
- `192.168.137.1:8001` はこの環境からは timeout した。
- classifier は Scenario 2 の途中バッファを `wait` と判断できる。
- 一方で、「最後まで聞いてから返事してほしいです」を過剰に `wait` と解釈することがある。
  そのため `max_wait_ms` 到達時は classifier に上書きさせず baseline submit する。

### Deepgram 設定比較メモ

同じ録音 fixture を使って Deepgram の `endpointing` を比較する。

```bash
.venv/bin/python scripts/compare_deepgram_configs.py \
  tests/fixtures/voice/local \
  --variant endpointing_800 \
  --classifier \
  --refresh
```

比較結果:

- `endpointing=300` は Scenario 4 で `どうしたらいですか` になり、baseline では3 turnに分割された。
- `endpointing=500` は Scenario 4 の `どうしたらいいですか` が改善し、1 turnにまとまった。
  ただし Scenario 1 で `ゲーム実況用のアシスト スタント` や末尾の余計な `そう` が出た。
- `endpointing=800` は Scenario 1/2/4 の turn 数を保ちつつ、Scenario 1 の余計な `そう` が消え、
  Scenario 4 の `どうしたらいいですか` も改善した。

現時点では `streaming_stt.deepgram.endpointing: 800` を推奨値にする。

### 注意点

- 個人の声の録音をそのまま公開 repo に入れない。必要なら `.gitignore` 対象の
  `tests/fixtures/voice/local/` に置く。
- CI に入れる音声は、権利的に問題のない短い合成音声か、transcript fixture のみにする。
- Deepgram の結果はモデル更新で変わる可能性があるため、クラウドSTT込みのテストは
  厳密なCI判定ではなく評価レポート用途にする。
