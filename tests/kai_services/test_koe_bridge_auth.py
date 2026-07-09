"""Issue #77 C1: koe-bridge の共有トークン認証と fail-closed 起動の回帰。

koe-bridge はオーナー課金の LLM への汎用リレー。認証なしで非 loopback に
公開されると踏み台・課金枯渇になるため:
  * KOE_BRIDGE_TOKEN 設定時は POST に Authorization: Bearer を要求（401）
  * /health は認証なしで応答（監視用・機微情報なし）
  * 非 loopback bind ＋ トークン未設定は起動拒否（fail-closed）
"""

import http.client
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_bridge():
    spec = importlib.util.spec_from_file_location(
        "koe_bridge_test", REPO_ROOT / "kai-services" / "koe-bridge" / "koe_bridge.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def bridge(monkeypatch):
    mod = _load_bridge()
    monkeypatch.setattr(mod, "_complete", lambda body: "ok-text")
    server = ThreadingHTTPServer(("127.0.0.1", 0), mod._Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield mod, server.server_address[1]
    server.shutdown()
    server.server_close()


def _request(port, method="POST", path="/v1/chat/completions", token=None):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps({"messages": [{"role": "user", "content": "x"}]}) if method == "POST" else None
    conn.request(method, path, body, headers)
    resp = conn.getresponse()
    data = json.loads(resp.read() or b"{}")
    conn.close()
    return resp.status, data


def test_no_token_configured_allows_loopback_post(bridge, monkeypatch):
    mod, port = bridge
    monkeypatch.setattr(mod, "TOKEN", "")
    status, data = _request(port)
    assert status == 200
    assert data["choices"][0]["message"]["content"] == "ok-text"


def test_token_required_when_configured(bridge, monkeypatch):
    mod, port = bridge
    monkeypatch.setattr(mod, "TOKEN", "sharedtoken123")
    assert _request(port)[0] == 401  # ヘッダなし
    assert _request(port, token="wrong")[0] == 401  # 不一致
    status, data = _request(port, token="sharedtoken123")
    assert status == 200
    assert data["choices"][0]["message"]["content"] == "ok-text"


def test_health_is_open_even_with_token(bridge, monkeypatch):
    mod, port = bridge
    monkeypatch.setattr(mod, "TOKEN", "sharedtoken123")
    status, data = _request(port, method="GET", path="/health")
    assert status == 200
    assert data["ok"] is True


def test_main_refuses_nonloopback_bind_without_token(monkeypatch):
    mod = _load_bridge()
    monkeypatch.setattr(mod, "BIND", "0.0.0.0")
    monkeypatch.setattr(mod, "TOKEN", "")
    with pytest.raises(SystemExit) as exc:
        mod.main()
    assert exc.value.code == 2


def test_is_loopback(monkeypatch):
    mod = _load_bridge()
    assert mod._is_loopback("127.0.0.1")
    assert mod._is_loopback("localhost")
    assert not mod._is_loopback("0.0.0.0")
    assert not mod._is_loopback("100.125.189.49")
