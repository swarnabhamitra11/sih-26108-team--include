import re
from typing import NamedTuple, Optional, List

class Designation(NamedTuple):
    """Parsed representation of a standard designation.

    Attributes
    ----------
    base_is_number: str
        The base IS number (e.g. "IS 432" or "IS/ISO 10434").
    part: Optional[str]
        Canonical part label (digits only) or ``None`` if no part or an annex.
    year: Optional[int]
        Edition year, if present.
    """
    base_is_number: str
    part: Optional[str]
    year: Optional[int]

# Regular expression to capture the components of a designation.
# It is deliberately permissive to handle the many formats listed.
_PATTERN = re.compile(
    r"(?i)"                                 # case‑insensitive
    r"(?P<base>IS(?:/ISO)?\s*\d+)"        # base (IS or IS/ISO + number)
    r"(?:\s*\((?P<paren>[^)]+)\))?"      # optional parentheses (part / annex)
    r"(?:\s*-\s*(?P<hyphen>\d{1,4}))?"   # optional hyphen section (part or year)
    r"(?:\s*:\s*(?P<colon_year>\d{4}))?"  # optional colon year
    r"(?:\s*\(Reaffirmed\s*\d{4}\))?"   # ignore reaffirmed clause
    , re.IGNORECASE)

def _canonical_part(paren: Optional[str], hyphen: Optional[str]) -> Optional[str]:
    """Derive the canonical part label.

    * If the parenthetical text contains the word ``Annex`` → ``None``.
    * If it contains ``Part <digits>`` → return only the digits.
    * If it contains a hyphen pattern inside parentheses (e.g., ``P-4``) → return the digits.
    * If the hyphen part (outside parentheses) is 1‑2 digits → treat as part.
    * Otherwise ``None``.
    """
    if paren:
        if re.search(r"annex", paren, re.IGNORECASE):
            return None
        # Look for "Part <digits>" inside parentheses
        m = re.search(r"part\s*(\d{1,2})", paren, re.IGNORECASE)
        if m:
            return m.group(1)
        # Look for hyphen pattern inside parentheses, e.g., "-4" or "P-4"
        m = re.search(r"-(\d{1,2})", paren)
        if m:
            return m.group(1)
    if hyphen and len(hyphen) <= 2:
        # strip leading zeros but keep "0" if that ever occurs
        return hyphen.lstrip('0') or hyphen
    return None

def parse_designation(desig: str) -> Designation:
    """Parse a designation string.

    Returns ``Designation('', None, None)`` for any non‑IS input instead of raising.
    """
    if not desig or not isinstance(desig, str):
        return Designation('', None, None)

    # Extract raw base (including possible IS/ISO prefix)
    m = _PATTERN.search(desig.strip())
    if not m:
        return Designation('', None, None)
    raw_base = m.group('base')
    # Normalize whitespace in the raw base
    raw_base_norm = re.sub(r'\s+', ' ', raw_base).strip()
    # Preserve IS/ISO prefix if present; otherwise format as 'IS <number>'
    if '/' in raw_base_norm.upper():
        base = raw_base_norm.upper()
    else:
        num_match = re.search(r'\d+', raw_base_norm)
        if num_match:
            base = f"IS {num_match.group(0)}"
        else:
            base = raw_base_norm

    # Determine part label (canonical part or "Part N" after a colon)
    part = _canonical_part(m.group('paren'), m.group('hyphen'))
    if part is None:
        colon_part_match = re.search(r'Part\s*(\d{1,2})', desig, re.IGNORECASE)
        if colon_part_match:
            part = colon_part_match.group(1)

    # Determine year
    year: Optional[int] = None
    if m.group('colon_year'):
        year = int(m.group('colon_year'))
    elif m.group('hyphen') and len(m.group('hyphen')) == 4:
        year = int(m.group('hyphen'))
    else:
        cleaned = re.sub(r'\(Reaffirmed\s*\d{4}\)', '', desig, flags=re.IGNORECASE)
        year_match = re.search(r'\b(19|20)\d{2}\b', cleaned)
        if year_match:
            year = int(year_match.group(0))

    return Designation(base_is_number=base, part=part, year=year)

def find_designations(text: str) -> List[Designation]:
    """Find all designations in *text* in order, deduplicated.
    """
    if not text:
        return []
    seen = set()
    results: List[Designation] = []
    for m in _PATTERN.finditer(text):
        base = re.sub(r"\s+", " ", m.group('base').strip())
        year: Optional[int] = None
        if m.group('colon_year'):
            year = int(m.group('colon_year'))
        elif m.group('hyphen') and len(m.group('hyphen')) == 4:
            year = int(m.group('hyphen'))
        part = _canonical_part(m.group('paren'), m.group('hyphen'))
        desig = Designation(base_is_number=base, part=part, year=year)
        key = (desig.base_is_number, desig.part, desig.year)
        if key not in seen:
            seen.add(key)
            results.append(desig)
    return results
