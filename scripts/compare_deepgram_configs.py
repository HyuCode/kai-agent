#!/usr/bin/env python3
"""Replay voice WAV fixtures with multiple Deepgram setting variants."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.replay_voice_fixture import _parse_args as parse_replay_args  # noqa: E402
from scripts.replay_voice_fixture import _replay  # noqa: E402
from scripts.replay_voice_turns import _load_events, replay_turns  # noqa: E402
from hermes_cli.turn_classifier import TurnClassifierConfig  # noqa: E402


@dataclass(frozen=True)
class Variant:
    name: str
    endpointing: int | None = None
    smart_format: bool | None = None


VARIANTS = (
    Variant("default"),
    Variant("endpointing_500", endpointing=500),
    Variant("endpointing_800", endpointing=800),
    Variant("smart_format_off", smart_format=False),
)


def _wav_files(root: Path) -> list[Path]:
    return sorted(root.glob("*.wav"))


def _out_path(out_dir: Path, wav: Path, variant: Variant) -> Path:
    return out_dir / f"{wav.stem}.{variant.name}.deepgram_events.jsonl"


def _final_text(events: list[dict]) -> str:
    return " ".join(str(e.get("text") or "").strip() for e in events if e.get("is_final") and e.get("text")).strip()


async def _run_variant(args: argparse.Namespace, wav: Path, variant: Variant, out_path: Path) -> None:
    replay_argv = [
        str(wav),
        "--out",
        str(out_path),
        "--quiet",
        "--realtime" if args.realtime else "--no-realtime",
        "--close-timeout",
        str(args.close_timeout),
    ]
    if args.model:
        replay_argv += ["--model", args.model]
    if args.language:
        replay_argv += ["--language", args.language]
    if variant.endpointing is not None:
        replay_argv += ["--endpointing", str(variant.endpointing)]
    if variant.smart_format is not None:
        replay_argv.append("--smart-format" if variant.smart_format else "--no-smart-format")
    code = await _replay(parse_replay_args(replay_argv))
    if code:
        raise RuntimeError(f"Deepgram replay failed for {wav.name} {variant.name}: {code}")


async def _main_async(args: argparse.Namespace) -> int:
    root = Path(args.root).expanduser().resolve()
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    variants = [variant for variant in VARIANTS if not args.variant or variant.name in args.variant]
    rows = []

    for wav in _wav_files(root):
        for variant in variants:
            out_path = _out_path(out_dir, wav, variant)
            if not out_path.exists() or args.refresh:
                await _run_variant(args, wav, variant, out_path)
            events = _load_events(out_path)
            turns = replay_turns(
                events,
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
            )
            rows.append(
                {
                    "wav": wav.name,
                    "variant": variant.name,
                    "jsonl": str(out_path),
                    "final_count": sum(1 for event in events if event.get("is_final")),
                    "turn_count": len(turns),
                    "final_text": _final_text(events),
                    "turns": turns,
                }
            )

    if args.json:
        print(json.dumps({"results": rows}, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print(f"{row['wav']} [{row['variant']}] finals={row['final_count']} turns={row['turn_count']}")
            print(f"  final: {row['final_text']}")
            for index, turn in enumerate(row["turns"], start=1):
                print(f"  turn {index}: {turn}")
            print()
    return 0


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default="tests/fixtures/voice/local")
    parser.add_argument("--out-dir", default="tests/fixtures/voice/local/deepgram_compare")
    parser.add_argument("--variant", action="append", help="Variant name to run. Can be repeated.")
    parser.add_argument("--refresh", action="store_true", help="Regenerate JSONL even if it exists")
    parser.add_argument("--classifier", action="store_true")
    parser.add_argument("--classifier-base-url", default="http://100.94.173.74:8001/v1")
    parser.add_argument("--classifier-model", default="gemma-4-e4b")
    parser.add_argument("--classifier-timeout-ms", type=int, default=3000)
    parser.add_argument("--model")
    parser.add_argument("--language")
    parser.add_argument("--min-chars", type=int, default=8)
    parser.add_argument("--max-wait-ms", type=int, default=6000)
    parser.add_argument("--debounce-ms", type=int, default=1800)
    parser.add_argument("--llm-wait-debounce-ms", type=int, default=3000)
    parser.add_argument("--close-timeout", type=float, default=10.0)
    parser.add_argument("--realtime", action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(_main_async(_parse_args(argv or sys.argv[1:])))


if __name__ == "__main__":
    raise SystemExit(main())
