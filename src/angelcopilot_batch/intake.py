from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from angelcopilot_batch.models import DealInput

SUPPORTED_DOC_EXTENSIONS = {".txt", ".md", ".pdf", ".docx", ".zip"}
STANDALONE_DEAL_FILE_EXTENSIONS = {".pdf", ".docx", ".zip"}


def discover_recent_deals(
    deals_root: Path,
    since_days: int = 7,
    now: datetime | None = None,
    top_level_containers: bool = False,
) -> list[DealInput]:
    if not deals_root.exists() or not deals_root.is_dir():
        return []

    now_utc = now or datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(days=since_days)
    discovered: list[DealInput] = []

    candidates = _discover_deal_candidates(deals_root, top_level_containers=top_level_containers)
    for candidate in candidates:
        supported_files = _collect_supported_files_for_candidate(candidate)
        if not supported_files:
            continue

        latest_modified_at = _latest_modified_timestamp(candidate, supported_files)
        if latest_modified_at < cutoff:
            continue

        deal_id = candidate.stem if candidate.is_file() else candidate.name
        discovered.append(
            DealInput(
                deal_id=deal_id,
                path=candidate,
                supported_files=supported_files,
                latest_modified_at=latest_modified_at,
            )
        )

    return sorted(discovered, key=lambda item: item.latest_modified_at, reverse=True)


def _discover_deal_candidates(root: Path, top_level_containers: bool) -> list[Path]:
    candidates: list[Path] = []
    for child in sorted(root.iterdir()):
        if child.is_dir():
            candidates.extend(
                _discover_deal_candidates_in(child, depth=1, top_level_containers=top_level_containers)
            )
    return candidates


def _discover_deal_candidates_in(folder: Path, depth: int, top_level_containers: bool) -> list[Path]:
    direct_supported_files = _collect_supported_files_direct(folder)
    direct_standalone_files = _collect_standalone_deal_files_direct(folder)
    child_dirs = [child for child in sorted(folder.iterdir()) if child.is_dir()]
    active_children = [child for child in child_dirs if _has_supported_files_recursive(child)]

    if len(active_children) >= 2:
        candidates: list[Path] = []
        for child_dir in active_children:
            candidates.extend(
                _discover_deal_candidates_in(
                    child_dir,
                    depth=depth + 1,
                    top_level_containers=top_level_containers,
                )
            )
        candidates.extend(direct_standalone_files)
        return candidates

    if top_level_containers and depth == 1 and direct_supported_files and not active_children:
        return direct_standalone_files

    if direct_supported_files and not active_children:
        return [folder]

    if not active_children:
        return []

    if depth > 1 and len(active_children) == 1:
        return [folder]

    candidates: list[Path] = []
    for child_dir in active_children:
        candidates.extend(
            _discover_deal_candidates_in(
                child_dir,
                depth=depth + 1,
                top_level_containers=top_level_containers,
            )
        )
    if top_level_containers and depth == 1:
        candidates.extend(direct_standalone_files)
    return candidates


def _collect_supported_files(folder: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in folder.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
            files.append(file_path)
    return sorted(files)


def _collect_supported_files_for_candidate(candidate: Path) -> list[Path]:
    if candidate.is_file():
        if candidate.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
            return [candidate]
        return []
    return _collect_supported_files(candidate)


def _collect_supported_files_direct(folder: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in sorted(folder.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
            files.append(file_path)
    return files


def _collect_standalone_deal_files_direct(folder: Path) -> list[Path]:
    files: list[Path] = []
    for file_path in sorted(folder.iterdir()):
        if file_path.is_file() and file_path.suffix.lower() in STANDALONE_DEAL_FILE_EXTENSIONS:
            files.append(file_path)
    return files


def _has_supported_files_recursive(folder: Path) -> bool:
    for file_path in folder.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED_DOC_EXTENSIONS:
            return True
    return False


def _latest_modified_timestamp(folder: Path, files: list[Path]) -> datetime:
    timestamps = [folder.stat().st_mtime, *[file_path.stat().st_mtime for file_path in files]]
    return datetime.fromtimestamp(max(timestamps), tz=timezone.utc)
