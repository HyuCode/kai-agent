"""Issue #77 M-a / M-b: ローカル HTTP サービスの CSRF・URL allowlist 強化の回帰。

  * stream-browser: cmd_open の URL allowlist（https 信頼ドメイン＋自ホストのみ）
  * speechd: POST /say の Origin 検査（ブラウザ由来クロスオリジンを 403）
"""

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relpath: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / relpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --- stream-browser: URL allowlist（M-a）----------------------------------------


@pytest.fixture()
def sb(monkeypatch):
    monkeypatch.delenv("STREAM_BROWSER_ALLOW", raising=False)
    return _load("stream_browser_test", "kai-services/streaming/vm/stream-browser.py")


def test_url_allowed_trusted_https(sb):
    assert sb._url_allowed("https://github.com/seiichi3141/kai-agent/issues/77")
    assert sb._url_allowed("https://raw.githubusercontent.com/x/y/main/z")  # サブドメイン
    # 自ホスト（overlay 等の確認）は http でも可
    assert sb._url_allowed("http://127.0.0.1:8900/overlay/")
    assert sb._url_allowed("http://localhost:8910/")


def test_url_denied(sb):
    assert not sb._url_allowed("https://evil.example.com/phish")
    assert not sb._url_allowed("http://github.com/x")           # 外部は https 必須
    assert not sb._url_allowed("file:///home/kai/.hermes/.env")  # scheme 不可
    assert not sb._url_allowed("javascript:alert(1)")
    assert not sb._url_allowed("https://github.com.evil.com/x")  # サフィックス偽装
    assert not sb._url_allowed("")


def test_url_allow_extra_domain_via_env(monkeypatch):
    monkeypatch.setenv("STREAM_BROWSER_ALLOW", "example.org, docs.rs")
    mod = _load("stream_browser_env_test", "kai-services/streaming/vm/stream-browser.py")
    assert mod._url_allowed("https://example.org/a")
    assert mod._url_allowed("https://docs.rs/tokio")
    assert not mod._url_allowed("https://other.net/a")


# --- speechd: Origin 検査（M-b）-------------------------------------------------


@pytest.fixture()
def spd():
    return _load("speechd_hardening_test", "kai-services/speechd/speechd.py")


def test_origin_forbidden(spd):
    # 正規 producer（narrator の urllib・curl）は Origin を送らない → 許可
    assert spd._origin_forbidden(None, 8900) is False
    # 自ホスト Origin は許可
    assert spd._origin_forbidden("http://127.0.0.1:8900", 8900) is False
    assert spd._origin_forbidden("http://localhost:8900", 8900) is False
    # ブラウザ由来のクロスオリジン（外部ページ・file:// = null）は拒否
    assert spd._origin_forbidden("https://evil.example.com", 8900) is True
    assert spd._origin_forbidden("null", 8900) is True
    assert spd._origin_forbidden("http://127.0.0.1:9999", 8900) is True
