"""Issue #77 H-b: 三層マスク（kai_narrator / kai_trace / speechd）の強化の回帰。

検証すること:
  * env 秘密層が os.environ だけでなく ~/.hermes/.env 直読みでも収集される
    （hermes は資格情報を環境変数に載せないため、従来は実行時に空だった）
  * 追加トークンパターン（AIza / AKIA / JWT / URL 埋め込み認証 / RTMP /
    YouTube ストリームキー形）がマスクされる
  * kebab-case 識別子（数字なし）を YouTube キー形として誤マスクしない

3 実装は plugin 単体完結の原則で意図的なコピー。このテストが 3 箇所の同期を守る。
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _load_narrator():
    if "hermes_plugins" not in sys.modules:
        ns = types.ModuleType("hermes_plugins")
        ns.__path__ = []
        sys.modules["hermes_plugins"] = ns
    return _load_module("hermes_plugins.kai_narrator_mask_test",
                        REPO_ROOT / "plugins" / "kai_narrator" / "__init__.py")


def _load_trace():
    if "hermes_plugins" not in sys.modules:
        ns = types.ModuleType("hermes_plugins")
        ns.__path__ = []
        sys.modules["hermes_plugins"] = ns
    return _load_module("hermes_plugins.kai_trace_mask_test",
                        REPO_ROOT / "plugins" / "kai_trace" / "__init__.py")


def _load_speechd():
    return _load_module("speechd_mask_test",
                        REPO_ROOT / "kai-services" / "speechd" / "speechd.py")


def _point_at_dotenv(mod, monkeypatch, dotenv: Path):
    """各実装の .env 解決先をテスト用ファイルへ向ける。"""
    if hasattr(mod, "_dotenv_path"):  # kai_narrator
        monkeypatch.setattr(mod, "_dotenv_path", lambda: str(dotenv))
    elif hasattr(mod, "DOTENV_FILE"):  # speechd
        monkeypatch.setattr(mod, "DOTENV_FILE", dotenv)
    else:  # kai_trace（get_hermes_home()/.env を読む）
        monkeypatch.setattr(mod, "get_hermes_home", lambda: dotenv.parent)


@pytest.fixture(params=["narrator", "trace", "speechd"])
def mask_mod(request):
    return {"narrator": _load_narrator,
            "trace": _load_trace,
            "speechd": _load_speechd}[request.param]()


def test_collects_secrets_from_dotenv_file(mask_mod, monkeypatch, tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(
        "# comment\n"
        "OPENAI_API_KEY=filesecretvalue123\n"
        "QUOTED_TOKEN='quotedsecret456'\n"
        "SHORT_KEY=abc12\n"          # 6字未満は集めない（誤マスク防止）
        "SOME_BASE_URL=http://example.test/v1\n"  # 秘密っぽくないキー名は集めない
        "broken line without equals\n",
        encoding="utf-8")
    _point_at_dotenv(mask_mod, monkeypatch, dotenv)
    secrets = mask_mod._collect_env_secrets()
    assert "filesecretvalue123" in secrets
    assert "quotedsecret456" in secrets  # クォートは剥がす
    assert "abc12" not in secrets
    assert "http://example.test/v1" not in secrets
    # 集めた値が実際にマスクされる
    monkeypatch.setattr(mask_mod, "_ENV_SECRETS", secrets)
    assert "filesecretvalue123" not in mask_mod._mask("key is filesecretvalue123 ok")


def test_collects_secrets_from_environ_too(mask_mod, monkeypatch, tmp_path):
    _point_at_dotenv(mask_mod, monkeypatch, tmp_path / "missing.env")  # .env 無しでも動く
    monkeypatch.setenv("MY_TEST_TOKEN", "environsecret789")
    secrets = mask_mod._collect_env_secrets()
    assert "environsecret789" in secrets


@pytest.mark.parametrize("leak", [
    "AIzaSyA1234567890abcdefghijklm",                     # Google API key
    "AKIAIOSFODNN7EXAMPLE",                               # AWS access key ID
    "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.sflKxwRJSM",  # JWT
    "postgres://kai:hunter2secret@db.internal:5432/kai",  # URL 埋め込み認証情報
    "rtmp://a.rtmp.youtube.com/live2/abcd-1234-efgh-5678",  # RTMP URL
    "abcd-1234-efgh-5678-ijkl",                           # YouTube ストリームキー形
])
def test_new_token_patterns_are_masked(mask_mod, leak):
    masked = mask_mod._mask(f"leaked: {leak} end")
    assert leak not in masked
    assert "«redacted»" in masked


def test_kebab_identifiers_are_not_masked(mask_mod):
    # 数字を含まない kebab-case 識別子は YouTube キー形として誤マスクしない
    text = "auto-init-repo-sync を feature-flag-name-here で切り替える"
    assert mask_mod._mask(text) == text
