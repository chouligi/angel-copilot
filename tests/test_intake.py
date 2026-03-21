from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import zipfile

from angelcopilot_batch.intake import discover_recent_deals


def test_discover_recent_deals__returns_only_recent_deals(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_recent = deals_root / "recent_ai_deal"
    deal_old = deals_root / "old_fintech_deal"
    deal_recent.mkdir(parents=True)
    deal_old.mkdir(parents=True)

    recent_file = deal_recent / "memo.txt"
    old_file = deal_old / "memo.txt"
    recent_file.write_text("recent", encoding="utf-8")
    old_file.write_text("old", encoding="utf-8")

    old_timestamp = (datetime.now(timezone.utc) - timedelta(days=10)).timestamp()
    recent_timestamp = (datetime.now(timezone.utc) - timedelta(days=1)).timestamp()
    old_file.touch()
    recent_file.touch()
    deal_old.touch()
    deal_recent.touch()

    import os

    os.utime(old_file, (old_timestamp, old_timestamp))
    os.utime(deal_old, (old_timestamp, old_timestamp))
    os.utime(recent_file, (recent_timestamp, recent_timestamp))
    os.utime(deal_recent, (recent_timestamp, recent_timestamp))

    deals = discover_recent_deals(deals_root=deals_root, since_days=7)

    assert len(deals) == 1
    assert deals[0].deal_id == "recent_ai_deal"
    assert deals[0].path == deal_recent
    assert recent_file in deals[0].supported_files


def test_discover_recent_deals__ignores_deals_without_supported_files(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "deal_without_docs"
    deal_folder.mkdir(parents=True)
    (deal_folder / "image.png").write_bytes(b"binary")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7)

    assert deals == []


def test_discover_recent_deals__includes_zip_only_deal_folder(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    deal_folder = deals_root / "zip_only_deal"
    deal_folder.mkdir(parents=True)

    zip_path = deal_folder / "docs.zip"
    with zipfile.ZipFile(zip_path, mode="w") as archive:
        archive.writestr("memo.txt", "This deal includes traction details.")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7)

    assert len(deals) == 1
    assert deals[0].deal_id == "zip_only_deal"
    assert zip_path in deals[0].supported_files
