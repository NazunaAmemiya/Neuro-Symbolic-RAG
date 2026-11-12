from __future__ import annotations

from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import Any
from zipfile import ZipFile

from .models import (
    AssetKind,
    BlockKind,
    DocumentBlock,
    EmbeddedAsset,
    ExtractionReport,
    SourceDocument,
    SourceFormat,
    SourceRole,
    stable_id,
)


def extract_xlsx(path: Path) -> SourceDocument:
    """Read an XLSX form without flattening sheets, merges, formulas, or validations."""

    try:
        from openpyxl import load_workbook
    except ImportError as exc:  # pragma: no cover - exercised by deployment configuration
        raise RuntimeError("Install openpyxl to ingest XLSX form workbooks.") from exc

    source_bytes = path.read_bytes()
    document_id = stable_id("workbook", path.name, sha256(source_bytes).hexdigest())
    report = ExtractionReport()
    blocks: list[DocumentBlock] = []
    assets: list[EmbeddedAsset] = []
    asset_hashes: set[str] = set()
    workbook = load_workbook(path, data_only=False, read_only=False, keep_links=True)
    cached_workbook = load_workbook(path, data_only=True, read_only=False, keep_links=True)
    sheet_names = list(workbook.sheetnames)
    order = 0

    try:
        for sheet_index, worksheet in enumerate(workbook.worksheets, start=1):
            report.worksheet_count += 1
            validations = _validations(worksheet)
            report.data_validation_count += len(validations)
            merged_ranges = [str(value) for value in worksheet.merged_cells.ranges]
            report.merged_cell_count += len(merged_ranges)
            hidden_rows = sorted(
                index for index, dimension in worksheet.row_dimensions.items() if dimension.hidden
            )
            hidden_columns = sorted(
                index
                for index, dimension in worksheet.column_dimensions.items()
                if dimension.hidden
            )
            order += 1
            blocks.append(
                DocumentBlock(
                    block_id=stable_id(document_id, "worksheet", str(sheet_index)),
                    kind=BlockKind.WORKSHEET,
                    order=order,
                    text=f"[TRANG TÍNH] {worksheet.title}",
                    locator=f"workbook/sheet[{sheet_index}]",
                    metadata={
                        "sheet": worksheet.title,
                        "sheet_index": sheet_index,
                        "state": worksheet.sheet_state,
                        "dimension": worksheet.calculate_dimension(),
                        "merged_ranges": merged_ranges,
                        "data_validations": validations,
                        "hidden_rows": hidden_rows,
                        "hidden_columns": hidden_columns,
                        "freeze_panes": str(worksheet.freeze_panes)
                        if worksheet.freeze_panes
                        else None,
                        "auto_filter": worksheet.auto_filter.ref,
                        "print_area": str(worksheet.print_area) if worksheet.print_area else None,
                    },
                )
            )

            populated_by_row: dict[int, list[Any]] = {}
            # Sparse iteration avoids expanding styled workbooks to their declared dimensions.
            for cell in worksheet._cells.values():
                if cell.value not in (None, ""):
                    populated_by_row.setdefault(cell.row, []).append(cell)

            for row_number, cells in sorted(populated_by_row.items()):
                cell_metadata: list[dict[str, object]] = []
                text_values: list[str] = []
                formula_coordinates: list[str] = []
                for cell in sorted(cells, key=lambda item: item.column):
                    report.nonempty_cell_count += 1
                    value = cell.value
                    is_formula = cell.data_type == "f" or (
                        isinstance(value, str) and value.startswith("=")
                    )
                    metadata: dict[str, object] = {
                        "coordinate": cell.coordinate,
                        "data_type": cell.data_type,
                        "number_format": cell.number_format,
                    }
                    if is_formula:
                        report.formula_cell_count += 1
                        metadata["formula"] = str(value)
                        cached_value = cached_workbook[worksheet.title][cell.coordinate].value
                        if cached_value is not None:
                            metadata["cached_value"] = _json_value(cached_value)
                            report.formula_cached_value_count += 1
                        formula_coordinates.append(cell.coordinate)
                    else:
                        metadata["value"] = _json_value(value)
                        text_values.append(f"{cell.coordinate}: {value}")
                    cell_metadata.append(metadata)

                if not text_values and not formula_coordinates:
                    continue
                if formula_coordinates:
                    text_values.append(f"[CÔNG THỨC: {', '.join(formula_coordinates)}]")
                order += 1
                blocks.append(
                    DocumentBlock(
                        block_id=stable_id(
                            document_id, "worksheet-row", str(sheet_index), str(row_number)
                        ),
                        kind=BlockKind.TABLE,
                        order=order,
                        text=" | ".join(text_values),
                        locator=f"workbook/sheet[{sheet_index}]/row[{row_number}]",
                        metadata={
                            "sheet": worksheet.title,
                            "sheet_index": sheet_index,
                            "row": row_number,
                            "cells": cell_metadata,
                        },
                    )
                )

            for image_index, image in enumerate(getattr(worksheet, "_images", []), start=1):
                # openpyxl currently exposes image bytes only through this method.
                data = image._data()
                extension = (getattr(image, "format", None) or "png").casefold()
                filename = f"sheet-{sheet_index}-image-{image_index}.{extension}"
                asset = EmbeddedAsset(
                    asset_id=stable_id(
                        document_id, "worksheet-image", str(sheet_index), str(image_index)
                    ),
                    kind=AssetKind.IMAGE,
                    package_path=f"workbook/sheet[{sheet_index}]/image[{image_index}]",
                    content_type=f"image/{extension}",
                    filename=filename,
                    relationship_id=None,
                    data=data,
                    metadata={"sheet": worksheet.title, "sheet_index": sheet_index},
                )
                assets.append(asset)
                asset_hashes.add(sha256(data).hexdigest())
                report.image_count += 1
                order += 1
                blocks.append(
                    DocumentBlock(
                        block_id=stable_id(document_id, "worksheet-image-block", asset.asset_id),
                        kind=BlockKind.IMAGE,
                        order=order,
                        text=f"[HÌNH ẢNH TRONG TRANG TÍNH: {asset.asset_id}]",
                        locator=asset.package_path,
                        asset_ids=[asset.asset_id],
                        metadata={"sheet": worksheet.title, "sheet_index": sheet_index},
                    )
                )
    finally:
        workbook.close()
        cached_workbook.close()

    archive_counts = _archive_assets(
        path=path,
        document_id=document_id,
        blocks=blocks,
        assets=assets,
        asset_hashes=asset_hashes,
        report=report,
        start_order=order,
    )

    return SourceDocument(
        document_id=document_id,
        source_file=path.name,
        blocks=blocks,
        assets=assets,
        report=report,
        source_role=SourceRole.FORM_WORKBOOK,
        source_format=SourceFormat.XLSX,
        metadata={"sheet_names": sheet_names, "archive": archive_counts},
    )


