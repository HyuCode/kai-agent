"""kai-trace: 全事象ロギング plugin（要件 F-22）。

hermes の lifecycle hook を観測し、相関 ID つきの構造化イベントを
追記専用 JSONL として永続化する。振り返りループ（F-30）の分析対象。
設計: docs/kai/02-architecture/01-system.md（ADR-1 / §5.1 共通エンベロープ）。

重要な制約（設計 ADR-1）:
- hook は同期・エージェントのターンスレッド上で実行される。
  hook 内では構造化イベントをキューに積んで即 return し、
  JSONL 書き込みはバックグラウンドスレッドで行う（作業・配信を止めない）。
- 純オブザーバなのでコールバックは常に None を返す（transform 系は使わない）。
"""

from __future__ import annotations

import atexit
import json
import os
import queue
import re
import threading
import time
from pathlib import Path
from typing import Any

try:
    from hermes_constants import get_hermes_home
except Exception:  # pragma: no cover - plugin 単体実行時のフォールバック
    def get_hermes_home() -> Path:
        return Path(os.path.expanduser("~/.hermes"))

SCHEMA_VERSION = 1
_MAX_FIELD_CHARS = 4000
_QUEUE_MAXSIZE = 10000

# --- 秘匿マスク（設計 §5.3。書き込み前に必ず適用）---------------------------
# 注意: この 3 実装は plugin 単体完結の原則でコピーになっている。パターンや
# 収集ロジックを変えるときは 3 箇所（kai_narrator / kai_trace / speechd）を
# 同時に更新する（Issue #77 H-b）。

_TOKEN_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{16,}"),
    re.compile(r"gh[posur]_[A-Za-z0-9]{20,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9\-]{10,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{10,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),  # Google API key
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key ID
    re.compile(r"eyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{4,}"),  # JWT
    re.compile(r"://[^/\s:@]{1,64}:[^/\s@]{1,256}@"),  # URL 埋め込み認証情報（user:pass@）
    re.compile(r"rtmps?://[^\s\"']+"),  # RTMP 配信 URL（パスにストリームキーが載る）
    # YouTube ストリームキー形（xxxx-xxxx-xxxx-xxxx[-xxxx]）。kebab-case 識別子の
    # 誤マスクを避けるため数字を1つ以上含むものだけ対象にする
    re.compile(r"\b(?=[0-9a-z\-]*\d)[0-9a-z]{4}(?:-[0-9a-z]{4}){3,4}\b"),
]


def _iter_dotenv_items():
    """~/.hermes/.env の KEY=VALUE を直接読む（Issue #77 H-b）。

    hermes は資格情報を .env 直読み（get_env_value_prefer_dotenv）で解決し
    環境変数に載せないため、os.environ だけでは env 秘密層が実行時に空になる。
    """
    try:
        with open(get_hermes_home() / ".env", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                yield k.strip(), v.strip().strip("'\"")
    except OSError:
        return


def _collect_env_secrets() -> list[str]:
    """秘密っぽいキー名の値（os.environ ＋ .env 直読み）を長いものから順に集める。"""
    vals: set[str] = set()
    for k, v in list(os.environ.items()) + list(_iter_dotenv_items()):
        if not v or len(v) < 6:
            continue
        if re.search(r"(KEY|TOKEN|SECRET|PASSWORD|PAT|CREDENTIAL)", k, re.IGNORECASE):
            vals.add(v)
    return sorted(vals, key=lambda s: len(s), reverse=True)


_ENV_SECRETS = _collect_env_secrets()


def _mask(text: str) -> str:
    if not text:
        return text
    for secret in _ENV_SECRETS:
        if secret in text:
            text = text.replace(secret, "«redacted»")
    for pat in _TOKEN_PATTERNS:
        text = pat.sub("«redacted»", text)
    return text


def _clip(value: Any) -> Any:
    """任意の値を文字列化 → マスク → 長さ制限。"""
    if value is None:
        return None
    try:
        s = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, default=str)
    except Exception:
        s = str(value)
    s = _mask(s)
    if len(s) > _MAX_FIELD_CHARS:
        s = s[:_MAX_FIELD_CHARS] + f"…(+{len(s) - _MAX_FIELD_CHARS} chars)"
    return s


def _iso_now() -> str:
    now = time.time()
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(now)) + f".{int((now % 1) * 1000):03d}Z"


# --- バックグラウンド JSONL ライター -----------------------------------------


