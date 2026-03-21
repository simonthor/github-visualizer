#!/usr/bin/env python3
"""Generate a long, wide SVG of a GitHub user's contribution graph."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape
from html.parser import HTMLParser
from pathlib import Path


GITHUB_LEVEL_COLORS = {
    0: "#ebedf0",
    1: "#9be9a8",
    2: "#40c463",
    3: "#30a14e",
    4: "#216e39",
}


class GitHubFetchError(RuntimeError):
    """Raised when GitHub data cannot be fetched or parsed."""


@dataclass(frozen=True)
class ContributionCell:
    count: int | None


def _parse_count_from_tooltip(text: str) -> int | None:
    normalized = " ".join(text.split())
    if not normalized:
        return None
    if normalized.lower().startswith("no contributions"):
        return 0
    match = re.search(r"([\d,]+)\s+contribution", normalized, re.IGNORECASE)
    if match is None:
        return None
    try:
        return int(match.group(1).replace(",", ""))
    except ValueError:
        return None


class ContributionRectParser(HTMLParser):
    """Extract contribution day cells from GitHub contribution HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.cells: dict[date, ContributionCell] = {}
        self._cell_id_to_date: dict[str, date] = {}
        self._active_tooltip_for: str | None = None
        self._active_tooltip_chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "tool-tip":
            attr_map = dict(attrs)
            tool_tip_for = attr_map.get("for")
            if tool_tip_for:
                self._active_tooltip_for = tool_tip_for
                self._active_tooltip_chunks = []
            return

        if tag not in {"rect", "td"}:
            return

        attr_map = dict(attrs)
        raw_date = attr_map.get("data-date")
        if raw_date is None:
            return

        try:
            day = date.fromisoformat(raw_date)
        except ValueError:
            return

        raw_count = attr_map.get("data-count")
        count: int | None = None
        if raw_count is not None:
            try:
                count = int(raw_count)
            except ValueError:
                count = None

        self.cells[day] = ContributionCell(count=count)
        cell_id = attr_map.get("id")
        if isinstance(cell_id, str) and cell_id:
            self._cell_id_to_date[cell_id] = day

    def handle_data(self, data: str) -> None:
        if self._active_tooltip_for is not None:
            self._active_tooltip_chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag != "tool-tip":
            return
        if self._active_tooltip_for is None:
            return

        tooltip_text = "".join(self._active_tooltip_chunks)
        count = _parse_count_from_tooltip(tooltip_text)
        if count is not None:
            day = self._cell_id_to_date.get(self._active_tooltip_for)
            if day is not None and day in self.cells:
                self.cells[day] = ContributionCell(count=count)

        self._active_tooltip_for = None
        self._active_tooltip_chunks = []


