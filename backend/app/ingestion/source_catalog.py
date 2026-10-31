from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from hashlib import sha256
from pathlib import Path, PurePosixPath

from .models import SourceFormat, SourceRole, stable_id

# Only immutable Office originals belong to the shared source catalog. Generated
# Markdown/text must never be rediscovered as another authoritative source.
SUPPORTED_SOURCE_SUFFIXES = {".doc", ".docx", ".xlsx"}
_DOCUMENT_CODE = re.compile(r"^(\d+_\d{4}_[A-Z0-9]+(?:-[A-Z0-9]+)?)")


class CorpusCatalogError(ValueError):
    """Raised when the source hierarchy cannot identify one authoritative primary file."""


@dataclass(frozen=True, slots=True)
class CorpusEntry:
    path: Path
    relative_path: str
    source_id: str
    source_hash: str
    package_id: str
    parent_document_id: str
    role: SourceRole
    source_format: SourceFormat
    association: str
    metadata: dict[str, object] = field(default_factory=dict)


def build_source_catalog(source_root: Path) -> list[CorpusEntry]:
    """Discover standalone legal texts and folder-scoped attachment packages."""

    source_root = source_root.resolve()
    files = sorted(
        path
        for path in source_root.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
        and not path.name.startswith("~$")
        and ".cache" not in path.relative_to(source_root).parts
    )
    if not files:
        return []

    records = [_record(source_root, path) for path in files]
    grouped: dict[str, list[_CatalogRecord]] = {}
    for record in records:
        grouped.setdefault(record.package_id, []).append(record)

    entries: list[CorpusEntry] = []
    for package_id, package_records in sorted(grouped.items()):
        primary_records = [record for record in package_records if record.is_primary]
        if len(primary_records) != 1:
            paths = ", ".join(record.relative_path for record in package_records)
            raise CorpusCatalogError(
                f"Package {package_id!r} has {len(primary_records)} primary candidates: {paths}"
            )
        primary = primary_records[0]
        parent_document_id = primary.source_id
        for record in package_records:
            role = SourceRole.PRIMARY_LEGAL_DOCUMENT if record.is_primary else _attachment_role(record)
            entries.append(
                CorpusEntry(
                    path=record.path,
                    relative_path=record.relative_path,
                    source_id=record.source_id,
                    source_hash=record.source_hash,
                    package_id=package_id,
                    parent_document_id=parent_document_id,
                    role=role,
                    source_format=record.source_format,
                    association="document_code" if record.is_primary else "folder_structure",
                    metadata={"filename_code": record.filename_code},
                )
            )
    return sorted(entries, key=lambda entry: entry.relative_path.casefold())


@dataclass(frozen=True, slots=True)
class _CatalogRecord:
    path: Path
    relative_path: str
    source_id: str
    source_hash: str
    package_id: str
    filename_code: str | None
    is_primary: bool
    source_format: SourceFormat


def _record(source_root: Path, path: Path) -> _CatalogRecord:
    relative = PurePosixPath(path.relative_to(source_root).as_posix())
    parts = relative.parts
    filename_code = document_code(path.stem)

    # Support both <root>/Bidding_Law/<package>/... and <root>/<package>/...
    if len(parts) >= 2 and document_code(parts[0]) is not None:
        package_name = parts[0]
        package_code = document_code(package_name)
        assert package_code is not None
        package_id = package_code
        is_primary = filename_code == package_code
    elif len(parts) >= 3:
        package_name = parts[1]
        package_code = document_code(package_name)
        if package_code is None:
            raise CorpusCatalogError(f"Package folder has no document code: {package_name}")
        package_id = package_code
        is_primary = filename_code == package_code
    else:
        if filename_code is None:
            raise CorpusCatalogError(f"Standalone source has no document code: {relative}")
        package_id = filename_code
        is_primary = True

    source_bytes = path.read_bytes()
    source_hash = sha256(source_bytes).hexdigest()
    source_id = stable_id("source", relative.as_posix(), source_hash)
    return _CatalogRecord(
        path=path,
        relative_path=relative.as_posix(),
        source_id=source_id,
        source_hash=source_hash,
        package_id=package_id,
        filename_code=filename_code,
        is_primary=is_primary,
        source_format=SourceFormat(path.suffix.casefold().lstrip(".")),
    )


def document_code(value: str) -> str | None:
    match = _DOCUMENT_CODE.match(_ascii_key(value))
    return match.group(1) if match else None


def _ascii_key(value: str) -> str:
    value = value.replace("Đ", "D").replace("đ", "d")
    return unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode().upper()


def _attachment_role(record: _CatalogRecord) -> SourceRole:
    if record.source_format is SourceFormat.XLSX:
        return SourceRole.FORM_WORKBOOK
    name = _ascii_key(record.path.stem)
    if "PHU LUC" in name:
        return SourceRole.APPENDIX
    if "MAU" in name:
        return SourceRole.FORM_DOCUMENT
    return SourceRole.SUPPLEMENTAL
