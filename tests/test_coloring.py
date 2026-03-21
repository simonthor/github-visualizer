from datetime import date

from github_visualizer.main import (
    ContributionCell,
    _contribution_count_to_level,
    build_svg,
)


def test_count_to_level_rules():
    assert _contribution_count_to_level(0, 20) == 0
    assert _contribution_count_to_level(-5, 20) == 0
    assert _contribution_count_to_level(1, 20) == 1
    assert _contribution_count_to_level(20, 20) == 4


def test_count_to_level_mid_buckets():
    # ratio=(2-1)/(10-1)=0.11
    assert _contribution_count_to_level(2, 10) == 2
    # ratio=(5-1)/(10-1)=0.44
    assert _contribution_count_to_level(5, 10) == 3
    # ratio=(8-1)/(10-1)=0.77
    assert _contribution_count_to_level(8, 10) == 4


def test_count_to_level_when_max_is_one():
    assert _contribution_count_to_level(1, 1) == 1
    assert _contribution_count_to_level(2, 1) == 1


def test_build_svg_uses_count_based_colors():
    cells = {
        date(2025, 1, 1): ContributionCell(count=0),
        date(2025, 1, 2): ContributionCell(count=1),
        date(2025, 1, 3): ContributionCell(count=10),
        date(2025, 1, 4): ContributionCell(count=20),
    }

    svg = build_svg("tester", cells, start_year=2025, end_year=2025)

    assert (
        'fill="#ebedf0"' in svg
        and "<title>0 contributions on 2025-01-01</title>" in svg
    )
    assert (
        'fill="#9be9a8"' in svg and "<title>1 contribution on 2025-01-02</title>" in svg
    )
    assert (
        'fill="#30a14e"' in svg
        and "<title>10 contributions on 2025-01-03</title>" in svg
    )
    assert (
        'fill="#216e39"' in svg
        and "<title>20 contributions on 2025-01-04</title>" in svg
    )
