# koe-bridge

hermes の auxiliary LLM を OpenAI 互換 API として中継する薄い HTTP サーバー。
Mac 側の aquestalk-server が行う koe 生成から、hermes の auxiliary クライアントを
OpenAI 互換の `POST /v1/chat/completions` として呼ぶための橋。

`koe_bridge.py` の実装上、リクエストは `agent.auxiliary_client.call_llm()` に渡され、
`KOE_BRIDGE_TASK`（既定 `koe`）の per-task 設定で解決される。`auxiliary.koe.*` が
未設定なら auxiliary クライアントの `auto` 解決に入り、メインプロバイダ +
メインモデルを先頭にした解決チェーンを使う。Codex OAuth モデルを生の OpenAI
互換エンドポイントとして直接呼べないため、このサーバーが hermes 経由で包む。

aquestalk-server 側では `.env` に次を設定する。

```bash
KOE_LLM_BASE_URL=http://<kai-vm の Tailscale IP>:8930/v1
KOE_LLM_API_KEY=<KOE_BRIDGE_TOKEN と同じ値>
```

## 依存

- Python 3
- hermes リポジトリ直下の `.venv`（`install.sh` が `.venv/bin/python3` を使う）
- hermes 本体の Python モジュール（`koe_bridge.py` がリポジトリ直下を import パスに追加する）

## セットアップ（VM 上）

systemd --user サービスとして登録する。

```bash
bash ~/kai-agent/kai-services/koe-bridge/install.sh
```

`install.sh` が行うこと:

1. リポジトリ直下の `.venv/bin/python3` が実行可能か確認
2. `.venv/bin/python3 -m py_compile koe_bridge.py` で構文確認
3. `koe-bridge.service` の `@REPO_DIR@` を実パスに置換して
   `~/.config/systemd/user/koe-bridge.service` に配置
4. `systemctl --user daemon-reload`
5. `systemctl --user enable --now koe-bridge.service`

## 環境変数

| 変数               | デフォルト  | 意味                                                             |
| ------------------ | ----------- | ---------------------------------------------------------------- |
| `KOE_BRIDGE_PORT`  | `8930`      | HTTP サーバーの listen ポート                                    |
| `KOE_BRIDGE_BIND`  | `127.0.0.1` | HTTP サーバーの bind アドレス                                    |
| `KOE_BRIDGE_TASK`  | `koe`       | `call_llm(task=...)` に渡す auxiliary task 名                    |
| `KOE_BRIDGE_TOKEN` | （空）      | 共有トークン。設定時 POST は `Authorization: Bearer <値>` を照合 |

**認証（Issue #77 C1）**: このサーバーはオーナー課金の LLM への汎用リレーなので、
非 loopback bind（Tailscale 越し利用）には `KOE_BRIDGE_TOKEN` が必須。トークン無しで
`KOE_BRIDGE_BIND` を loopback 以外にすると起動を拒否する（fail-closed）。トークンは
unit に直書きせず `~/.config/kai/koe-bridge.env` に置き、`EnvironmentFile` で読む
（`koe-bridge.service` のコメント参照）。Tailscale ACL で 8930 を Mac ノード限定に
するのを推奨（多層防御）。

## API

### `GET /health`

現在の task 名を返す。

```text
200 {"ok": true, "task": "koe"}
```

### `POST /v1/chat/completions`

OpenAI 互換の chat completions 形式で受け取り、auxiliary クライアントへ中継する。
`/chat/completions` も同じ処理に入る。

入力で使う項目:

| 項目          | 意味                                            |
| ------------- | ----------------------------------------------- |
| `messages`    | 必須。空でない配列でなければ `500` エラー       |
| `max_tokens`  | 省略時 `500`。`int()` して `call_llm()` に渡す  |
| `temperature` | 省略時 `0`。`float()` して `call_llm()` に渡す  |
| `model`       | レスポンスの `model` に文字列化してそのまま入る |

成功時のレスポンス形式:

```json
{
  "object": "chat.completion",
  "model": "",
  "choices": [
    {
      "index": 0,
      "message": { "role": "assistant", "content": "..." },
      "finish_reason": "stop"
    }
  ]
}
```

`messages` 不正、auxiliary 呼び出し失敗、空応答などの例外は
`500 {"error":"..."}` で返す。未対応パスは `404 {"error":"not found"}`。

## モデル解決

`koe_bridge.py` は `call_llm()` に `task=KOE_BRIDGE_TASK` だけを渡し、provider や model
を直接指定しない。そのため `agent.auxiliary_client` の解決順に従う。

1. `config.yaml` の `auxiliary.<task>.provider` / `model` / `base_url` / `api_key` /
   `api_mode` を読む（既定 task は `auxiliary.koe.*`）
2. per-task provider が `auto` または未設定なら `auto` 解決
3. `auto` はメインプロバイダ + メインモデルを先頭にした auxiliary の解決チェーンを使う

`koe` 生成で `gpt-5.4-mini` などの特定モデルを使う場合は、`config.yaml` の
`auxiliary.koe.*` に設定する。未設定ならメインプロバイダ + メインモデルに
解決される。

## 手動検証（curl）

VM 上でサービスが起動している前提。

```bash
# 起動確認
curl -s http://127.0.0.1:8930/health
# => {"ok": true, "task": "koe"}

# chat completions 互換 API
curl -s -X POST http://127.0.0.1:8930/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"user","content":"短く返事して"}],"max_tokens":50,"temperature":0}'
# => {"object":"chat.completion","model":"","choices":[...]}

# messages が空の場合はエラー
curl -s -X POST http://127.0.0.1:8930/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"messages":[]}'
# => {"error":"messages is required"}
```

## 運用コマンド

```bash
systemctl --user status koe-bridge.service
journalctl --user -u koe-bridge.service -f
systemctl --user restart koe-bridge.service
systemctl --user stop koe-bridge.service
```

## 制約

- 対応している生成 API は `POST /v1/chat/completions` と `/chat/completions` のみ
- ストリーミング応答は実装していない
- `GET /health` 以外の GET は `404` を返す
- 既定 bind は `127.0.0.1`（loopback）。Tailscale 越しに使う場合は
  `KOE_BRIDGE_BIND` を広げ、`KOE_BRIDGE_TOKEN` を必ず設定する
- `log_message()` は何もしないため、`http.server` の通常アクセスログは出さない
