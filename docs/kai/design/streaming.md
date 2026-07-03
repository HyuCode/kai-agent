# streaming 基本設計書

- **ステータス:** ドラフト
- **作成日 / 更新日:** 2026-07-04
- **満たす要件:** F-6（ライブ配信管理の基盤部分）、要件 §7.4（Linux 配信スタック）
- **マイルストーン:** M0（インフラ PoC）。obs-websocket による配信制御 skill は M4 で本書に追記する
- **種別:** 独立プロセス（セットアップスクリプト + systemd/user units）
- **配置:** `kai-services/streaming/`

## 1. 目的と責務

kai の作業デスクトップ（配信映像の実体）と、それを YouTube へ届ける経路を提供する。具体的には (a) ヘッドレス VM 上の永続 X デスクトップ、(b) 発話音声を配信に乗せるオーディオ経路、(c) OBS によるキャプチャと RTMP 送出、(d) オーナー用リモート GUI（Tailscale 内 VNC）。

**やらないこと（非責務）:**

- 発話・字幕の生成と同期（speechd の責務。本コンポーネントは null-sink という「音の通り道」だけ提供する）
- YouTube broadcast の作成・メタデータ管理（F-6 の API 部分。フェーズ 4 以降）
- アバター表示（avatar の責務）
- kai 本体のセットアップ（M1）

## 2. 配置と Footprint Ladder

- **選んだ段:** ⑥ 独立プロセス（hermes 外の配信スタック）
- **理由:** OS レベルのインフラ（X サーバー・音声・OBS）であり、エージェントのツール面には載らない。kai からの操作は M4 で skill（②）として追加する
- **コア改変:** なし

## 3. インターフェース

### 3.1 提供するインターフェース

| IF                  | 形式                     | 内容                                                                           |
| ------------------- | ------------------------ | ------------------------------------------------------------------------------ |
| `DISPLAY=:0`        | X11                      | 1920x1080 の永続デスクトップ。kai のブラウザ・エディタ等はここに表示する       |
| `kai_speaker`       | PipeWire null-sink       | speechd が WAV を再生する出力先。OBS がその monitor を音声ソースとして取り込む |
| VNC :5900           | RFB（Tailscale IP bind） | オーナーのリモート GUI（:0 と同一画面）。パスワード認証                        |
| obs-websocket :4455 | WebSocket（127.0.0.1）   | M4 の配信制御 skill と speechd の字幕更新が使用                                |

### 3.2 依存するインターフェース

| 依存先                                           | 形式    | 用途               | 不達時の挙動                                          |
| ------------------------------------------------ | ------- | ------------------ | ----------------------------------------------------- |
| YouTube RTMP (`rtmp://a.rtmp.youtube.com/live2`) | RTMP    | 配信送出           | OBS が再接続リトライ。デスクトップと kai の作業は継続 |
| Tailscale                                        | tailnet | VNC / SSH の到達性 | 配信は継続（外部到達のみ喪失）                        |

## 4. データモデル

永続化データなし。設定ファイルのみ:

- `/etc/X11/xorg.conf.d/10-dummy.conf` — dummy ドライバで 1920x1080
- `/etc/X11/Xwrapper.config` — 非 root で Xorg を起動可能にする（`allowed_users=anybody` / `needs_root_rights=no`）
- `~/.config/pipewire/pipewire.conf.d/10-kai-speaker.conf` — null-sink `kai_speaker` の永続定義
- `~/.vnc/passwd` — x11vnc パスワード（秘匿。リポジトリに含めない）
- OBS プロファイル/シーン（GUI で作成し `~/.config/obs-studio/` に保存。ストリームキーを含むため**リポジトリに含めない**）

## 5. 処理フロー

起動順（systemd 依存関係で表現）:

1. `kai-xorg.service`（user unit）: `Xorg :0 -config 10-dummy.conf` → 永続デスクトップ
2. `kai-desktop.service`: XFCE セッション（`startxfce4`）を `DISPLAY=:0` で起動
3. PipeWire（Ubuntu 標準の user unit）が `kai_speaker` null-sink を設定ファイルから生成
4. `kai-x11vnc.service`: `x11vnc -display :0 -listen <tailscale-ip> -rfbauth ~/.vnc/passwd -forever`
5. OBS: M0 では VNC から手動起動・手動設定（画面キャプチャ(:0) + `kai_speaker.monitor` + ストリームキー設定 + obs-websocket 有効化）。常駐 unit 化は M4
6. ユーザー unit を VM 再起動後も動かすため `loginctl enable-linger`

## 6. エラー処理・縮退

| 失敗モード         | 検知                       | 挙動                                   | 復旧                                             |
| ------------------ | -------------------------- | -------------------------------------- | ------------------------------------------------ |
| Xorg 落ち          | unit 失敗                  | 依存 unit ごと再起動                   | `Restart=on-failure`                             |
| RTMP 切断          | OBS 内部                   | OBS が自動再接続。kai の作業は影響なし | 自動                                             |
| OBS クラッシュ     | プロセス消滅               | 配信断。デスクトップは維持             | M0 は手動再起動（VNC から）。M4 で監視 unit 化   |
| VNC 不達           | オーナー操作不能           | 配信・作業は継続                       | Tailscale/SSH から unit 再起動                   |
| エンコード性能不足 | CPU 飽和・ドロップフレーム | 解像度/ビットレートを下げる            | 720p30 へフォールバック（§9 の検証で閾値を実測） |

