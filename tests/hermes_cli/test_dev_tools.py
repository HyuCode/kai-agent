import json
import subprocess

import pytest

from tools.dev_tools import (
    check_dev_requirements,
    dev_assign_tool,
    dev_run_tool,
    dev_status_tool,
)


def _git(repo_path, *args):
    subprocess.run(["git", "-C", str(repo_path), *args], check=True, capture_output=True, text=True)


@pytest.fixture
def tool_env(tmp_path, monkeypatch):
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(home))
    repo_path = tmp_path / "proj"
    repo_path.mkdir()
    _git(tmp_path, "init", "-q", "-b", "main", str(repo_path))
    _git(repo_path, "config", "user.email", "t@e.com")
    _git(repo_path, "config", "user.name", "T")
    (repo_path / "README.md").write_text("hi\n")
    _git(repo_path, "add", "README.md")
    _git(repo_path, "commit", "-q", "-m", "init")
    config = {
        "dev_orchestrator": {
            "default_worker": "claude",
            "worktree_root": str(tmp_path / "worktrees"),
        },
        "repositories": {"proj": {"local_path": str(repo_path)}},
    }
    monkeypatch.setattr("tools.dev_tools._load_config", lambda: config)
    return config


def test_check_dev_requirements(tool_env, monkeypatch):
    assert check_dev_requirements() is True

    monkeypatch.setattr("tools.dev_tools._load_config", lambda: {"repositories": {}})
    assert check_dev_requirements() is False

    monkeypatch.setattr(
        "tools.dev_tools._load_config",
        lambda: {"dev_orchestrator": {"enabled": False}, "repositories": {"a": {}}},
    )
    assert check_dev_requirements() is False


def test_dev_tools_assign_status_run_roundtrip(tool_env):
    assigned = json.loads(dev_assign_tool("proj", "Fix the flicker"))
    assert assigned["success"] is True
    task_id = assigned["task_id"]

    status = json.loads(dev_status_tool())
    assert status["success"] is True
    assert status["repositories"][0]["repo_id"] == "proj"
    assert status["tasks"][0]["task_id"] == task_id

    def fake_worker(command):
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("hermes_cli.dev_orchestrator.shutil.which", lambda _name: "/usr/bin/x")
        mp.setattr("hermes_cli.dev_orchestrator._default_worker_run", lambda *a, **k: fake_worker(a[0]))
        started = json.loads(dev_run_tool(task_id))

        import time

        from hermes_cli import kanban_db as kb

        deadline = time.time() + 30
        task_status = "running"
        while time.time() < deadline and task_status == "running":
            with kb.connect_closing() as conn:
                task_status = kb.get_task(conn, task_id).status
            time.sleep(0.05)

    assert started["success"] is True
    assert started["status"] == "started"
    assert "thread" not in started
    assert task_status == "done"


def test_dev_tools_report_errors_as_json(tool_env):
    missing = json.loads(dev_run_tool("t_nope"))
    bad_repo = json.loads(dev_assign_tool("nope", "task"))

    assert missing["success"] is False
    assert bad_repo["success"] is False
