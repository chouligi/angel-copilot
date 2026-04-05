"""Prepare per-deal workspaces with flattened, supported input documents."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path, PurePosixPath
import shutil
import tempfile
import zipfile

from angelcopilot_batch.intake import SUPPORTED_DOC_EXTENSIONS

DIRECT_DOC_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_ZIP_RECURSION_DEPTH = 6


@dataclass
class PreparedDealWorkspace:
    """Temporary prepared docs plus provenance and extraction warnings."""

    workspace_path: Path
    files_used: list[str]
    warnings: list[str]


def prepare_deal_workspace(
    deal_path: Path,
    supported_files: list[Path],
    deal_id: str,
) -> PreparedDealWorkspace:
    """Copy/extract supported deal files into an isolated temp workspace.

    Args:
        deal_path: Original deal folder/file path.
        supported_files: Supported documents discovered during intake.
        deal_id: Deal identifier used for temp workspace naming.

    Returns:
        Prepared workspace metadata with provenance and warnings.
    """

    workspace = Path(tempfile.mkdtemp(prefix=f"angelcopilot_{_slugify(deal_id)}_"))
    files_used: list[str] = []
    warnings: list[str] = []
    used_targets: set[Path] = set()

    docs_dir = workspace / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)

    for source_file in sorted(supported_files):
        extension = source_file.suffix.lower()
        if extension not in SUPPORTED_DOC_EXTENSIONS:
            continue

        if extension in DIRECT_DOC_EXTENSIONS:
            target_name = _unique_target_name(docs_dir, source_file.name, used_targets)
            target_path = docs_dir / target_name
            shutil.copy2(source_file, target_path)
            files_used.append(str(source_file))
            continue

        if extension == ".zip":
            extracted_count = _extract_zip_recursive_from_path(
                zip_path=source_file,
                output_root=docs_dir,
                used_targets=used_targets,
                files_used=files_used,
                warnings=warnings,
            )
            if extracted_count == 0:
                warnings.append(f"No supported docs found in archive: {source_file}")

    return PreparedDealWorkspace(workspace_path=workspace, files_used=files_used, warnings=warnings)


def cleanup_prepared_workspace(workspace: PreparedDealWorkspace) -> None:
    """Delete a previously prepared temporary workspace.
    
    Args:
        workspace: Value for ``workspace``.
    
    Returns:
        None.
    """

    shutil.rmtree(workspace.workspace_path, ignore_errors=True)


def _extract_zip_recursive_from_path(
    zip_path: Path,
    output_root: Path,
    used_targets: set[Path],
    files_used: list[str],
    warnings: list[str],
) -> int:
    """Extract supported documents from a zip path (including nested zips).
    
    Args:
        zip_path: Value for ``zip_path``.
        output_root: Value for ``output_root``.
        used_targets: Value for ``used_targets``.
        files_used: Value for ``files_used``.
        warnings: Value for ``warnings``.
    
    Returns:
        int: Value returned by this function.
    """

    try:
        with zipfile.ZipFile(zip_path) as archive:
            return _extract_zip_archive_members(
                archive=archive,
                output_root=output_root,
                label_prefix=str(zip_path),
                recursion_depth=1,
                used_targets=used_targets,
                files_used=files_used,
                warnings=warnings,
            )
    except zipfile.BadZipFile as exc:
        warnings.append(f"Invalid zip archive {zip_path}: {exc}")
        return 0


def _extract_zip_archive_members(
    archive: zipfile.ZipFile,
    output_root: Path,
    label_prefix: str,
    recursion_depth: int,
    used_targets: set[Path],
    files_used: list[str],
    warnings: list[str],
) -> int:
    """Extract supported archive members into the workspace docs directory.
    
    Args:
        archive: Value for ``archive``.
        output_root: Value for ``output_root``.
        label_prefix: Value for ``label_prefix``.
        recursion_depth: Value for ``recursion_depth``.
        used_targets: Value for ``used_targets``.
        files_used: Value for ``files_used``.
        warnings: Value for ``warnings``.
    
    Returns:
        int: Value returned by this function.
    """

    if recursion_depth > MAX_ZIP_RECURSION_DEPTH:
        warnings.append(f"Archive recursion depth exceeded for: {label_prefix}")
        return 0

    extracted = 0
    for member in sorted(archive.infolist(), key=lambda item: item.filename):
        if member.is_dir():
            continue

        member_suffix = Path(member.filename).suffix.lower()
        if member_suffix not in SUPPORTED_DOC_EXTENSIONS:
            continue

        try:
            payload = archive.read(member.filename)
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Failed reading archive member {label_prefix}!{member.filename}: {exc}")
            continue

        if member_suffix in DIRECT_DOC_EXTENSIONS:
            target_relative = _safe_member_relative_path(member.filename)
            target_name = _unique_target_name(output_root, target_relative.name, used_targets)
            target_path = output_root / target_name
            target_path.write_bytes(payload)
            files_used.append(f"{label_prefix}!{member.filename}")
            extracted += 1
            continue

        if member_suffix == ".zip":
            nested_label = f"{label_prefix}!{member.filename}"
            extracted += _extract_nested_zip_bytes(
                payload=payload,
                output_root=output_root,
                label_prefix=nested_label,
                recursion_depth=recursion_depth + 1,
                used_targets=used_targets,
                files_used=files_used,
                warnings=warnings,
            )

    return extracted


def _extract_nested_zip_bytes(
    payload: bytes,
    output_root: Path,
    label_prefix: str,
    recursion_depth: int,
    used_targets: set[Path],
    files_used: list[str],
    warnings: list[str],
) -> int:
    """Extract nested zip payload bytes using the same archive rules.
    
    Args:
        payload: Value for ``payload``.
        output_root: Value for ``output_root``.
        label_prefix: Value for ``label_prefix``.
        recursion_depth: Value for ``recursion_depth``.
        used_targets: Value for ``used_targets``.
        files_used: Value for ``files_used``.
        warnings: Value for ``warnings``.
    
    Returns:
        int: Value returned by this function.
    """

    try:
        from io import BytesIO

        with zipfile.ZipFile(BytesIO(payload)) as nested_archive:
            return _extract_zip_archive_members(
                archive=nested_archive,
                output_root=output_root,
                label_prefix=label_prefix,
                recursion_depth=recursion_depth,
                used_targets=used_targets,
                files_used=files_used,
                warnings=warnings,
            )
    except zipfile.BadZipFile as exc:
        warnings.append(f"Invalid nested zip archive {label_prefix}: {exc}")
        return 0


def _safe_member_relative_path(member_name: str) -> Path:
    """Normalize archive member names to safe relative paths.
    
    Args:
        member_name: Value for ``member_name``.
    
    Returns:
        Path: Value returned by this function.
    """

    parts = [
        part
        for part in PurePosixPath(member_name).parts
        if part not in {"", ".", ".."} and not part.endswith(":")
    ]
    if not parts:
        return Path("archive_member")
    return Path(*parts)


def _slugify(raw: str) -> str:
    """Create a filesystem-safe slug for temporary directory naming.
    
    Args:
        raw: Value for ``raw``.
    
    Returns:
        str: Value returned by this function.
    """

    sanitized = "".join(char.lower() if char.isalnum() else "_" for char in raw).strip("_")
    return sanitized or "deal"


def _unique_target_name(output_root: Path, desired_name: str, used_targets: set[Path]) -> str:
    """Generate a collision-safe filename within the target workspace.
    
    Args:
        output_root: Value for ``output_root``.
        desired_name: Value for ``desired_name``.
        used_targets: Value for ``used_targets``.
    
    Returns:
        str: Value returned by this function.
    """

    candidate = output_root / desired_name
    if candidate not in used_targets and not candidate.exists():
        used_targets.add(candidate)
        return desired_name

    stem = Path(desired_name).stem
    suffix = Path(desired_name).suffix
    index = 2
    while True:
        candidate_name = f"{stem}_{index}{suffix}"
        candidate_path = output_root / candidate_name
        if candidate_path not in used_targets and not candidate_path.exists():
            used_targets.add(candidate_path)
            return candidate_name
        index += 1
