#!/usr/bin/env python3
"""Evaluate recorded voice fixtures against expected turn outputs."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hermes_cli.turn_classifier import TurnClassifierConfig  # noqa: E402
from scripts.replay_voice_turns import _load_events, _load_expected, replay_turns  # noqa: E402


@dataclass(frozen=True)
class FixtureResult:
    name: str
    jsonl: Path
    expected_path: Path | None
    turns: list[str]
    expected: list[str] | None

    @property
    def passed(self) -> bool:
        return self.expected is not None and self.turns == self.expected

    @property
    def missing_expected(self) -> bool:
        return self.expected is None


def _discover(root: Path) -> list[Path]:
    return sorted(root.glob("*.deepgram_events.jsonl"))


def _expected_for(jsonl: Path) -> Path:
    return jsonl.with_name(jsonl.name.replace(".deepgram_events.jsonl", ".expected_turns.json"))


def _evaluate_one(args: argparse.Namespace, jsonl: Path) -> FixtureResult:
    expected_path = _expected_for(jsonl)
    expected = _load_expected(expected_path) if expected_path.exists() else None
    classifier_config = TurnClassifierConfig(
        enabled=bool(args.classifier),
        base_url=args.classifier_base_url,
        model=args.classifier_model,
        timeout_ms=args.classifier_timeout_ms,
    )
    turns = replay_turns(
        _load_events(jsonl),
        min_chars=args.min_chars,
        max_wait_ms=args.max_wait_ms,
        debounce_ms=args.debounce_ms,
        llm_wait_debounce_ms=args.llm_wait_debounce_ms,
        commit_delay_ms=args.commit_delay_ms,
        classifier_config=classifier_config,
    )
    return FixtureResult(
        name=jsonl.name.replace(".deepgram_events.jsonl", ""),
        jsonl=jsonl,
        expected_path=expected_path if expected_path.exists() else None,
        turns=turns,
        expected=expected,
    )


def _print_result(result: FixtureResult) -> None:
    if result.missing_expected:
        mark = "WARN"
    else:
        mark = "PASS" if result.passed else "FAIL"
    print(f"{mark} {result.name}")
    print(f"  jsonl: {result.jsonl}")
    if result.expected_path:
        print(f"  expect: {result.expected_path}")
    else:
        print("  expect: (missing)")
    print("  observed:")
    for index, turn in enumerate(result.turns, start=1):
        print(f"    {index}. {turn}")
    if result.expected is not None and result.turns != result.expected:
        print("  expected:")
        for index, turn in enumerate(result.expected, start=1):
            print(f"    {index}. {turn}")


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "root",
        nargs="?",
        default="tests/fixtures/voice/local",
        help="Directory containing *.deepgram_events.jsonl fixtures",
    )
    parser.add_argument("--classifier", action="store_true", help="Use OpenAI-compatible LLM classifier")
    parser.add_argument("--classifier-base-url", default="http://100.94.173.74:8001/v1")
    parser.add_argument("--classifier-model", default="gemma-4-e4b")
    parser.add_argument("--classifier-timeout-ms", type=int, default=3000)
    parser.add_argument("--min-chars", type=int, default=8)
    parser.add_argument("--max-wait-ms", type=int, default=6000)
    parser.add_argument("--debounce-ms", type=int, default=1800)
    parser.add_argument("--llm-wait-debounce-ms", type=int, default=3000)
    parser.add_argument("--commit-delay-ms", type=int, default=0)
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    root = Path(args.root).expanduser().resolve()
    fixtures = _discover(root)
    results = [_evaluate_one(args, fixture) for fixture in fixtures]

    if args.json:
        print(
            json.dumps(
                {
                    "root": str(root),
                    "count": len(results),
                    "passed": sum(1 for result in results if result.passed),
                    "missing_expected": sum(1 for result in results if result.missing_expected),
                    "results": [
                        {
                            "name": result.name,
                            "jsonl": str(result.jsonl),
                            "expected_path": str(result.expected_path) if result.expected_path else None,
                            "passed": result.passed,
                            "missing_expected": result.missing_expected,
                            "turns": result.turns,
                            "expected": result.expected,
                        }
                        for result in results
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(f"Voice fixture evaluation: {root}")
        print(f"mode: {'classifier' if args.classifier else 'baseline'}")
        print()
        for result in results:
            _print_result(result)
            print()

    failures = [result for result in results if not result.missing_expected and not result.passed]
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
