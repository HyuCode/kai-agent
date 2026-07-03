# streaming 基本設計書

- **ステータス:** ドラフト（v0.2 — 実行環境を Mac 上の Docker に変更）
- **作成日 / 更新日:** 2026-07-04
- **満たす要件:** F-6（ライブ配信管理の基盤部分）、要件 §7.4（Linux 配信スタック）
- **マイルストーン:** M0(インフラ PoC)。obs-websocket による配信制御 skill は M4 で本書に追記する
- **種別:** 独立プロセス（Docker コンテナ）
- **配置:** `kai-services/streaming/docker/`

> **v0.2 の変更（2026-07-04、オーナー決定）:** 実行環境を Oracle A1 VM から**オーナーの Mac（M4 Pro / 12 コア / 24GB）上の Docker コンテナ**に変更。理由は A1 の CPU 力不足懸念（ソフトウェアレンダリング + x264 の同居）。Docker on Mac も GPU パススルーはないが、M4 Pro の CPU 性能で十分吸収できる。OCI 用の VM セットアップ（`setup.sh` / `units/` / `oracle/`）は復帰オプションとして温存する（A1 インスタンスは停止済み）。

## 1. 目的と責務

kai の作業デスクトップ（配信映像の実体）と、それを YouTube へ届ける経路を提供する。具体的には (a) コンテナ内の永続 X デスクトップ（GPU 不要のソフトウェアレンダリング）、(b) 発話音声を配信に乗せるオーディオ経路、(c) OBS によるキャプチャと RTMP 送出、(d) オーナー用リモート GUI（VNC）。

**やらないこと（非責務）:**

- 発話・字幕の生成と同期（speechd の責務。本コンポーネントは null-sink という「音の通り道」だけ提供する）
- YouTube broadcast の作成・メタデータ管理（F-6 の API 部分。フェーズ 4 以降）
- アバター表示（avatar の責務）
- kai 本体（hermes）のセットアップ（M1）

## 2. 配置と Footprint Ladder

- **選んだ段:** ⑥ 独立プロセス（hermes 外の配信スタック、Docker コンテナ）
- **理由:** OS レベルのインフラ（X サーバー・音声・OBS）であり、エージェントのツール面には載らない。kai からの操作は M4 で skill（②）として追加する
- **コア改変:** なし

## 3. インターフェース

### 3.1 提供するインターフェース

| IF                                 | 形式                                         | 内容                                                                                                                       |
| ---------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `DISPLAY=:0`                       | X11（コンテナ内）                            | 1920x1080 の永続デスクトップ。kai のブラウザ・エディタ等はここに表示する                                                   |
| `kai_speaker`                      | PulseAudio null-sink（コンテナ内）           | speechd が WAV を再生する出力先。OBS がその monitor を音声ソースとして取り込む                                             |
| VNC（ホスト 5901 → コンテナ 5900） | RFB（**Mac の 127.0.0.1 に publish**）       | オーナーのリモート GUI（:0 と同一画面）。パスワード認証。ホスト側 5901 なのは Mac 自身の画面共有が 5900 を使用しているため |
| obs-websocket :4455                | WebSocket（**Mac の 127.0.0.1 に publish**） | M4 の配信制御 skill と speechd の字幕更新が使用                                                                            |

他端末（MacBook 等）から VNC を見る場合は Mac の Tailscale 経由（`tailscale serve` またはトンネル）。ポートを LAN・インターネットに直接公開しない。

### 3.2 依存するインターフェース

| 依存先                                           | 形式 | 用途     | 不達時の挙動                                                      |
| ------------------------------------------------ | ---- | -------- | ----------------------------------------------------------------- |
| YouTube RTMP (`rtmp://a.rtmp.youtube.com/live2`) | RTMP | 配信送出 | OBS が再接続リトライ。デスクトップと kai の作業は継続             |
| Docker Desktop（Mac 常駐）                       | —    | 実行基盤 | Mac 再起動時は Docker 起動 → `restart: unless-stopped` で自動復帰 |

## 4. データモデル

コンテナイメージ（`docker/Dockerfile`、Debian trixie ベース）+ 設定ファイル:

