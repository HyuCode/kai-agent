"""Development orchestrator helpers for multi-repository work."""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


ConfigSaver = Callable[[str, Any], bool]
Opener = Callable[[list[str]], subprocess.CompletedProcess[str]]

_GITHUB_RE = re.compile(r"github\.com[:/]([^/\s]+)/([^/\s]+?)(?:\.git)?$")

KNOWN_WORKERS = ("codex", "claude", "hermes")

_WORKER_ALIASES = {
    "claude_code": "claude",
    "claude-code": "claude",
    "claudecode": "claude",
}


def normalize_worker(value: str) -> str:
    cleaned = str(value or "").strip().lower()
    return _WORKER_ALIASES.get(cleaned, cleaned)


DEV_TENANT = "dev"
_DEV_META_RE = re.compile(r"```dev-task-meta\s*\n(\{.*?\})\s*\n```", re.DOTALL)
_TITLE_MAX_CHARS = 80


@dataclass(frozen=True)
class RepositoryInfo:
    repo_id: str
    local_path: str
    github: str = ""
    default_branch: str = ""
    worktree_root: str = ""
    worker: str = ""
    exists: bool = False
    is_git_repo: bool = False


def save_config_value(key_path: str, value: Any) -> bool:
    """Persist one config value using the round-trip YAML updater."""
    from hermes_cli.config import ensure_hermes_home, get_config_path, is_managed, managed_error
    from utils import atomic_roundtrip_yaml_update

    if is_managed():
        managed_error("save dev orchestrator config")
        return False
    ensure_hermes_home()
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_roundtrip_yaml_update(config_path, key_path, value)
        return True
    except Exception:
        return False


def _expand_path(path: str) -> Path:
    raw = str(path or "").strip()
    raw = raw.replace("$HERMES_HOME", str(_hermes_home()))
    raw = raw.replace("${HERMES_HOME}", str(_hermes_home()))
    return Path(raw).expanduser()


def _hermes_home() -> Path:
    from hermes_constants import get_hermes_home

    return get_hermes_home()


def _repo_config(config: dict[str, Any] | None) -> dict[str, Any]:
    root = config if isinstance(config, dict) else {}
    repos = root.get("repositories")
    return repos if isinstance(repos, dict) else {}


def _dev_config(config: dict[str, Any] | None) -> dict[str, Any]:
    root = config if isinstance(config, dict) else {}
    dev = root.get("dev_orchestrator")
    return dev if isinstance(dev, dict) else {}


def _git_remote_github(path: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "remote", "get-url", "origin"],
            text=True,
            capture_output=True,
            timeout=5,
            check=False,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    match = _GITHUB_RE.search((proc.stdout or "").strip())
    if not match:
        return ""
    return f"{match.group(1)}/{match.group(2)}"


def _git_default_branch(path: Path) -> str:
    commands = (
        ["git", "-C", str(path), "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD"],
        ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
    )
    for cmd in commands:
        try:
            proc = subprocess.run(
                cmd,
                text=True,
                capture_output=True,
                timeout=5,
                check=False,
            )
        except Exception:
            continue
        if proc.returncode != 0:
            continue
        value = (proc.stdout or "").strip()
        if value.startswith("origin/"):
            value = value.split("/", 1)[1]
        if value and value != "HEAD":
            return value
    return ""


def load_repositories(config: dict[str, Any] | None) -> list[RepositoryInfo]:
    repos: list[RepositoryInfo] = []
    dev = _dev_config(config)
    default_worktree_root = str(dev.get("worktree_root") or "")
    default_worker = str(dev.get("default_worker") or "")
    for repo_id, raw in sorted(_repo_config(config).items()):
        if not isinstance(raw, dict):
            continue
        local_path = str(raw.get("local_path") or raw.get("path") or "").strip()
        if not local_path:
            continue
        path = _expand_path(local_path)
        exists = path.is_dir()
        is_git_repo = (path / ".git").exists()
        github = str(raw.get("github") or "").strip()
        default_branch = str(raw.get("default_branch") or "").strip()
        if exists and is_git_repo:
            github = github or _git_remote_github(path)
            default_branch = default_branch or _git_default_branch(path)
        worktree_root = str(raw.get("worktree_root") or "").strip()
        if not worktree_root and default_worktree_root:
            worktree_root = str(_expand_path(default_worktree_root) / str(repo_id))
        repos.append(
            RepositoryInfo(
                repo_id=str(repo_id),
                local_path=str(path),
                github=github,
                default_branch=default_branch,
                worktree_root=worktree_root,
                worker=normalize_worker(raw.get("worker") or default_worker or ""),
                exists=exists,
                is_git_repo=is_git_repo,
            )
        )
    return repos


