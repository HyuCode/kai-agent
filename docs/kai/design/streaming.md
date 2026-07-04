# streaming 基本設計書

- **ステータス:** 実装済み（M0 検証済み）
- **作成日 / 更新日:** 2026-07-04（v0.3 — 実行環境を UTM VM に変更・実機検証反映）
- **満たす要件:** F-6（ライブ配信管理の基盤部分）、要件 §7.4（Linux 配信スタック）
- **マイルストーン:** M0（インフラ PoC）。obs-websocket による配信制御 skill は M4 で本書に追記する
- **種別:** 独立環境（UTM 仮想マシン）
- **配置:** `kai-services/streaming/vm/`（セットアップスクリプト）

> **変更履歴:** v0.1 = Oracle A1 VM（PoC 済み・停止中）→ v0.2 = Mac 上の Docker（XFCE 版は動作、GNOME 版はコンテナ制約で断念）→ **v0.3 = Mac 上の UTM VM（Ubuntu 24.04 Desktop arm64）**。オーナー要望「本物の GNOME（Ubuntu 標準 UI）」は VM でのみ無改造で成立する。snap が使えるため本物の Chromium も入り、Docker 時代のハック（systemd PID1 / --no-sandbox / Brave 代替）がすべて不要になった。

## 1. 目的と責務

kai の作業デスクトップ（配信映像の実体 = **本物の Ubuntu GNOME デスクトップ**）と、それを YouTube へ届ける経路を提供する。(a) UTM VM 内の Ubuntu Desktop（自動ログイン・X11）、(b) 発話音声を配信に乗せるオーディオ経路（PipeWire null-sink）、(c) OBS によるキャプチャと RTMP 送出。

**やらないこと（非責務）:**

- 発話・字幕の生成と同期（speechd の責務。本コンポーネントは null-sink という「音の通り道」だけ提供する）
- YouTube broadcast の作成・メタデータ管理（F-6 の API 部分。フェーズ 4 以降）
- アバター表示（avatar の責務）
- kai 本体（hermes）のセットアップ（M1。同 VM 内に導入予定）

## 2. 配置と Footprint Ladder

- **選んだ段:** ⑥ 独立環境（hermes 外の VM）
- **理由:** OS レベルのインフラであり、エージェントのツール面には載らない。kai からの操作は M4 で skill（②）として追加する
- **コア改変:** なし

## 3. 構成（実機確定値）

| 項目             | 値                                                                                                                                            |
| ---------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| ハイパーバイザ   | UTM（QEMU バックエンド）。**GPU/OpenGL アクセラレーションはオフ必須**（§8 既知の問題）                                                        |
| ゲスト OS        | Ubuntu 24.04.4 Desktop (arm64)。インストーラーは英語（文字化け回避）→ setup.sh で日本語化                                                     |
| VM リソース      | 6 CPU / 12GB RAM / 64GB ディスク                                                                                                              |
| デスクトップ     | GNOME（Ubuntu 標準）+ 自動ログイン + **X11 固定**（gdm3 で WaylandEnable=false。OBS XSHM / xdotool のため）                                   |
| 解像度           | 1920x1080（autostart の xrandr で毎ログイン適用）                                                                                             |
| 音声             | PipeWire。null-sink `kai_speaker` を**デフォルトシンク**に設定（アプリ音声も自動で配信に乗る）。OBS は default（= kai_speaker.monitor）を取込 |
| ブラウザ         | **Chromium（snap・本物）**。サンドボックス改造不要                                                                                            |
| OBS              | 30.0.2（universe deb）。ソース = 画面キャプチャ (XSHM) Screen 0。GL は llvmpipe（OpenGL 4.5 ソフトウェアレンダリング）                        |
| リモート操作     | Tailscale SSH（`ssh kai@kai-vm`、sudo NOPASSWD）。GUI は UTM ウィンドウ（Mac ⇄ VM クリップボード共有 = spice-vdagent）                        |
| プログラム的操作 | `xdotool`（XAUTHORITY=/run/user/1000/gdm/Xauthority DISPLAY=:0）。スクリーンショットは `ffmpeg -f x11grab`                                    |

## 4. データモデル

- `kai-services/streaming/vm/setup.sh` — VM 内セットアップ（冪等）: apt / snap chromium / Tailscale / null-sink conf（`conf/10-kai-speaker.conf` を `~/.config/pipewire/pipewire.conf.d/` へ）/ gdm 自動ログイン + X11 / GNOME ロック・スリープ無効 / 日本語化
- OBS 設定 — VM 内 `~/.config/obs-studio/`（ストリームキー含む。**VM 外に出さない**）
- VM イメージ — UTM ライブラリ内（`~/Library/Containers/com.utmapp.UTM/`）。スナップショット可

## 5. 処理フロー

1. Mac 起動 → UTM 起動（自動起動設定は M4 で整備）→ VM 起動 → gdm 自動ログイン → GNOME デスクトップ（X11・1920x1080）
2. OBS 起動（M0 は手動 / xdotool。常駐化は M4）→ XSHM で :0 をキャプチャ、default sink monitor を音声取込
3. 「配信開始」→ RTMPS で YouTube へ（xdotool によるリモートクリックでも可能なことを実証済み）
4. 発話音声（M2 以降）: speechd が `paplay --device=kai_speaker` → OBS 経由で配信へ

## 6. エラー処理・縮退

