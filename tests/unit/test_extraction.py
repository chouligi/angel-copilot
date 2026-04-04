from __future__ import annotations

from pathlib import Path
import zipfile

from angelcopilot_batch.extraction import extract_evidence_bundle


def test_extract_evidence_bundle__extracts_txt_and_md(tmp_path: Path) -> None:
    txt_file = tmp_path / "memo.txt"
    md_file = tmp_path / "notes.md"
    txt_file.write_text("Revenue is growing 20% MoM.", encoding="utf-8")
    md_file.write_text("# Team\nStrong founders.", encoding="utf-8")

    bundle = extract_evidence_bundle([txt_file, md_file])

    assert len(bundle.evidence_blocks) == 2
    assert bundle.warnings == []
    assert "Revenue is growing" in bundle.evidence_blocks[0].text
    assert "Strong founders" in bundle.evidence_blocks[1].text


def test_extract_evidence_bundle__warns_on_unsupported_files(tmp_path: Path) -> None:
    unsupported_file = tmp_path / "chart.png"
    unsupported_file.write_bytes(b"binary")

    bundle = extract_evidence_bundle([unsupported_file])

    assert bundle.evidence_blocks == []
    assert len(bundle.warnings) == 1
    assert "Unsupported file type" in bundle.warnings[0]


def test_extract_evidence_bundle__extracts_supported_docs_from_zip(tmp_path: Path) -> None:
    zip_path = tmp_path / "docs.zip"
    with zipfile.ZipFile(zip_path, mode="w") as archive:
        archive.writestr("memo.txt", "Revenue is growing strongly.")
        archive.writestr("deck.md", "# Product\nStrong wedge.")
        archive.writestr("image.png", b"binary")

    bundle = extract_evidence_bundle([zip_path])

    assert len(bundle.evidence_blocks) == 2
    extracted_text = "\n".join(block.text for block in bundle.evidence_blocks)
    assert "Revenue is growing strongly." in extracted_text
    assert "Strong wedge." in extracted_text
