# 実況再設計 — 調査メモ（証跡）

`02-target-narration.md`（目指す実況像）の根拠。2026-07-09 に 2 系統で調査した要約。

- [A] Web 調査 — 人格設計・場面別語彙・実況技法（一人称・自己実況の枠で）
- [B] 現状棚卸し — 現 narrator 実装・ペルソナ・操作セット・元 kai 資産（コード接地）

---

## [A] Web 調査の要点

### 人格（ペルソナ）

- キャラは声・口調・性格・価値観を一度決めたら**一貫**させる。少数の不変 core（3〜5）に絞り、
  周辺は状況で揺らす。署名的な口癖/リアクション語を 1〜2 個持つと即「そのキャラ」と分かる。
- AITuber のシステムプロンプトは**一人称・語尾・口癖・セリフ例を大量に**与えるほど口調が安定する。
- 出典: VTuber Sensei（persona design）, Gank（vtuber persona guide）, ろてじん note（AITuber セリフ例）,
  romptn（キャラ設定の階層化）。

### 場面別レジスタ

- 一本調子は飽きの最大要因。**抑揚・語彙・文長・情報密度を場面で変える**。
- 実況は「淡々と描写する層」と「理由・感情を乗せる層」の 2 層。一人称では
  「いま何をしているか」と「なぜ/どう感じたか」を**交互に**。
- 感情は少し大げさに。小さいことにもリアクション。
- 出典: 富家 note, ライブ GOGO, JEA（play-by-play vs color）, ライバーサーチ。

### 思考の実況（think-aloud ＋ 語りかけ）

- concurrent think-aloud = やりながら「見ているもの・考え・迷い・決定」をその瞬間ごとに言語化。
  「何を」だけでなく「**なぜ**（理由・仮説）」を露わにする。
- ライブコーディングの鉄則: とにかく喋る。**予告→書く→説明**。ミスは隠さず直し方を実況。
  チャットを数分ごとに名前を呼んで拾う。沈黙に気づいたら「次に何をするか」に戻って口に出す。
- プロの技: ①予告→実行→結果の 3 拍 ②仮説の明示 ③行動に必ず"なぜ" ④オノマトペで映像化
  ⑤チャット巻き込み。
- 出典: dev.to（live-coding tips）, freeCodeCamp, zleague, In Third Person, Quali-Fi / The Decision Lab
  （think-aloud protocol）。

### アンチパターンと回避

- 単調反復 → phrase bank ＋ 直近使用回避、文長・冒頭を揺らす。
- 専門語/内部 ID ダダ漏れ → 発話前の翻訳レイヤ（allowlist）。
- **confabulation（作業と食い違う作文）** → LLM は知識の穴をもっともらしい捏造で埋める。
  **一人称化が最大の防御**（自分の意図＝既知、自分のツール出力＝観測済みだけ喋る）。
  出典: Nature 2024（confabulation）, Promptfoo / Microsoft（hallucination mitigation）。

### 日本語のキャラ付け

- 一人称・文末（語尾）が**属性タグ**として機能（役割語）。地の文なしで話者が分かる。
- 一人称候補: わたし（中立）／うち（砕け）／僕（中性）／ボク（既存 kai）。
- 出典: 役割語（Wikipedia）, 金水敏（ResOU）, kosiboro（語尾一覧・WebFetch 確認済み）,
  mirrativ（WebFetch 確認済み）。

> 検証状況: URL は WebSearch が返した実在ページ。kosiboro・mirrativ は本文取得で確認済み。
> 他は検索スニペット基準（本文全文は未確認）。間投詞・翻訳ポリシーの具体例は一般知見に基づく設計提案。

---

## [B] 現状棚卸し（コード接地）

### 現 narrator の仕組み（`plugins/kai_narrator/__init__.py`）

- hook（pre/post_tool_call, pre/post_llm_call）は**キューに積むだけ**で即 return。背景スレッドが
  2 秒間隔で ①最終応答を発話（source=agent_response＝本物の一人称）②溜まったツールイベントを
  補助 LLM で一言実況（source=narrator）③無音を heartbeat で埋める。
- 補助 LLM に渡すのは 3 ブロックだけ: **【いまの作業】=`_context`（前ターンの最終応答）**／
  【さっき実況したこと】（直近 3 件）／【直近の操作ログ】（ツール名＋args 1 フィールド＋status＋error＋duration）。
- 補助タスク `narration`（会話とは独立した別 LLM 呼び出し。temp 0.7 / max 120 / penalty 未指定）。

### confabulation・ID 漏れ・反復の機械的原因

