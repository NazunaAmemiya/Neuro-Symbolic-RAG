"""Check structural coverage of generated Markdown against its Office source."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import quote
from xml.etree import ElementTree
from zipfile import ZipFile

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

from lxml import etree

from backend.app.core.settings import get_settings
from backend.app.ingestion.source_catalog import SUPPORTED_SOURCE_SUFFIXES

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class TableCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "table":
            self.tables += 1


def audit(source_root: Path, artifact_root: Path, markdown_root: Path) -> dict:
    manifest = json.loads((artifact_root / "manifest.json").read_text(encoding="utf-8"))
    coverage = _source_coverage(source_root, manifest)
    results = []
    for item in manifest:
        source = source_root / item["source_file"]
        markdown_path = markdown_root / item["markdown_relative_path"]
        artifact_dir = artifact_root / item["artifact_dir"]
        problems: list[str] = []
        if not source.is_file() or not markdown_path.is_file():
            results.append(
                {"source": item["source_file"], "problems": ["source_or_markdown_missing"]}
            )
            continue
        if hashlib.sha256(source.read_bytes()).hexdigest() != item["source_hash"]:
            problems.append("source_hash_mismatch")
        markdown = markdown_path.read_text(encoding="utf-8")
        report = json.loads((artifact_dir / "report.json").read_text(encoding="utf-8"))
        blocks = [
            json.loads(line)
            for line in (artifact_dir / "blocks.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        tables = [b for b in blocks if b["kind"] == "table" and b.get("table")]
        formulas = [b for b in blocks if b["kind"] == "formula"]
        formula_images = [
            block for block in formulas if block.get("metadata", {}).get("source_type") == "image"
        ]
        formula_omml = [
            block for block in formulas if block.get("metadata", {}).get("source_type") == "omml"
        ]
        formula_paragraphs = [
            block
            for block in formulas
            if block.get("metadata", {}).get("source_type") == "reviewed_paragraph"
        ]
        unreviewed_formulas = [
            block
            for block in formulas
            if block.get("metadata", {}).get("review_status") != "reviewed_visual"
        ]
        counter = TableCounter()
        counter.feed(markdown)
        nested = sum(_nested_tables(b["table"]) for b in tables)
        expected_tables = len(tables) + nested
        if counter.tables != expected_tables:
            problems.append(f"markdown_tables:{counter.tables}_expected:{expected_tables}")

        source_media: set[str] = set()
        body_media: set[str] = set()
        source_tables: int | None = None
        original_media_hashes: dict[str, str] = {}
        if source.suffix.lower() == ".docx":
            with ZipFile(source) as package:
                body = etree.fromstring(package.read("word/document.xml")).find(f"{W}body")
                if body is None:
                    problems.append("docx_body_missing")
                else:
                    source_tables = sum(element.tag == f"{W}tbl" for element in body)
                    if source_tables != len(tables):
                        problems.append(f"extracted_tables:{len(tables)}_source:{source_tables}")
                source_media = {p for p in package.namelist() if p.startswith("word/media/")}
                original_media_hashes = {
                    path: hashlib.sha256(package.read(path)).hexdigest() for path in source_media
                }
                rels_path = "word/_rels/document.xml.rels"
                if rels_path in package.namelist():
                    relationships = ElementTree.fromstring(package.read(rels_path))
                    body_media = {
                        f"word/{element.attrib['Target'].lstrip('/')}"
                        for element in relationships
                        if element.attrib.get("Type", "").endswith("/image")
                        and element.attrib.get("Target", "").startswith("media/")
                    }
        assets = report["assets"]
        captured_media = {a["package_path"] for a in assets if a["package_path"] in source_media}
        if body_media - captured_media:
            problems.append(f"uncaptured_document_media:{len(body_media - captured_media)}")

        for asset in assets:
            filename = f"{asset['asset_id']}-{Path(asset['filename']).name}"
            artifact_asset = artifact_dir / "assets" / filename
            markdown_asset = markdown_path.parent / "_assets" / item["document_id"] / filename
            if not artifact_asset.is_file() or not markdown_asset.is_file():
                problems.append(f"missing_asset:{asset['asset_id']}")
            elif artifact_asset.read_bytes() != markdown_asset.read_bytes():
                problems.append(f"asset_bytes_differ:{asset['asset_id']}")
            if (
                artifact_asset.is_file()
                and asset["package_path"] in original_media_hashes
                and hashlib.sha256(artifact_asset.read_bytes()).hexdigest()
                != original_media_hashes[asset["package_path"]]
            ):
                problems.append(f"source_media_bytes_differ:{asset['asset_id']}")
        for block in blocks:
            if block["kind"] not in {"image", "formula", "attachment"}:
                continue
            for asset_id in block["asset_ids"]:
                asset = next((a for a in assets if a["asset_id"] == asset_id), None)
                if asset is None:
                    problems.append(f"unresolved_asset:{asset_id}")
                    continue
                link = quote(
                    f"_assets/{item['document_id']}/{asset_id}-{Path(asset['filename']).name}",
                    safe="/",
                )
                if f"({link})" not in markdown:
                    problems.append(f"missing_markdown_link:{asset_id}")
        results.append(
            {
                "source": item["source_file"],
                "source_tables": source_tables,
                "markdown_tables": counter.tables,
                "formula_blocks": len(formulas),
                "formula_image_blocks": len(formula_images),
                "formula_omml_blocks": len(formula_omml),
                "formula_paragraph_blocks": len(formula_paragraphs),
                "unreviewed_formula_blocks": len(unreviewed_formulas),
                "source_media": len(source_media),
                "other_package_media": len(source_media - body_media),
                "assets": len(assets),
                "problems": problems,
            }
        )
    return {
        "documents": len(results),
        "failed": sum(bool(row["problems"]) for row in results) + int(not coverage["complete"]),
        "coverage": coverage,
        "table_count": sum(row.get("markdown_tables", 0) for row in results),
        "formula_block_count": sum(row.get("formula_blocks", 0) for row in results),
        "formula_image_count": sum(row.get("formula_image_blocks", 0) for row in results),
        "formula_omml_count": sum(row.get("formula_omml_blocks", 0) for row in results),
        "formula_paragraph_count": sum(
            row.get("formula_paragraph_blocks", 0) for row in results
        ),
        "unreviewed_formula_count": sum(
            row.get("unreviewed_formula_blocks", 0) for row in results
        ),
        "results": results,
        "scope": "structural coverage and linked bytes; semantic and visual fidelity require review",
    }


def _source_coverage(source_root: Path, manifest: list[dict]) -> dict:
    discovered = {
        path.relative_to(source_root).as_posix()
        for path in source_root.rglob("*")
        if path.is_file()
        and path.suffix.casefold() in SUPPORTED_SOURCE_SUFFIXES
        and not path.name.startswith("~$")
        and ".cache" not in path.relative_to(source_root).parts
    }
    prepared = {item["source_file"].replace("\\", "/") for item in manifest}
    missing = sorted(discovered - prepared)
    stale = sorted(prepared - discovered)
    return {
        "complete": not missing and not stale,
        "discovered_office_files": len(discovered),
        "prepared_sources": len(prepared),
        "unprepared_sources": missing,
        "manifest_sources_not_found": stale,
    }


def _nested_tables(table: dict) -> int:
    nested = [child for cell in table["cells"] for child in cell.get("nested_tables", [])]
    return len(nested) + sum(_nested_tables(child) for child in nested)


def main() -> None:
    settings = get_settings()
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path(settings.source_docs_dir))
    parser.add_argument("--artifact-dir", type=Path, default=Path(settings.ingest_artifacts_dir))
    parser.add_argument("--markdown-dir", type=Path, default=Path(settings.markdown_output_dir))
    parser.add_argument("--output", type=Path, default=Path("data/derived/markdown_fidelity.json"))
    args = parser.parse_args()
    result = audit(args.source_dir, args.artifact_dir, args.markdown_dir)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    print(json.dumps(result, ensure_ascii=True, indent=2))
    if result["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
