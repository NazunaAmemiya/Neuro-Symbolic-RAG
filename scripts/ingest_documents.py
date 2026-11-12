"""Prepare local Markdown and extraction evidence without parsing or chunking."""

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
from backend.app.ingestion.formula_ocr import Pix2TexOCR
from backend.app.ingestion.formula_reviews import load_formula_reviews
from backend.app.ingestion.markdown_renderer import write_markdown_view
from backend.app.ingestion.models import BlockKind, SourceDocument, SourceFormat, SourceRole
from backend.app.ingestion.pipeline import prepare_entry_document
from backend.app.ingestion.source_catalog import build_source_catalog


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path(settings.source_docs_dir))
    parser.add_argument("--output-dir", type=Path, default=Path(settings.ingest_artifacts_dir))
    parser.add_argument("--conversion-dir", type=Path, default=Path(settings.converted_docs_dir))
    parser.add_argument("--markdown-dir", type=Path, default=Path(settings.markdown_output_dir))
    parser.add_argument(
        "--no-markdown",
        action="store_true",
        help="Skip the portable local Markdown view.",
    )
    parser.add_argument(
        "--docx-only",
        action="store_true",
        help="Ignore legacy Markdown/text even if they are present below source-dir.",
    )
    parser.add_argument(
        "--formula-ocr",
        choices=("off", "pix2tex"),
        default="off",
        help="Optional local math OCR; predictions always require review.",
    )
    parser.add_argument(
        "--formula-reviews",
        type=Path,
        help="Local JSON with source-bound, visually reviewed formula transcriptions.",
    )
    args = parser.parse_args()
    try:
        formula_ocr = Pix2TexOCR() if args.formula_ocr == "pix2tex" else None
    except RuntimeError as exc:
        parser.error(str(exc))
    formula_reviews = load_formula_reviews(args.formula_reviews) if args.formula_reviews else None

    source_entries = build_source_catalog(args.source_dir)
    if args.docx_only:
        source_entries = [
            entry for entry in source_entries if entry.source_format is SourceFormat.DOCX
        ]
    if not source_entries:
        raise SystemExit(f"No supported source documents found in {args.source_dir}")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []
    for entry in source_entries:
        document = prepare_entry_document(
            entry,
            conversion_dir=args.conversion_dir,
            formula_ocr=formula_ocr,
            formula_reviews=formula_reviews,
        )
        artifact_relative_dir = Path(entry.package_id) / entry.source_id
        document_dir = args.output_dir / artifact_relative_dir
        assets_dir = document_dir / "assets"
        assets_dir.mkdir(parents=True, exist_ok=True)
        markdown_relative_path = None
        if not args.no_markdown:
            markdown_path = write_markdown_view(document, args.markdown_dir)
            markdown_relative_path = markdown_path.relative_to(args.markdown_dir).as_posix()

        _write_jsonl(
            document_dir / "blocks.jsonl",
            [block.to_dict() for block in document.blocks],
        )
        validation = _validation_state(document)
        _write_json(
            document_dir / "report.json",
            {
                "source_file": document.source_file,
                "document_id": document.document_id,
                "package_id": entry.package_id,
                "parent_document_id": entry.parent_document_id,
                "source_role": entry.role.value,
                "source_format": entry.source_format.value,
                "source_hash": entry.source_hash,
                "association": entry.association,
                "extraction": document.report.to_dict(),
                "issues": [issue.to_dict() for issue in document.report.issues],
                "footnotes": document.footnotes,
                "assets": [asset.to_dict() for asset in document.assets],
                "metadata": document.metadata,
                "markdown_relative_path": markdown_relative_path,
                "validation": validation,
            },
        )
        for asset in document.assets:
            destination = assets_dir / f"{asset.asset_id}-{asset.safe_filename}"
            destination.write_bytes(asset.data)

        errors = sum(issue.severity.value == "error" for issue in document.report.issues)
        warnings = sum(issue.severity.value == "warning" for issue in document.report.issues)
        manifest.append(
            {
                "source_file": document.source_file,
                "document_id": document.document_id,
                "package_id": entry.package_id,
                "parent_document_id": entry.parent_document_id,
                "source_role": entry.role.value,
                "source_format": entry.source_format.value,
                "source_hash": entry.source_hash,
                "block_count": len(document.blocks),
                "asset_count": len(document.assets),
                "warning_count": warnings,
                "error_count": errors,
                "artifact_dir": artifact_relative_dir.as_posix(),
                "markdown_relative_path": markdown_relative_path,
                "validation_status": validation["status"],
                "review_reasons": validation["review_reasons"],
            }
        )

    _write_json(args.output_dir / "manifest.json", manifest)
    _write_json(
        args.output_dir / "validation_summary.json",
        {
            "status": "requires_review",
            "chunking_enabled": False,
            "source_count": len(manifest),
            "review_queue": [
                {
                    "source_file": item["source_file"],
                    "source_role": item["source_role"],
                    "review_reasons": item["review_reasons"],
                }
                for item in manifest
            ],
        },
    )
    print(
        f"Prepared Markdown and extraction evidence for {len(manifest)} source(s) "
        f"in {args.output_dir}. No chunks were created; manual validation is required."
    )


def _validation_state(document: SourceDocument) -> dict[str, object]:
    reasons = ["visual_and_semantic_fidelity_not_yet_reviewed"]
    if document.source_role is not SourceRole.PRIMARY_LEGAL_DOCUMENT:
        reasons.append("no_reference_validation_for_appendix_or_form")
    if document.source_format is SourceFormat.XLSX:
        reasons.append("spreadsheet_layout_and_formula_results_require_review")
    unreviewed = [
        block
        for block in document.blocks
        if block.kind is BlockKind.FORMULA
        and block.metadata.get("review_status") != "reviewed_visual"
    ]
    if any(block.metadata.get("source_type") == "image" for block in unreviewed):
        reasons.append("formula_images_require_human_transcription_review")
    if any(block.metadata.get("source_type") == "omml" for block in unreviewed):
        reasons.append("omml_candidates_require_visual_review")
    if document.report.attachment_count or document.report.ole_object_count:
        reasons.append("embedded_payloads_require_recursive_review")
    return {
        "status": "requires_review",
        "automated_checks_only": [
            "source_catalog_association",
            "office_structure_extraction",
            "relative_markdown_and_asset_paths",
        ],
        "review_reasons": reasons,
        "ground_truth_scope": (
            "legacy_primary_document_review_only"
            if document.source_role is SourceRole.PRIMARY_LEGAL_DOCUMENT
            else "none_for_appendix_or_form"
        ),
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
