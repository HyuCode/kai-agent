"""Conversation turn detection helpers for streaming speech transcripts."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TurnDetectionConfig:
    min_chars: int = 8
    max_wait_ms: int = 6000
    turn_detection: str = "rules"
    require_speech_final: bool = True


@dataclass(frozen=True)
class TurnDetectionSignals:
    speech_final: bool = False


def classify_streaming_stt_turn(
    text: str,
    *,
    elapsed_ms: int,
    config: TurnDetectionConfig,
    signals: TurnDetectionSignals | None = None,
) -> tuple[str, str]:
    """Return (submit|wait|ignore, reason) without content-specific matching.

    This baseline intentionally avoids judging Japanese phrases, punctuation,
    or explicit hold/release words. Natural turn-taking should be handled by
    provider speech events, timing features, and an LLM-based classifier.
    """
    stripped = (text or "").strip()
    if not stripped:
        return "ignore", "empty"

    if config.turn_detection == "off":
        return "submit", "turn_detection_off"

    signals = signals or TurnDetectionSignals()

    if config.require_speech_final and not signals.speech_final:
        if elapsed_ms < config.max_wait_ms:
            return "wait", "awaiting_speech_final"

    if len(stripped) < config.min_chars:
        return "ignore", "below_min_chars"

    if elapsed_ms >= config.max_wait_ms:
        return "submit", "max_wait"

    if signals.speech_final:
        return "submit", "speech_final"

    return "submit", "debounced_silence"
