"""Tests for the kai_ide plugin (plugins/kai_ide/).

VSCode ブリッジ（127.0.0.1:8920）への HTTP をスタブして、状態系ツール
（vscode_state / vscode_open / vscode_close_tab）の handler を検証する。
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest


def _load_plugin():
    repo_root = Path(__file__).resolve().parents[2]
    plugin_dir = repo_root / "plugins" / "kai_ide"
    spec = importlib.util.spec_from_file_location(
        "hermes_plugins.kai_ide", plugin_dir / "__init__.py",
        submodule_search_locations=[str(plugin_dir)],
    )
    if "hermes_plugins" not in sys.modules:
        ns = types.ModuleType("hermes_plugins")
        ns.__path__ = []
        sys.modules["hermes_plugins"] = ns
    mod = importlib.util.module_from_spec(spec)
    mod.__package__ = "hermes_plugins.kai_ide"
    sys.modules["hermes_plugins.kai_ide"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def ide(monkeypatch):
    mod = _load_plugin()
    monkeypatch.setattr(mod, "_plugin_cfg", lambda: {})
    return mod


def _stub_bridge(ide, monkeypatch, response=None, fail=False):
    """_bridge_request をスタブし、送信内容を記録する。"""
    sent = {}

    def _fake(method, path, body=None, timeout=3.0):
        sent["method"] = method
        sent["path"] = path
        sent["body"] = body
        if fail:
            raise RuntimeError("VSCode ブリッジに接続できません（配信外か拡張未起動）: boom")
        return response or {}

    monkeypatch.setattr(ide, "_bridge_request", _fake)
    return sent


# --- vscode_state ---------------------------------------------------------------


def test_vscode_state_formats_tabs_and_active(ide, monkeypatch):
    state = {
        "tabs": [
            {"path": "/a.py", "active": True, "dirty": False},
            {"path": "/b.md", "active": False, "dirty": True},
        ],
        "active": {"path": "/a.py", "line": 12, "dirty": False},
    }
    _stub_bridge(ide, monkeypatch, response=state)
    out = ide.handle_vscode_state({})
    assert "開いているタブ 2 個" in out
    assert "/a.py" in out and "/b.md" in out
    assert "12 行目" in out


def test_vscode_state_bridge_unavailable(ide, monkeypatch):
    _stub_bridge(ide, monkeypatch, fail=True)
    out = ide.handle_vscode_state({})
    assert "ブリッジに接続できません" in out  # 縮退メッセージ、例外は投げない


# --- vscode_open ----------------------------------------------------------------


def test_vscode_open_sends_path_and_line(ide, monkeypatch):
    sent = _stub_bridge(ide, monkeypatch, response={"opened": "/x.py"})
    out = ide.handle_vscode_open({"path": "/x.py", "line": 42})
    assert sent["method"] == "POST" and sent["path"] == "/open"
    assert sent["body"] == {"path": "/x.py", "line": 42}
    assert "/x.py" in out and "42 行目" in out


def test_vscode_open_requires_path(ide, monkeypatch):
    _stub_bridge(ide, monkeypatch)
    assert "path が必要" in ide.handle_vscode_open({"path": ""})


def test_vscode_open_bridge_unavailable(ide, monkeypatch):
    _stub_bridge(ide, monkeypatch, fail=True)
    assert "ブリッジに接続できません" in ide.handle_vscode_open({"path": "/x.py"})


# --- vscode_close_tab -----------------------------------------------------------


def test_vscode_close_tab_by_path(ide, monkeypatch):
    sent = _stub_bridge(ide, monkeypatch, response={"closed": "/x.py", "count": 1})
    out = ide.handle_vscode_close_tab({"path": "/x.py"})
    assert sent["body"] == {"path": "/x.py"}
    assert "/x.py" in out


def test_vscode_close_tab_all(ide, monkeypatch):
    sent = _stub_bridge(ide, monkeypatch, response={"closed": "all"})
    out = ide.handle_vscode_close_tab({"close_all": True})
    assert sent["body"] == {"all": True}
    assert "すべてのタブ" in out


def test_vscode_close_tab_requires_target(ide, monkeypatch):
    _stub_bridge(ide, monkeypatch)
    assert "どちらかが必要" in ide.handle_vscode_close_tab({})


# --- terminal override（#48 PR-2）----------------------------------------------


def test_terminal_falls_back_when_no_tmux(ide, monkeypatch):
    monkeypatch.setattr(ide, "_tmux_target_exists", lambda t: False)
    called = {}

    def _fb(args, kw):
        called["fb"] = args
        return "FALLBACK"

    monkeypatch.setattr(ide, "_fallback_terminal", _fb)
    out = ide.handle_terminal({"command": "ls"})
    assert out == "FALLBACK"
    assert called["fb"]["command"] == "ls"


def test_terminal_complex_mode_falls_back(ide, monkeypatch):
    monkeypatch.setattr(ide, "_fallback_terminal", lambda args, kw: "FALLBACK")
    # background/pty/watch_patterns は built-in へ（可視実行の対象外）
    assert ide.handle_terminal({"command": "sleep 100", "background": True}) == "FALLBACK"
    assert ide.handle_terminal({"command": "python", "pty": True}) == "FALLBACK"


def _wire_visible(ide, monkeypatch, tmp_path, output_text):
    """可視実行の副作用（ヘルパー ready・出力/マーカー生成）を tmp_path でスタブする。"""
    out = tmp_path / "out"
    done = tmp_path / "done"
    ready = tmp_path / "ready"
    monkeypatch.setattr(ide, "_TERM_OUT", str(out))
    monkeypatch.setattr(ide, "_TERM_DONE", str(done))
    monkeypatch.setattr(ide, "_TERM_READY", str(ready))
    monkeypatch.setattr(ide, "_tmux_target_exists", lambda t: True)
    ready.write_text("")  # ヘルパー定義済み扱い

    sent = []

    def _fake_send(target, literal):
        sent.append(literal)
        # kai '<cmd>' が送られたら出力/マーカーを生成（実行を擬似）
        if literal.startswith("kai '"):
            out.write_text(output_text)
            done.write_text("KAI_EXIT:0\n")

    monkeypatch.setattr(ide, "_tmux_send", _fake_send)
    return sent


def test_terminal_visible_run_captures_output(ide, monkeypatch, tmp_path):
    sent = _wire_visible(ide, monkeypatch, tmp_path, "hello\nworld\n")
    out = ide.handle_terminal({"command": "echo hello"})
    data = __import__("json").loads(out)
    assert data["exit_code"] == 0
    assert "hello" in data["output"] and "world" in data["output"]
    # 視聴者には kai '...' だけが見える（配管が露出しない）
    assert any(s == "kai 'echo hello'" for s in sent)
    assert not any("tee" in s for s in sent)


def test_terminal_visible_masks_secrets(ide, monkeypatch, tmp_path):
    _wire_visible(ide, monkeypatch, tmp_path, "token=ghp_ABCDEFGHIJKLMNOPQRSTUV\n")
    out = ide.handle_terminal({"command": "cat .netrc"})
    assert "ghp_ABCDEFGHIJKLMNOPQRSTUV" not in out
    assert "«redacted»" in out


def test_terminal_visible_escapes_single_quotes(ide, monkeypatch, tmp_path):
    sent = _wire_visible(ide, monkeypatch, tmp_path, "ok\n")
    ide.handle_terminal({"command": "echo 'hi there'"})
    # 単一引用符は '\'' にエスケープして kai '...' に包む
    assert any(s == "kai 'echo '\\''hi there'\\'''" for s in sent)


# --- register -------------------------------------------------------------------


def test_register_registers_state_tools_and_terminal_override(ide, monkeypatch):
    registered = []

    class _Ctx:
        def register_tool(self, **kwargs):
            registered.append((kwargs["name"], kwargs.get("override", False)))

    ide.register(_Ctx())
    names = {n for n, _ in registered}
    assert {"vscode_state", "vscode_open", "vscode_close_tab"} <= names
    # terminal は override=True で登録（TERMINAL_SCHEMA が import できる環境のみ）
    term = [ov for n, ov in registered if n == "terminal"]
    if term:  # import 可能な環境では override 登録される
        assert term[0] is True
