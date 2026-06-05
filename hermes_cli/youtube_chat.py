"""Read-only YouTube Live Chat polling helpers."""

from __future__ import annotations

import logging
import json
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"


@dataclass(frozen=True)
class YouTubeChatConfig:
    enabled: bool = False
    video_id: str = ""
    live_chat_id: str = ""
    poll_interval_seconds: float = 5.0
    max_results: int = 50
    timeout_seconds: float = 10.0
    selected_only: bool = True
    min_chars: int = 1
    max_chars: int = 220
    blocked_terms: tuple[str, ...] = ()
    spoiler_terms: tuple[str, ...] = ("ネタバレ", "spoiler")
    overlay_enabled: bool = True
    overlay_ttl_seconds: float = 12.0
    backend: str = "innertube"
    bridge_path: str = ""
    node_path: str = "node"


@dataclass(frozen=True)
class YouTubeChatMessage:
    message_id: str
    author_name: str
    text: str
    published_at: str = ""
    author_channel_id: str = ""
    is_owner: bool = False
    is_moderator: bool = False
    is_member: bool = False
    is_selected: bool = False
    rejection_reason: str = ""

    @property
    def display_text(self) -> str:
        if self.author_name:
            return f"{self.author_name}: {self.text}"
        return self.text


def _get_env_value(name: str) -> str:
    try:
        from hermes_cli.config import get_env_value

        return str(get_env_value(name) or "")
    except Exception:
        import os

        return os.getenv(name, "")


