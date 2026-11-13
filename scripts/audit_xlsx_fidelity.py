"""Compare every XLSX source cell and workbook feature with prepared artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def audit(source_root: Path, artifact_root: Path, markdown_root: Path) -> dict:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - deployment configuration
        raise RuntimeError("Install openpyxl to audit XLSX workbooks.") from exc

    manifest = json.loads((artifact_root / "manifest.json").read_text(encoding="utf-8"))
    results: list[dict] = []
    for item in manifest:
        if Path(item["source_file"]).suffix.casefold() != ".xlsx":
            continue
        source = source_root / item["source_file"]
        artifact_dir = artifact_root / item["artifact_dir"]
        markdown_path = markdown_root / item["markdown_relative_path"]
        report = json.loads((artifact_dir / "report.json").read_text(encoding="utf-8"))
        blocks = [
            json.loads(line)
            for line in (artifact_dir / "blocks.jsonl").read_text(encoding="utf-8").splitlines()
            if line
        ]
        extraction = report["extraction"]
        problems: list[str] = []
        workbook = load_workbook(source, data_only=False, read_only=False, keep_links=True)
        cached = load_workbook(source, data_only=True, read_only=False, keep_links=True)
        source_nonempty = 0
        source_formulas = 0
        source_cached = 0
        source_merges = 0
        source_validations = 0
        source_hidden_rows = 0
        extracted_cells = 0
        markdown = markdown_path.read_text(encoding="utf-8")
        worksheet_blocks = {
            block["metadata"]["sheet"]: block
            for block in blocks
            if block["kind"] == "worksheet"
        }
        row_blocks = [
            block
            for block in blocks
            if block["kind"] == "table" and "cells" in block.get("metadata", {})
        ]
        extracted_by_sheet: dict[str, dict[str, dict]] = {}
        for block in row_blocks:
            sheet = block["metadata"]["sheet"]
            for cell in block["metadata"]["cells"]:
                extracted_by_sheet.setdefault(sheet, {})[cell["coordinate"]] = cell
                extracted_cells += 1

        try:
            for worksheet in workbook.worksheets:
                title = worksheet.title
                sheet_block = worksheet_blocks.get(title)
                if sheet_block is None:
                    problems.append(f"missing_worksheet:{title}")
                    continue
                metadata = sheet_block["metadata"]
                merged = [str(value) for value in worksheet.merged_cells.ranges]
                validations = [
                    {
                        "ranges": str(value.sqref),
                        "type": value.type,
                        "formula1": value.formula1,
                        "formula2": value.formula2,
                        "allow_blank": value.allow_blank,
                    }
                    for value in (
                        worksheet.data_validations.dataValidation
                        if worksheet.data_validations
                        else []
                    )
                ]
                hidden_rows = sorted(
                    index
                    for index, dimension in worksheet.row_dimensions.items()
                    if dimension.hidden
                )
                hidden_columns = sorted(
                    index
                    for index, dimension in worksheet.column_dimensions.items()
                    if dimension.hidden
                )
                source_merges += len(merged)
                source_validations += len(validations)
                source_hidden_rows += len(hidden_rows)
                if metadata.get("merged_ranges") != merged:
                    problems.append(f"merged_ranges_differ:{title}")
                if metadata.get("data_validations") != validations:
                    problems.append(f"data_validations_differ:{title}")
                if metadata.get("hidden_rows") != hidden_rows:
                    problems.append(f"hidden_rows_differ:{title}")
                if metadata.get("hidden_columns") != hidden_columns:
                    problems.append(f"hidden_columns_differ:{title}")
                if f"## Trang tính {title}" not in markdown:
                    problems.append(f"markdown_sheet_missing:{title}")

                extracted = extracted_by_sheet.get(title, {})
                for cell in worksheet._cells.values():
                    if cell.value in (None, ""):
                        continue
                    source_nonempty += 1
                    actual = extracted.get(cell.coordinate)
                    if actual is None:
                        problems.append(f"cell_missing:{title}!{cell.coordinate}")
                        continue
                    expected_base = {
                        "coordinate": cell.coordinate,
                        "data_type": cell.data_type,
                        "number_format": cell.number_format,
                    }
                    for key, value in expected_base.items():
                        if actual.get(key) != value:
                            problems.append(f"cell_{key}_differs:{title}!{cell.coordinate}")
                    is_formula = cell.data_type == "f" or (
                        isinstance(cell.value, str) and cell.value.startswith("=")
                    )
                    if is_formula:
                        source_formulas += 1
                        if actual.get("formula") != str(cell.value):
                            problems.append(f"formula_differs:{title}!{cell.coordinate}")
                        cached_value = cached[title][cell.coordinate].value
                        if cached_value is not None:
                            source_cached += 1
                            if actual.get("cached_value") != _json_value(cached_value):
                                problems.append(f"cached_value_differs:{title}!{cell.coordinate}")
                    elif actual.get("value") != _json_value(cell.value):
                        problems.append(f"value_differs:{title}!{cell.coordinate}")
                    if f"`{cell.coordinate}`" not in markdown:
                        problems.append(f"markdown_cell_missing:{title}!{cell.coordinate}")
        finally:
            workbook.close()
            cached.close()

        expected_counts = {
            "worksheet_count": len(worksheet_blocks),
            "nonempty_cell_count": source_nonempty,
            "formula_cell_count": source_formulas,
            "formula_cached_value_count": source_cached,
            "merged_cell_count": source_merges,
            "data_validation_count": source_validations,
        }
        for key, expected in expected_counts.items():
            if extraction.get(key) != expected:
                problems.append(f"report_{key}:{extraction.get(key)}_expected:{expected}")
        if extracted_cells != source_nonempty:
            problems.append(f"extracted_cells:{extracted_cells}_expected:{source_nonempty}")

        with ZipFile(source) as package:
            source_media = {
                name: hashlib.sha256(package.read(name)).hexdigest()
                for name in package.namelist()
                if name.startswith("xl/media/")
            }
        captured_media = {
            asset["package_path"]: asset
            for asset in report["assets"]
            if asset["package_path"].startswith("xl/media/")
        }
        if set(source_media) != set(captured_media):
            problems.append("workbook_media_paths_differ")
        for package_path, digest in source_media.items():
            asset = captured_media.get(package_path)
            if not asset:
                continue
            asset_path = artifact_dir / "assets" / (
                f"{asset['asset_id']}-{Path(asset['filename']).name}"
            )
            if not asset_path.is_file():
                problems.append(f"artifact_media_missing:{package_path}")
            elif hashlib.sha256(asset_path.read_bytes()).hexdigest() != digest:
                problems.append(f"artifact_media_differs:{package_path}")

        results.append(
            {
                "source": item["source_file"],
                "worksheets": len(worksheet_blocks),
                "nonempty_cells": source_nonempty,
                "formula_cells": source_formulas,
                "cached_formula_values": source_cached,
                "merged_ranges": source_merges,
                "data_validations": source_validations,
                "hidden_rows": source_hidden_rows,
                "package_media": len(source_media),
                "problems": sorted(set(problems)),
            }
        )
    return {
        "workbooks": len(results),
        "failed": sum(bool(item["problems"]) for item in results),
        "totals": {
            "worksheets": sum(item["worksheets"] for item in results),
            "nonempty_cells": sum(item["nonempty_cells"] for item in results),
            "formula_cells": sum(item["formula_cells"] for item in results),
            "cached_formula_values": sum(
                item["cached_formula_values"] for item in results
            ),
            "merged_ranges": sum(item["merged_ranges"] for item in results),
            "data_validations": sum(item["data_validations"] for item in results),
            "hidden_rows": sum(item["hidden_rows"] for item in results),
            "package_media": sum(item["package_media"] for item in results),
        },
        "results": results,
        "scope": (
            "exact cell values, formulas, cached results, merges, validations, hidden rows, "
            "worksheet inventory, and packaged media"
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-dir", type=Path, default=Path("data/source_packages"))
    parser.add_argument("--artifact-dir", type=Path, default=Path("data/artifacts"))
    parser.add_argument("--markdown-dir", type=Path, default=Path("data/derived/markdown"))
    parser.add_argument("--output", type=Path, default=Path("data/derived/xlsx_fidelity.json"))
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
