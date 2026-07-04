import { test } from "node:test";
import assert from "node:assert/strict";
import { initTokenizer, toKoe, preprocessSymbols, formatKoe } from "./converter.mjs";
import { splitSentences } from "./text-splitter.mjs";

// kuromoji の辞書読み込みには数秒かかることがあるため、テスト全体を待ってから実行する。
await initTokenizer();

test("preprocessSymbols: 技術用語を日本語読みに置換する", () => {
  const result = preprocessSymbols("Issue #42 を確認");
  assert.match(result, /いっしゅー/);
  assert.match(result, /<NUMK VAL=42>/);
});

test("preprocessSymbols: 空文字はそのまま空文字を返す", () => {
  assert.equal(preprocessSymbols(""), "");
});

test("formatKoe: 空文字は句点のみを返す", () => {
  assert.equal(formatKoe(""), "。");
});

test("formatKoe: カタカナをひらがなに変換し文末に句点を付与する", () => {
  assert.equal(formatKoe("コンニチハ"), "こんにちは。");
});

test("formatKoe: 既に句点・疑問符で終わる場合は追加しない", () => {
  assert.equal(formatKoe("ソウデスカ？"), "そうですか？");
  assert.equal(formatKoe("ソウデス。"), "そうです。");
});

test("toKoe: ひらがな入力をそのまま音声記号列に変換する", async () => {
  const koe = await toKoe("こんにちは");
  assert.equal(koe, "こんにちは。");
});

test("toKoe: 技術用語を含むテキストを変換する", async () => {
  const koe = await toKoe("Issue #42 の実装を開始します");
  assert.match(koe, /いっしゅー/);
  assert.match(koe, /<NUMK VAL=42>/);
  assert.ok(koe.endsWith("。"));
});

test("toKoe: 空文字は空文字を返す", async () => {
  assert.equal(await toKoe(""), "");
});

test("formatKoe: づ・ぢを AquesTalk10 が解釈できる ず・じ に正規化する", () => {
  // AquesTalk10 の音声記号列では づ・ぢ が未定義で合成失敗する（実機確認済み）
  assert.equal(formatKoe("ヒヅケ"), "ひずけ。");
  assert.equal(formatKoe("チヂミ"), "ちじみ。");
});

test("formatKoe: ハイフン類は読点（短ポーズ）に正規化する", () => {
  // 素通しすると合成失敗する（実機確認済み）
  assert.equal(formatKoe("テスト-テスト"), "てすと、てすと。");
  assert.equal(formatKoe("テスト–テスト"), "てすと、てすと。");
});

test("formatKoe: 読めずに残った漢字・ASCII 残渣は除去して発話を継続する", () => {
  // 許可リスト方式の最終サニタイズ。文まるごと合成失敗より一部欠落を取る
  assert.equal(formatKoe("漢テスト"), "てすと。");
  assert.equal(formatKoe("テストabc"), "てすと。");
});

test("toKoe: 英単語と数字はタグとして保持される（除去しない）", async () => {
  const koe = await toKoe("uname -a を 7 秒で実行");
  assert.match(koe, /<ALPHA VAL=UNAME>/);
  assert.match(koe, /<ALPHA VAL=A>/);
  assert.match(koe, /<NUMK VAL=7>/);
  assert.doesNotMatch(koe, /-/); // ハイフンは読点化され残らない
});

test("splitSentences: 句点・感嘆符・疑問符・改行で分割する", () => {
  const sentences = splitSentences("こんにちは。元気ですか？さようなら！\nまた明日。");
  assert.deepEqual(sentences, ["こんにちは。", "元気ですか？", "さようなら！", "また明日。"]);
});

test("splitSentences: 空文字や空白のみの入力は空配列を返す", () => {
  assert.deepEqual(splitSentences(""), []);
  assert.deepEqual(splitSentences("   "), []);
});

test("splitSentences: 句切記号のないテキストは1文として返す", () => {
  assert.deepEqual(splitSentences("句点なしテキスト"), ["句点なしテキスト"]);
});
