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
    first_contribution_day,
    has_contributions_before_year,
)
from github_visualizer.svg import ContributionCell, build_svg


def parse_args() -> argparse.Namespace:
    """Parse CLI options for :func:`main`.

    :returns: Parsed command-line arguments including username, date range,
        output path, interval mode, and first-contribution clipping flag.
    """

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
    parser.add_argument(
        "--from-first",
        action="store_true",
        help=(
            "When the first contribution day is within the loaded years, "
            "omit squares for earlier days."
        ),
    )
    return parser.parse_args()


def _resolve_year_range(
    args: argparse.Namespace, today: date, created_year: int
) -> tuple[int, int]:
    """Resolve and validate the inclusive year range for graph generation.

    :param args: Parsed command-line arguments.
    :param today: Current local date used to reject future years.
    :param created_year: Account creation year for default start-year behavior.
    :returns: Inclusive ``(start_year, end_year)`` tuple.
    :raises ValueError: If ``start_year`` is greater than ``end_year`` or if
        ``end_year`` is in the future.
    """

    start_year = args.start_year if args.start_year is not None else created_year
    end_year = args.end_year if args.end_year is not None else today.year

    if start_year > end_year:
        raise ValueError("start-year must be <= end-year.")
    if end_year > today.year:
        raise ValueError("end-year cannot be in the future.")
    return start_year, end_year


def _resolve_output_path(username: str, output: Path | None) -> Path:
    """Return the final output path for the generated SVG file.

    :param username: GitHub username used for default filename generation.
    :param output: Optional explicit output path from CLI arguments.
    :returns: Output file path to write.
    """

    if output is not None:
        return output
    return Path(f"{username}-contributions.svg")


def _resolve_first_visible_day(
    *,
    username: str,
    created_year: int,
    cells: dict[date, ContributionCell],
    from_first: bool,
) -> date | None:
    """Determine the first day that should render as a square.

    :param username: GitHub username.
    :param created_year: User account creation year.
    :param cells: Loaded contribution cells.
    :param from_first: Whether ``--from-first`` is enabled.
    :returns: Earliest visible day when clipping applies, else ``None``.
    """

    if not from_first:
        return None

    loaded_first = first_contribution_day(cells)
    if loaded_first is None:
        return None

    # Only clip if loaded years include the user's true first contribution day.
    if has_contributions_before_year(username, created_year, loaded_first.year):
        return None

    return loaded_first


def main() -> int:
    """Run the CLI workflow and write the contribution SVG.

    Coordinates argument parsing, GitHub data fetching via
    :mod:`github_visualizer.github_fetch`, and SVG rendering via
    :func:`github_visualizer.svg.build_svg`.

    :returns: Process exit code ``0`` on success.
    :raises ValueError: If user-provided year range arguments are invalid.
    :raises github_visualizer.github_fetch.GitHubFetchError: If GitHub API or
        contribution HTML fetch/parsing fails.
    :raises OSError: If writing the output file fails.
    """

    args = parse_args()
    today = date.today()
    created_year = fetch_created_year(args.username)
    start_year, end_year = _resolve_year_range(args, today, created_year)

    cells = fetch_all_cells(args.username, start_year=start_year, end_year=end_year)
    first_visible_day = _resolve_first_visible_day(
        username=args.username,
        created_year=created_year,
        cells=cells,
        from_first=args.from_first,
    )
    svg_text = build_svg(
        args.username,
        cells,
        start_year=start_year,
        end_year=end_year,
        interval=args.interval,
        first_visible_day=first_visible_day,
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