## 7. 設定

| キー                      | 置き場所             | デフォルト                                                       | 説明                                                       |
| ------------------------- | -------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------- |
| 解像度                    | `10-dummy.conf`      | 1920x1080                                                        | 配信解像度と一致させる                                     |
| VNC bind                  | `kai-x11vnc.service` | Tailscale IP                                                     | 公開インターフェースに bind しない                         |
| RTMP URL / ストリームキー | OBS 設定（GUI）      | —                                                                | **ストリームキーは秘匿**。ファイル・ログ・設計書に書かない |
| 映像設定                  | OBS 設定             | 1080p30 / x264 veryfast / 6000kbps（不可なら 720p30 / 4500kbps） | M0 の実測で確定                                            |

## 8. セキュリティ

- **秘匿情報:** YouTube ストリームキー（OBS 設定内のみ）、VNC パスワード（`~/.vnc/passwd`）。いずれもリポジトリ・ログ・配信画面に出さない。OBS の「設定画面を開く操作」は配信中に行わない（キーが映るため）
- **入力の信頼境界:** なし（外部入力を受けない）
- **ネットワーク:** 公開ポートなし。VNC は Tailscale IP のみ bind、obs-websocket は 127.0.0.1 のみ。SSH も Tailscale 経由に限定（クラウド側 FW で 0.0.0.0/0 の 22 番を閉じる。Tailscale 直接接続用に udp/41641 のみ開放）
- **許容リスク（2026-07-04 実機確認）:** Ubuntu の x11vnc は `-listen <ip>` 指定でも `[::]:5900`（IPv6 ワイルドカード）を開く（`-no6` / `-noipv6` とも無効）。ホストにグローバル IPv6 アドレスがなく（リンクローカルのみ）、OCI Security List もデフォルト拒否のため外部から到達不能であり許容する。VM 内 iptables は Oracle イメージ標準の最終 REJECT ルールを持つが、Tailscale の `ts-input` チェーンが先頭にあり tailnet 経由の到達は機能する（Mac からの疎通確認済み）

## 9. テスト・検証

- **ユニットテスト:** なし（インフラスクリプトのため）
- **runtime acceptance（M0 の完了検証）:**

```bash
# 1. デスクトップが立っている
DISPLAY=:0 xdpyinfo | grep dimensions        # → 1920x1080

# 2. null-sink が存在する
pactl list short sinks | grep kai_speaker

# 3. テスト音声が OBS に乗る（VNC で OBS の音声メーターを目視）
paplay --device=kai_speaker /usr/share/sounds/alsa/Front_Center.wav

# 4. VNC 接続（Mac から）: <server-tailscale-ip>:5900 に VNC クライアントで接続し :0 が見える

# 5. 限定公開でテスト配信 30 分: 映像・音声が YouTube で視聴でき、
#    ドロップフレーム率と CPU 使用率を記録（obs 統計 + `top`）
```

## 10. 実装手順（コーディングエージェント向け）

1. `kai-services/streaming/` に以下を作成: `README.md`（ランブック）、`setup.sh`（冪等セットアップ）、`conf/10-dummy.conf`、`conf/10-kai-speaker.conf`、`units/kai-xorg.service`、`units/kai-desktop.service`、`units/kai-x11vnc.service`
2. サーバー実機（M0）で `setup.sh` を実行し、§9 の検証を通す。実機で判明した修正をスクリプトに反映してコミット（スクリプトが常に実態を表す）
3. OBS の arm64 動作が不安定な場合は `ffmpeg x11grab` 直配信スクリプト（`fallback-ffmpeg.sh`）を追加

**変更してよいファイル:** `kai-services/streaming/**`、`docs/kai/design/streaming.md`。他は変更禁止

## 11. 完了条件（DoD チェックリスト）

- [ ] §9 の 1〜4 がすべて通る
- [ ] 限定公開テスト配信 30 分が安定（ドロップフレーム < 1%、CPU に余裕）
- [ ] VM 再起動後に unit が自動復帰する（linger 確認）
- [ ] ストリームキー・VNC パスワードがリポジトリ・ログに含まれない
- [ ] 実機での修正がスクリプトに反映済み

## 12. 制約・禁止事項

- コアファイル改変禁止（本コンポーネントは hermes に一切触れない）
- 公開ポートを開けない（Tailscale 内のみ）
- ストリームキーをファイル・ログ・設計書・コミットに含めない

## 13. 未決事項

| #   | 事項                                             | 決め方 / 期限                                               |
| --- | ------------------------------------------------ | ----------------------------------------------------------- |
| 1   | OBS arm64 の安定性・エンコード余力（1080p 可否） | M0 実機で計測。不可なら 720p / ffmpeg fallback              |
| 2   | WM を XFCE にするか openbox にするか             | まず XFCE。メモリ/CPU が惜しければ openbox へ               |
| 3   | OBS の常駐 unit 化と自動復旧                     | M4（配信制御 skill）で設計                                  |
| 4   | Wayland 移行の要否                               | 当面 X11 固定（cua-driver / x11vnc / xdotool の互換性優先） |