def _validations(worksheet: Any) -> list[dict[str, object]]:
    if worksheet.data_validations is None:
        return []
    return [
        {
            "ranges": str(item.sqref),
            "type": item.type,
            "formula1": item.formula1,
            "formula2": item.formula2,
            "allow_blank": item.allow_blank,
        }
        for item in worksheet.data_validations.dataValidation
    ]


def _archive_assets(
    *,
    path: Path,
    document_id: str,
    blocks: list[DocumentBlock],
    assets: list[EmbeddedAsset],
    asset_hashes: set[str],
    report: ExtractionReport,
    start_order: int,
) -> dict[str, int]:
    order = start_order
    counts = {"media": 0, "embeddings": 0, "drawings": 0, "external_links": 0}
    with ZipFile(path) as package:
        names = package.namelist()
        counts["drawings"] = sum(name.startswith("xl/drawings/") for name in names)
        counts["external_links"] = sum(name.startswith("xl/externalLinks/") for name in names)
        for package_path in names:
            if package_path.startswith("xl/media/"):
                kind = AssetKind.IMAGE
                block_kind = BlockKind.IMAGE
                counts["media"] += 1
            elif package_path.startswith("xl/embeddings/"):
                kind = AssetKind.ATTACHMENT
                block_kind = BlockKind.ATTACHMENT
                counts["embeddings"] += 1
            else:
                continue
            data = package.read(package_path)
            digest = sha256(data).hexdigest()
            if digest in asset_hashes:
                continue
            asset_hashes.add(digest)
            filename = PurePosixPath(package_path).name
            asset = EmbeddedAsset(
                asset_id=stable_id(document_id, "xlsx-package-asset", package_path, digest),
                kind=kind,
                package_path=package_path,
                content_type=_content_type(filename, kind),
                filename=filename,
                relationship_id=None,
                data=data,
                metadata={"association": "preserved_from_xlsx_package"},
            )
            assets.append(asset)
            if kind is AssetKind.IMAGE:
                report.image_count += 1
                label = "HÌNH ẢNH TRONG WORKBOOK"
            else:
                report.attachment_count += 1
                label = "TỆP NHÚNG TRONG WORKBOOK"
            order += 1
            blocks.append(
                DocumentBlock(
                    block_id=stable_id(document_id, "xlsx-package-asset-block", asset.asset_id),
                    kind=block_kind,
                    order=order,
                    text=f"[{label}: {asset.asset_id}]",
                    locator=package_path,
                    asset_ids=[asset.asset_id],
                    metadata={"association": "workbook_package"},
                )
            )
    return counts


def _content_type(filename: str, kind: AssetKind) -> str:
    suffix = PurePosixPath(filename).suffix.casefold()
    if kind is AssetKind.IMAGE:
        return {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".bmp": "image/bmp",
            ".emf": "image/emf",
            ".wmf": "image/wmf",
        }.get(suffix, "application/octet-stream")
    return "application/octet-stream"


def _json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)
