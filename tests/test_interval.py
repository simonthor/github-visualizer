from datetime import date

from github_visualizer.svg import ContributionCell, build_svg


def test_build_svg_interval_year_splits_rows():
    cells = {
        date(2024, 12, 31): ContributionCell(count=3),
        date(2025, 1, 1): ContributionCell(count=4),
    }
    svg = build_svg("tester", cells, start_year=2024, end_year=2025, interval="year")

    assert ">2024</text>" in svg
    assert ">2025</text>" in svg
    assert "<title>3 contributions on 2024-12-31</title>" in svg
    assert "<title>4 contributions on 2025-01-01</title>" in svg


def test_build_svg_interval_month_splits_rows():
    cells = {
        date(2025, 1, 31): ContributionCell(count=2),
        date(2025, 2, 1): ContributionCell(count=5),
    }
    svg = build_svg("tester", cells, start_year=2025, end_year=2025, interval="month")

    assert ">2025-01</text>" in svg
    assert ">2025-02</text>" in svg
    assert "<title>2 contributions on 2025-01-31</title>" in svg
    assert "<title>5 contributions on 2025-02-01</title>" in svg


def test_year_interval_first_week_alignment_uses_sunday_column():
    # 2025-01-01 is Wednesday, so with Sunday-aligned columns it must not be in the first column.
    cells = {date(2025, 1, 1): ContributionCell(count=1)}
    svg = build_svg("tester", cells, start_year=2025, end_year=2025, interval="year")
    assert (
        '<rect x="88" y="78" width="10" height="10" fill="#9be9a8" rx="2" ry="2"><title>1 contribution on 2025-01-01</title></rect>'
        in svg
    )


def test_year_interval_last_week_keeps_all_days():
    # Ensure late-year days render across the final Sunday-aligned week.
    cells = {
        date(2025, 12, 28): ContributionCell(count=2),  # Sunday
        date(2025, 12, 29): ContributionCell(count=3),  # Monday
        date(2025, 12, 30): ContributionCell(count=4),  # Tuesday
        date(2025, 12, 31): ContributionCell(count=5),  # Wednesday
    }
    svg = build_svg("tester", cells, start_year=2025, end_year=2025, interval="year")
    assert "<title>2 contributions on 2025-12-28</title>" in svg
    assert "<title>3 contributions on 2025-12-29</title>" in svg
    assert "<title>4 contributions on 2025-12-30</title>" in svg
    assert "<title>5 contributions on 2025-12-31</title>" in svg
