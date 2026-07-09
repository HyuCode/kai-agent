#!/usr/bin/env python3
"""koe-bridge — hermes の auxiliary LLM を OpenAI 互換 API として中継する。

目的: aquestalk-server（Mac・Node）の koe 生成に Codex の gpt-5.5 を使う。
gpt-5.5 は Codex OAuth 経由でしか呼べず、生の OpenAI 互換エンドポイントが
存在しないため、hermes の auxiliary クライアント（メインプロバイダ =
OpenAI Codex を解決できる）を薄い HTTP サーバーで包む。

- kai-vm 上で hermes の venv を使って常駐する（install.sh 参照）
- 対応 API は POST /v1/chat/completions のみ（koe 生成に必要な最小限）
- per-task 設定は auxiliary.koe.*（config.yaml）。未設定ならメイン
  プロバイダ + メインモデル（= Codex / gpt-5.5）に解決される

セキュリティ（Issue #77 C1）: このサーバーはオーナー課金の LLM への汎用リレー
なので、認証なしで LAN/Tailnet に公開してはならない（踏み台・課金枯渇）。
- bind の既定は 127.0.0.1。Tailscale 越しに使う場合のみ KOE_BRIDGE_BIND を
  広げ、そのときは KOE_BRIDGE_TOKEN（共有トークン）が必須（無ければ起動拒否）
- KOE_BRIDGE_TOKEN 設定時、POST は `Authorization: Bearer <token>` を照合する

使い方（Mac 側 aquestalk-server の .env）:
  KOE_LLM_BASE_URL=http://<kai-vm の Tailscale IP>:8930/v1
  KOE_LLM_API_KEY=<KOE_BRIDGE_TOKEN と同じ値>
"""

from __future__ import annotations

import hmac
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

# hermes（リポジトリ直下）を import パスに載せる（venv は hermes のものを使う）
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

PORT = int(os.environ.get("KOE_BRIDGE_PORT", "8930"))
BIND = os.environ.get("KOE_BRIDGE_BIND", "127.0.0.1")  # 既定 loopback（#77 C1）
TASK = os.environ.get("KOE_BRIDGE_TASK", "koe")
TOKEN = os.environ.get("KOE_BRIDGE_TOKEN", "").strip()


def _is_loopback(bind: str) -> bool:
    return bind in ("127.0.0.1", "::1", "localhost")


def _complete(body: dict) -> str:
    """OpenAI 互換リクエストを auxiliary クライアントで実行しテキストを返す。"""
    from agent.auxiliary_client import call_llm, extract_content_or_reasoning

    messages = body.get("messages") or []
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages is required")
    resp = call_llm(
        task=TASK,
        messages=messages,
        max_tokens=int(body.get("max_tokens") or 500),
        temperature=float(body.get("temperature") or 0),
    )
    text = extract_content_or_reasoning(resp) or ""
    if not text:
        raise ValueError("empty completion")
    return text


class _Handler(BaseHTTPRequestHandler):
    server_version = "koe-bridge/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        pass

    def _send_json(self, obj: dict, code: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        """共有トークン照合（KOE_BRIDGE_TOKEN 設定時のみ有効。定数時間比較）。"""
        if not TOKEN:
            return True  # トークン未設定は loopback bind 限定（main で強制）
        auth = self.headers.get("Authorization") or ""
        return hmac.compare_digest(auth, f"Bearer {TOKEN}")

    def do_GET(self) -> None:  # noqa: N802 - http.server の規約
        if self.path == "/health":
            self._send_json({"ok": True, "task": TASK})
            return
        self._send_json({"error": "not found"}, code=404)

    def do_POST(self) -> None:  # noqa: N802 - http.server の規約
        if self.path.rstrip("/") not in ("/v1/chat/completions", "/chat/completions"):
            self._send_json({"error": "not found"}, code=404)
            return
        if not self._authorized():
            self._send_json({"error": "unauthorized"}, code=401)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(length) or b"{}")
            text = _complete(body)
            self._send_json({
                "object": "chat.completion",
                "model": str(body.get("model") or ""),
                "choices": [{
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop",
                }],
            })
        except Exception as e:  # クライアント（aquestalk-server）側がフォールバックする
            self._send_json({"error": str(e)}, code=500)


def main() -> None:
    if not _is_loopback(BIND) and not TOKEN:
        # fail-closed: 認証なしの非 loopback 公開はオーナー課金 LLM の踏み台になる
        print(
            f"[koe-bridge] ERROR: KOE_BRIDGE_BIND={BIND} (non-loopback) には "
            "KOE_BRIDGE_TOKEN が必須です（Issue #77 C1）。起動を中止します。",
            file=sys.stderr,
        )
        sys.exit(2)
    server = ThreadingHTTPServer((BIND, PORT), _Handler)
    print(f"[koe-bridge] listening on http://{BIND}:{PORT} "
          f"(task: {TASK}, auth: {'token' if TOKEN else 'loopback-only'})")
    server.serve_forever()


if __name__ == "__main__":
    main()
