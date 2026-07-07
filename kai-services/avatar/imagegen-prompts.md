# kai imagegen プロンプト（タチコマ型 kai）

> asset-production kit の `templates/imagegen-prompts.md` を kai 用に記入したもの。
> **非人型のため「目/口の差分」を「単眼レンズの絞り開閉 + コア発光の 3 段」に読み替え**
> ている（`character-brief.md` 参照）。プロンプトは英語（画像モデル向け）。
> 背景はクロマキー `#00ff00` で生成し、`harness/chroma_key_to_alpha.py` で透過化する。
>
> **出力ファイル名は PuruPuru の要求どおり**（`eyes-*` / `*-hair`）にし、中身を
> タチコマのパーツにする。差分は「レンズ以外を完全一致」させるのが最重要。

## 眼の状態 → ファイル名 対応

| ファイル名                     | レンズ絞り | コア発光 |
| ------------------------------ | ---------- | -------- |
| `eyes-open-mouth-closed.png`   | 開（虹彩） | 弱       |
| `eyes-open-mouth-half.png`     | 開（虹彩） | 中       |
| `eyes-open-mouth-open.png`     | 開（虹彩） | 強       |
| `eyes-closed-mouth-closed.png` | 閉（横線） | 弱       |
| `eyes-closed-mouth-half.png`   | 閉（横線） | 中       |
| `eyes-closed-mouth-open.png`   | 閉（横線） | 強       |

## 1. ベース機体（最初に 1 枚。以後これを固定して差分を作る）

```text
Use case: stylized-concept
Asset type: PuruPuru PNGTuber base avatar source
Primary request: Generate a front-facing cute anime-style mascot robot avatar base image.
Subject: A cute chibi anime-style "thinking tank" robot inspired by multi-legged spider-tanks
  (Tachikoma-like). A rounded pod-shaped body-head in soft cyan-blue with white accents. One
  large round camera-eye centered on the front: a glossy circular lens with a glowing cyan-white
  core (iris). Small sensor antennae on top of the pod (a couple in front, one or two at the
  back). Several short, cute mechanical legs partially visible at the bottom. Friendly, curious,
  toy-like. No human face, no mouth, no hair, no human eyes — a single camera-eye only.
Style/medium: clean anime illustration, crisp line art, simple readable shapes, soft cel shading
Composition/framing: centered bust-up avatar, the pod and camera-eye near the upper center,
  legs small at the bottom, generous padding all around, identical pose reusable for variants
Scene/backdrop: perfectly flat solid #00ff00 chroma-key background for background removal
Constraints: keep the robot fully separated from the background; no cast shadow; no floor;
  no background objects; no watermark; no extra text
Avoid: human face, human eyes (two eyes), mouth, hair, cropped body, strong lighting gradients,
  semi-transparent background, changing the pose
```

## 2. 眼の差分（ベース機体を編集。レンズだけ変える）

各差分は「上の対応表」の 1 行ぶん。`<lens>` と `<glow>` を差し替える。

```text
Use case: precise-object-edit
Asset type: PuruPuru PNGTuber expression variant (robot single-eye)
Primary request: Create the <filename> variant from the base robot.
Input images: Image 1 is the base robot reference/edit target.
Change ONLY the single camera-eye:
  - Lens aperture = <lens: "open, iris ring fully visible" | "closed, a simple horizontal shutter line (blink)">
  - Core glow = <glow: "dim/soft" | "medium" | "bright/strong cyan-white glow">
Constraints: Keep the pod body shape, head position, antennae, legs, colors, canvas framing,
  and silhouette EXACTLY unchanged. Preserve exact identity and pixel alignment. Only the lens
  aperture and core glow differ.
Avoid: moving the pod, changing antennae or legs, changing body color, adding a mouth, adding
  a second eye, adding new highlights elsewhere, adding text, adding a background
```

## 3. 前触角レイヤー（front-hair.png に相当）

```text
Use case: background-extraction
Asset type: PuruPuru PNGTuber front-hair.png (front antennae layer)
Primary request: Extract only the antennae/sensor rods that sit in FRONT of the pod.
Input images: Image 1 is the aligned full robot reference/edit target.
Constraints: Keep the exact canvas size and alignment. Output only the front antennae pixels;
  everything else should be flat #00ff00 chroma-key for removal. Preserve their shape, line art,
  and edge detail (these will wobble like hair).
Scene/backdrop: perfectly flat solid #00ff00 chroma-key background
Avoid: including the pod body, camera-eye, lens, legs, back antennae, shadows, text, watermark
```

## 4. 後触角レイヤー（back-hair.png に相当）

```text
Use case: background-extraction
Asset type: PuruPuru PNGTuber back-hair.png (back antennae/fin layer)
Primary request: Extract only the antennae/fins that sit BEHIND the pod and body.
Input images: Image 1 is the aligned full robot reference/edit target.
Constraints: Keep the exact canvas size and alignment. Output only the back antennae/fin pixels;
  everything else should be flat #00ff00 chroma-key for removal. Preserve shape and edge detail.
Scene/backdrop: perfectly flat solid #00ff00 chroma-key background
Avoid: including the pod body, camera-eye, lens, legs, front antennae, shadows, text, watermark
```

## 5.（任意）ボディレイヤー（body.png = ポッド + 多脚）

```text
Use case: background-extraction
Asset type: PuruPuru PNGTuber body.png (pod + legs)
Primary request: Extract the pod body and legs only (no antennae, no lens glow).
Input images: Image 1 is the aligned full robot reference/edit target.
Constraints: Keep exact canvas size and alignment. Flat #00ff00 chroma-key elsewhere.
Avoid: antennae, camera-eye lens core glow, shadows, text
```

## 透過化・検査（生成後）

1. 各 PNG を `harness/chroma_key_to_alpha.py` で #00ff00 → 透過にする
2. `uv run python harness/validate_purupuru_assets.py <folder>` でサイズ・アルファを検査
3. `uv run python harness/review_purupuru_assets.py <folder>` でコンタクトシートを作り、
   **レンズ以外がズレていないか**を目視 QA（細部の発光アルファは崩れやすい）
