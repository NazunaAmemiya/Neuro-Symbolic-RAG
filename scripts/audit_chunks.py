"""Audit generated chunks against preparation artifacts block by block."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preparation-dir", type=Path, default=Path("data/artifacts"))
    parser.add_argument("--chunks-dir", type=Path, default=Path("data/derived/chunks"))
    parser.add_argument(
        "--output", type=Path, default=Path("data/derived/chunk_audit.json")
    )
    args = parser.parse_args()
    report = audit_chunks(args.preparation_dir, args.chunks_dir)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    if report["summary"]["failed_documents"]:
        raise SystemExit(1)


def audit_chunks(preparation_dir: Path, chunks_dir: Path) -> dict[str, Any]:
    preparation = _load_json(preparation_dir / "manifest.json")
    chunk_manifest = _load_json(chunks_dir / "manifest.json")
    if not isinstance(preparation, list) or not isinstance(chunk_manifest, list):
        raise TypeError("Preparation and chunk manifests must be arrays")
    chunk_by_document = {row["document_id"]: row for row in chunk_manifest}
    results = []
    for source in preparation:
        document_id = source["document_id"]
        problems: list[str] = []
        chunk_entry = chunk_by_document.get(document_id)
        if chunk_entry is None:
            results.append({"source": source["source_file"], "problems": ["missing_chunks"]})
            continue
        blocks = _load_jsonl(preparation_dir / source["artifact_dir"] / "blocks.jsonl")
        chunks = _load_jsonl(chunks_dir / chunk_entry["output_dir"] / "chunks.jsonl")
        block_map = {block["block_id"]: block for block in blocks}
        references = Counter(
            block_id for chunk in chunks for block_id in chunk.get("block_ids", [])
        )
        missing = sorted(set(block_map) - set(references))
        duplicate = sorted(block_id for block_id, count in references.items() if count != 1)
        extra = sorted(set(references) - set(block_map))
        if missing:
            problems.append(f"missing_blocks:{len(missing)}")
        if duplicate:
            problems.append(f"nonunique_block_references:{len(duplicate)}")
        if extra:
            problems.append(f"unknown_blocks:{len(extra)}")

        expected_assets = {
            asset_id for block in blocks for asset_id in block.get("asset_ids", [])
        }
        chunk_assets = {asset_id for chunk in chunks for asset_id in chunk.get("asset_ids", [])}
        if expected_assets != chunk_assets:
            problems.append(
                f"asset_coverage:missing_{len(expected_assets - chunk_assets)}:extra_{len(chunk_assets - expected_assets)}"
            )

        table_blocks = [block for block in blocks if block["kind"] == "table"]
        formula_blocks = [block for block in blocks if block["kind"] == "formula"]
        formula_cells = 0
        cached_formula_values = 0
        reviewed_formula_blocks = 0
        unreviewed_formula_blocks = 0
        table_failures = 0
        formula_failures = 0
        for block in table_blocks:
            matches = [chunk for chunk in chunks if block["block_id"] in chunk.get("block_ids", [])]
            if len(matches) != 1 or _chunk_kind(matches[0]) != "table":
                table_failures += 1
                continue
            if block.get("text") and block["text"] not in matches[0].get("display_text", ""):
                table_failures += 1
            copied = _chunk_block_payload(matches[0], block["block_id"])
            if block.get("table") is not None:
                actual_table = matches[0].get("metadata", {}).get("table")
                if actual_table is None and copied:
                    actual_table = copied.get("table")
                if actual_table != block["table"]:
                    table_failures += 1
            cells = block.get("metadata", {}).get("cells", [])
            source_formulas = {
                cell["coordinate"]: {
                    "formula": cell["formula"],
                    "cached_value": cell.get("cached_value"),
                }
                for cell in cells
                if isinstance(cell, dict) and cell.get("formula")
            }
            formula_cells += len(source_formulas)
            cached_formula_values += sum(
                value["cached_value"] is not None for value in source_formulas.values()
            )
            if source_formulas:
                copied_cells = (copied or {}).get("metadata", {}).get("cells", [])
                copied_formulas = {
                    cell["coordinate"]: {
                        "formula": cell["formula"],
                        "cached_value": cell.get("cached_value"),
                    }
                    for cell in copied_cells
                    if isinstance(cell, dict) and cell.get("formula")
                }
                if copied_formulas != source_formulas:
                    formula_failures += 1
                if not all(
                    formula in matches[0].get("display_text", "")
                    for formula in (value["formula"] for value in source_formulas.values())
                ):
                    formula_failures += 1

        for block in formula_blocks:
            if block.get("metadata", {}).get("review_status") == "reviewed_visual":
                reviewed_formula_blocks += 1
            else:
                unreviewed_formula_blocks += 1
            matches = [chunk for chunk in chunks if block["block_id"] in chunk.get("block_ids", [])]
            if len(matches) != 1 or _chunk_kind(matches[0]) != "formula":
                formula_failures += 1
                continue
            if block.get("text") and block["text"] not in matches[0].get("display_text", ""):
                formula_failures += 1
            actual = matches[0].get("metadata", {}).get("formula")
            if actual is None:
                copied = _chunk_block_payload(matches[0], block["block_id"])
                actual = (copied or {}).get("metadata")
            if actual != block.get("metadata", {}):
                formula_failures += 1
        if table_failures:
            problems.append(f"table_failures:{table_failures}")
        if formula_failures:
            problems.append(f"formula_failures:{formula_failures}")

        if source["source_role"] != "primary_legal_document":
            for chunk in chunks:
                if (
                    chunk.get("source_role") != source["source_role"]
                    or chunk.get("package_id") != source["package_id"]
                    or chunk.get("parent_document_id") != source["parent_document_id"]
                ):
                    problems.append("form_or_appendix_linkage_mismatch")
                    break
        results.append(
            {
                "source": source["source_file"],
                "source_role": source["source_role"],
                "blocks": len(blocks),
                "chunks": len(chunks),
                "tables": len(table_blocks),
                "formula_blocks": len(formula_blocks),
                "reviewed_formula_blocks": reviewed_formula_blocks,
                "unreviewed_formula_blocks": unreviewed_formula_blocks,
                "formula_cells": formula_cells,
                "cached_formula_values": cached_formula_values,
                "assets": len(expected_assets),
                "problems": problems,
            }
        )

    manifest_extras = sorted(set(chunk_by_document) - {row["document_id"] for row in preparation})
    summary = {
        "source_documents": len(preparation),
        "chunked_documents": len(chunk_manifest),
        "chunks": sum(row.get("chunks", 0) for row in results),
        "source_blocks": sum(row.get("blocks", 0) for row in results),
        "table_blocks": sum(row.get("tables", 0) for row in results),
        "formula_blocks": sum(row.get("formula_blocks", 0) for row in results),
        "reviewed_formula_blocks": sum(
            row.get("reviewed_formula_blocks", 0) for row in results
        ),
        "unreviewed_formula_blocks": sum(
            row.get("unreviewed_formula_blocks", 0) for row in results
        ),
        "xlsx_formula_cells": sum(row.get("formula_cells", 0) for row in results),
        "xlsx_cached_formula_values": sum(
            row.get("cached_formula_values", 0) for row in results
        ),
        "linked_assets": sum(row.get("assets", 0) for row in results),
        "failed_documents": sum(bool(row["problems"]) for row in results)
        + int(bool(manifest_extras)),
        "extra_chunk_manifest_documents": manifest_extras,
        "scope": "exact block/table/formula/form-link coverage; not semantic legal validation",
    }
    return {"summary": summary, "results": results}


def _chunk_kind(chunk: dict[str, Any]) -> str | None:
    metadata = chunk.get("metadata", {})
    return metadata.get("chunk_kind") or metadata.get("content_kind")


def _chunk_block_payload(chunk: dict[str, Any], block_id: str) -> dict[str, Any] | None:
    for block in chunk.get("metadata", {}).get("blocks", []):
        if block.get("block_id") == block_id:
            return block
    return None


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


if __name__ == "__main__":
    main()