1. **接地の欠落**: Issue 本文・エージェントの思考（reasoning）・ツールの**実行結果**・編集の**中身**を
   narrator が使っていない。なのにプロンプトが「目的か結果を必ず 1 つ入れる」を強制 → 材料不足を捏造で埋める。
   **【2026-07-09 訂正】** これらは「渡っていない」のではなく、**既に hook でプラグインに届いているのに
   narrator が捨てている**のが正しい（`post_tool_call` は `result` を渡す＝`model_tools.py:884`、
   `_on_post_tool_call` が `**_` で破棄。full `args` も来るが `_ARG_KEYS` が `content/new_string/todos` を落とす。
   本体の意図は `post_api_request` で観測可能だが未購読）。→ **接地強化は core 改変不要・プラグインのみ**。
   詳細は `05-implementation-plan.md`。
2. **文脈の時間ズレ**: `_context` = 前ターンの最終応答。`post_llm_call` はターン完了後に 1 回のみ発火
   （`turn_finalizer.py:365`）。長ターン中の per-tool の意図が届かない。`conversation_history` は
   hook に渡っているのに narrator は未使用（未活用の接地源）。
3. **ID 漏れ**: マスク対象は secret トークンのみ。ブランチ名・PR/Issue 番号・session/task ID・
   commit hash は素通り。`json.dumps(args)` フォールバックが args 丸ごとダンプ。
4. **反復**: 固定 3 文の heartbeat idle 行＋固定フォールバック文＋penalty 無しの小型 LLM。

### 現ペルソナ（`kai-services/persona/SOUL.md`）

- 既に「一人称『ボク』・視聴者『みんな』・自分の言葉で具体的に実況・冒頭で Issue を説明・
  検証を通してから『できた』」を**主役**と明記。**設計意図と実装（第三者観測）が乖離**しているだけ。

### 固定の操作セット（実況対象）

- 計画=`todo`（content）／調査=`read_file`(path)・`search_files`(pattern)／
  編集=`write_file`(content)・`patch`(old/new_string)／実行=`terminal`(command→git/gh/verify/test)・`process`／
  表示=`stream-browser open`・`vscode_open/close`。
- 接地に最も効く: `terminal.command`・`search_files.pattern`。
  **届いていない意図/中身**: `todo.content`・`write_file.content`・`patch.new_string`（最大のギャップ）。

### 元 kai 資産（`/Volumes/ExSSD/apps/seiichi3141/kai`）— 移植テンプレ

- **二段ナレーター**（`docs/design/two-stage-narrator.md` ほか）: agent の thought＋tool_use＋tool_result を
  `AgentActivity` バッファに積み、`formatActivityBuffer()` で**一人称ログ**化してから生成。
  thought=理由・tool_result=結果が入るため食い違いを**構造的に**潰す。三人称禁止。
- **skip 判断**（プロンプト内「喋る/黙る—最重要」）: 気づき/方針/テスト結果/予想外は喋る、
  読むだけ/反復/新発見なしは `{"skip":true}`。「迷ったら黙る」。
- **3 フェーズ**: kickoff（Issue を非エンジニア向けに説明）→ work（tool_result ごと）→ summary。
- **反復/反捏造対策**: XML タグでデータと指示を分離・「payload にない原因を推測しない」明示・
  `sanitizeSpeech`/`safeSpeechFallback`・`frequency_penalty 0.6 / presence_penalty 0.3`・会話履歴を直近 6 に剪定。
- **kai-facts**: 名前の由来「開＋改＋AI＝k-AI」・一人称カタカナ「ボク」・オーナー「せいさん」・
  不明質問は「今の手元情報では確認できないよ。推測では答えないでおくね」。
- **最大の学び（メトリクス）**: 読み上げ占有率 441%→101%（平均 155 字→36 字）。**短く**。

### アーキテクチャ評価（第三者観測者 → 一人称の自己実況へ）

| 案            | 内容                                                            | キャッシュ影響                 | トレードオフ                                                         |
| ------------- | --------------------------------------------------------------- | ------------------------------ | -------------------------------------------------------------------- |
| A             | 観測者のまま接地強化（Issue 本文・tool 結果・中身・思考を渡す） | 無傷（会話外の別 LLM）         | 依然「別 LLM が本人になりきる」。接地で食い違いは大幅減              |
| B             | メイン本体が自分の声で per-tool 実況                            | 出力なので無傷。会話トークン増 | 最も本物。沈黙区間を埋めきれない（heartbeat 別途）                   |
| **C（推奨）** | 本体＝意図・要点、観測者＝沈黙埋め・結果反応・冒頭 Issue 説明   | 両立で不可侵を守れる           | 2 経路で実装は複雑だが confabulation・無音・キャッシュを同時に解ける |

> キャッシュ不可侵の根拠: `docs/kai/02-architecture/01-system.md:57`「hook は観測専用でキャッシュに触れない。
> auxiliary LLM は会話外の独立メッセージ」。本体の一人称発話は「出力」なのでキャッシュを壊さない。
