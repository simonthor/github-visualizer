from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from urllib.parse import quote
from typing import Literal


GITHUB_LEVEL_COLORS = {
    0: "#ebedf0",
    1: "#9be9a8",
    2: "#40c463",
    3: "#30a14e",
    4: "#216e39",
}

IntervalMode = Literal["none", "year", "month"]
"""Row segmentation mode for :func:`build_svg`."""


@dataclass(frozen=True)
class ContributionCell:
    """Contribution data for one calendar day."""

    count: int | None


@dataclass(frozen=True)
class ContributionSegment:
    """Inclusive date segment represented as one SVG row."""

    label: str
    start: date
    end: date


@dataclass(frozen=True)
class SegmentLayout:
    """Precomputed grid layout metadata for a :class:`ContributionSegment`."""

    segment: ContributionSegment
    grid_start: date
    grid_end: date
    total_weeks: int


@dataclass(frozen=True)
class SvgGeometry:
    """Geometry constants used to position labels and contribution cells."""

    cell_size: int = 10
    gap: int = 2
    left_pad: int = 88
    top_pad: int = 26
    row_header_height: int = 16
    row_gap: int = 14
    right_pad: int = 18
    bottom_pad: int = 16
    segment_label_x: int = 8
    weekday_label_x: int = 44

    @property
    def pitch(self) -> int:
        return self.cell_size + self.gap

    @property
    def row_height(self) -> int:
        return 7 * self.pitch

    @property
    def row_block_height(self) -> int:
        return self.row_header_height + self.row_height


WEEKDAY_LABELS: tuple[tuple[str, int], ...] = (
    ("Sun", 0),
    ("Tue", 2),
    ("Thu", 4),
    ("Sat", 6),
)
"""Displayed weekday labels and their Sunday-first row indices."""


def _weekday_sunday_first(day: date) -> int:
    """Convert Python weekday index to Sunday-first row index.

    :param day: Date to map.
    :returns: Integer row index where Sunday is ``0`` and Saturday is ``6``.
    """

    return (day.weekday() + 1) % 7


def _previous_sunday(day: date) -> date:
    """Return the Sunday at or before ``day``.

    :param day: Anchor date.
    :returns: Previous or same Sunday.
    """

    # Python weekday: Monday=0 ... Sunday=6, so convert to distance from Sunday.
    offset = (day.weekday() + 1) % 7
    return day - timedelta(days=offset)


def _next_saturday(day: date) -> date:
    """Return the Saturday at or after ``day``.

    :param day: Anchor date.
    :returns: Next or same Saturday.
    """

    # Python weekday: Monday=0 ... Saturday=5.
    offset = (5 - day.weekday()) % 7
    return day + timedelta(days=offset)


def _next_month_start(day: date) -> date:
    """Return the first day of the month after ``day``.

    :param day: Date within a month.
    :returns: First date of the following month.
    """

    if day.month == 12:
        return date(day.year + 1, 1, 1)
    return date(day.year, day.month + 1, 1)


def _build_segments(
    first_day: date, last_day: date, interval: IntervalMode
) -> list[ContributionSegment]:
    """Build row segments from an inclusive date range.

    :param first_day: Inclusive start date.
    :param last_day: Inclusive end date.
    :param interval: Segmentation mode.
    :returns: Ordered list of row segments.
    :raises ValueError: If ``interval`` is unsupported.
    """

    if interval == "none":
        return [ContributionSegment(label="All", start=first_day, end=last_day)]

    if interval == "year":
        segments: list[ContributionSegment] = []
        for year in range(first_day.year, last_day.year + 1):
            segment_start = date(year, 1, 1)
            segment_end = min(date(year, 12, 31), last_day)
            segments.append(
                ContributionSegment(
                    label=str(year),
                    start=segment_start,
                    end=segment_end,
                )
            )
        return segments

    if interval == "month":
        segments = []
        cursor = date(first_day.year, first_day.month, 1)
        while cursor <= last_day:
            next_start = _next_month_start(cursor)
            segment_end = min(next_start - timedelta(days=1), last_day)
            segments.append(
                ContributionSegment(
                    label=cursor.strftime("%Y-%m"),
                    start=cursor,
                    end=segment_end,
                )
            )
            cursor = next_start
        return segments

    raise ValueError(f"Unsupported interval: {interval}")