def get_repository(config: dict[str, Any] | None, repo_id: str) -> RepositoryInfo | None:
    target = str(repo_id or "").strip()
    if not target:
        return None
    for repo in load_repositories(config):
        if repo.repo_id == target:
            return repo
    return None


def format_repositories(repos: list[RepositoryInfo]) -> str:
    if not repos:
        return (
            "Development repositories\n"
            "  (none configured)\n\n"
            "Add one with: /dev repo add <repo_id> <local_path> [--github owner/repo]"
        )
    lines = ["Development repositories"]
    for repo in repos:
        state = "ok" if repo.exists and repo.is_git_repo else "missing" if not repo.exists else "not-git"
        details = []
        if repo.github:
            details.append(repo.github)
        if repo.default_branch:
            details.append(f"branch={repo.default_branch}")
        if repo.worker:
            details.append(f"worker={repo.worker}")
        suffix = f" ({', '.join(details)})" if details else ""
        lines.append(f"  - {repo.repo_id}: {repo.local_path} [{state}]{suffix}")
    return "\n".join(lines)


def format_repository(repo: RepositoryInfo | None, repo_id: str = "") -> str:
    if repo is None:
        return f"Repository not found: {repo_id}"
    return "\n".join(
        [
            f"Repository: {repo.repo_id}",
            f"  Path:          {repo.local_path}",
            f"  Exists:        {'yes' if repo.exists else 'no'}",
            f"  Git repo:      {'yes' if repo.is_git_repo else 'no'}",
            f"  GitHub:        {repo.github or '-'}",
            f"  Default branch:{' ' + repo.default_branch if repo.default_branch else ' -'}",
            f"  Worktree root: {repo.worktree_root or '-'}",
            f"  Worker:        {repo.worker or '-'}",
        ]
    )


def add_repository(
    repo_id: str,
    local_path: str,
    *,
    github: str = "",
    default_branch: str = "",
    worker: str = "",
    saver: ConfigSaver | None = None,
) -> dict[str, Any]:
    clean_id = str(repo_id or "").strip()
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9_-]*$", clean_id):
        return {"success": False, "error": "repo_id must contain only letters, numbers, underscore, or dash"}
    clean_worker = normalize_worker(worker)
    if clean_worker and clean_worker not in KNOWN_WORKERS:
        return {"success": False, "error": f"unknown worker: {worker} (expected one of: {', '.join(KNOWN_WORKERS)})"}
    path = _expand_path(local_path)
    value: dict[str, Any] = {"local_path": str(path)}
    if github:
        value["github"] = github
    if default_branch:
        value["default_branch"] = default_branch
    if clean_worker:
        value["worker"] = clean_worker
    writer = saver or save_config_value
    ok = writer(f"repositories.{clean_id}", value)
    return {"success": ok, "repo_id": clean_id, "repository": value, "error": "" if ok else "failed to save config"}


def _compose_dev_task_body(task_text: str, meta: dict[str, Any]) -> str:
    return "\n".join(
        [
            task_text.strip(),
            "",
            "```dev-task-meta",
            json.dumps(meta, ensure_ascii=False, indent=2, sort_keys=True),
            "```",
        ]
    )


def parse_dev_task_metadata(body: str | None) -> dict[str, Any]:
    match = _DEV_META_RE.search(str(body or ""))
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def assign_dev_task(
    config: dict[str, Any] | None,
    repo_id: str,
    task_text: str,
    *,
    worker: str = "",
    requested_by: str = "cli",
) -> dict[str, Any]:
    cleaned = str(task_text or "").strip()
    if not cleaned:
        return {"success": False, "error": "task description is required"}
    repo = get_repository(config, repo_id)
    if repo is None:
        return {"success": False, "error": f"repository not found: {repo_id}"}
    if not repo.exists or not repo.is_git_repo:
        return {"success": False, "error": f"repository is not a usable git checkout: {repo.local_path}"}
    dev = _dev_config(config)
    clean_worker = normalize_worker(worker or repo.worker or str(dev.get("default_worker") or ""))
    if clean_worker not in KNOWN_WORKERS:
        return {"success": False, "error": f"unknown worker: {clean_worker or '(empty)'} (expected one of: {', '.join(KNOWN_WORKERS)})"}

    meta = {
        "kind": "dev_task",
        "repo_id": repo.repo_id,
        "github": repo.github,
        "local_path": repo.local_path,
        "worktree_path": "",
        "branch": "",
        "issue": None,
        "pr": None,
        "worker": clean_worker,
        "requested_by": requested_by,
        "notify_voice": True,
        "last_reported_event_id": None,
    }
    title = cleaned if len(cleaned) <= _TITLE_MAX_CHARS else cleaned[: _TITLE_MAX_CHARS - 3] + "..."
    try:
        from hermes_cli import kanban_db as kb

        with kb.connect_closing() as conn:
            # The worker name doubles as the assignee so the kanban
            # dispatcher's default_assignee never adopts dev tasks; the dev
            # orchestrator runs them itself (Phase 4).
            task_id = kb.create_task(
                conn,
                title=title,
                body=_compose_dev_task_body(cleaned, meta),
                assignee=clean_worker,
                created_by="dev-orchestrator",
                tenant=DEV_TENANT,
            )
    except Exception as exc:
        return {"success": False, "error": f"failed to create dev task: {exc}"}
    return {
        "success": True,
        "task_id": task_id,
        "repo_id": repo.repo_id,
        "worker": clean_worker,
        "title": title,
    }


