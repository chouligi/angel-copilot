from __future__ import annotations

from io import BytesIO
from pathlib import Path
import zipfile

from angelcopilot_batch.preparation import cleanup_prepared_workspace, prepare_deal_workspace


def test_prepare_deal_workspace__extracts_nested_zip_members(tmp_path: Path) -> None:
    deal_dir = tmp_path / "deal_nested"
    deal_dir.mkdir(parents=True)
    outer_zip = deal_dir / "bundle.zip"

    inner_buffer = BytesIO()
    with zipfile.ZipFile(inner_buffer, mode="w") as inner:
        inner.writestr("memo.txt", "Nested memo content")

    with zipfile.ZipFile(outer_zip, mode="w") as outer:
        outer.writestr("inner.zip", inner_buffer.getvalue())

    prepared = prepare_deal_workspace(
        deal_path=deal_dir,
        supported_files=[outer_zip],
        deal_id="deal_nested",
    )
    try:
        prepared_docs = sorted((prepared.workspace_path / "docs").iterdir())
        assert prepared_docs
        assert any(path.name.endswith(".txt") for path in prepared_docs)
        assert any("inner.zip!memo.txt" in source for source in prepared.files_used)
        assert prepared.warnings == []
    finally:
        cleanup_prepared_workspace(prepared)


def test_prepare_deal_workspace__copies_direct_docs_and_records_sources(tmp_path: Path) -> None:
    deal_dir = tmp_path / "deal_direct"
    deal_dir.mkdir(parents=True)
    pdf_file = deal_dir / "deck.pdf"
    txt_file = deal_dir / "memo.txt"
    pdf_file.write_bytes(b"%PDF-1.4\n%test\n")
    txt_file.write_text("Memo body", encoding="utf-8")

    prepared = prepare_deal_workspace(
        deal_path=deal_dir,
        supported_files=[pdf_file, txt_file],
        deal_id="deal_direct",
    )
    try:
        prepared_docs = sorted((prepared.workspace_path / "docs").iterdir())
        assert len(prepared_docs) == 2
        assert str(pdf_file) in prepared.files_used
        assert str(txt_file) in prepared.files_used
    finally:
        cleanup_prepared_workspace(prepared)
