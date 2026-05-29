#!/usr/bin/env python3
"""Replay Deepgram transcript JSONL into Hermes turn detection."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hermes_cli.turn_detection import (  # noqa: E402
    TurnDetectionConfig,
    TurnDetectionSignals,
    classify_streaming_stt_turn,
)
from hermes_cli.turn_classifier import (  # noqa: E402
    TurnClassifierConfig,
    TurnClassifierInput,
    TurnClassifierResult,
    classify_turn_with_llm,
)


def _load_events(path: Path) -> list[dict]:
    events: list[dict] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{path}:{lineno}: invalid JSON: {exc}") from exc
        if isinstance(event, dict):
            events.append(event)
    return events


def _load_expected(path: Path) -> list[str]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("expected_user_messages"), list):
        raise ValueError(f"{path} must contain expected_user_messages")
    return [str(item) for item in payload["expected_user_messages"]]


def replay_turns(
    events: list[dict],
    *,
    min_chars: int,
    max_wait_ms: int,
    debounce_ms: int = 1800,
    llm_wait_debounce_ms: int = 3000,
    classifier_config: TurnClassifierConfig | None = None,
    classifier=None,
    commit_delay_ms: int = 0,
) -> list[str]:
    """Return logical voice.transcript payloads from recorded STT events.

    This intentionally uses event boundaries, not transcript text matching.
    Partial events are ignored for agent input; final events are buffered until
    Deepgram marks a speech boundary.
    """
    cfg = TurnDetectionConfig(
        min_chars=min_chars,
        max_wait_ms=max_wait_ms,
        turn_detection="rules",
        require_speech_final=True,
    )
    parts: list[str] = []
    turns: list[str] = []
    last_activity_at_ms: int | None = None
    buffered_speech_final = False
    llm_wait_seen = False
    pending_turn: str | None = None
    pending_at_ms: int | None = None

    def cancel_pending_if_needed(received_at_ms: int | None) -> None:
        nonlocal pending_turn, pending_at_ms
        if pending_turn is None:
            return
        if isinstance(received_at_ms, int) and pending_at_ms is not None and received_at_ms - pending_at_ms < commit_delay_ms:
            parts.insert(0, pending_turn)
            pending_turn = None
            pending_at_ms = None

    def commit_pending_if_due(received_at_ms: int | None) -> None:
        nonlocal pending_turn, pending_at_ms
        if pending_turn is None:
            return
        if not isinstance(received_at_ms, int) or pending_at_ms is None or received_at_ms - pending_at_ms >= commit_delay_ms:
            turns.append(pending_turn)
            pending_turn = None
            pending_at_ms = None

    def classify(buffered: str, elapsed_ms: int) -> tuple[str, str]:
        if classifier_config and classifier_config.enabled and elapsed_ms < max_wait_ms:
            classify_fn = classifier or classify_turn_with_llm
            result: TurnClassifierResult | None = classify_fn(
                classifier_config,
                TurnClassifierInput(
                    text=buffered,
                    elapsed_ms=elapsed_ms,
                    speech_final=buffered_speech_final,
                    partial_activity_seen=False,
                ),
            )
            if result is not None:
                if result.action == "backchannel":
                    return "wait", f"llm:{result.reason or 'backchannel'}"
                return result.action, f"llm:{result.reason or result.action}"
        return classify_streaming_stt_turn(
            buffered,
            elapsed_ms=elapsed_ms,
            config=cfg,
            signals=TurnDetectionSignals(speech_final=buffered_speech_final),
        )

    def flush(elapsed_ms: int, *, now_ms: int | None = None) -> str | None:
        nonlocal buffered_speech_final, llm_wait_seen, pending_turn, pending_at_ms
        if not parts:
            return None
        buffered = " ".join(parts).strip()
        decision, _reason = classify(buffered, elapsed_ms)
        if decision == "ignore":
            parts.clear()
            buffered_speech_final = False
            llm_wait_seen = False
            return None
        elif decision == "submit":
            if commit_delay_ms > 0 and now_ms is not None:
                pending_turn = buffered
                pending_at_ms = now_ms
            else:
                turns.append(buffered)
            parts.clear()
            buffered_speech_final = False
            llm_wait_seen = False
            return None
        if _reason.startswith("llm:"):
            llm_wait_seen = True
        return _reason

    for event in events:
        received_at_ms = event.get("received_at_ms")
        commit_pending_if_due(received_at_ms if isinstance(received_at_ms, int) else None)
        cancel_pending_if_needed(received_at_ms if isinstance(received_at_ms, int) else None)
        active_debounce_ms = llm_wait_debounce_ms if llm_wait_seen else debounce_ms
        if (
            isinstance(received_at_ms, int)
            and last_activity_at_ms is not None
            and parts
            and received_at_ms - last_activity_at_ms >= active_debounce_ms
        ):
            reason = flush(received_at_ms - last_activity_at_ms, now_ms=received_at_ms)

        if not event.get("is_final"):
            if parts and isinstance(received_at_ms, int):
                last_activity_at_ms = received_at_ms
            continue

        text = str(event.get("text") or "").strip()
        if not text:
            continue
        parts.append(text)
        buffered_speech_final = buffered_speech_final or bool(event.get("speech_final"))
        last_activity_at_ms = received_at_ms if isinstance(received_at_ms, int) else last_activity_at_ms

    if parts:
        flush(max_wait_ms, now_ms=None)
    commit_pending_if_due(None)
    return turns


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("jsonl", help="Deepgram event JSONL generated by replay_voice_fixture.py")
    parser.add_argument("--min-chars", type=int, default=8)
    parser.add_argument("--max-wait-ms", type=int, default=6000)
    parser.add_argument("--debounce-ms", type=int, default=1800)
    parser.add_argument("--llm-wait-debounce-ms", type=int, default=3000)
    parser.add_argument("--commit-delay-ms", type=int, default=0)
    parser.add_argument("--classifier", action="store_true", help="Use OpenAI-compatible LLM turn classifier")
    parser.add_argument("--classifier-base-url", default="http://100.94.173.74:8001/v1")
    parser.add_argument("--classifier-model", default="gemma-4-e4b")
    parser.add_argument("--classifier-timeout-ms", type=int, default=3000)
    parser.add_argument("--expect", help="Compare turns with expected_turns.json")
    parser.add_argument("--json", action="store_true", help="Print turns as JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    turns = replay_turns(
        _load_events(Path(args.jsonl).expanduser().resolve()),
        min_chars=args.min_chars,
        max_wait_ms=args.max_wait_ms,
        debounce_ms=args.debounce_ms,
        llm_wait_debounce_ms=args.llm_wait_debounce_ms,
        classifier_config=TurnClassifierConfig(
            enabled=bool(args.classifier),
            base_url=args.classifier_base_url,
            model=args.classifier_model,
            timeout_ms=args.classifier_timeout_ms,
        ),
        commit_delay_ms=args.commit_delay_ms,
    )
    if args.json:
        print(json.dumps({"turns": turns}, ensure_ascii=False, indent=2))
    else:
        for index, turn in enumerate(turns, start=1):
            print(f"{index}: {turn}")
    if args.expect:
        expected = _load_expected(Path(args.expect).expanduser().resolve())
        if turns != expected:
            print("\nexpected:", file=sys.stderr)
            for index, turn in enumerate(expected, start=1):
                print(f"{index}: {turn}", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
