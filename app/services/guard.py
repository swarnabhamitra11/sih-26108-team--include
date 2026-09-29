"""Hallucination guard service for Standards Navigator.

Exposes guard_text(text, known_keys) -> (clean_text, removed_list).
Scans text with find_designations(). If any designation is not in known_keys,
it is removed from the text and recorded in removed_list.
"""

import re
import logging
from typing import Set, Tuple, Optional, List
from app.services.designation import find_designations, Designation

logger = logging.getLogger("standards_navigator.guard")


def _normalize_part(part: Optional[str]) -> Optional[str]:
    if part is None or part == "":
        return None
    return str(part).strip()


def guard_text(text: str, known_keys: Set[Tuple[str, Optional[str]]]) -> Tuple[str, List[str]]:
    """Clean text by removing unknown standard designations.

    Args:
        text: Free-text input string.
        known_keys: Set of (base_is_number, canonical_part) tuples present in DB.

    Returns:
        (clean_text, removed_list)
    """
    if not text:
        return text, []

    # Normalize known keys for safe lookup
    normalized_known = {
        (k[0].strip().upper(), _normalize_part(k[1]))
        for k in known_keys
    }

    found = find_designations(text)
    removed: List[str] = []
    clean_text = text

    for desig in found:
        key = (desig.base_is_number.strip().upper(), _normalize_part(desig.part))
        if key not in normalized_known:
            # Construct a flexible regex to remove this designation and its year/part from text
            # E.g. "IS 0000:2001" or "IS 0000 (Part 1)"
            base_esc = re.escape(desig.base_is_number)
            pattern = (
                rf"\b{base_esc}"
                rf"(?:\s*\([^)]+\))?"
                rf"(?:\s*-\s*\d+)?"
                rf"(?:\s*:\s*\d{{4}})?"
                rf"(?:\s*Part\s*\d+)?"
                rf"(?:\s*\(Reaffirmed\s*\d{{4}}\))?"
            )
            # Find matching strings to add to removed list
            matches = re.findall(pattern, clean_text, flags=re.IGNORECASE)
            for m in matches:
                removed.append(m.strip())

            clean_text = re.sub(pattern, "", clean_text, flags=re.IGNORECASE)
            logger.warning("Guard removed unknown standard %s (key=%s)", desig, key)

    # Clean up double spaces or dangling punctuation left over
    clean_text = re.sub(r"\s+", " ", clean_text)
    clean_text = re.sub(r"\s+([.,;:!?])", r"\1", clean_text).strip()

    return clean_text, removed
