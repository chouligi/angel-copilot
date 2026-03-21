from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from angelcopilot_batch.models import DealInput

SUPPORTED_DOC_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".zip"}


def discover_recent_deals(
    deals_root: Path,
    since_days: int = 7,
    now: datetime | None = None,
) -> list[DealInput]:
    if not deals_root.exists() or not deals_root.is_dir():
        return []

    now_utc = now or datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=since_days)
    discovered: list[DealInput] = []

    for candidate in sorted(deals_root.iterdir()):
        if not candidate.is_dir():
            continue

        supported_files = _collect_supported_files(candidate)
        if not supported_files:
            continue

        latest_modified_at = _latest_modified_timestamp(candidate, supported_files)
        if latest_modified_at < cutoff:
            continue

        discovered.append(
            DealInput(
                deal_id=candidate.name,
                path=candidate,
                supported_files=supported_files,
                latest_modified_at=latest_modified_at,
            )
        )

    return sorted(discovered, key=lambda item: item.latest_modified_at, reverse=True)


def _collect_supported_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in folder.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
            files.append(file_path)
    return sorted(files)


def _latest_modified_timestamp(folder: Path, files: list[Path]) -> datetime:
    timestamps = [folder.stat().st_mtime, *[file_path.stat().st_mtime for file_path in files]]
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc)
