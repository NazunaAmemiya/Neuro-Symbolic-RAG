from __future__ import annotations

import html
import json
import re
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from .models import BlockKind, DocumentBlock, EmbeddedAsset, SourceDocument, TableData

_LEGAL_HEADING = re.compile(
    r"^(?:(PHẦN|CHƯƠNG|MỤC|TIỂU MỤC)\s+[0-9IVXLCDM]+|(ĐIỀU)\s+\d+[A-ZÀ-ỸĐ]*[.:]?)",
    re.IGNORECASE,
)
_HEADING_LEVEL = {"PHẦN": 1, "CHƯƠNG": 2, "MỤC": 3, "TIỂU MỤC": 4, "ĐIỀU": 4}


def write_markdown_view(document: SourceDocument, output_root: Path) -> Path:
    """Write a portable Markdown view while retaining structured JSON as authority."""

    source_relative = document.source_relative_path or document.source_file
    source_path = PurePosixPath(source_relative.replace("\\", "/"))
    markdown_relative = source_path.parent / f"{source_path.name}.md"
    markdown_path = output_root.joinpath(*markdown_relative.parts)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)

    asset_relative_dir = PurePosixPath("_assets") / document.document_id
    asset_dir = markdown_path.parent.joinpath(*asset_relative_dir.parts)
    asset_links = _write_assets(document.assets, asset_dir, asset_relative_dir)
    content = render_markdown(document, asset_links)
    markdown_path.write_text(content, encoding="utf-8", newline="\n")
    return markdown_path


def render_markdown(document: SourceDocument, asset_links: dict[str, str] | None = None) -> str:
    asset_links = asset_links or {}
    source_hash = document.metadata.get("source_hash") or document.metadata.get(
        "original_source_hash"
    )
    lines = [
        "---",
        f"source_id: {_yaml_value(document.document_id)}",
        f"source_path: {_yaml_value(document.source_relative_path or document.source_file)}",
        f"package_id: {_yaml_value(document.package_id)}",
        f"parent_document_id: {_yaml_value(document.parent_document_id)}",
        f"source_role: {_yaml_value(document.source_role.value)}",
        f"source_format: {_yaml_value(document.source_format.value)}",
        f"source_sha256: {_yaml_value(source_hash)}",
        "derived: true",
        "---",
        "",
        f"# {document.package_id or Path(document.source_file).stem}",
        "",
        (
            f"> Nguồn dẫn xuất từ `{document.source_relative_path or document.source_file}`. "
            "Tệp Office gốc và JSON có cấu trúc là dữ liệu có thẩm quyền."
        ),
        "",
    ]

    index = 0
    while index < len(document.blocks):
        block = document.blocks[index]
        if block.kind is BlockKind.WORKSHEET:
            sheet_lines, index = _render_worksheet(document.blocks, index)
            lines.extend(sheet_lines)
            continue
        rendered = _render_block(block, asset_links)
        if rendered:
            lines.extend([rendered, ""])
        index += 1

    if document.footnotes:
        lines.extend(["## Chú thích", ""])
        for note_id, text in document.footnotes.items():
            lines.append(f"[^{note_id}]: {text}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _render_worksheet(
    blocks: list[DocumentBlock], start: int
) -> tuple[list[str], int]:
    worksheet = blocks[start]
    sheet = str(worksheet.metadata.get("sheet") or worksheet.text)
    lines = [f"## Trang tính {sheet}", ""]
    merged = worksheet.metadata.get("merged_ranges") or []
    validations = worksheet.metadata.get("data_validations") or []
    if merged:
        lines.extend([f"Vùng gộp: `{', '.join(str(value) for value in merged)}`", ""])
    if validations:
        lines.extend(["### Ràng buộc nhập liệu", ""])
        for validation in validations:
            ranges = validation.get("ranges")
            validation_type = validation.get("type") or "custom"
            formula = validation.get("formula1")
            suffix = f" — `{formula}`" if formula else ""
            lines.append(f"- `{ranges}`: {validation_type}{suffix}")
        lines.append("")

    rows: list[DocumentBlock] = []
    index = start + 1
    while index < len(blocks):
        candidate = blocks[index]
        if candidate.kind is BlockKind.WORKSHEET:
            break
        if candidate.metadata.get("sheet") != worksheet.metadata.get("sheet"):
            break
        if candidate.kind is BlockKind.TABLE and "cells" in candidate.metadata:
            rows.append(candidate)
            index += 1
            continue
        break

    if rows:
        lines.extend(
            [
                "| Hàng | Ô | Nội dung | Công thức | Định dạng |",
                "|---:|---|---|---|---|",
            ]
        )
        for row in rows:
            row_number = row.metadata.get("row")
            for cell in row.metadata.get("cells", []):
                value = cell.get("value", "")
                formula = cell.get("formula", "")
                lines.append(
                    "| {row} | `{coordinate}` | {value} | {formula} | `{number_format}` |".format(
                        row=row_number,
                        coordinate=_markdown_cell(cell.get("coordinate", "")),
                        value=_markdown_cell(value),
                        formula=_markdown_cell(formula),
                        number_format=_markdown_cell(cell.get("number_format", "")),
                    )
                )
        lines.append("")
    return lines, index


