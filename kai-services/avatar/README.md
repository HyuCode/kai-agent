# kai アバター制作ワークスペース

kai のアバター（**多脚メカ型多脚多脚ロボット**、PNGTuber）の素材制作用。要件は
`docs/kai/03-features/01-avatar/01-requirements.md`。ここには **kai 固有の入力**（キャラブリーフ・
プロンプト）を置く。制作の一般ツール（テンプレ・QA ハーネス）は下記キットを使う。

## 使うもの

- **制作キット:** `shinshin86/PuruPuruPNGTuber` の branch
  `codex/add-imagegen-asset-production-kit` の `asset-production/`
  （参照/ベース固定 → 目/口だけ差分 → 透過統一 → QA ハーネスの一貫フロー）
- **PuruPuruPNGTuber 本体:** `seiichi3141/PuruPuruPNGTuber`（口パク=マイク音量駆動・
  まばたき/髪揺れ自動・OBS 透過表示）

## このフォルダのファイル

| ファイル              | 内容                                                            |
| --------------------- | --------------------------------------------------------------- |
| `character-brief.md`  | kai のキャラ仕様（キットの brief を記入。**眼中心の読み替え**） |
| `imagegen-prompts.md` | kai 用の画像生成プロンプト（レンズ絞り + 発光 3 段に読み替え）  |

## リギング方針（暫定確定・V0）

多脚メカは髪も口も無いので、PuruPuru の人型レイヤーを**眼中心に読み替える**:

- **口パク（口 3 段）→ 単眼レンズのコア発光の弱/中/強**（＝喋るとレンズが光る）
- **まばたき（目開/閉）→ レンズの絞り開閉（シャッター）**
- **髪揺れ（前髪/後ろ髪）→ 前後の触角／アンテナの揺れ**
- **body → ポッド + 多脚**

（オーナーが「小さな可愛い口を足す」案に変える余地あり。§要件 V0 参照）

## 制作手順（検証フェーズ）

1. `character-brief.md` を確認（キャラ確定）
2. `imagegen-prompts.md` の**ベース機体プロンプト**で 1 枚生成（→ 画像生成ツールは
   別途。Codex/ChatGPT の imagegen or Windows ComfyUI）
3. ベースを固定し、**眼の差分 6 枚** + **前後触角** + **ボディ**を生成
4. クロマキー #00ff00 → 透過化: `uv run python <kit>/harness/chroma_key_to_alpha.py ...`
5. 検査: `uv run python <kit>/harness/validate_purupuru_assets.py <folder>`
6. コンタクトシート QA: `uv run python <kit>/harness/review_purupuru_assets.py <folder>`
7. PuruPuru に読み込み、口パク（発光）/まばたき/揺れを確認 → `.purupuru` 保存

## 現状（2026-07-07）

- 要件定義・キャラ確定（多脚メカ型）・リギング暫定確定・プロンプト作成まで完了
- QA ハーネスは Mac で動作確認済み（`uv` 経由）
- **未:** 実画像の生成（到達手段 = Codex imagegen or ComfyUI を確立して着手）