def _http_get(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json, text/html;q=0.9",
            "User-Agent": "github-contribution-svg-cli",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise GitHubFetchError("GitHub user not found.") from exc
        raise GitHubFetchError(f"GitHub returned HTTP {exc.code} for {url}") from exc
    except urllib.error.URLError as exc:
        raise GitHubFetchError(f"Network error while calling GitHub: {exc.reason}") from exc


def fetch_created_year(username: str) -> int:
    encoded_username = urllib.parse.quote(username, safe="")
    body = _http_get(f"https://api.github.com/users/{encoded_username}")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise GitHubFetchError("GitHub API returned non-JSON user data.") from exc

    created_at = payload.get("created_at")
    if not isinstance(created_at, str):
        message = payload.get("message")
        if isinstance(message, str) and message:
            raise GitHubFetchError(f"GitHub API error: {message}")
        raise GitHubFetchError("GitHub API response did not include created_at.")

    try:
        created_dt = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GitHubFetchError("Could not parse created_at from GitHub API response.") from exc
    return created_dt.year


def fetch_year_cells(username: str, year: int, year_end: date) -> dict[date, ContributionCell]:
    year_start = date(year, 1, 1)
    to_date = min(year_end, date(year, 12, 31))
    encoded_username = urllib.parse.quote(username, safe="")
    url = (
        f"https://github.com/users/{encoded_username}/contributions"
        f"?from={year_start.isoformat()}&to={to_date.isoformat()}"
    )
    html = _http_get(url)
    parser = ContributionRectParser()
    parser.feed(html)
    parser.close()
    if not parser.cells:
        raise GitHubFetchError(
            "No contribution cells were found in GitHub response. "
            "GitHub markup may have changed."
        )
    return parser.cells


def fetch_all_cells(username: str, start_year: int, end_year: int) -> dict[date, ContributionCell]:
    today = date.today()
    all_cells: dict[date, ContributionCell] = {}
    for year in range(start_year, end_year + 1):
        cells = fetch_year_cells(username=username, year=year, year_end=today)
        all_cells.update(cells)
    return all_cells


def _previous_sunday(day: date) -> date:
    # Python weekday: Monday=0 ... Sunday=6, so convert to distance from Sunday.
    offset = (day.weekday() + 1) % 7
    return day - timedelta(days=offset)


def _next_saturday(day: date) -> date:
    # Python weekday: Monday=0 ... Saturday=5.
    offset = (5 - day.weekday()) % 7
    return day + timedelta(days=offset)


def _weekday_sunday_first(day: date) -> int:
    return (day.weekday() + 1) % 7


def _contribution_count_to_level(contribution_count: int, max_count: int) -> int:
    if contribution_count <= 0:
        return 0
    if contribution_count == 1:
        return 1
    if max_count <= 1:
        return 1
    if contribution_count >= max_count:
        return 4

    ratio = (contribution_count - 1) / (max_count - 1)
    if ratio < 0.34:
        return 2
    if ratio < 0.67:
        return 3
    return 4


def build_svg(
    username: str,
    cells: dict[date, ContributionCell],
    start_year: int,
    end_year: int,
) -> str:
    today = date.today()
    first_day = date(start_year, 1, 1)
    last_day = min(date(end_year, 12, 31), today)

    grid_start = _previous_sunday(first_day)
    grid_end = _next_saturday(last_day)

    cell_size = 10
    gap = 2
    pitch = cell_size + gap
    left_pad = 44
    top_pad = 28
    right_pad = 18
    bottom_pad = 16

    total_weeks = ((grid_end - grid_start).days // 7) + 1
    width = left_pad + total_weeks * pitch + right_pad
    height = top_pad + 7 * pitch + bottom_pad

    svg_lines: list[str] = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="GitHub contributions for {escape(username)}">'
        ),
        "<style>",
        "  text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; }",
        "</style>",
        f'<text x="{left_pad}" y="14" font-size="12" fill="#24292f">{escape(username)} contributions ({start_year}-{end_year})</text>',
    ]

    for year in range(start_year, end_year + 1):
        jan_first = date(year, 1, 1)
        if jan_first > grid_end:
            continue
        x = left_pad + ((jan_first - grid_start).days // 7) * pitch
        svg_lines.append(
            f'<text x="{x}" y="26" font-size="10" fill="#57606a">{year}</text>'
        )

    weekday_labels = [("Sun", 0), ("Tue", 2), ("Thu", 4), ("Sat", 6)]
    for label, row in weekday_labels:
        y = top_pad + row * pitch + 8
        svg_lines.append(
            f'<text x="8" y="{y}" font-size="9" fill="#57606a">{label}</text>'
        )

    max_count = max((cell.count or 0) for cell in cells.values()) if cells else 0

    day = grid_start
    while day <= grid_end:
        week_index = (day - grid_start).days // 7
        row = _weekday_sunday_first(day)
        x = left_pad + week_index * pitch
        y = top_pad + row * pitch

        cell = cells.get(day)
        count = cell.count if cell is not None else None

        contribution_count = count if count is not None else 0
        level = _contribution_count_to_level(contribution_count, max_count)
        color = GITHUB_LEVEL_COLORS.get(level, GITHUB_LEVEL_COLORS[0])
        unit = "contribution" if contribution_count == 1 else "contributions"
        title = f"{contribution_count} {unit} on {day.isoformat()}"

        svg_lines.append(
            f'<rect x="{x}" y="{y}" width="{cell_size}" height="{cell_size}" fill="{color}" rx="2" ry="2">'
            f"<title>{escape(title)}</title>"
            "</rect>"
        )
        day += timedelta(days=1)

    svg_lines.append("</svg>")
    return "\n".join(svg_lines) + "\n"


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
        "--start-year",
        type=int,
        help="Override first year (default: account creation year)",
    )
    parser.add_argument(
        "--end-year",
        type=int,
        help="Override last year (default: current year)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    today = date.today()

    created_year = fetch_created_year(args.username)
    start_year = args.start_year if args.start_year is not None else created_year
    end_year = args.end_year if args.end_year is not None else today.year

    if start_year > end_year:
        raise ValueError("start-year must be <= end-year.")
    if end_year > today.year:
        raise ValueError("end-year cannot be in the future.")

    cells = fetch_all_cells(args.username, start_year=start_year, end_year=end_year)
    svg_text = build_svg(args.username, cells, start_year=start_year, end_year=end_year)

    output_path = args.output if args.output is not None else Path(
        f"{args.username}-contributions.svg"
    )
    output_path.write_text(svg_text, encoding="utf-8")
    print(f"Wrote {output_path} ({start_year}-{end_year}, {len(cells)} days parsed)")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (ValueError, GitHubFetchError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise SystemExit(1)