def _build_segment_layouts(segments: list[ContributionSegment]) -> list[SegmentLayout]:
    """Compute Sunday/Saturday-aligned grid bounds for each segment.

    :param segments: Contribution segments to place on rows.
    :returns: Layout records with aligned week grid metadata.
    """

    layouts: list[SegmentLayout] = []
    for segment in segments:
        grid_start = _previous_sunday(segment.start)
        grid_end = _next_saturday(segment.end)
        total_weeks = ((grid_end - grid_start).days // 7) + 1
        layouts.append(
            SegmentLayout(
                segment=segment,
                grid_start=grid_start,
                grid_end=grid_end,
                total_weeks=total_weeks,
            )
        )
    return layouts


def _max_contribution_count(cells: dict[date, ContributionCell]) -> int:
    """Return the maximum contribution count across all cells.

    :param cells: Contribution map keyed by day.
    :returns: Highest contribution count, or ``0`` for empty input.
    """

    return max((cell.count or 0) for cell in cells.values()) if cells else 0


def _calculate_svg_size(
    layouts: list[SegmentLayout], geometry: SvgGeometry
) -> tuple[int, int]:
    """Calculate output SVG width and height.

    :param layouts: Row layout metadata.
    :param geometry: Positioning constants.
    :returns: ``(width, height)`` for the root SVG element.
    """

    max_weeks = max(layout.total_weeks for layout in layouts)
    total_rows = len(layouts)
    width = geometry.left_pad + max_weeks * geometry.pitch + geometry.right_pad
    height = (
        geometry.top_pad
        + total_rows * geometry.row_block_height
        + max(0, total_rows - 1) * geometry.row_gap
        + geometry.bottom_pad
    )
    return width, height


def _build_svg_header_lines(
    *,
    width: int,
    height: int,
    username: str,
    start_year: int,
    end_year: int,
    interval: IntervalMode,
    geometry: SvgGeometry,
) -> list[str]:
    """Build initial SVG lines including metadata and top title.

    :param width: SVG width.
    :param height: SVG height.
    :param username: GitHub username.
    :param start_year: Inclusive start year label.
    :param end_year: Inclusive end year label.
    :param interval: Active interval mode.
    :param geometry: Positioning constants.
    :returns: List of SVG lines that open the document and render the title.
    """

    encoded_username = quote(username, safe="")
    profile_url = f"https://github.com/{encoded_username}"
    title_text = f" contributions ({start_year}-{end_year}, interval={interval})"

    return [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="GitHub contributions for {escape(username)}">'
        ),
        "<style>",
        "  text { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif; }",
        "</style>",
        f'<text x="{geometry.left_pad}" y="14" font-size="12">',
        # Add underline and blue color to username to indicate it's a link, but don't make the whole title a link
        f'<a href="{profile_url}" target="_blank" rel="noopener noreferrer" fill="#0969da" text-decoration="underline">'
        f"{escape(username)}"
        "</a>"
        f"{title_text}"
        "</text>",
    ]


def _row_grid_top(row_index: int, geometry: SvgGeometry) -> tuple[int, int]:
    """Compute y coordinates for row header text and cell grid.

    :param row_index: Zero-based row index.
    :param geometry: Positioning constants.
    :returns: ``(row_title_y, grid_top)`` coordinates.
    """

    block_top = geometry.top_pad + row_index * (
        geometry.row_block_height + geometry.row_gap
    )
    row_title_y = block_top + 11
    grid_top = block_top + geometry.row_header_height
    return row_title_y, grid_top


def _append_weekday_labels(
    svg_lines: list[str], grid_top: int, geometry: SvgGeometry
) -> None:
    """Append weekday labels for one row.

    :param svg_lines: Mutable SVG line buffer.
    :param grid_top: Top y-coordinate of the row cell grid.
    :param geometry: Positioning constants.
    """

    for label, weekday_row in WEEKDAY_LABELS:
        y = grid_top + weekday_row * geometry.pitch + 8
        svg_lines.append(
            f'<text x="{geometry.weekday_label_x}" y="{y}" font-size="9" fill="#57606a">{label}</text>'
        )


