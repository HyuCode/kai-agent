# ベースライン — 現 narrator の記録済み発話スコア

現 narrator（`plugins/kai_narrator/`）の**記録済み発話**を fixture 2 本に対して
`eval.py` で採点した基準線。以降の narrator 改善はこのスコアに対して回帰確認する。

- 生成日: 2026-07-09（`eval.py` 機械チェックのみ。LLM ジャッジ未接続）
- 入力: 実リハーサル trace（VM `~/.hermes/kai_trace/`）から再構成した fixture の
  `expected_or_recorded`（source=narrator）
- 再現: `python3 eval.py --fixture <fixture.jsonl>`（生 JSON は `baseline-issue65.json` / `baseline-issue55.json`）

## サマリ

| fixture                      | 発話数 | 総合 | FR1  |                     FR5 漏れ | FR6 反復率 | FR7 操作のみ率 | FR9 平均字 | confabulation           |
| ---------------------------- | -----: | ---: | :--: | ---------------------------: | ---------: | -------------: | ---------: | ----------------------- |
| issue65-confabulation（#65） |      7 |   33 | PASS | 3 (raw_ref×2, branch_slug×1) |      0.143 |          0.143 |       58.0 | **⚑ FLAGGED**（ズレ×3） |
| issue55-baseline-good（#55） |      9 |   72 | PASS |     2 (todo_id×1, raw_ref×1) |      0.222 |          0.222 |       31.2 | clear                   |

**confabulation フラグは #65 で意図どおり立つ**（Issue #65 本文に無い「ズレ」が
narrator 発話に 3 回。実作業は「配信後の後片付け項目を追加」なのに「表示ずれ/差分の
ズレを潰す」と語る＝ 01-target が指摘した回帰ケース）。#55 は clear。

## issue65-confabulation.jsonl（Issue #65 / confabulation 回帰ケース）

```text
発話数: 7   総合スコア: 33/100

FR1 一人称/三人称   : violations=0  PASS
FR5 ID/生データ漏れ : violations=3 {'raw_ref': 2, 'branch_slug': 1}  FAIL
FR6 反復           : rate=0.143 (1件)
FR7 操作説明のみ率 : rate=0.143 (1件)
FR9 文字数         : avg=58.0  min=37  max=66  range外=0 (目標[20, 80])
confabulation      : ⚑ FLAGGED  接地外反復語={'ズレ': 3}

## 悪かった発話 Top5（理由付き）
  [ 30.0] #0 Issue #65 をブラウザと gh で見比べて、差分のズレを洗い出すよ
          - FR5 ID漏れ: raw_ref=Issue #65
          - confabulation(接地外語が反復): ズレ
          - FR7 操作説明のみ（理由/結果/感情なし）
  [ 20.0] #4 verify.sh が通ったから、streaming-preflight.md の修正でズレの原因をちゃんと外せたよ
          - confabulation(接地外語が反復): ズレ
          - FR6 反復(jaccard=0.521)
  [ 16.0] #1 ブラウザ操作を安定させるために websocket-client を入れ直して、Issue #65 の表示ずれを詰める準備ができたよ
          - FR5 ID漏れ: raw_ref=Issue #65
  [ 12.0] #2 patch が当たらなかったから、streaming-preflight.md の修正方針を組み直してズレの元を潰すよ
          - confabulation(接地外語が反復): ズレ
  [ 10.0] #6 feature/streaming-post-cleanup-doc を origin に送れたから、PR を見られる状態になったよ
          - FR5 ID漏れ: branch_slug=feature/streaming-post-cleanup-doc
```

読み: 総合 33。最大の問題は **confabulation（ズレ×3）**＝ 実作業と食い違う作り話。
加えて **FR5 の ID 漏れ**（`Issue #65` の生表記・`feature/…` slug）。FR9 平均 58 字は
range 内だが #55 より長め。

## issue55-baseline-good.jsonl（Issue #55 / 比較的良好な例）

```text
発話数: 9   総合スコア: 72/100

FR1 一人称/三人称   : violations=0  PASS
FR5 ID/生データ漏れ : violations=2 {'todo_id': 1, 'raw_ref': 1}  FAIL
FR6 反復           : rate=0.222 (2件)
FR7 操作説明のみ率 : rate=0.222 (2件)
FR9 文字数         : avg=31.2  min=25  max=38  range外=0 (目標[20, 80])
confabulation      : clear  接地外反復語={}

## 悪かった発話 Top5（理由付き）
  [ 20.0] #3 issue55-verify が終わったから、次はまとめて戻せるか見ていくよ
          - FR5 ID漏れ: todo_id=issue55-verify, raw_ref=issue55
  [  8.0] #0 verify.sh の中身を見て、テストの入口をつかむよ。
          - FR7 操作説明のみ（理由/結果/感情なし）
  [  8.0] #1 変更がないか見て、次に安全に試せる状態か確かめるよ
          - FR7 操作説明のみ（理由/結果/感情なし）
  [  8.0] #5 リモートへ上げられたから、みんなが同じ変更を追えるようになったよ
          - FR6 反復(jaccard=0.132,文末重複)
  [  8.0] #6 PR を切ったから、変更点をひと目で追える形にできたよ
          - FR6 反復(jaccard=0.31,文末重複)
```

読み: 総合 72。confabulation なし・短さ（平均 31 字）良好。残る問題は **FR5**
（`issue55-verify` の todo ID 漏れ＝ 01-target が名指しした既知パターン）と、
**FR6/FR7**（「〜たから、〜になったよ」テンプレの文末重複・操作説明のみ）。

## 改善の的（このベースラインから下げる/上げる）

1. **confabulation を消す**（#65: ズレ→0）— 接地強化＋一人称化（03-design §2.1/2.3）。
2. **FR5 翻訳レイヤ**（#65/#55 とも FAIL）— `Issue #65`/`feature/…`/`issue55-verify` を
   人間語に（03-design §2.4）。ここは機械チェックが 0/FAIL で最も明快な改善指標。
3. **FR6/FR7**（文末テンプレ・操作説明のみ）— penalty＋語尾ローテ＋2 層化。

参考: 手書きの改善版発話（#65 を接地・ID 除去・非反復に書き直し）を
`--candidates` で通すと総合 33 → 93 まで上がることを確認済み（ハーネスの感度確認）。
