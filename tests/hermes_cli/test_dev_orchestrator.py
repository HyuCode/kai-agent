import subprocess

import pytest

from hermes_cli.dev_orchestrator import (
    add_repository,
    assign_dev_task,
    create_task_worktree,
    format_repositories,
    get_repository,
    handle_dev_command,
    list_dev_tasks,
    load_repositories,
    open_repository,
    parse_dev_task_metadata,
    run_dev_task,
)


def _git(repo_path, *args):
    subprocess.run(
        ["git", "-C", str(repo_path), *args],
        check=True,
        capture_output=True,
        text=True,
    )


def _init_git_repo(repo_path):
    repo_path.mkdir(parents=True, exist_ok=True)
    _git(repo_path.parent, "init", "-q", "-b", "main", str(repo_path))
    _git(repo_path, "config", "user.email", "test@example.com")
    _git(repo_path, "config", "user.name", "Test")
    (repo_path / "README.md").write_text("hello\n")
    _git(repo_path, "add", "README.md")
    _git(repo_path, "commit", "-q", "-m", "init")


@pytest.fixture
def dev_env(tmp_path, monkeypatch):
    """Isolated HERMES_HOME plus one registered git repo."""
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(home))
    repo_path = tmp_path / "kai"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    config = {
        "dev_orchestrator": {"default_worker": "codex"},
        "repositories": {"kai": {"local_path": str(repo_path)}},
    }
    return config