def list_dev_tasks(
    config: dict[str, Any] | None,
    *,
    repo_id: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    del config
    try:
        from hermes_cli import kanban_db as kb

        with kb.connect_closing() as conn:
            tasks = kb.list_tasks(conn, tenant=DEV_TENANT, limit=limit)
    except Exception:
        return []
    items: list[dict[str, Any]] = []
    for task in tasks:
        meta = parse_dev_task_metadata(task.body)
        if meta.get("kind") != "dev_task":
            continue
        if repo_id and str(meta.get("repo_id") or "") != repo_id:
            continue
        items.append(
            {
                "task_id": task.id,
                "title": task.title,
                "status": task.status,
                "repo_id": str(meta.get("repo_id") or ""),
                "worker": str(meta.get("worker") or task.assignee or ""),
                "branch": str(meta.get("branch") or ""),
                "pr": meta.get("pr"),
                "issue": meta.get("issue"),
                "created_at": task.created_at,
            }
        )
    return items


def format_dev_tasks(items: list[dict[str, Any]], repo_id: str = "") -> str:
    scope = f" ({repo_id})" if repo_id else ""
    if not items:
        return (
            f"Dev tasks{scope}\n"
            "  (none)\n\n"
            "Create one with: /dev assign <repo_id> <task description>"
        )
    lines = [f"Dev tasks{scope}"]
    for item in items:
        details = [item["repo_id"], f"worker={item['worker']}"]
        if item.get("branch"):
            details.append(f"branch={item['branch']}")
        if item.get("pr"):
            details.append(f"pr={item['pr']}")
        lines.append(f"  - {item['task_id']} [{item['status']}] {item['title']} ({', '.join(d for d in details if d)})")
    return "\n".join(lines)


def summarize_dev_tasks(items: list[dict[str, Any]]) -> str:
    if not items:
        return "no tasks"
    counts: dict[str, int] = {}
    for item in items:
        counts[item["status"]] = counts.get(item["status"], 0) + 1
    parts = [f"{count} {status}" for status, count in sorted(counts.items())]
    return f"{len(items)} total ({', '.join(parts)})"


def _vscode_command(config: dict[str, Any] | None, path: str) -> list[str]:
    dev = _dev_config(config)
    vscode = dev.get("vscode")
    vscode = vscode if isinstance(vscode, dict) else {}
    configured = str(vscode.get("command") or "").strip()
    command = configured or "code"
    if shutil.which(command):
        return [command, path]
    if platform.system() == "Darwin":
        app = str(vscode.get("fallback_macos_app") or "Visual Studio Code").strip()
        return ["open", "-a", app, path]
    return [command, path]


def open_repository(
    config: dict[str, Any] | None,
    repo_id: str,
    *,
    opener: Opener | None = None,
) -> dict[str, Any]:
    repo = get_repository(config, repo_id)
    if repo is None:
        return {"success": False, "error": f"repository not found: {repo_id}"}
    if not repo.exists:
        return {"success": False, "error": f"repository path does not exist: {repo.local_path}"}
    command = _vscode_command(config, repo.local_path)
    run = opener or _default_open
    try:
        proc = run(command)
    except Exception as exc:
        return {"success": False, "error": str(exc), "repo_id": repo.repo_id, "path": repo.local_path, "command": command}
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        return {
            "success": False,
            "error": detail or f"open command failed with exit code {proc.returncode}",
            "repo_id": repo.repo_id,
            "path": repo.local_path,
            "command": command,
        }
    return {"success": True, "repo_id": repo.repo_id, "path": repo.local_path, "command": command}


def _default_open(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=15, check=False)


def format_open_result(result: dict[str, Any]) -> str:
    if result.get("success"):
        return f"Opened {result.get('repo_id')} in VS Code: {result.get('path')}"
    return f"Failed to open repository: {result.get('error') or 'unknown error'}"


def handle_dev_command(
    arg: str,
    *,
    config: dict[str, Any] | None,
    saver: ConfigSaver | None = None,
    opener: Opener | None = None,
) -> dict[str, Any]:
    try:
        parts = shlex.split(str(arg or "").strip())
    except ValueError as exc:
        return {"success": False, "error": f"failed to parse /dev command: {exc}"}
    if not parts:
        parts = ["status"]
    sub = parts[0].lower()
    if sub in {"status"}:
        repos = load_repositories(config)
        ok_count = sum(1 for repo in repos if repo.exists and repo.is_git_repo)
        tasks = list_dev_tasks(config)
        return {
            "success": True,
            "output": "\n".join(
                [
                    "Development Orchestrator Status",
                    f"  Repositories: {ok_count}/{len(repos)} ready",
                    f"  Dev tasks:     {summarize_dev_tasks(tasks)}",
                    "  Task runner:   not implemented yet",
                    "  Voice notify:  not implemented yet",
                ]
            ),
        }
    if sub == "assign":
        if len(parts) < 3:
            return {
                "success": False,
                "error": "usage: /dev assign <repo_id> <task description> [--worker codex|claude|hermes]",
            }
        worker = ""
        words: list[str] = []
        rest = parts[2:]
        idx = 0
        while idx < len(rest):
            if rest[idx] == "--worker" and idx + 1 < len(rest):
                worker = rest[idx + 1]
                idx += 2
            else:
                words.append(rest[idx])
                idx += 1
        result = assign_dev_task(config, parts[1], " ".join(words), worker=worker)
        if result.get("success"):
            return {
                "success": True,
                "output": (
                    f"Dev task created: {result['task_id']}\n"
                    f"  Repo:   {result['repo_id']}\n"
                    f"  Worker: {result['worker']}\n"
                    f"  Title:  {result['title']}"
                ),
            }
        return {"success": False, "error": result.get("error") or "failed to create dev task"}
    if sub == "tasks":
        repo_filter = parts[1] if len(parts) > 1 else ""
        if repo_filter and get_repository(config, repo_filter) is None:
            return {"success": False, "error": f"repository not found: {repo_filter}"}
        items = list_dev_tasks(config, repo_id=repo_filter)
        return {"success": True, "output": format_dev_tasks(items, repo_filter)}
    if sub in {"repos", "repositories"}:
        return {"success": True, "output": format_repositories(load_repositories(config))}
    if sub == "repo":
        action = parts[1].lower() if len(parts) > 1 else "list"
        if action in {"list", "repos"}:
            return {"success": True, "output": format_repositories(load_repositories(config))}
        if action == "show" and len(parts) >= 3:
            return {"success": True, "output": format_repository(get_repository(config, parts[2]), parts[2])}
        if action == "add" and len(parts) >= 4:
            github = ""
            default_branch = ""
            worker = ""
            rest = parts[4:]
            idx = 0
            while idx < len(rest):
                key = rest[idx]
                value = rest[idx + 1] if idx + 1 < len(rest) else ""
                if key == "--github":
                    github = value
                    idx += 2
                elif key == "--default-branch":
                    default_branch = value
                    idx += 2
                elif key == "--worker":
                    worker = value
                    idx += 2
                else:
                    idx += 1
            result = add_repository(parts[2], parts[3], github=github, default_branch=default_branch, worker=worker, saver=saver)
            if result.get("success"):
                return {"success": True, "output": f"Repository added: {result['repo_id']}"}
            return {"success": False, "error": result.get("error") or "failed to add repository"}
        return {
            "success": False,
            "error": (
                "usage: /dev repo [list|show <repo_id>|add <repo_id> <local_path> "
                "[--github owner/repo] [--worker codex|claude|hermes]]"
            ),
        }
    if sub == "open":
        if len(parts) < 2:
            return {"success": False, "error": "usage: /dev open <repo_id>"}
        result = open_repository(config, parts[1], opener=opener)
        return {"success": bool(result.get("success")), "output": format_open_result(result), "error": result.get("error")}
    return {"success": False, "error": "usage: /dev [status|repos|repo show|repo add|assign|tasks|open]"}
