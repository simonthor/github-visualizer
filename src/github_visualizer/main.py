#!/usr/bin/env python3
"""Generate a long, wide SVG of a GitHub user's contribution graph."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path
from github_visualizer.github_fetch import (
    GitHubFetchError,
    fetch_all_cells,
    fetch_created_year,
)
from github_visualizer.svg import build_svg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch a GitHub user's contribution graph across all years and write a wide SVG."
        )
    )
    parser.add_argument("username", help="GitHub username")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="Output SVG path (default: <username>-contributions.svg)",
    )
    parser.add_argument(
        "-s",
        "--start-year",
        type=int,
        help="Override first year (default: account creation year)",
    )
    parser.add_argument(
        "-e",
        "--end-year",
        type=int,
        help="Override last year (default: current year)",
    )
    parser.add_argument(
        "--interval",
        choices=("none", "year", "month"),
        default="none",
        help="Split rows by interval: none (single row), year, or month.",
    )
    return parser.parse_args()


def _resolve_year_range(args: argparse.Namespace, today: date) -> tuple[int, int]:
    created_year = fetch_created_year(args.username)
    start_year = args.start_year if args.start_year is not None else created_year
    end_year = args.end_year if args.end_year is not None else today.year

    if start_year > end_year:
        raise ValueError("start-year must be <= end-year.")
    if end_year > today.year:
        raise ValueError("end-year cannot be in the future.")
    return start_year, end_year


def _resolve_output_path(username: str, output: Path | None) -> Path:
    if output is not None:
        return output
    return Path(f"{username}-contributions.svg")


def main() -> int:
    args = parse_args()
    today = date.today()
    start_year, end_year = _resolve_year_range(args, today)

    cells = fetch_all_cells(args.username, start_year=start_year, end_year=end_year)
    svg_text = build_svg(
        args.username,
        cells,
        start_year=start_year,
        end_year=end_year,
        interval=args.interval,
    )
    output_path = _resolve_output_path(args.username, args.output)
    output_path.write_text(svg_text, encoding="utf-8")
    print(f"Wrote {output_path} ({start_year}-{end_year}, {len(cells)} days parsed)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, GitHubFetchError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
