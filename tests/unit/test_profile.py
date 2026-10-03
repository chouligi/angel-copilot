from __future__ import annotations

from pathlib import Path

from angelcopilot.profile import load_investor_profile
import pytest


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


@pytest.mark.parametrize('field', ['Remaining Angel Budget', 'Ticket Min'])
def test_negative_amounts_are_rejected_instead_of_becoming_positive(tmp_path: Path, field: str) -> None:
    path=tmp_path/'profile.md'
    path.write_text(f'{field}: -€6,000\n',encoding='utf-8')
    with pytest.raises(ValueError):load_investor_profile(path)


def test_zero_remaining_budget_is_preserved(tmp_path: Path) -> None:
    path=tmp_path/'profile.md';path.write_text('Remaining Angel Budget: €0\n',encoding='utf-8')
    assert load_investor_profile(path).remaining_angel_budget==0


def test_profile_triplet_sets_minimum_typical_and_maximum(tmp_path: Path) -> None:
    path=tmp_path/'profile.md'
    path.write_text('ticket_min/typical/max: €2,000 / €2,000 / €5,000\n',encoding='utf-8')
    profile=load_investor_profile(path)
    assert profile.ticket_min==2000 and profile.ticket_typical==2000 and profile.ticket_max==5000