| 失敗モード          | 検知         | 挙動                                       | 復旧                                                           |
| ------------------- | ------------ | ------------------------------------------ | -------------------------------------------------------------- |
| RTMP 切断           | OBS 内部     | OBS が自動再接続。デスクトップと作業は継続 | 自動                                                           |
| OBS クラッシュ      | プロセス消滅 | 配信断。デスクトップは維持                 | M0 は手動再起動。M4 で監視設計                                 |
| VM 停止・Mac 再起動 | 配信全断     | —                                          | UTM の自動起動 + VM 内自動ログインで復帰（手順は M4 で自動化） |
| Mac のスリープ      | 配信全断     | —                                          | Mac のスリープ無効化を運用前提とする                           |

## 7. 設定

| キー                   | 置き場所                                     | 値                                              | 説明                                         |
| ---------------------- | -------------------------------------------- | ----------------------------------------------- | -------------------------------------------- |
| gdm 自動ログイン / X11 | VM 内 `/etc/gdm3/custom.conf`                | AutomaticLogin=kai / WaylandEnable=false        | setup.sh が設定                              |
| 解像度                 | `~/.config/autostart/kai-resolution.desktop` | xrandr 1920x1080                                | setup.sh が設定                              |
| デフォルトシンク       | wireplumber 状態                             | kai_speaker                                     | `pactl set-default-sink kai_speaker`（永続） |
| ストリームキー         | OBS 設定（GUI）                              | —                                               | **秘匿**。ファイル・ログ・設計書に書かない   |
| 映像設定               | OBS                                          | 1080p30 / x264 / 約 2.5Mbps（ウィザード推定値） | 必要なら 6000kbps へ引き上げ検討             |

## 8. セキュリティ・既知の問題

- **秘匿情報:** ストリームキーは VM 内 OBS 設定のみ。配信中に OBS 設定画面を開かない
- **ネットワーク:** VM は NAT（外部からの着信なし）。リモートアクセスは Tailscale SSH のみ
- **既知の問題（実機確定）:**
  - **UTM の GPU アクセラレーション（virgl）を有効にすると OBS が起動しない**。オフ（llvmpipe ソフトウェアレンダリング）が正解。性能は十分（配信中 OBS プロセス CPU 約 50%、30/30 FPS、ドロップ 0%）
  - Ubuntu インストーラーは VM 上で日本語表示が文字化けする → 英語でインストールし setup.sh で日本語化
  - VM 再作成時は Mac の known_hosts から旧ホスト鍵を削除（`ssh-keygen -R kai-vm`）、Tailscale 管理画面で旧ノードを削除

## 9. テスト・検証

- **runtime acceptance（M0）:**

```bash
ssh kai@kai-vm '
  for s in $(loginctl list-sessions --no-legend | awk "{print \$1}"); do loginctl show-session $s -p Type --value; done  # → x11
  export XAUTHORITY=/run/user/1000/gdm/Xauthority DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000
  xrandr | grep current                          # → 1920x1080
  pactl info | grep -i "default sink"            # → kai_speaker
  glxinfo -B | grep renderer                     # → llvmpipe
'
# OBS プレビュー・音声メーターの確認はスクリーンショットで:
# ssh kai@kai-vm 'DISPLAY=:0 XAUTHORITY=/run/user/1000/gdm/Xauthority ffmpeg -f x11grab -video_size 1920x1080 -i :0 -frames:v 1 -y /tmp/s.png'
# 限定公開でテスト配信 30 分: ドロップフレーム率と CPU を記録
```

## 10. 実装手順（コーディングエージェント向け）

1. ~~VM 作成・セットアップ~~（実施済み 2026-07-04）
2. ~~実機で加えた追加設定を `vm/setup.sh` に反映~~（反映済み 2026-07-04）
3. M4: OBS 自動起動・配信開始/停止の skill 化（obs-websocket 有効化を含む）

**変更してよいファイル:** `kai-services/streaming/**`、`docs/kai/design/streaming.md`

## 11. 完了条件（DoD チェックリスト）

- [x] X11 セッション・自動ログイン・1920x1080・kai_speaker・llvmpipe を確認
- [x] OBS 起動・XSHM プレビュー表示・音声メーター動作をスクリーンショットで確認
- [x] 配信開始に成功（2512kbps / 30fps / ドロップ 0%）
- [ ] 限定公開テスト配信 30 分が安定（計測中）
- [x] 実機での追加設定を vm/setup.sh に反映（§10-2）
- [x] ストリームキーがリポジトリ・ログに含まれない

## 12. 制約・禁止事項

- コアファイル改変禁止（本コンポーネントは hermes に一切触れない）
- UTM の GPU アクセラレーションを有効にしない（OBS が起動不能になる）
- ストリームキーをファイル・ログ・設計書・コミットに含めない

## 13. 未決事項

| #   | 事項                                                                                 | 決め方 / 期限                                          |
| --- | ------------------------------------------------------------------------------------ | ------------------------------------------------------ |
| 1   | Mac 再起動時の全自動復帰（UTM 自動起動 → VM 自動起動 → OBS 自動起動 → 配信自動開始） | M4（配信制御 skill）で設計                             |
| 2   | ビットレート（現状ウィザード推定 ~2.5Mbps）を 1080p30 推奨の 6000kbps へ上げるか     | テスト配信の画質を見て判断                             |
| 3   | 旧環境の後始末（Oracle A1 の terminate / Docker volume・イメージ削除）               | M0 完了後にオーナー判断                                |
| 4   | kai 本体（hermes）を VM 内に置くか Mac 側に置くか                                    | M1 設計時に決定（VM 内が有力: デスクトップ操作と同居） |
