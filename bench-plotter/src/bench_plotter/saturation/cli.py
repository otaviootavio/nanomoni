"""Command-line entry point for the expected-vs-real TPS report."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def bool_flag(value: str) -> bool:
    """argparse ``type`` validator for ``--title``: accepts only 'true'/'false'."""
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    raise argparse.ArgumentTypeError(f"expected 'true' or 'false', got {value!r}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compare each run's target TPS against the TPS the vendor actually "
            "served, and report the highest target a single sequential client "
            "sustained"
        )
    )
    parser.add_argument(
        "intervals",
        help="Path to the sweep timing JSON (e.g. tps_saturation_timing.json)",
    )
    parser.add_argument(
        "--output",
        default="plots",
        help="Root output directory (default: plots); timestamp subdir is created inside",
    )
    parser.add_argument(
        "--title",
        type=bool_flag,
        required=True,
        help="'true' or 'false': whether rendered figures get a title",
    )
    args = parser.parse_args()

    intervals_path = Path(args.intervals)
    if not intervals_path.exists():
        print(f"Error: {intervals_path} not found")
        sys.exit(1)

    print(f"Using timing file: {intervals_path}")
    print(f"Output root: {args.output}")

    from .runner import generate_saturation_report

    written, _summary = generate_saturation_report(
        timing_path=str(intervals_path),
        output_root=str(args.output),
        show_title=args.title,
    )
    print(f"Saturation report complete: {len(written)} file(s) written")


if __name__ == "__main__":
    main()