- `conf/10-dummy.conf` — Xorg dummy ドライバで 1920x1080（VM 版と共通）
- `docker/pulse-kai-speaker.pa` — null-sink `kai_speaker` の定義（`/etc/pulse/default.pa.d/`）
- `docker/supervisord.conf` — プロセス起動順（xorg → pulseaudio → desktop → x11vnc）
- `docker/docker-compose.yml` — ポート公開（127.0.0.1 のみ）・`kai-home` volume（OBS 設定等を永続化）
- `docker/.env` — `VNC_PASSWORD`（**コミットしない**。`.gitignore` 済み）
- OBS プロファイル/シーン — GUI で作成し volume 内 `~/.config/obs-studio/` に永続化。**ストリームキーを含むためコンテナ外へ出さない**

**ベースイメージの選定理由:** Ubuntu 24.04 は chromium / obs-studio が snap 配布でコンテナ内で扱えないため、deb で揃う **Debian trixie** を採用（arm64 対応）。

## 5. 処理フロー

起動順（supervisord の priority で制御）:

1. entrypoint（root）: `/tmp/.X11-unix`・`/run/user/1000` 準備、システム DBus 起動、VNC パスワード生成（`VNC_PASSWORD` env、既存ファイル優先）
2. `xorg`（priority 10）: `Xorg :0 -ac -noreset -nolisten tcp`（dummy ドライバ、kai ユーザー）
3. `pulseaudio`（15）: null-sink `kai_speaker` を含めて起動
4. `desktop`（20）: X の起動を待って `dbus-launch startxfce4`
5. `x11vnc`（30）: :0 にアタッチ、`-rfbauth` 認証
6. OBS: M0 では VNC から手動起動・手動設定（画面キャプチャ(:0) + `kai_speaker` monitor + ストリームキー + obs-websocket 有効化）。常駐化は M4

## 6. エラー処理・縮退

| 失敗モード             | 検知                       | 挙動                                   | 復旧                                                     |
| ---------------------- | -------------------------- | -------------------------------------- | -------------------------------------------------------- |
| コンテナ内プロセス落ち | supervisord                | 個別に自動再起動                       | `autorestart=true`                                       |
| コンテナ自体の停止     | Docker                     | 配信断                                 | `restart: unless-stopped`。healthcheck（xdpyinfo）で検知 |
| RTMP 切断              | OBS 内部                   | OBS が自動再接続。kai の作業は影響なし | 自動                                                     |
| OBS クラッシュ         | プロセス消滅               | 配信断。デスクトップは維持             | M0 は手動再起動（VNC から）。M4 で監視を設計             |
| Mac のスリープ         | 配信全断                   | —                                      | Mac のスリープ無効化を運用前提とする（§8 運用注意）      |
| エンコード性能不足     | CPU 飽和・ドロップフレーム | 解像度/ビットレートを下げる            | M4 Pro では想定薄。Docker VM の CPU 割当も調整可         |

## 7. 設定

| キー                      | 置き場所             | デフォルト                           | 説明                                                       |
| ------------------------- | -------------------- | ------------------------------------ | ---------------------------------------------------------- |
| 解像度                    | `conf/10-dummy.conf` | 1920x1080                            | 配信解像度と一致させる                                     |
| `VNC_PASSWORD`            | `docker/.env`        | —（必須）                            | コミットしない                                             |
| ポート公開                | `docker-compose.yml` | 127.0.0.1:5901→5900 / 127.0.0.1:4455 | Mac の localhost のみ                                      |
| RTMP URL / ストリームキー | OBS 設定（GUI）      | —                                    | **ストリームキーは秘匿**。ファイル・ログ・設計書に書かない |
| 映像設定                  | OBS 設定             | 1080p30 / x264 veryfast / 6000kbps   | M0 の実測で確定                                            |
| Docker VM リソース        | Docker Desktop 設定  | 現状 8 CPU / 8GB                     | 不足時に増やす（M4 Pro は 12 コア / 24GB）                 |

## 8. セキュリティ