def _contribution_count_to_level(contribution_count: int, max_count: int) -> int:
    """Map a contribution count to a GitHub-like color level.

    Guarantees ``0 -> 0`` and ``1 -> 1``, while scaling larger values relative
    to ``max_count``.

    :param contribution_count: Day contribution count.
    :param max_count: Maximum contribution count across the full range.
    :returns: Integer level in ``0..4``.
    """

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


def _append_segment_cells(
    svg_lines: list[str],
    *,
    layout: SegmentLayout,
    grid_top: int,
    geometry: SvgGeometry,
    cells: dict[date, ContributionCell],
    max_count: int,
    first_visible_day: date | None,
) -> None:
    """Append contribution cells for one segment row.

    :param svg_lines: Mutable SVG line buffer.
    :param layout: Segment layout metadata.
    :param grid_top: Top y-coordinate of the row cell grid.
    :param geometry: Positioning constants.
    :param cells: Contribution map keyed by date.
    :param max_count: Maximum contribution count across all rows.
    :param first_visible_day: Optional first day that should render a square.
        Days before this date are skipped.
    """

    day = layout.segment.start
    while day <= layout.segment.end:
        if first_visible_day is not None and day < first_visible_day:
            day += timedelta(days=1)
            continue

        week_index = (day - layout.grid_start).days // 7
        weekday_row = _weekday_sunday_first(day)
        x = geometry.left_pad + week_index * geometry.pitch
        y = grid_top + weekday_row * geometry.pitch

        cell = cells.get(day)
        contribution_count = (
            cell.count if cell is not None and cell.count is not None else 0
        )
        level = _contribution_count_to_level(contribution_count, max_count)
        color = GITHUB_LEVEL_COLORS.get(level, GITHUB_LEVEL_COLORS[0])
        unit = "contribution" if contribution_count == 1 else "contributions"
        title = f"{contribution_count} {unit} on {day.isoformat()}"

        svg_lines.append(
            f'<rect x="{x}" y="{y}" width="{geometry.cell_size}" height="{geometry.cell_size}" fill="{color}" rx="2" ry="2">'
            f"<title>{escape(title)}</title>"
            "</rect>"
        )
        day += timedelta(days=1)


def build_svg(
    username: str,
    cells: dict[date, ContributionCell],
    start_year: int,
    end_year: int,
    interval: IntervalMode = "none",
    first_visible_day: date | None = None,
) -> str:
    """Render an SVG contribution graph for the selected date range.

    :param username: GitHub username used in title and accessibility label.
    :param cells: Contribution map keyed by date.
    :param start_year: Inclusive start year.
    :param end_year: Inclusive end year.
    :param interval: Row segmentation mode.
    :param first_visible_day: Optional day to start rendering cells from. Days
        before this date are omitted.
    :returns: Complete SVG document text.
    """

    today = date.today()
    first_day = date(start_year, 1, 1)
    last_day = min(date(end_year, 12, 31), today)
    segments = _build_segments(
        first_day=first_day, last_day=last_day, interval=interval
    )
    layouts = _build_segment_layouts(segments)
    geometry = SvgGeometry()
    width, height = _calculate_svg_size(layouts, geometry)
    svg_lines = _build_svg_header_lines(
        width=width,
        height=height,
        username=username,
        start_year=start_year,
        end_year=end_year,
        interval=interval,
        geometry=geometry,
    )
    max_count = _max_contribution_count(cells)

    for row_index, layout in enumerate(layouts):
        row_title_y, grid_top = _row_grid_top(row_index, geometry)

        svg_lines.append(
            f'<text x="{geometry.segment_label_x}" y="{row_title_y}" font-size="10" fill="#57606a">{escape(layout.segment.label)}</text>'
        )
        _append_weekday_labels(svg_lines, grid_top, geometry)
        _append_segment_cells(
            svg_lines,
            layout=layout,
            grid_top=grid_top,
            geometry=geometry,
            cells=cells,
            max_count=max_count,
            first_visible_day=first_visible_day,
        )

    svg_lines.append("</svg>")
    return "\n".join(svg_lines) + "\n"
