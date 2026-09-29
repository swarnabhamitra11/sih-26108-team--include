import re
from typing import NamedTuple, Optional

class Designation(NamedTuple):
    """Parsed representation of a standard designation.

    Attributes
    ----------
    base_is_number: str
        The base IS number without part or year, e.g. "IS 432".
    part: Optional[str]
        The part or annex string inside parentheses, if present.
    year: Optional[int]
        The four‑digit year after a colon, if present.
    """
    base_is_number: str
    part: Optional[str]
    year: Optional[int]


def parse_designation(desig: str) -> Designation:
    """Parse a standard designation string.

    The function extracts three components:
    * **base_is_number** – the ``IS <number>`` prefix (required).
    * **part** – optional text inside parentheses, e.g. ``(Part 1)``.
    * **year** – optional four‑digit year after a colon, e.g. ``:1982``.

    Examples
    --------
    >>> parse_designation("IS 432 (Part 1):1982")
    Designation(base_is_number='IS 432', part='Part 1', year=1982)
    >>> parse_designation("IS 1234:2020")
    Designation(base_is_number='IS 1234', part=None, year=2020)
    >>> parse_designation("IS 5678")
    Designation(base_is_number='IS 5678', part=None, year=None)
    """
    pattern = r"^(?P<base>IS\s*\d+)(?:\s*\((?P<part>[^)]+)\))?(?::(?P<year>\d{4}))?$"
    m = re.match(pattern, desig.strip())
    if not m:
        raise ValueError(f"Unable to parse designation: {desig!r}")
    base = m.group('base').strip()
    part = m.group('part')
    year_str = m.group('year')
    year = int(year_str) if year_str else None
    return Designation(base_is_number=base, part=part, year=year)