def test_load_repositories_reads_config_and_expands_paths(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()

    config = {
        "dev_orchestrator": {
            "default_worker": "codex",
            "worktree_root": str(tmp_path / "worktrees"),
        },
        "repositories": {
            "kai": {
                "local_path": str(repo_path),
                "github": "seiichi3141/kai",
                "default_branch": "main",
            }
        },
    }

    repos = load_repositories(config)

    assert len(repos) == 1
    assert repos[0].repo_id == "kai"
    assert repos[0].exists is True
    assert repos[0].is_git_repo is True
    assert repos[0].worker == "codex"
    assert repos[0].worktree_root.endswith("/worktrees/kai")
    assert "kai" in format_repositories(repos)


def test_add_repository_uses_config_saver(tmp_path):
    calls = []

    result = add_repository(
        "hermes-agent",
        str(tmp_path / "hermes-agent"),
        github="seiichi3141/hermes-agent",
        saver=lambda key, value: calls.append((key, value)) or True,
    )

    assert result["success"] is True
    assert calls == [
        (
            "repositories.hermes-agent",
            {
                "local_path": str(tmp_path / "hermes-agent"),
                "github": "seiichi3141/hermes-agent",
            },
        )
    ]


def test_add_repository_rejects_dot_in_repo_id(tmp_path):
    result = add_repository("bad.repo", str(tmp_path), saver=lambda _key, _value: True)

    assert result["success"] is False


def test_add_repository_normalizes_claude_code_worker(tmp_path):
    calls = []

    result = add_repository(
        "kai",
        str(tmp_path / "kai"),
        worker="Claude_Code",
        saver=lambda key, value: calls.append((key, value)) or True,
    )

    assert result["success"] is True
    assert calls[0][1]["worker"] == "claude"


def test_add_repository_rejects_unknown_worker(tmp_path):
    result = add_repository(
        "kai",
        str(tmp_path / "kai"),
        worker="copilot",
        saver=lambda _key, _value: True,
    )

    assert result["success"] is False
    assert "unknown worker" in result["error"]


def test_load_repositories_normalizes_worker_aliases(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    config = {
        "dev_orchestrator": {"default_worker": "claude-code"},
        "repositories": {"repo": {"local_path": str(repo_path)}},
    }

    repos = load_repositories(config)

    assert repos[0].worker == "claude"


def test_open_repository_uses_configured_code_command(tmp_path):
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    (repo_path / ".git").mkdir()
    calls = []
    config = {
        "dev_orchestrator": {"vscode": {"command": "definitely-missing-code-command"}},
        "repositories": {"repo": {"local_path": str(repo_path)}},
    }

    def opener(command):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "", "")

    result = open_repository(config, "repo", opener=opener)

    assert result["success"] is True
    assert calls
    assert calls[0][-1] == str(repo_path)


def test_handle_dev_command_repos_and_repo_add(tmp_path):
    calls = []
    config = {"repositories": {}}

    empty = handle_dev_command("repos", config=config)
    added = handle_dev_command(
        f"repo add kai {tmp_path / 'kai'} --github seiichi3141/kai",
        config=config,
        saver=lambda key, value: calls.append((key, value)) or True,
    )

    assert empty["success"] is True
    assert "(none configured)" in empty["output"]
    assert added["success"] is True
    assert calls[0][0] == "repositories.kai"
    assert calls[0][1]["github"] == "seiichi3141/kai"


def test_handle_dev_command_repo_add_accepts_quoted_path(tmp_path):
    calls = []
    repo_path = tmp_path / "repo with spaces"

    result = handle_dev_command(
        f'repo add spaced "{repo_path}" --github seiichi3141/spaced',
        config={"repositories": {}},
        saver=lambda key, value: calls.append((key, value)) or True,
    )

    assert result["success"] is True
    assert calls[0][0] == "repositories.spaced"
    assert calls[0][1]["local_path"] == str(repo_path)


def test_get_repository_returns_none_for_unknown():
    assert get_repository({"repositories": {}}, "missing") is None


def test_assign_dev_task_creates_kanban_task_with_metadata(dev_env):
    result = assign_dev_task(dev_env, "kai", "Fix the AquesTalk reading bug", worker="claude")

    assert result["success"] is True
    assert result["worker"] == "claude"

    items = list_dev_tasks(dev_env)
    assert len(items) == 1
    assert items[0]["task_id"] == result["task_id"]
    assert items[0]["repo_id"] == "kai"
    assert items[0]["worker"] == "claude"
    assert items[0]["status"] == "ready"

    from hermes_cli import kanban_db as kb

    with kb.connect_closing() as conn:
        task = kb.get_task(conn, result["task_id"])
    assert task.tenant == "dev"
    assert task.assignee == "claude"
    meta = parse_dev_task_metadata(task.body)
    assert meta["kind"] == "dev_task"
    assert meta["repo_id"] == "kai"
    assert "Fix the AquesTalk reading bug" in task.body


def test_assign_dev_task_rejects_unknown_repo_and_missing_text(dev_env):
    missing_repo = assign_dev_task(dev_env, "nope", "Fix something")
    empty_task = assign_dev_task(dev_env, "kai", "   ")

    assert missing_repo["success"] is False
    assert "repository not found" in missing_repo["error"]
    assert empty_task["success"] is False
    assert "task description is required" in empty_task["error"]


def test_list_dev_tasks_filters_by_repo(dev_env, tmp_path):
    other_path = tmp_path / "other"
    other_path.mkdir()
    (other_path / ".git").mkdir()
    dev_env["repositories"]["other"] = {"local_path": str(other_path)}

    assign_dev_task(dev_env, "kai", "Task for kai")
    assign_dev_task(dev_env, "other", "Task for other")

    assert len(list_dev_tasks(dev_env)) == 2
    kai_items = list_dev_tasks(dev_env, repo_id="kai")
    assert len(kai_items) == 1
    assert kai_items[0]["repo_id"] == "kai"


def test_handle_dev_command_assign_and_tasks(dev_env):
    created = handle_dev_command(
        "assign kai Fix the overlay flicker --worker claude_code",
        config=dev_env,
    )
    listed = handle_dev_command("tasks kai", config=dev_env)
    status = handle_dev_command("status", config=dev_env)
    unknown = handle_dev_command("tasks nope", config=dev_env)

    assert created["success"] is True
    assert "Worker: claude" in created["output"]
    assert listed["success"] is True
    assert "Fix the overlay flicker" in listed["output"]
    assert "1 total (1 ready)" in status["output"]
    assert unknown["success"] is False


def test_parse_dev_task_metadata_is_shape_safe():
    assert parse_dev_task_metadata(None) == {}
    assert parse_dev_task_metadata("no fence here") == {}
    assert parse_dev_task_metadata("```dev-task-meta\nnot json\n```") == {}


@pytest.fixture
def worker_env(tmp_path, monkeypatch):
    """Isolated HERMES_HOME plus a real git repo registered as 'proj'."""
    home = tmp_path / "hermes-home"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    monkeypatch.setenv("HERMES_KANBAN_HOME", str(home))
    repo_path = tmp_path / "proj"
    _init_git_repo(repo_path)
    config = {
        "dev_orchestrator": {
            "default_worker": "claude",
            "worktree_root": str(tmp_path / "worktrees"),
        },
        "repositories": {"proj": {"local_path": str(repo_path)}},
    }
    return config


def test_create_task_worktree_creates_branch_and_dir(worker_env):
    repo = get_repository(worker_env, "proj")

    result = create_task_worktree(repo, "t_abc123")

    assert result["success"] is True
    assert result["branch"] == "dev/t_abc123"
    worktree = subprocess.run(
        ["git", "-C", result["worktree_path"], "rev-parse", "--abbrev-ref", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert worktree.stdout.strip() == "dev/t_abc123"

    again = create_task_worktree(repo, "t_abc123")
    assert again["success"] is True
    assert again["reused"] is True


def test_run_dev_task_completes_task_with_change_summary(worker_env):
    created = assign_dev_task(worker_env, "proj", "Add a feature file")
    task_id = created["task_id"]

    def fake_worker(command):
        assert command[0] == "claude"
        return subprocess.CompletedProcess(command, 0, stdout="did the work\n", stderr="")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("hermes_cli.dev_orchestrator.shutil.which", lambda _name: "/usr/bin/claude")
        result = run_dev_task(worker_env, task_id, runner=fake_worker)

    assert result["success"] is True
    assert result["status"] == "done"
    assert result["branch"] == f"dev/{task_id}"

    from hermes_cli import kanban_db as kb

    with kb.connect_closing() as conn:
        task = kb.get_task(conn, task_id)
    assert task.status == "done"
    meta = parse_dev_task_metadata(task.body)
    assert meta["branch"] == f"dev/{task_id}"
    assert meta["worktree_path"] == result["worktree_path"]


def test_run_dev_task_blocks_on_worker_failure(worker_env):
    created = assign_dev_task(worker_env, "proj", "Break something")
    task_id = created["task_id"]

    def fake_worker(command):
        return subprocess.CompletedProcess(command, 2, stdout="", stderr="boom API_KEY=secret123456")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("hermes_cli.dev_orchestrator.shutil.which", lambda _name: "/usr/bin/claude")
        result = run_dev_task(worker_env, task_id, runner=fake_worker)

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert "secret123456" not in result["output"]

    from hermes_cli import kanban_db as kb

    with kb.connect_closing() as conn:
        task = kb.get_task(conn, task_id)
    assert task.status == "blocked"


def test_run_dev_task_validates_task_and_status(worker_env):
    missing = run_dev_task(worker_env, "t_nope")
    assert missing["success"] is False
    assert "task not found" in missing["error"]

    created = assign_dev_task(worker_env, "proj", "Run twice")
    task_id = created["task_id"]

    def fake_worker(command):
        return subprocess.CompletedProcess(command, 0, stdout="ok", stderr="")

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("hermes_cli.dev_orchestrator.shutil.which", lambda _name: "/usr/bin/claude")
        first = run_dev_task(worker_env, task_id, runner=fake_worker)
        second = run_dev_task(worker_env, task_id, runner=fake_worker)

    assert first["success"] is True
    assert second["success"] is False
    assert "not ready" in second["error"]


def test_run_dev_task_rejects_hermes_worker(worker_env):
    created = assign_dev_task(worker_env, "proj", "Use hermes lane", worker="hermes")

    result = run_dev_task(worker_env, created["task_id"])

    assert result["success"] is False
    assert "not implemented" in result["error"]
