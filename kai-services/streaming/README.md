# kai-services/streaming — M0 ランブック

kai の配信スタック（永続 Linux デスクトップ + 音声経路 + OBS + VNC）。**現行の実行環境はオーナーの Mac 上の Docker コンテナ**（`docker/`）。設計は `docs/kai/02-architecture/02-streaming.md`、検証基準は同 §9。

> **旧構成（温存）:** Oracle A1 VM 向けの `setup.sh` / `units/` / `oracle/` は復帰オプションとして残している（A1 インスタンスは停止中）。VM 版の手順・トラブルシュートは git 履歴の本 README 旧版を参照。

## 0. 前提（オーナーが事前に済ませること）

| #   | 項目                                                                      | 備考                                   |
| --- | ------------------------------------------------------------------------- | -------------------------------------- |
| 1   | Docker Desktop が起動していること（Mac ログイン時に自動起動を推奨）       | VM リソース割当は Settings → Resources |
| 2   | Mac のスリープ無効化（System Settings → Energy、または `caffeinate`）     | 配信の常時性は Mac の稼働に依存        |
| 3   | YouTube: チャンネルの**ライブ配信を有効化**（初回は有効化後 24 時間待ち） | 最初に申請しておく                     |

## 1. セットアップ

```bash
cd kai-services/streaming/docker
echo "VNC_PASSWORD=<パスワード>" > .env   # 初回のみ（.env はコミットされない）
docker compose up -d --build
```

## 2. 検証（設計 §9 の 1〜5）

```bash
docker compose ps    # → healthy（起動から1分後）
docker exec kai-streaming su kai -c "DISPLAY=:0 xdpyinfo | grep dimensions"          # → 1920x1080
docker exec kai-streaming su kai -c "XDG_RUNTIME_DIR=/run/user/1000 pactl list short sinks"   # → kai_speaker
docker exec kai-streaming su kai -c "XDG_RUNTIME_DIR=/run/user/1000 sh -c 'ffmpeg -f lavfi -i sine=frequency=440:duration=2 -y /tmp/t.wav 2>/dev/null && paplay --device=kai_speaker /tmp/t.wav'"
```

この Mac の VNC クライアント（Finder → ⌘K → `vnc://127.0.0.1:5901`）で XFCE デスクトップが見えること（ホスト側 5901: Mac 自身の画面共有が 5900 を使用しているため）。

## 3. OBS 初期設定（VNC 内で手動・初回のみ）

1. XFCE のターミナルで `obs` を起動
2. ソース: **「画面キャプチャ (XSHM)」**→ Screen 0（⚠️「ウィンドウキャプチャ (Xcomposite)」はヘッドレス X で黒くなる。使わない）
3. 音声: 設定 → 音声 → デスクトップ音声 = `Monitor of kai_speaker`
4. 配信: サービス = YouTube、**ストリームキーを設定**（キーは画面共有中・配信中に表示しない）
5. 出力: x264 / veryfast / 1080p30 / 6000kbps
6. ツール → obs-websocket 設定: 有効化、ポート 4455、認証パスワード設定
7. 設定は `kai-home` volume に永続化される（コンテナ再作成でも維持）

## 4. テスト配信（限定公開・30 分）

1. YouTube Studio で限定公開のライブ配信を作成し、OBS で「配信開始」
2. 別端末で視聴し、映像・音声（`paplay` テスト音）を確認
3. 記録する: OBS 統計のドロップフレーム率 / `docker stats` と Activity Monitor の CPU / 体感遅延
4. 30 分安定したら M0 の DoD（設計 §11）をチェック

## 5. トラブルシュート

| 症状                   | 対処                                                                                                      |
| ---------------------- | --------------------------------------------------------------------------------------------------------- |
| コンテナが unhealthy   | `docker compose logs` と `docker exec kai-streaming supervisorctl status` で失敗プロセス特定              |
| 音が OBS に乗らない    | 検証 §2 の pactl / paplay で切り分け → OBS のデスクトップ音声デバイスを再選択                             |
| CPU が高い             | Docker Desktop → Resources で CPU 割当を増やす（M4 Pro は 12 コア）。OBS を 720p30 へ                     |
| VNC に繋がらない       | `docker compose ps` でポート公開確認。パスワードは `docker/.env`                                          |
| OBS のプレビューが黒い | ソースが「ウィンドウキャプチャ (Xcomposite)」になっていないか確認 → 「画面キャプチャ (XSHM)」に置き換える |

## 実機検証後のルール

実機で加えた修正は必ずこのディレクトリのファイルに反映してコミットする（構成ファイルが常に実態を表す）。
