"""Generate local legal/content chunks after the Markdown preparation phase."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from backend.app.core.settings import get_settings
from backend.app.ingestion.chunker import build_chunks
from backend.app.ingestion.content_chunker import build_content_chunks
from backend.app.ingestion.models import SourceFormat, SourceRole
from backend.app.ingestion.parser import parse_hierarchy
from backend.app.ingestion.pipeline import prepare_entry_document
from backend.app.ingestion.source_catalog import build_source_catalog


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path(settings.source_docs_dir))
    parser.add_argument("--output-dir", type=Path, default=Path(settings.chunks_output_dir))
    parser.add_argument(
        "--conversion-dir", type=Path, default=Path(settings.converted_docs_dir)
    )
    parser.add_argument(
        "--preparation-dir", type=Path, default=Path(settings.ingest_artifacts_dir)
    )
    parser.add_argument(
        "--docx-only",
        action="store_true",
        help="Process only DOCX sources (useful for the legacy 31-document mock corpus).",
    )
    args = parser.parse_args()

    entries = build_source_catalog(args.source_dir)
    if args.docx_only:
        entries = [entry for entry in entries if entry.source_format is SourceFormat.DOCX]
    if not entries:
        raise SystemExit(f"No supported source documents found in {args.source_dir}")

    prepared_ids = _prepared_source_ids(args.preparation_dir)
    missing = [entry.relative_path for entry in entries if entry.source_id not in prepared_ids]
    if missing:
        preview = "\n  - ".join(missing[:10])
        raise SystemExit(
            "Chunking requires a matching completed Markdown preparation run. "
            "Run scripts/ingest_documents.py first. Missing:\n  - " + preview
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for entry in entries:
        document = prepare_entry_document(entry, conversion_dir=args.conversion_dir)
        issues = list(document.report.issues)
        hierarchy = None
        if document.source_role is SourceRole.PRIMARY_LEGAL_DOCUMENT:
            hierarchy, parser_issues = parse_hierarchy(document)
            issues.extend(parser_issues)
            chunks = build_chunks(document, hierarchy)
            chunk_strategy = "legal_provision"
        else:
            chunks = build_content_chunks(document)
            chunk_strategy = "content_window"

        relative_dir = Path(entry.package_id) / entry.source_id
        document_dir = args.output_dir / relative_dir
        document_dir.mkdir(parents=True, exist_ok=True)
        _write_jsonl(document_dir / "chunks.jsonl", [chunk.to_dict() for chunk in chunks])
        if hierarchy is not None:
            _write_json(document_dir / "hierarchy.json", hierarchy.to_dict())
        _write_json(
            document_dir / "report.json",
            {
                "source_file": document.source_file,
                "document_id": document.document_id,
                "package_id": document.package_id,
                "parent_document_id": document.parent_document_id,
                "source_role": document.source_role.value,
                "source_hash": entry.source_hash,
                "chunk_strategy": chunk_strategy,
                "chunk_count": len(chunks),
                "issues": [issue.to_dict() for issue in issues],
                "validation_notice": (
                    "Generated locally; chunks are not validated legal ground truth."
                ),
            },
        )
        manifest.append(
            {
                "source_file": document.source_file,
                "document_id": document.document_id,
                "package_id": document.package_id,
                "source_role": document.source_role.value,
                "chunk_strategy": chunk_strategy,
                "chunk_count": len(chunks),
                "output_dir": relative_dir.as_posix(),
            }
        )

    _write_json(args.output_dir / "manifest.json", manifest)
    total = sum(int(item["chunk_count"]) for item in manifest)
    print(
        f"Generated {total} local chunk(s) for {len(manifest)} source(s) "
        f"in {args.output_dir}. Generated data remains local and ignored by Git."
    )


def _prepared_source_ids(preparation_dir: Path) -> set[str]:
    manifest_path = preparation_dir / "manifest.json"
    if not manifest_path.is_file():
        raise SystemExit(
            f"Preparation manifest not found: {manifest_path}. "
            "Run scripts/ingest_documents.py first."
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit(f"Invalid preparation manifest: {manifest_path}")
    return {
        str(item["document_id"])
        for item in payload
        if isinstance(item, dict) and item.get("document_id")
    }


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
