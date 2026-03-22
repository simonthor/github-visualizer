from __future__ import annotations

import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from html.parser import HTMLParser

from github_visualizer.svg import ContributionCell


class GitHubFetchError(RuntimeError):
    """Raised when GitHub data cannot be fetched or parsed."""


def _parse_count_from_tooltip(text: str) -> int | None:
    """Extract a numeric contribution count from tooltip text.

    :param text: Tooltip text from GitHub contribution markup.
    :returns: Parsed contribution count, ``0`` for ``"No contributions"``, or
        ``None`` when the text does not contain a parseable count.
    """

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
    """Fetch a URL and return UTF-8 decoded response content.

    :param url: HTTP URL to fetch.
    :returns: Decoded response body text.
    :raises GitHubFetchError: When network or HTTP failures occur.
    """

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
        raise GitHubFetchError(
            f"Network error while calling GitHub: {exc.reason}"
        ) from exc


def fetch_created_year(username: str) -> int:
    """Fetch the account creation year for a GitHub user.

    :param username: GitHub username.
    :returns: Year extracted from ``created_at`` in the GitHub user API
        response.
    :raises GitHubFetchError: If API response parsing fails or the user cannot
        be retrieved.
    """

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
        raise GitHubFetchError(
            "Could not parse created_at from GitHub API response."
        ) from exc
    return created_dt.year


def fetch_year_cells(
    username: str, year: int, year_end: date
) -> dict[date, ContributionCell]:
    """Fetch contribution cells for one year slice.

    Uses the GitHub contributions endpoint bounded by ``year`` start and
    ``year_end`` to avoid requesting future dates.

    :param username: GitHub username.
    :param year: Year to fetch.
    :param year_end: Upper date bound applied to the selected year.
    :returns: Mapping of day to :class:`github_visualizer.svg.ContributionCell`.
    :raises GitHubFetchError: If parsing fails or no contribution cells are
        found.
    """

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


def fetch_all_cells(
    username: str, start_year: int, end_year: int
) -> dict[date, ContributionCell]:
    """Fetch contribution cells across an inclusive year range.

    :param username: GitHub username.
    :param start_year: First year to fetch.
    :param end_year: Last year to fetch.
    :returns: Combined mapping of day to
        :class:`github_visualizer.svg.ContributionCell`.
    """

    today = date.today()
    all_cells: dict[date, ContributionCell] = {}
    for year in range(start_year, end_year + 1):
        cells = fetch_year_cells(username=username, year=year, year_end=today)
        all_cells.update(cells)
    return all_cells
