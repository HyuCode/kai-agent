"""LLM-based turn classification for streaming voice input."""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class TurnClassifierConfig:
    enabled: bool = False
    base_url: str = "http://100.94.173.74:8001/v1"
    model: str = "gemma-4-e4b"
    api_key: str = ""
    timeout_ms: int = 800


@dataclass(frozen=True)
class TurnClassifierInput:
    text: str
    elapsed_ms: int
    speech_final: bool
    partial_activity_seen: bool = False


@dataclass(frozen=True)
class TurnClassifierResult:
    action: str
    reason: str = ""


def parse_turn_classifier_response(text: str) -> TurnClassifierResult | None:
    """Parse a small JSON object from an LLM response."""
    raw = (text or "").strip()
    if not raw:
        return None
    match = _JSON_FENCE_RE.search(raw)
    if match:
        raw = match.group(1)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            payload = json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    action = str(payload.get("action") or payload.get("classification") or "").strip().lower()
    if action not in {"submit", "wait", "ignore", "backchannel"}:
        return None
    reason = str(payload.get("reason") or "").strip()
    return TurnClassifierResult(action=action, reason=reason)


def classify_turn_with_llm(config: TurnClassifierConfig, item: TurnClassifierInput) -> TurnClassifierResult | None:
    """Call an OpenAI-compatible local LLM and classify a buffered utterance."""
    if not config.enabled or not config.base_url or not config.model:
        return None

    endpoint = config.base_url.rstrip("/") + "/chat/completions"
    prompt = (
        "You classify whether a Japanese live-stream speaker has finished a turn.\n"
        "You are called after a silence/debounce window on the buffered transcript so far.\n"
        "Return only JSON with keys: action and reason.\n"
        "action must be one of: submit, wait, ignore, backchannel.\n"
        "Use semantic judgment, not keyword matching.\n"
        "submit: the assistant should answer now.\n"
        "wait: the speaker is likely continuing or asked the assistant to wait.\n"
        "ignore: noise, filler, or not addressed to the assistant.\n"
        "backchannel: a tiny acknowledgement would be appropriate, but no full answer.\n"
        "If the transcript is a complete request or instruction, choose submit.\n"
        "Do not choose wait merely because the speaker mentions that the assistant should listen until the end.\n"
        "Choose wait only when the buffered transcript itself is semantically incomplete or clearly promises more details.\n"
        "If the buffered transcript is a complete request and no speech has arrived during the debounce window, choose submit.\n"
        "Prefer wait when uncertain.\n"
    )
    user = {
        "transcript": item.text,
        "no_speech_for_ms": item.elapsed_ms,
        "speech_final": item.speech_final,
        "partial_activity_seen": item.partial_activity_seen,
    }
    body = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": json.dumps(user, ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 80,
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    timeout = max(0.05, config.timeout_ms / 1000)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        logger.debug("turn classifier request failed: %s", exc)
        return None

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None
    return parse_turn_classifier_response(str(content))