def _bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _int(value: Any, default: int, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    if parsed < minimum or parsed > maximum:
        return default
    return parsed


def _float(value: Any, default: float, *, minimum: float) -> float:
    if isinstance(value, bool):
        return default
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= minimum else default


def _string_list(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value.strip(),) if value.strip() else ()
    if not isinstance(value, list):
        return ()
    items: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            items.append(item.strip())
    return tuple(items)


def extract_youtube_video_id(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if re.fullmatch(r"[\w-]{11}", raw):
        return raw
    parsed = urlparse(raw)
    host = parsed.netloc.lower()
    if host.endswith("youtu.be"):
        candidate = parsed.path.strip("/").split("/", 1)[0]
        return candidate if re.fullmatch(r"[\w-]{11}", candidate or "") else ""
    if "youtube.com" in host:
        query_id = parse_qs(parsed.query).get("v", [""])[0]
        if re.fullmatch(r"[\w-]{11}", query_id or ""):
            return query_id
        match = re.search(r"/(?:live|shorts|embed)/([\w-]{11})(?:/|$)", parsed.path)
        if match:
            return match.group(1)
    return ""


def load_youtube_chat_config(config: dict | None) -> YouTubeChatConfig:
    root = config if isinstance(config, dict) else {}
    section = root.get("youtube_chat")
    section = section if isinstance(section, dict) else {}
    selection = section.get("selection")
    selection = selection if isinstance(selection, dict) else {}
    overlay = section.get("overlay")
    overlay = overlay if isinstance(overlay, dict) else {}

    video_id = str(section.get("video_id") or "").strip()
    video_url = str(section.get("video_url") or "").strip()
    if not video_id and video_url:
        video_id = extract_youtube_video_id(video_url)

    return YouTubeChatConfig(
        enabled=_bool(section.get("enabled"), False),
        video_id=video_id,
        live_chat_id=str(section.get("live_chat_id") or "").strip(),
        poll_interval_seconds=_float(section.get("poll_interval_seconds"), 5.0, minimum=0.5),
        max_results=_int(section.get("max_results"), 50, minimum=1, maximum=200),
        timeout_seconds=_float(section.get("timeout_seconds"), 10.0, minimum=1.0),
        selected_only=_bool(selection.get("selected_only"), True),
        min_chars=_int(selection.get("min_chars"), 1, minimum=0, maximum=1000),
        max_chars=_int(selection.get("max_chars"), 220, minimum=1, maximum=2000),
        blocked_terms=_string_list(selection.get("blocked_terms")),
        spoiler_terms=_string_list(selection.get("spoiler_terms")) or ("ネタバレ", "spoiler"),
        overlay_enabled=_bool(overlay.get("enabled"), True),
        overlay_ttl_seconds=_float(overlay.get("ttl_seconds"), 12.0, minimum=0.5),
        backend=str(section.get("backend") or "innertube").strip().lower(),
        bridge_path=str(section.get("bridge_path") or "").strip(),
        node_path=str(section.get("node_path") or "node").strip() or "node",
    )


def _youtube_get(path: str, *, api_key: str, params: dict[str, Any], timeout: float) -> dict[str, Any]:
    import requests

    query = dict(params)
    query["key"] = api_key
    response = requests.get(f"{YOUTUBE_API_BASE}/{path}", params=query, timeout=timeout)
    if response.status_code >= 400:
        detail = response.text[:300]
        raise RuntimeError(f"YouTube API failed with HTTP {response.status_code}: {detail}")
    data = response.json()
    return data if isinstance(data, dict) else {}


def resolve_live_chat_id(
    *,
    video_id: str,
    api_key: Optional[str] = None,
    timeout_seconds: float = 10.0,
) -> str:
    key = api_key or _get_env_value("YOUTUBE_API_KEY")
    if not key:
        raise ValueError("YOUTUBE_API_KEY is required for YouTube chat polling")
    if not video_id:
        raise ValueError("youtube_chat.video_id or video_url is required")
    data = _youtube_get(
        "videos",
        api_key=key,
        params={"part": "liveStreamingDetails", "id": video_id},
        timeout=timeout_seconds,
    )
    items = data.get("items") if isinstance(data.get("items"), list) else []
    if not items:
        raise RuntimeError(f"YouTube video not found or inaccessible: {video_id}")
    details = items[0].get("liveStreamingDetails") if isinstance(items[0], dict) else {}
    live_chat_id = details.get("activeLiveChatId") if isinstance(details, dict) else ""
    if not live_chat_id:
        raise RuntimeError(f"YouTube video has no active live chat: {video_id}")
    return str(live_chat_id)


def parse_youtube_chat_message(item: dict[str, Any]) -> YouTubeChatMessage:
    snippet = item.get("snippet") if isinstance(item.get("snippet"), dict) else {}
    author = item.get("authorDetails") if isinstance(item.get("authorDetails"), dict) else {}
    text = snippet.get("displayMessage") or snippet.get("textMessageDetails", {}).get("messageText") or ""
    return YouTubeChatMessage(
        message_id=str(item.get("id") or ""),
        author_name=str(author.get("displayName") or ""),
        text=str(text or "").strip(),
        published_at=str(snippet.get("publishedAt") or ""),
        author_channel_id=str(author.get("channelId") or ""),
        is_owner=bool(author.get("isChatOwner")),
        is_moderator=bool(author.get("isChatModerator")),
        is_member=bool(author.get("isChatSponsor")),
    )


def classify_youtube_chat_message(
    message: YouTubeChatMessage,
    config: YouTubeChatConfig,
) -> YouTubeChatMessage:
    text = message.text.strip()
    lowered = text.lower()
    if not text:
        reason = "empty"
    elif len(text) < config.min_chars:
        reason = "too_short"
    elif len(text) > config.max_chars:
        reason = "too_long"
    elif any(term.lower() in lowered for term in config.blocked_terms):
        reason = "blocked_term"
    elif any(term.lower() in lowered for term in config.spoiler_terms):
        reason = "spoiler_term"
    else:
        reason = ""
    return YouTubeChatMessage(
        message_id=message.message_id,
        author_name=message.author_name,
        text=message.text,
        published_at=message.published_at,
        author_channel_id=message.author_channel_id,
        is_owner=message.is_owner,
        is_moderator=message.is_moderator,
        is_member=message.is_member,
        is_selected=reason == "",
        rejection_reason=reason,
    )


def fetch_youtube_chat_messages(
    *,
    live_chat_id: str,
    config: YouTubeChatConfig,
    api_key: Optional[str] = None,
    page_token: Optional[str] = None,
) -> tuple[list[YouTubeChatMessage], str, float]:
    key = api_key or _get_env_value("YOUTUBE_API_KEY")
    if not key:
        raise ValueError("YOUTUBE_API_KEY is required for YouTube chat polling")
    if not live_chat_id:
        raise ValueError("live_chat_id is required")
    params: dict[str, Any] = {
        "liveChatId": live_chat_id,
        "part": "snippet,authorDetails",
        "maxResults": config.max_results,
    }
    if page_token:
        params["pageToken"] = page_token
    data = _youtube_get(
        "liveChat/messages",
        api_key=key,
        params=params,
        timeout=config.timeout_seconds,
    )
    raw_items = data.get("items") if isinstance(data.get("items"), list) else []
    messages = [
        classify_youtube_chat_message(parse_youtube_chat_message(item), config)
        for item in raw_items
        if isinstance(item, dict)
    ]
    next_token = str(data.get("nextPageToken") or "")
    interval_ms = data.get("pollingIntervalMillis")
    try:
        interval_seconds = max(config.poll_interval_seconds, float(interval_ms) / 1000.0)
    except (TypeError, ValueError):
        interval_seconds = config.poll_interval_seconds
    return messages, next_token, interval_seconds


def _default_innertube_bridge_path() -> str:
    return str(Path(__file__).resolve().parent.parent / "scripts" / "youtube-chat-innertube-bridge.mjs")


def parse_innertube_bridge_message(payload: dict[str, Any], config: YouTubeChatConfig) -> YouTubeChatMessage | None:
    if payload.get("type") != "message":
        return None
    message = YouTubeChatMessage(
        message_id=str(payload.get("id") or ""),
        author_name=str(payload.get("author") or ""),
        text=str(payload.get("text") or "").strip(),
        published_at=str(payload.get("timestamp") or ""),
        author_channel_id=str(payload.get("authorChannelId") or ""),
        is_moderator=bool(payload.get("isModerator")),
        is_member=bool(payload.get("isMember")),
    )
    return classify_youtube_chat_message(message, config)


class YouTubeInnerTubeBridge:
    """Node/youtubei.js read-only bridge that streams chat as NDJSON."""

    def __init__(
        self,
        config: YouTubeChatConfig,
        *,
        on_message: Optional[Callable[[YouTubeChatMessage], None]] = None,
    ) -> None:
        self.config = config
        self.on_message = on_message
        self._proc: subprocess.Popen[str] | None = None
        self._thread: threading.Thread | None = None
        self._messages: queue.Queue[YouTubeChatMessage] = queue.Queue(maxsize=1000)
        self._seen_ids: set[str] = set()

    def start(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            return
        if not self.config.video_id:
            raise ValueError("youtube_chat.video_id or video_url is required for innertube backend")
        bridge_path = self.config.bridge_path or _default_innertube_bridge_path()
        if not Path(bridge_path).is_file():
            raise FileNotFoundError(f"YouTube InnerTube bridge not found: {bridge_path}")
        self._proc = subprocess.Popen(
            [self.config.node_path, bridge_path, "--video-id", self.config.video_id],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        self._thread = threading.Thread(target=self._read_loop, name="hermes-youtube-innertube", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        proc = self._proc
        self._proc = None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def drain(self) -> list[YouTubeChatMessage]:
        messages: list[YouTubeChatMessage] = []
        while True:
            try:
                messages.append(self._messages.get_nowait())
            except queue.Empty:
                break
        return messages

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                logger.debug("invalid youtube innertube bridge line: %r", line[:200])
                continue
            event_type = payload.get("type")
            if event_type in {"error", "fatal"}:
                logger.warning("YouTube InnerTube bridge %s: %s", event_type, payload.get("message"))
                continue
            message = parse_innertube_bridge_message(payload, self.config)
            if message is None:
                continue
            if message.message_id and message.message_id in self._seen_ids:
                continue
            if message.message_id:
                self._seen_ids.add(message.message_id)
            if self.config.selected_only and not message.is_selected:
                logger.debug("youtube innertube chat skipped id=%s reason=%s", message.message_id, message.rejection_reason)
                continue
            self._safe_put(message)
            if self.on_message is not None:
                self.on_message(message)

    def _safe_put(self, message: YouTubeChatMessage) -> None:
        try:
            self._messages.put_nowait(message)
        except queue.Full:
            try:
                self._messages.get_nowait()
            except queue.Empty:
                pass
            try:
                self._messages.put_nowait(message)
            except queue.Full:
                pass


def publish_youtube_chat_to_overlay(
    root_config: dict | None,
    message: YouTubeChatMessage,
    *,
    ttl_seconds: float | None = None,
) -> dict[str, Any] | None:
    cfg = load_youtube_chat_config(root_config)
    if not cfg.overlay_enabled:
        return None
    if cfg.selected_only and not message.is_selected:
        return None
    try:
        from hermes_cli.live_overlay import publish_caption

        return publish_caption(
            root_config,
            message.display_text,
            final=True,
            speaker="chat",
            ttl_seconds=ttl_seconds if ttl_seconds is not None else cfg.overlay_ttl_seconds,
        )
    except Exception as exc:
        logger.warning("failed to publish YouTube chat to overlay: %s", exc)
        return None


class YouTubeLiveChatPoller:
    """Small read-only polling loop for YouTube Live Chat."""

    def __init__(
        self,
        config: YouTubeChatConfig,
        *,
        api_key: Optional[str] = None,
        on_message: Optional[Callable[[YouTubeChatMessage], None]] = None,
    ) -> None:
        self.config = config
        self.api_key = api_key
        self.on_message = on_message
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._page_token = ""
        self._seen_ids: set[str] = set()
        self._last_interval_seconds = config.poll_interval_seconds

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="hermes-youtube-chat", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2)

    def poll_once(self) -> list[YouTubeChatMessage]:
        live_chat_id = self.config.live_chat_id or resolve_live_chat_id(
            video_id=self.config.video_id,
            api_key=self.api_key,
            timeout_seconds=self.config.timeout_seconds,
        )
        messages, self._page_token, interval = fetch_youtube_chat_messages(
            live_chat_id=live_chat_id,
            config=self.config,
            api_key=self.api_key,
            page_token=self._page_token or None,
        )
        self._last_interval_seconds = interval
        fresh: list[YouTubeChatMessage] = []
        for message in messages:
            if message.message_id and message.message_id in self._seen_ids:
                continue
            if message.message_id:
                self._seen_ids.add(message.message_id)
            if self.config.selected_only and not message.is_selected:
                logger.debug("youtube chat skipped id=%s reason=%s", message.message_id, message.rejection_reason)
                continue
            fresh.append(message)
            if self.on_message is not None:
                self.on_message(message)
        return fresh

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.poll_once()
            except Exception as exc:
                logger.warning("YouTube chat poll failed: %s", exc)
            interval = self._last_interval_seconds
            self._stop_event.wait(interval)


def create_youtube_chat_reader(
    config: YouTubeChatConfig,
    *,
    api_key: Optional[str] = None,
    on_message: Optional[Callable[[YouTubeChatMessage], None]] = None,
) -> YouTubeInnerTubeBridge | YouTubeLiveChatPoller:
    if config.backend in {"innertube", "youtubei", "youtubei.js"}:
        return YouTubeInnerTubeBridge(config, on_message=on_message)
    if config.backend in {"api", "data_api", "youtube_api"}:
        return YouTubeLiveChatPoller(config, api_key=api_key, on_message=on_message)
    raise ValueError("youtube_chat.backend must be 'innertube' or 'api'")