- **秘匿情報:** YouTube ストリームキー（OBS 設定内のみ、volume に閉じる）、VNC パスワード（`docker/.env`、gitignore 済み）。いずれもリポジトリ・ログ・配信画面に出さない。OBS の設定画面を配信中に開かない
- **入力の信頼境界:** なし（外部入力を受けない）
- **ネットワーク:** コンテナのポートは **Mac の 127.0.0.1 にのみ** publish。LAN・インターネットへの公開なし。他端末からは Mac の Tailscale 経由。X ソケットは `-ac`（アクセス制御なし）だがコンテナ内に閉じている
- **運用注意:** Mac のスリープを無効化（System Settings → Energy、または `caffeinate`）。配信の常時性は Mac の稼働に依存する

## 9. テスト・検証

- **ユニットテスト:** なし（インフラのため）
- **runtime acceptance（M0 の完了検証）:**

```bash
cd kai-services/streaming/docker
docker compose up -d --build

# 1. コンテナ健全性
docker compose ps                 # → healthy（起動から1分後）

# 2. デスクトップが立っている
docker exec kai-streaming su kai -c "DISPLAY=:0 xdpyinfo | grep dimensions"   # → 1920x1080

# 3. null-sink が存在する
docker exec kai-streaming su kai -c "XDG_RUNTIME_DIR=/run/user/1000 pactl list short sinks"  # → kai_speaker

# 4. テスト音が再生できる（OBS 設定後はメーターで目視）
docker exec kai-streaming su kai -c "XDG_RUNTIME_DIR=/run/user/1000 sh -c 'ffmpeg -f lavfi -i sine=frequency=440:duration=2 -y /tmp/t.wav 2>/dev/null && paplay --device=kai_speaker /tmp/t.wav'"

# 5. VNC 接続（この Mac から）: vnc://127.0.0.1:5901

# 6. 限定公開でテスト配信 30 分: 映像・音声が YouTube で視聴でき、
#    ドロップフレーム率と CPU（docker stats / Activity Monitor）を記録
```

## 10. 実装手順（コーディングエージェント向け）

1. `kai-services/streaming/docker/` に Dockerfile / docker-compose.yml / supervisord.conf / entrypoint.sh / pulse-kai-speaker.pa / .gitignore を作成
2. ローカルでビルド・起動し、§9 の 1〜5 を通す。実機で判明した修正をファイルに反映してコミット
3. OBS を VNC 内で初期設定（オーナー、ストリームキー投入）→ §9-6 のテスト配信

**変更してよいファイル:** `kai-services/streaming/**`、`docs/kai/design/streaming.md`。他は変更禁止

## 11. 完了条件（DoD チェックリスト）

- [ ] §9 の 1〜5 がすべて通る
- [ ] 限定公開テスト配信 30 分が安定（ドロップフレーム < 1%、CPU に余裕）
- [ ] コンテナ再作成（`docker compose down && up -d`）後も OBS 設定が volume で維持される
- [ ] ストリームキー・VNC パスワードがリポジトリ・ログに含まれない
- [ ] 実機での修正がファイルに反映済み

## 12. 制約・禁止事項

- コアファイル改変禁止（本コンポーネントは hermes に一切触れない）
- コンテナのポートを 127.0.0.1 以外に publish しない
- ストリームキーをファイル・ログ・設計書・コミットに含めない

## 13. 未決事項

| #   | 事項                                                          | 決め方 / 期限                                              |
| --- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| 1   | 1080p30 での CPU 実測（Docker VM 8 CPU 割当で足りるか）       | M0 テスト配信で計測。不足なら Docker Desktop の割当増      |
| 2   | 他端末からの VNC 視聴経路（tailscale serve 等）               | 必要になったら設計（当面はこの Mac から直接）              |
| 3   | OBS の常駐・自動配信開始                                      | M4（配信制御 skill）で設計                                 |
| 4   | Mac 再起動時の全自動復帰（Docker Desktop 自動起動 + compose） | M4 までに運用手順化                                        |
| 5   | OCI（Oracle A1）への復帰判断                                  | Mac 運用に支障が出た場合。VM 版資産は温存済み・A1 は停止中 |
