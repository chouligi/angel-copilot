from __future__ import annotations

from pathlib import Path

from angelcopilot_batch.intake import discover_recent_deals


def test_discover_recent_deals__finds_dummy_fixture_deals(deals_fixtures_root: Path) -> None:
    deals = discover_recent_deals(deals_root=deals_fixtures_root, since_days=7)

    assert len(deals) == 2
    deal_ids = {deal.deal_id for deal in deals}
    assert deal_ids == {"alpha_ai", "beta_ops"}

    zip_deal = [deal for deal in deals if deal.deal_id == "beta_ops"][0]
    assert any(path.suffix.lower() == ".zip" for path in zip_deal.supported_files)