class _Writer:
    def __init__(self) -> None:
        self._q: "queue.Queue[dict | None]" = queue.Queue(maxsize=_QUEUE_MAXSIZE)
        self._dir = get_hermes_home() / "kai_trace"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._thread = threading.Thread(target=self._run, name="kai-trace-writer", daemon=True)
        self._thread.start()
        atexit.register(self._drain)

    def _path(self) -> Path:
        day = time.strftime("%Y-%m-%d", time.gmtime())
        return self._dir / f"{day}.jsonl"

    def emit(self, event: dict) -> None:
        try:
            self._q.put_nowait(event)
        except queue.Full:
            pass  # キュー飽和時はドロップ（作業・配信を止めない）

    def _run(self) -> None:
        while True:
            ev = self._q.get()
            if ev is None:
                break
            self._write(ev)

    def _write(self, ev: dict) -> None:
        try:
            with self._path().open("a", encoding="utf-8") as f:
                f.write(json.dumps(ev, ensure_ascii=False, default=str) + "\n")
        except Exception:
            pass  # ロギング失敗はメインループを壊さない

    def _drain(self) -> None:
        try:
            while not self._q.empty():
                ev = self._q.get_nowait()
                if ev is not None:  # None は writer 停止用センチネル。書き込まない
                    self._write(ev)
        except Exception:
            pass


_writer: _Writer | None = None


def _emit(component: str, kind: str, session_id: str, payload: dict, work_thread_id: str = "") -> None:
    if _writer is None:
        return
    _writer.emit({
        "v": SCHEMA_VERSION,
        "ts": _iso_now(),
        "session_id": session_id or None,
        "work_thread_id": work_thread_id or None,  # 自律ループ実装時に Issue/PR を付与
        "component": component,
        "kind": kind,
        "payload": payload,
    })


# --- hook コールバック（すべて同期・None 返し）--------------------------------


def _on_post_tool_call(tool_name: str = "", args: Any = None, result: Any = None,
                       task_id: str = "", session_id: str = "", duration_ms: Any = None,
                       status: str = "", error_type: str = "", error_message: str = "",
                       **_: Any) -> None:
    _emit("kai_trace", "tool_call", session_id, {
        "tool": tool_name,
        "args": _clip(args if args is not None else {}),
        "result": _clip(result),
        "status": status or None,
        "duration_ms": duration_ms,
        "error_type": error_type or None,
        "error_message": _mask(error_message) if error_message else None,
        "task_id": task_id or None,
    })


def _on_post_api_request(session_id: str = "", model: str = "", provider: str = "",
                         api_mode: str = "", api_duration: Any = None, finish_reason: str = "",
                         usage: Any = None, response_model: str = "",
                         assistant_content_chars: Any = None, assistant_tool_call_count: Any = None,
                         task_id: str = "", **_: Any) -> None:
    _emit("kai_trace", "llm_call", session_id, {
        "model": model or response_model or None,
        "provider": provider or None,
        "api_mode": api_mode or None,
        "duration_ms": int(api_duration * 1000) if isinstance(api_duration, (int, float)) else None,
        "finish_reason": finish_reason or None,
        "usage": usage or {},
        "assistant_chars": assistant_content_chars,
        "tool_calls": assistant_tool_call_count,
        "task_id": task_id or None,
    })


def _on_post_llm_call(session_id: str = "", task_id: str = "", turn_id: str = "",
                      assistant_response: str = "", model: str = "", **_: Any) -> None:
    _emit("kai_trace", "turn", session_id, {
        "turn_id": turn_id or None,
        "model": model or None,
        "assistant_response": _clip(assistant_response),
        "task_id": task_id or None,
    })


def _on_session_start(session_id: str = "", model: str = "", platform: str = "", **_: Any) -> None:
    _emit("kai_trace", "session_start", session_id, {"model": model or None, "platform": platform or None})


def _on_session_end(session_id: str = "", task_id: str = "", completed: Any = None,
                    interrupted: Any = None, model: str = "", platform: str = "", **_: Any) -> None:
    _emit("kai_trace", "session_end", session_id, {
        "completed": completed,
        "interrupted": interrupted,
        "model": model or None,
        "platform": platform or None,
        "task_id": task_id or None,
    })


def _on_subagent_start(parent_session_id: str = "", child_session_id: str = "",
                       child_role: str = "", child_goal: str = "", **_: Any) -> None:
    _emit("kai_trace", "subagent_start", parent_session_id, {
        "child_session_id": child_session_id or None,
        "child_role": child_role or None,
        "goal": _clip(child_goal),
    })


def _on_subagent_stop(parent_session_id: str = "", child_session_id: str = "",
                      child_role: str = "", child_status: str = "", child_summary: str = "",
                      duration_ms: Any = None, **_: Any) -> None:
    _emit("kai_trace", "subagent_stop", parent_session_id, {
        "child_session_id": child_session_id or None,
        "child_role": child_role or None,
        "status": child_status or None,
        "summary": _clip(child_summary),
        "duration_ms": duration_ms,
    })


def register(ctx) -> None:
    """hermes plugin エントリポイント。lifecycle hook を JSONL ライターに繋ぐ。"""
    global _writer
    if _writer is None:
        _writer = _Writer()
    ctx.register_hook("post_tool_call", _on_post_tool_call)
    ctx.register_hook("post_api_request", _on_post_api_request)
    ctx.register_hook("post_llm_call", _on_post_llm_call)
    ctx.register_hook("on_session_start", _on_session_start)
    ctx.register_hook("on_session_end", _on_session_end)
    ctx.register_hook("subagent_start", _on_subagent_start)
    ctx.register_hook("subagent_stop", _on_subagent_stop)
