"""Load and normalize investor profile fields from local markdown files."""

from __future__ import annotations

from pathlib import Path
import re

from angelcopilot_batch.models import InvestorProfile

KEY_ALIASES = {
    "themes": "sectors_themes",
    "theme_focus": "sectors_themes",
    "sector_focus": "sectors_themes",
    "sectors": "sectors_themes",
    "geo": "geo_focus",
    "geography": "geo_focus",
    "geographies": "geo_focus",
    "geographic_focus": "geo_focus",
    "ticket_min/typical/max": "ticket_typical_triplet",
    "ticket_min_typical_max": "ticket_typical_triplet",
}


def load_investor_profile(profile_path: Path) -> InvestorProfile:
    """Parse a profile markdown file into an ``InvestorProfile``.

    Args:
        profile_path: Path to profile markdown file.

    Returns:
        Normalized investor profile. Missing files return defaults.
    """

    if not profile_path.exists():
        return InvestorProfile()

    lines = profile_path.read_text(encoding="utf-8").splitlines()
    values: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        normalized_key = key.strip().lower().replace(" ", "_")
        canonical_key = KEY_ALIASES.get(normalized_key, normalized_key)
        values[canonical_key] = value.strip()

    return InvestorProfile(
        region=values.get("region", ""),
        currency=values.get("currency", ""),
        inferred_risk_level=values.get("inferred_risk_level", ""),
        ticket_typical=_resolve_ticket_typical(values),
        sectors_themes=_to_list(values.get("sectors_themes", "")),
        geo_focus=_to_list(values.get("geo_focus", "")),
    )


def _to_list(value: str) -> list[str]:
    """Split a free-form list field into normalized string values.
    
    Args:
        value: Value for ``value``.
    
    Returns:
        list[str]: Value returned by this function.
    """

    if not value:
        return []
    chunks = re.split(r",|/|;|\||\s+&\s+", value)
    return [item.strip() for item in chunks if item.strip()]


def _to_int(value: str) -> int:
    """Extract digits from a string and convert to int (or 0).
    
    Args:
        value: Value for ``value``.
    
    Returns:
        int: Value returned by this function.
    """

    digits = "".join(ch for ch in value if ch.isdigit())
    return int(digits) if digits else 0


def _resolve_ticket_typical(values: dict[str, str]) -> int:
    """Resolve `ticket_typical` from direct or min/typical/max profile fields.
    
    Args:
        values: Value for ``values``.
    
    Returns:
        int: Value returned by this function.
    """

    direct = _to_int(values.get("ticket_typical", "0"))
    if direct > 0:
        return direct

    triplet_raw = values.get("ticket_typical_triplet", "")
    if not triplet_raw:
        return 0

    segments = [segment.strip() for segment in triplet_raw.split("/") if segment.strip()]
    if len(segments) >= 2:
        parsed = _to_int(segments[1])
        if parsed > 0:
            return parsed
    return _to_int(triplet_raw)
