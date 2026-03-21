from __future__ import annotations

from pathlib import Path

from angelcopilot_batch.profile import load_investor_profile


def test_load_investor_profile__parses_markdown_key_values(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_path.write_text(
        "\n".join(
            [
                "region: Greece",
                "currency: EUR",
                "ticket_typical: 25000",
                "sectors_themes: AI, DevTools, B2B SaaS",
                "geo_focus: Europe, US",
                "inferred_risk_level: High",
            ]
        ),
        encoding="utf-8",
    )

    profile = load_investor_profile(profile_path)

    assert profile.region == "Greece"
    assert profile.currency == "EUR"
    assert profile.ticket_typical == 25000
    assert profile.sectors_themes == ["AI", "DevTools", "B2B SaaS"]
    assert profile.geo_focus == ["Europe", "US"]


def test_load_investor_profile__returns_defaults_when_file_missing(tmp_path: Path) -> None:
    profile = load_investor_profile(tmp_path / "missing_profile.md")

    assert profile.region == ""
    assert profile.currency == ""
    assert profile.sectors_themes == []


def test_load_investor_profile__supports_aliases_and_flexible_delimiters(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_path.write_text(
        "\n".join(
            [
                "themes: AI / DevTools / Fintech",
                "geo_focus: EU & US",
            ]
        ),
        encoding="utf-8",
    )

    profile = load_investor_profile(profile_path)

    assert profile.sectors_themes == ["AI", "DevTools", "Fintech"]
    assert profile.geo_focus == ["EU", "US"]


def test_load_investor_profile__parses_ticket_typical_triplet_format(tmp_path: Path) -> None:
    profile_path = tmp_path / "profile.md"
    profile_path.write_text(
        "ticket_min/typical/max: €2,000 / €5,000 / €20,000",
        encoding="utf-8",
    )

    profile = load_investor_profile(profile_path)

    assert profile.ticket_typical == 5000