def _render_block(block: DocumentBlock, asset_links: dict[str, str]) -> str:
    if block.kind is BlockKind.PARAGRAPH:
        return _render_paragraph(block)
    if block.kind is BlockKind.TABLE and block.table is not None:
        return _render_table(block.table)
    if block.kind in {BlockKind.IMAGE, BlockKind.FORMULA, BlockKind.ATTACHMENT}:
        return _render_assets(block, asset_links)
    return block.text


def _render_paragraph(block: DocumentBlock) -> str:
    text = block.text.strip()
    if not text:
        return ""
    match = _LEGAL_HEADING.match(text)
    if match:
        heading_kind = match.group(1) or match.group(2)
        level = _HEADING_LEVEL[heading_kind.upper()]
        return f"{'#' * level} {text}"
    return text


def _render_table(table: TableData) -> str:
    cells_by_row: dict[int, list] = {}
    for cell in table.cells:
        cells_by_row.setdefault(cell.row, []).append(cell)
    rows = ["<table>"]
    for row_number in range(table.rows):
        rows.append("  <tr>")
        for cell in sorted(cells_by_row.get(row_number, []), key=lambda item: item.column):
            attributes = []
            if cell.row_span > 1:
                attributes.append(f'rowspan="{cell.row_span}"')
            if cell.column_span > 1:
                attributes.append(f'colspan="{cell.column_span}"')
            attribute_text = f" {' '.join(attributes)}" if attributes else ""
            value = cell.text
            for nested_table in cell.nested_tables:
                value = value.replace(nested_table.as_text(), "").strip()
            value = html.escape(value).replace("\n", "<br>")
            nested = "".join(_render_table(item) for item in cell.nested_tables)
            rows.append(f"    <td{attribute_text}>{value}{nested}</td>")
        rows.append("  </tr>")
    rows.append("</table>")
    return "\n".join(rows)


def _render_assets(block: DocumentBlock, asset_links: dict[str, str]) -> str:
    values = []
    for asset_id in block.asset_ids:
        link = asset_links.get(asset_id)
        if not link:
            values.append(block.text)
        elif block.kind in {BlockKind.IMAGE, BlockKind.FORMULA}:
            label = "Công thức" if block.kind is BlockKind.FORMULA else "Hình ảnh"
            values.append(f"![{label}]({link})")
        else:
            values.append(f"[Tệp đính kèm]({link})")
    return "\n".join(dict.fromkeys(values)) if values else block.text


def _write_assets(
    assets: list[EmbeddedAsset], asset_dir: Path, relative_dir: PurePosixPath
) -> dict[str, str]:
    links: dict[str, str] = {}
    if assets:
        asset_dir.mkdir(parents=True, exist_ok=True)
    for asset in assets:
        filename = f"{asset.asset_id}-{asset.safe_filename}"
        (asset_dir / filename).write_bytes(asset.data)
        links[asset.asset_id] = quote((relative_dir / filename).as_posix(), safe="/")
    return links


def _yaml_value(value: object) -> str:
    if value is None:
        return "null"
    return json.dumps(value, ensure_ascii=False)


def _markdown_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")
