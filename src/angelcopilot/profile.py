"""Load and normalize investor profile fields from local markdown files."""

from __future__ import annotations

from pathlib import Path
import json
import re

from angelcopilot.models import InvestorProfile
from angelcopilot.economics import number
from angelcopilot.contract import CATEGORIES

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
    weights: dict[str, float] = {}
    in_weights = False
    for line in lines:
        stripped = line.strip().removeprefix("- ")
        if not stripped or ":" not in stripped:
            continue
        key, value = stripped.split(":", 1)
        if in_weights and key.strip() in CATEGORIES:
            weights[key.strip()] = number(value.strip(), key.strip())
            continue
        in_weights = False
        normalized_key = key.strip().lower().replace(" ", "_")
        canonical_key = KEY_ALIASES.get(normalized_key, normalized_key)
        values[canonical_key] = value.strip()
        if canonical_key in {"evaluation_weight_overrides", "weight_overrides"}:
            in_weights = True
            if value.strip().startswith("{"):
                parsed = json.loads(value.strip())
                if not isinstance(parsed, dict) or set(parsed) - set(CATEGORIES):
                    raise ValueError("Weight overrides must use the seven rubric category names")
                weights.update({k: number(v, k) for k, v in parsed.items()})

    typical = _resolve_ticket_typical(values)
    triplet = values.get("ticket_typical_triplet", "").split("/")
    minimum = _parse_amount(values["ticket_min"], "ticket_min", allow_zero=False) if values.get("ticket_min") else (_parse_amount(triplet[0], "ticket_min", False) if len(triplet) >= 3 else 0)
    maximum = _parse_amount(values["ticket_max"], "ticket_max", False) if values.get("ticket_max") else (_parse_amount(triplet[2], "ticket_max", False) if len(triplet) >= 3 else 0)
    minimum = minimum or None
    maximum = maximum or None
    if (minimum is not None and maximum is not None and maximum < minimum) or (
        typical and ((minimum is not None and typical < minimum) or (maximum is not None and typical > maximum))
    ):
        raise ValueError("Ticket range must contain ticket_typical")
    hurdle_text = values.get("base_case_return_hurdle", values.get("return_hurdle", ""))
    hurdle = None
    if hurdle_text:
        hurdle = number(hurdle_text.removesuffix("%"), "return hurdle", maximum=100 if hurdle_text.endswith("%") else 1)
        if hurdle_text.endswith("%"):
            hurdle /= 100

    return InvestorProfile(
        region=values.get("region", ""),
        currency=values.get("currency", ""),
        inferred_risk_level=values.get("inferred_risk_level", ""),
        ticket_typical=typical,
        ticket_min=minimum,
        ticket_max=maximum,
        evaluation_weight_overrides=weights,
        return_hurdle=hurdle,
        remaining_angel_budget=_parse_amount(values["remaining_angel_budget"], "remaining_angel_budget", True) if values.get("remaining_angel_budget") else None,
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

    return int(_parse_amount(value, "amount", True)) if value.strip() else 0


def _parse_amount(value: str, name: str, allow_zero: bool) -> float:
    """Parse signed currency amounts and reject negative profile values."""
    match = re.search(r"[-+]?\s*(?:[A-Z]{3}\s*)?[$€£]?\s*([0-9][0-9,]*(?:\.[0-9]+)?)\s*([kKmM]?)", value)
    if not match:
        raise ValueError(f"{name} must be a numeric amount")
    sign_text = value[:match.start(1)].strip()
    sign = -1 if "-" in sign_text else 1
    multiplier = {"k": 1_000, "m": 1_000_000}.get(match.group(2).lower(), 1)
    amount = sign * float(match.group(1).replace(",", "")) * multiplier
    if amount < 0 or (amount == 0 and not allow_zero):
        raise ValueError(f"{name} must be {'nonnegative' if allow_zero else 'positive'}")
    return amount


def _resolve_ticket_typical(values: dict[str, str]) -> float:
    """Resolve `ticket_typical` from direct or min/typical/max profile fields.
    
    Args:
        values: Value for ``values``.
    
    Returns:
        int: Value returned by this function.
    """

    if values.get("ticket_typical"):
        return _parse_amount(values["ticket_typical"], "ticket_typical", False)

    triplet_raw = values.get("ticket_typical_triplet", "")
    if not triplet_raw:
        return 0

    segments = [segment.strip() for segment in triplet_raw.split("/") if segment.strip()]
    if len(segments) >= 2:
        return _parse_amount(segments[1], "ticket_typical", False)
    return _to_int(triplet_raw)
