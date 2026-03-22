from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import zipfile

from angelcopilot_batch.intake import discover_recent_deals


class MappingClassifier:
    def __init__(self, mapping: dict[str, bool]) -> None:
        self.mapping = mapping
        self.calls: list[tuple[str, str | None]] = []

    def is_deal_folder(self, folder_name: str, parent_name: str | None = None) -> bool:
        self.calls.append((folder_name, parent_name))
        return self.mapping.get(folder_name, True)


class FailingClassifier:
    def is_deal_folder(self, folder_name: str, parent_name: str | None = None) -> bool:
        del folder_name
        del parent_name
        raise RuntimeError("classifier unavailable")


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


def test_discover_recent_deals__recurses_into_syndicate_containers(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    syndicate = deals_root / "syndicate_container"
    deal_a = syndicate / "Deal A_03_21_2026"
    deal_b = syndicate / "Deal B_03_22_2026"
    deal_a.mkdir(parents=True)
    deal_b.mkdir(parents=True)
    (deal_a / "memo.txt").write_text("deal a", encoding="utf-8")
    (deal_b / "memo.txt").write_text("deal b", encoding="utf-8")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7, top_level_containers=True)

    deal_ids = {deal.deal_id for deal in deals}
    assert "syndicate_container" not in deal_ids
    assert deal_ids == {"Deal A_03_21_2026", "Deal B_03_22_2026"}


def test_discover_recent_deals__keeps_deal_parent_when_docs_are_in_nested_folder(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    syndicate = deals_root / "syndicate_container"
    deal_parent = syndicate / "Deal C_03_22_2026"
    docs_dir = deal_parent / "Data Room"
    docs_dir.mkdir(parents=True)
    (docs_dir / "memo.txt").write_text("deal c", encoding="utf-8")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7, top_level_containers=True)

    assert len(deals) == 1
    assert deals[0].deal_id == "Deal C_03_22_2026"
    assert deals[0].path == deal_parent


def test_discover_recent_deals__ignores_container_even_with_direct_docs(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    syndicate = deals_root / "syndicate_container"
    deal_a = syndicate / "Deal A_03_21_2026"
    deal_b = syndicate / "Deal B_03_22_2026"
    deal_a.mkdir(parents=True)
    deal_b.mkdir(parents=True)
    (syndicate / "cover_note.txt").write_text("container level note", encoding="utf-8")
    (deal_a / "memo.txt").write_text("deal a", encoding="utf-8")
    (deal_b / "memo.txt").write_text("deal b", encoding="utf-8")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7, top_level_containers=True)
    deal_ids = {deal.deal_id for deal in deals}

    assert "syndicate_container" not in deal_ids
    assert deal_ids == {"Deal A_03_21_2026", "Deal B_03_22_2026"}


def test_discover_recent_deals__includes_standalone_file_deals_in_container(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    syndicate = deals_root / "syndicate_container"
    deal_dir = syndicate / "Deal A_03_21_2026"
    deal_dir.mkdir(parents=True)
    (deal_dir / "memo.txt").write_text("deal a", encoding="utf-8")
    standalone = syndicate / "Deal B_03_22_2026.pdf"
    standalone.write_bytes(b"%PDF-1.4\n%test\n")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7, top_level_containers=True)
    deal_ids = {deal.deal_id for deal in deals}

    assert deal_ids == {"Deal A_03_21_2026", "Deal B_03_22_2026"}


def test_discover_recent_deals__does_not_emit_top_level_container_as_deal(tmp_path: Path) -> None:
    deals_root = tmp_path / "deals"
    syndicate = deals_root / "syndicate_container"
    syndicate.mkdir(parents=True)
    (syndicate / "Deal D_03_22_2026.pdf").write_bytes(b"%PDF-1.4\n%test\n")
    (syndicate / "Deal D_03_22_2026.txt").write_text("duplicate text export", encoding="utf-8")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7, top_level_containers=True)
    deal_ids = {deal.deal_id for deal in deals}

    assert "syndicate_container" not in deal_ids
    assert "Deal D_03_22_2026" in deal_ids


def test_discover_recent_deals__ignores_closing_documents_folder_candidate(tmp_path: Path) -> None:
    deals_root = tmp_path / "single_syndicate"
    closing_documents = deals_root / "Closing documents"
    deal_folder = deals_root / "Beyond Reach Labs"
    closing_documents.mkdir(parents=True)
    deal_folder.mkdir(parents=True)
    (closing_documents / "signed_terms.pdf").write_bytes(b"%PDF-1.4\n%test\n")
    (deal_folder / "memo.txt").write_text("actual deal docs", encoding="utf-8")

    deals = discover_recent_deals(deals_root=deals_root, since_days=7, top_level_containers=False)
    deal_ids = {deal.deal_id for deal in deals}

    assert "Closing documents" not in deal_ids
    assert deal_ids == {"Beyond Reach Labs"}


def test_discover_recent_deals__smart_filter_uses_classifier_for_folder_candidates(tmp_path: Path) -> None:
    deals_root = tmp_path / "single_syndicate"
    closing_documents = deals_root / "Closing documents"
    deal_folder = deals_root / "Beyond Reach Labs"
    closing_documents.mkdir(parents=True)
    deal_folder.mkdir(parents=True)
    (closing_documents / "signed_terms.pdf").write_bytes(b"%PDF-1.4\n%test\n")
    (deal_folder / "memo.txt").write_text("actual deal docs", encoding="utf-8")
    classifier = MappingClassifier({"Closing documents": False, "Beyond Reach Labs": True})

    deals = discover_recent_deals(
        deals_root=deals_root,
        since_days=7,
        top_level_containers=False,
        intake_filter="smart",
        folder_classifier=classifier,
    )

    assert {deal.deal_id for deal in deals} == {"Beyond Reach Labs"}
    assert ("Closing documents", "single_syndicate") in classifier.calls
    assert ("Beyond Reach Labs", "single_syndicate") in classifier.calls


def test_discover_recent_deals__smart_filter_falls_back_to_heuristic_when_classifier_fails(tmp_path: Path) -> None:
    deals_root = tmp_path / "single_syndicate"
    closing_documents = deals_root / "Closing documents"
    deal_folder = deals_root / "Beyond Reach Labs"
    closing_documents.mkdir(parents=True)
    deal_folder.mkdir(parents=True)
    (closing_documents / "signed_terms.pdf").write_bytes(b"%PDF-1.4\n%test\n")
    (deal_folder / "memo.txt").write_text("actual deal docs", encoding="utf-8")

    deals = discover_recent_deals(
        deals_root=deals_root,
        since_days=7,
        top_level_containers=False,
        intake_filter="smart",
        folder_classifier=FailingClassifier(),
    )

    assert {deal.deal_id for deal in deals} == {"Beyond Reach Labs"}
