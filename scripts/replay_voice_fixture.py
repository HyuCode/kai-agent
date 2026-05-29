#!/usr/bin/env python3
"""Replay a recorded WAV file through Deepgram streaming STT.

This is a manual evaluation tool for Hermes streaming voice input. It writes
Deepgram transcript events as JSONL so turn-detection behavior can be replayed
without recording the same utterance repeatedly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hermes_cli.streaming_stt import (  # noqa: E402
    DeepgramStreamingConfig,
    _default_ssl_context,
    build_deepgram_listen_url,
    iter_wav_pcm_chunks,
    load_deepgram_streaming_config,
    parse_deepgram_message,
    transcript_event_to_json,
)


def _config_from_args(args: argparse.Namespace) -> DeepgramStreamingConfig:
    base = load_deepgram_streaming_config()
    return DeepgramStreamingConfig(
        api_key=base.api_key,
        model=args.model or base.model,
        language=args.language or base.language,
        sample_rate=args.sample_rate or base.sample_rate,
        channels=args.channels or base.channels,
        interim_results=base.interim_results if args.interim_results is None else args.interim_results,
        smart_format=base.smart_format if args.smart_format is None else args.smart_format,
        endpointing=base.endpointing if args.endpointing is None else args.endpointing,
        vad_events=base.vad_events if args.vad_events is None else args.vad_events,
        chunk_ms=args.chunk_ms or base.chunk_ms,
        url=args.url or base.url,
    )


async def _replay(args: argparse.Namespace) -> int:
    try:
        import websockets
    except ImportError:
        print("websockets is required. Install with: uv pip install -e '.[deepgram-stt]'", file=sys.stderr)
        return 2

    config = _config_from_args(args)
    if not config.api_key:
        print("DEEPGRAM_API_KEY is required", file=sys.stderr)
        return 2

    wav_path = Path(args.wav).expanduser().resolve()
    out_path = Path(args.out).expanduser().resolve() if args.out else None
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)

    uri = build_deepgram_listen_url(config)
    headers = {"Authorization": f"Token {config.api_key}"}
    chunks = list(
        iter_wav_pcm_chunks(
            wav_path,
            sample_rate=config.sample_rate,
            channels=config.channels,
            chunk_ms=config.chunk_ms,
        )
    )

    event_count = 0
    final_count = 0
    writer = out_path.open("w", encoding="utf-8") if out_path else None

    try:
        started_at = time.monotonic()
        async with websockets.connect(
            uri,
            additional_headers=headers,
            ssl=_default_ssl_context(),
        ) as ws:

            async def send_audio() -> None:
                delay = config.chunk_ms / 1000
                for chunk in chunks:
                    await ws.send(chunk)
                    if args.realtime:
                        await asyncio.sleep(delay)
                await ws.send(json.dumps({"type": "CloseStream"}))

            async def receive_events() -> None:
                nonlocal event_count, final_count
                async for message in ws:
                    event = parse_deepgram_message(message)
                    if event is None:
                        continue
                    event_count += 1
                    if event.is_final:
                        final_count += 1
                    payload: dict[str, Any] = transcript_event_to_json(event)
                    payload["received_at_ms"] = int((time.monotonic() - started_at) * 1000)
                    line = json.dumps(payload, ensure_ascii=False)
                    if writer:
                        writer.write(line + "\n")
                        writer.flush()
                    if not args.quiet:
                        marker = "final" if event.is_final else "partial"
                        print(f"{marker} speech_final={event.speech_final}: {event.text}")

            sender = asyncio.create_task(send_audio())
            receiver = asyncio.create_task(receive_events())
            await sender
            try:
                await asyncio.wait_for(receiver, timeout=args.close_timeout)
            except asyncio.TimeoutError:
                receiver.cancel()
    finally:
        if writer:
            writer.close()

    if not args.quiet:
        dest = f" -> {out_path}" if out_path else ""
        print(f"events={event_count} finals={final_count}{dest}")
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wav", help="16-bit PCM mono WAV matching streaming_stt.deepgram.sample_rate")
    parser.add_argument("--out", help="Write Deepgram transcript events as JSONL")
    parser.add_argument("--model", help="Deepgram model override")
    parser.add_argument("--language", help="Deepgram language override")
    parser.add_argument("--sample-rate", type=int, help="Expected WAV/sample rate")
    parser.add_argument("--channels", type=int, help="Expected WAV channel count")
    parser.add_argument("--endpointing", type=int, help="Deepgram endpointing override")
    parser.add_argument("--chunk-ms", type=int, help="Chunk size override")
    parser.add_argument("--url", help="Deepgram listen URL override")
    parser.add_argument("--smart-format", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--interim-results", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--vad-events", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument(
        "--realtime",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Replay chunks with real-time pacing. Disable only for quick diagnostics.",
    )
    parser.add_argument("--close-timeout", type=float, default=10.0)
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_replay(_parse_args(argv or sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
