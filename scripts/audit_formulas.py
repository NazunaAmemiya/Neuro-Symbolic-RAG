"""Inventory DOCX equations and verify extracted media against source bytes.

The JSON is a local review queue. Byte equality and an OCR candidate do not
prove that the mathematical expression has been transcribed correctly.
"""

from __future__ import annotations

import argparse
import json
import sys
from hashlib import sha256
from pathlib import Path
from zipfile import ZipFile

from lxml import etree

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.ingestion.docx_reader import extract_docx
from backend.app.ingestion.formula_ocr import Pix2TexOCR
from backend.app.ingestion.formula_reviews import load_formula_reviews
from backend.app.ingestion.models import AssetKind, BlockKind
from backend.app.ingestion.omml import inline_math_component

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path("data/source_packages"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/formula_audit.json"))
    parser.add_argument("--formula-ocr", choices=("off", "pix2tex"), default="off")
    parser.add_argument("--formula-reviews", type=Path)
    args = parser.parse_args()
    unsupported = sorted(
        path.relative_to(args.source_dir).as_posix()
        for path in args.source_dir.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in {".doc", ".xlsx"}
        and not path.name.startswith("~$")
        and ".cache" not in path.relative_to(args.source_dir).parts
    )
    sources = sorted(args.source_dir.rglob("*.docx"))
    if not sources:
        raise SystemExit(f"No DOCX files found below {args.source_dir}")
    try:
        recognizer = Pix2TexOCR() if args.formula_ocr == "pix2tex" else None
    except RuntimeError as exc:
        parser.error(str(exc))
    reviews = load_formula_reviews(args.formula_reviews) if args.formula_reviews else None
    rows = []
    for source in sources:
        document = extract_docx(source, formula_ocr=recognizer, formula_reviews=reviews)
        with ZipFile(source) as package:
            root = etree.fromstring(package.read("word/document.xml"))
            source_math = root.findall(f".//{{{MATH_NS}}}oMath")
            source_omml = len(source_math)
            source_inline_omml = sum(
                inline_math_component(element) is not None for element in source_math
            )
            media = []
            other_images = []
            for asset in document.assets:
                if asset.kind not in {AssetKind.FORMULA_IMAGE, AssetKind.IMAGE}:
                    continue
                original = package.read(asset.package_path)
                block = next(
                    (item for item in document.blocks if asset.asset_id in item.asset_ids), None
                )
                item = {
                    "asset_id": asset.asset_id,
                    "package_path": asset.package_path,
                    "locator": block.locator if block else None,
                    "sha256": sha256(asset.data).hexdigest(),
                    "byte_identical_to_docx": asset.data == original,
                    "review_status": (
                        "reviewed_visual" if asset.metadata.get("reviewed_latex") else "unverified"
                    ),
                }
                if asset.kind is AssetKind.FORMULA_IMAGE:
                    item["ocr_status"] = asset.metadata.get("ocr_status")
                    item["ocr_candidate_latex"] = asset.metadata.get("ocr_candidate_latex")
                    item["reviewed_latex"] = asset.metadata.get("reviewed_latex")
                    item["reviewer"] = asset.metadata.get("reviewer")
                    media.append(item)
                else:
                    other_images.append(item)
        omml = [
            {
                "block_id": block.block_id,
                "locator": block.locator,
                "formula_id": block.metadata.get("formula_id"),
                "candidate_latex": block.metadata.get("candidate_latex"),
                "reviewed_latex": block.metadata.get("reviewed_latex"),
                "review_status": block.metadata.get("review_status"),
            }
            for block in document.blocks
            if block.kind is BlockKind.FORMULA and block.metadata.get("source_type") == "omml"
        ]
        rows.append(
            {
                "source_path": source.relative_to(args.source_dir).as_posix(),
                "source_sha256": sha256(source.read_bytes()).hexdigest(),
                "source_omml_count": source_omml,
                "source_inline_omml_component_count": source_inline_omml,
                "extracted_omml_count": len(omml),
                "omml_count_matches": source_omml == len(omml) + source_inline_omml,
                "omml": omml,
                "formula_images": media,
                "other_images_not_formula_classified": other_images,
                "issues": [issue.to_dict() for issue in document.report.issues],
            }
        )
    summary = {
        "source_count": len(rows),
        "skipped_non_docx_count": len(unsupported),
        "coverage_status": "partial" if unsupported else "docx_only_complete",
        "omml_count": sum(len(row["omml"]) for row in rows),
        "inline_omml_component_count": sum(
            row["source_inline_omml_component_count"] for row in rows
        ),
        "image_formula_count": sum(len(row["formula_images"]) for row in rows),
        "other_image_count": sum(len(row["other_images_not_formula_classified"]) for row in rows),
        "ocr_candidate_count": sum(
            bool(image["ocr_candidate_latex"]) for row in rows for image in row["formula_images"]
        ),
        "reviewed_formula_count": sum(
            item["review_status"] == "reviewed_visual"
            for row in rows
            for item in [*row["omml"], *row["formula_images"]]
        ),
        "source_byte_mismatches": sum(
            not image["byte_identical_to_docx"]
            for row in rows
            for image in [*row["formula_images"], *row["other_images_not_formula_classified"]]
        ),
        "omml_count_mismatches": sum(not row["omml_count_matches"] for row in rows),
    }
    total_formulas = summary["omml_count"] + summary["image_formula_count"]
    summary["formula_review_status"] = (
        "reviewed_visual"
        if total_formulas and summary["reviewed_formula_count"] == total_formulas
        else "unverified"
    )
    summary["semantic_review_status"] = (
        "reviewed_visual"
        if summary["formula_review_status"] == "reviewed_visual"
        and summary["omml_count_mismatches"] == 0
        and summary["source_byte_mismatches"] == 0
        else "unverified"
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"summary": summary, "skipped_non_docx_sources": unsupported, "documents": rows},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
