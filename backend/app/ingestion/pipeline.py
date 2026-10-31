from __future__ import annotations

from pathlib import Path

from .extractors import extract_document
from .models import SourceDocument
from .normalizer import normalize_document
from .source_catalog import CorpusEntry


def prepare_entry_document(
    entry: CorpusEntry,
    *,
    conversion_dir: Path = Path("data/derived/conversions"),
) -> SourceDocument:
    """Extract and normalize one catalog entry without parsing or chunking it."""

    document = extract_document(
        entry.path,
        conversion_dir=conversion_dir,
        source_hash=entry.source_hash,
    )
    document.document_id = entry.source_id
    document.source_file = entry.relative_path
    document.source_relative_path = entry.relative_path
    document.package_id = entry.package_id
    document.parent_document_id = entry.parent_document_id
    document.source_role = entry.role
    document.source_format = entry.source_format
    document.metadata.update(
        {
            "source_hash": entry.source_hash,
            "association": entry.association,
            **entry.metadata,
        }
    )
    return normalize_document(document)
