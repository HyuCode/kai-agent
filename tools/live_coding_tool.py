"""Tools for live-coding stream coordination."""

from __future__ import annotations

import json
import os
from typing import Any

from tools.registry import registry


def _load_config() -> dict[str, Any]:
    try:
        from hermes_cli.config import load_config

        config = load_config()
        return config if isinstance(config, dict) else {}
    except Exception:
        return {}


def check_live_coding_requirements() -> bool:
    try:
        from hermes_cli.live_coding import check_delegate_available

        return check_delegate_available(_load_config())
    except Exception:
        return False


def live_coding_delegate_tool(
    task: str,
    *,
    workdir: str | None = None,
    task_id: str | None = None,
) -> str:
    del task_id
    try:
        from hermes_cli.live_coding import run_delegate

        result = run_delegate(task, config=_load_config(), workdir=workdir or os.getcwd())
        return json.dumps(result, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False)


registry.register(
    name="live_coding_delegate",
    toolset="live_coding",
    schema={
        "name": "live_coding_delegate",
        "description": (
            "Delegate a focused live-coding implementation, investigation, or test task "
            "to the configured coding CLI (Codex or Claude Code) and publish progress "
            "to the live overlay. Use only during live-coding mode, and never for "
            "commit, push, destructive deletion, or secret inspection."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "Focused coding task to delegate to the coding CLI.",
                },
                "workdir": {
                    "type": "string",
                    "description": "Project directory to run the coding CLI in. Defaults to the current working directory.",
                },
            },
            "required": ["task"],
        },
    },
    handler=lambda args, **kw: live_coding_delegate_tool(
        task=args.get("task", ""),
        workdir=args.get("workdir"),
        task_id=kw.get("task_id"),
    ),
    check_fn=check_live_coding_requirements,
)
