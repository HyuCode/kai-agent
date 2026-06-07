"""Stream assistant mode presets."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ConfigSaver = Callable[[str, Any], bool]


@dataclass(frozen=True)
class StreamModeChange:
    key: str
    value: Any
    description: str


GAME_MODE_CHANGES: tuple[StreamModeChange, ...] = (
    StreamModeChange("stream_assistant.mode", "game", "配信モードをゲーム実況にする"),
    StreamModeChange("streaming_stt.enabled", True, "Deepgram streaming STT を有効にする"),
    StreamModeChange("streaming_stt.provider", "deepgram", "STT provider を Deepgram にする"),
    StreamModeChange("streaming_stt.always_on", True, "/voice on で常時聞き取りを始める"),
    StreamModeChange("streaming_stt.submit.min_chars", 4, "短い呼びかけも agent に送る"),
    StreamModeChange("streaming_stt.submit.debounce_ms", 1200, "無音後の送信待ちを短くする"),
    StreamModeChange("streaming_stt.submit.max_wait_ms", 4000, "turn 確定待ちの上限を短くする"),
    StreamModeChange("streaming_stt.submit.require_speech_final", False, "speech_final が来なくても無音で確定する"),
    StreamModeChange("voice.auto_tts", True, "/voice on で TTS も有効にする"),
    StreamModeChange("tts.aquestalk.koe_generation.timeout_ms", 3000, "AquesTalk 読み変換LLM不通時の待ちを短くする"),
    StreamModeChange("live_overlay.enabled", True, "OBS Browser Source overlay を有効にする"),
    StreamModeChange("youtube_chat.overlay.enabled", True, "選別チャットの overlay 表示を有効にする"),
    StreamModeChange("youtube_chat.selection.selected_only", True, "選別したチャットだけ扱う"),
)


def save_config_value(key_path: str, value: Any) -> bool:
    """Persist one config value using the round-trip YAML updater."""
    from hermes_cli.config import ensure_hermes_home, get_config_path, is_managed, managed_error
    from utils import atomic_roundtrip_yaml_update

    if is_managed():
        managed_error("save stream assistant mode")
        return False
    ensure_hermes_home()
    config_path = get_config_path()
    config_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        atomic_roundtrip_yaml_update(config_path, key_path, value)
        return True
    except Exception:
        return False


def apply_stream_mode(mode: str, *, saver: ConfigSaver | None = None) -> dict[str, Any]:
    normalized = str(mode or "").strip().lower()
    if normalized in {"game", "gaming", "実況", "ゲーム", "gameplay"}:
        changes = GAME_MODE_CHANGES
        mode_name = "game"
    else:
        return {
            "success": False,
            "error": f"unknown stream mode: {mode}",
            "supported_modes": ["game"],
        }

    writer = saver or save_config_value
    applied: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    for change in changes:
        if writer(change.key, change.value):
            applied.append({
                "key": change.key,
                "value": change.value,
                "description": change.description,
            })
        else:
            failed.append({
                "key": change.key,
                "value": change.value,
                "description": change.description,
            })

    return {
        "success": not failed,
        "mode": mode_name,
        "applied": applied,
        "failed": failed,
        "next_steps": [
            "/voice on で常時 STT と TTS を開始する",
            "OBS Browser Source に live_overlay の URL を設定する",
            "必要なら /voice status で状態を確認する",
        ],
    }


def stream_mode_status(config: dict[str, Any] | None) -> dict[str, Any]:
    root = config if isinstance(config, dict) else {}

    def get(path: str, default: Any = None) -> Any:
        cur: Any = root
        for part in path.split("."):
            if not isinstance(cur, dict) or part not in cur:
                return default
            cur = cur[part]
        return cur

    return {
        "mode": get("stream_assistant.mode", "game"),
        "streaming_stt_enabled": bool(get("streaming_stt.enabled", False)),
        "streaming_stt_provider": get("streaming_stt.provider", ""),
        "streaming_stt_always_on": bool(get("streaming_stt.always_on", False)),
        "streaming_stt_min_chars": get("streaming_stt.submit.min_chars", "-"),
        "streaming_stt_debounce_ms": get("streaming_stt.submit.debounce_ms", "-"),
        "streaming_stt_max_wait_ms": get("streaming_stt.submit.max_wait_ms", "-"),
        "streaming_stt_require_speech_final": bool(get("streaming_stt.submit.require_speech_final", True)),
        "voice_auto_tts": bool(get("voice.auto_tts", False)),
        "tts_provider": get("tts.provider", ""),
        "aquestalk_koe_timeout_ms": get("tts.aquestalk.koe_generation.timeout_ms", "-"),
        "live_overlay_enabled": bool(get("live_overlay.enabled", False)),
        "youtube_chat_overlay_enabled": bool(get("youtube_chat.overlay.enabled", False)),
        "youtube_chat_selected_only": bool(get("youtube_chat.selection.selected_only", True)),
    }


def format_apply_result(result: dict[str, Any]) -> str:
    if not result.get("success"):
        error = result.get("error") or "failed to apply stream mode"
        failed = result.get("failed") or []
        details = "\n".join(f"  - {item.get('key')}" for item in failed)
        return f"Stream mode setup failed: {error}" + (f"\n{details}" if details else "")

    lines = [f"Stream mode: {result.get('mode')} enabled"]
    for item in result.get("applied") or []:
        lines.append(f"  - {item['key']}: {item['value']}  ({item['description']})")
    lines.append("")
    lines.extend(f"  next: {step}" for step in result.get("next_steps") or [])
    return "\n".join(lines)


def format_status(status: dict[str, Any]) -> str:
    return "\n".join(
        [
            "Stream Assistant Status",
            f"  Mode:                  {status['mode']}",
            f"  Streaming STT:         {'ON' if status['streaming_stt_enabled'] else 'OFF'}",
            f"  STT provider:          {status['streaming_stt_provider'] or '-'}",
            f"  Always-on STT:         {'ON' if status['streaming_stt_always_on'] else 'OFF'}",
            f"  STT min chars:         {status['streaming_stt_min_chars']}",
            f"  STT debounce:          {status['streaming_stt_debounce_ms']} ms",
            f"  STT max wait:          {status['streaming_stt_max_wait_ms']} ms",
            f"  STT speech_final req:  {'ON' if status['streaming_stt_require_speech_final'] else 'OFF'}",
            f"  Voice auto TTS:        {'ON' if status['voice_auto_tts'] else 'OFF'}",
            f"  TTS provider:          {status['tts_provider'] or '-'}",
            f"  AquesTalk koe timeout: {status['aquestalk_koe_timeout_ms']} ms",
            f"  Live overlay:          {'ON' if status['live_overlay_enabled'] else 'OFF'}",
            f"  YouTube chat overlay:  {'ON' if status['youtube_chat_overlay_enabled'] else 'OFF'}",
            f"  Selected chat only:    {'ON' if status['youtube_chat_selected_only'] else 'OFF'}",
        ]
    )
