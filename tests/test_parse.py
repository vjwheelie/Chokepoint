from datetime import date

import pytest

from chokepoint.ingest.parse import (
    Competition,
    competition_bucket,
    fiscal_year_bounds,
    is_fiscal_year_final,
    parse_item_name,
)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        ("8511444589!MICROCIRCUIT,HYBRID", "MICROCIRCUIT,HYBRID"),
        ("8511610766!TERMINAL STRIP,GROU", "TERMINAL STRIP,GROU"),  # 19-char DLA truncation kept
        ("8511610766!  cable  assembly,spec ", "CABLE ASSEMBLY,SPEC"),  # whitespace/case normalized
        ("8511610766!", None),  # blank item name
        ("8511610766!   ", None),
        ("KU BAND AMPLIFIER", None),  # free text, no PR number
        ("SEE SOW! URGENT", None),  # '!' but prefix is not a PR number
        ("", None),
        (None, None),
    ],
)
def test_parse_item_name(description, expected):
    assert parse_item_name(description) == expected


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("A", Competition.COMPETED),
        ("D", Competition.COMPETED),
        ("F", Competition.COMPETED),
        ("CDO", Competition.COMPETED),
        ("B", Competition.NOT_COMPETED),
        ("C", Competition.NOT_COMPETED),
        ("G", Competition.NOT_COMPETED),
        ("NDO", Competition.NOT_COMPETED),
        ("E", Competition.AMBIGUOUS),
        (" g ", Competition.NOT_COMPETED),
        ("Z", Competition.UNKNOWN),
        ("", Competition.UNKNOWN),
        (None, Competition.UNKNOWN),
    ],
)
def test_competition_bucket(code, expected):
    assert competition_bucket(code) == expected


def test_fiscal_year_bounds():
    assert fiscal_year_bounds(2019) == (date(2018, 10, 1), date(2019, 9, 30))


def test_fiscal_year_final_respects_dod_delay():
    # FY2026 ended 2026-09-30; still settling three weeks later, final after 120 days.
    assert not is_fiscal_year_final(2026, date(2026, 10, 22))
    assert not is_fiscal_year_final(2026, date(2027, 1, 28))
    assert is_fiscal_year_final(2026, date(2027, 1, 29))
    assert is_fiscal_year_final(2019, date(2026, 10, 22))
