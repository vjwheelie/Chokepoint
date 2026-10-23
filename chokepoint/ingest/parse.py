"""Pure parsing rules for raw USAspending values. No I/O, so every rule is unit-tested."""

from datetime import date
from enum import StrEnum


class Competition(StrEnum):
    COMPETED = "competed"
    NOT_COMPETED = "not_competed"
    AMBIGUOUS = "ambiguous"
    UNKNOWN = "unknown"


# D-006, source: https://fpds.gov/help/Extent_Competed.htm
_COMPETITION_BY_CODE = {
    "A": Competition.COMPETED,  # full and open
    "D": Competition.COMPETED,  # full and open after exclusion of sources (e.g. set-aside)
    "F": Competition.COMPETED,  # competed under simplified acquisition procedures
    "CDO": Competition.COMPETED,  # competitive delivery order
    "B": Competition.NOT_COMPETED,  # not available for competition
    "C": Competition.NOT_COMPETED,  # not competed
    "G": Competition.NOT_COMPETED,  # not competed under simplified acquisition procedures
    "NDO": Competition.NOT_COMPETED,  # non-competitive delivery order
    "E": Competition.AMBIGUOUS,  # follow-on to a competed action
}


def competition_bucket(extent_competed_code: str | None) -> Competition:
    """Map an FPDS extent-competed code to competed / not_competed / ambiguous / unknown."""
    if not extent_competed_code:
        return Competition.UNKNOWN
    return _COMPETITION_BY_CODE.get(extent_competed_code.strip().upper(), Competition.UNKNOWN)


def parse_item_name(description: str | None) -> str | None:
    """Extract the DLA item name from a `PR_NUMBER!ITEM NAME` description (D-004).

    DLA truncates item names at 19 characters, so the truncated string is used as-is:
    it is a stable grouping key, not a display name. Returns None when the description
    is not in this format or the item name is blank, so unclassified rows are never guessed.
    """
    if not description or "!" not in description:
        return None
    prefix, _, item = description.partition("!")
    if not prefix.strip().isdigit():
        return None
    item = " ".join(item.split()).upper()
    return item or None


def fiscal_year_bounds(fy: int) -> tuple[date, date]:
    """Federal FY N runs Oct 1 of N-1 through Sep 30 of N."""
    return date(fy - 1, 10, 1), date(fy, 9, 30)


# DoD contract data is published to FPDS with a 90-day delay
# (https://www.fpds.gov/common/html/dodDataAvailability.html); 120 days adds a margin.
SETTLING_DAYS = 120


def is_fiscal_year_final(fy: int, today: date) -> bool:
    """True once a fiscal year's DoD data should no longer be changing (D-012)."""
    _, end = fiscal_year_bounds(fy)
    return (today - end).days > SETTLING_DAYS
