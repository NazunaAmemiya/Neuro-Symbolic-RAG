from __future__ import annotations

import posixpath
import re
import struct
from hashlib import sha256
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from lxml import etree

from .models import (
    AssetKind,
    BlockKind,
    DocumentBlock,
    EmbeddedAsset,
    ExtractionReport,
    IngestionIssue,
    InlineSpan,
    IssueSeverity,
    SourceDocument,
    TableCell,
    TableData,
    stable_id,
)

NS = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "ct": "http://schemas.openxmlformats.org/package/2006/content-types",
    "o": "urn:schemas-microsoft-com:office:office",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
}


def _q(prefix: str, local: str) -> str:
    return f"{{{NS[prefix]}}}{local}"


_FORMULA_CUE = re.compile(
    r"\b(công\s*thức|được\s+xác\s+định\s+như\s+sau|tính\s+theo)\b", re.IGNORECASE
)
_SUSPICIOUS_OPERATOR = re.compile(r"\b[A-Za-z]\s+[²³]\s*\d")


def extract_docx(path: Path) -> SourceDocument:
    """Read DOCX OOXML without flattening tables, media, footnotes, or run semantics."""

    source_bytes = path.read_bytes()
    document_id = stable_id("document", path.name, sha256(source_bytes).hexdigest())
    report = ExtractionReport()
    blocks: list[DocumentBlock] = []
    assets: list[EmbeddedAsset] = []

    with ZipFile(BytesIO(source_bytes)) as package:
        document_xml = etree.fromstring(package.read("word/document.xml"))
        relationships = _relationships(package, "word/_rels/document.xml.rels")
        content_types = _content_types(package)
        footnotes = _footnotes(package)
        body = document_xml.find("w:body", namespaces=NS)
        if body is None:
            raise ValueError(f"DOCX has no document body: {path.name}")

        order = 0
        previous_text = ""
        formula_budget = 0
        asset_keys: dict[tuple[str, AssetKind], EmbeddedAsset] = {}

        for body_index, element in enumerate(body, start=1):
            if element.tag == _q("w", "sectPr"):
                continue
            if element.tag == _q("w", "p"):
                report.paragraph_count += 1
                text, spans, footnote_ids = _paragraph_content(element)
                style_name = _paragraph_style(element)
                media = _media_descriptors(element)
                if _FORMULA_CUE.search(text):
                    formula_budget = 6

                order += 1
                paragraph_block_id = stable_id(document_id, "paragraph", str(body_index))
                if text or footnote_ids or not media:
                    blocks.append(
                        DocumentBlock(
                            block_id=paragraph_block_id,
                            kind=BlockKind.PARAGRAPH,
                            order=order,
                            text=text,
                            locator=f"word/document.xml#body[{body_index}]/p",
                            spans=spans,
                            footnote_ids=footnote_ids,
                            style_name=style_name,
                            is_bold=_is_bold_paragraph(spans),
                        )
                    )
                report.footnote_reference_count += len(footnote_ids)
                report.superscript_span_count += sum(span.superscript for span in spans)
                report.subscript_span_count += sum(span.subscript for span in spans)

                context = f"{previous_text}\n{text}".strip()
                media_blocks, new_assets = _materialize_media(
                    package=package,
                    descriptors=media,
                    relationships=relationships,
                    content_types=content_types,
                    document_id=document_id,
                    body_index=body_index,
                    start_order=order,
                    formula_candidate=bool(_FORMULA_CUE.search(context) or formula_budget > 0),
                    report=report,
                    asset_keys=asset_keys,
                )
                blocks.extend(media_blocks)
                assets.extend(new_assets)
                order += len(media_blocks)
                if media_blocks and formula_budget:
                    formula_budget -= 1
                elif text and not _FORMULA_CUE.search(text):
                    formula_budget = 0
                if text:
                    previous_text = text

                if _SUSPICIOUS_OPERATOR.search(text):
                    report.issues.append(
                        IngestionIssue(
                            code="suspicious_source_operator",
                            severity=IssueSeverity.WARNING,
                            message=(
                                "DOCX source contains a superscript digit where a mathematical "
                                "operator may have been intended; preserved without correction."
                            ),
                            locator=f"word/document.xml#body[{body_index}]/p",
                            block_id=paragraph_block_id,
                        )
                    )
            elif element.tag == _q("w", "tbl"):
                report.table_count += 1
                table = _table_data(element, report)
                order += 1
                table_block = DocumentBlock(
                    block_id=stable_id(document_id, "table", str(body_index)),
                    kind=BlockKind.TABLE,
                    order=order,
                    text=table.as_text(),
                    locator=f"word/document.xml#body[{body_index}]/tbl",
                    table=table,
                    footnote_ids=table.footnote_ids,
                )
                blocks.append(table_block)
                media_blocks, new_assets = _materialize_media(
                    package=package,
                    descriptors=_media_descriptors(element),
                    relationships=relationships,
                    content_types=content_types,
                    document_id=document_id,
                    body_index=body_index,
                    start_order=order,
                    formula_candidate=bool(_FORMULA_CUE.search(previous_text)),
                    report=report,
                    asset_keys=asset_keys,
                )
                table_block.asset_ids.extend(
                    asset_id for block in media_blocks for asset_id in block.asset_ids
                )
                blocks.extend(media_blocks)
                assets.extend(new_assets)
                order += len(media_blocks)
                previous_text = table.as_text()

    return SourceDocument(
        document_id=document_id,
        source_file=path.name,
        blocks=blocks,
        assets=assets,
        footnotes=footnotes,
        report=report,
    )


def _relationships(package: ZipFile, rels_path: str) -> dict[str, tuple[str, str | None]]:
    root = etree.fromstring(package.read(rels_path))
    result: dict[str, tuple[str, str | None]] = {}
    for relationship in root.findall("pr:Relationship", namespaces=NS):
        rel_id = relationship.get("Id")
        target = relationship.get("Target")
        if not rel_id or not target or relationship.get("TargetMode") == "External":
            continue
        package_path = posixpath.normpath(posixpath.join("word", target))
        result[rel_id] = (package_path, relationship.get("Type"))
    return result


def _content_types(package: ZipFile) -> dict[str, str]:
    root = etree.fromstring(package.read("[Content_Types].xml"))
    defaults = {
        item.get("Extension", "").casefold(): item.get("ContentType", "")
        for item in root.findall("ct:Default", namespaces=NS)
    }
    overrides = {
        item.get("PartName", "").lstrip("/"): item.get("ContentType", "")
        for item in root.findall("ct:Override", namespaces=NS)
    }
    result = dict(overrides)
    for name in package.namelist():
        result.setdefault(name, defaults.get(PurePosixPath(name).suffix.lstrip(".").casefold(), ""))
    return result


def _footnotes(package: ZipFile) -> dict[str, str]:
    if "word/footnotes.xml" not in package.namelist():
        return {}
    root = etree.fromstring(package.read("word/footnotes.xml"))
    result: dict[str, str] = {}
    for note in root.findall("w:footnote", namespaces=NS):
        note_id = note.get(_q("w", "id"))
        if note_id is None or note_id.startswith("-"):
            continue
        paragraphs = [_paragraph_content(p)[0] for p in note.findall("w:p", namespaces=NS)]
        result[note_id] = "\n".join(text for text in paragraphs if text).strip()
    return result


def _paragraph_content(element: etree._Element) -> tuple[str, list[InlineSpan], list[str]]:
    spans: list[InlineSpan] = []
    footnotes: list[str] = []
    pieces: list[str] = []
    for run in element.iter(_q("w", "r")):
        run_properties = run.find("w:rPr", namespaces=NS)
        bold = _on(run_properties, "b")
        italic = _on(run_properties, "i")
        vertical = None
        if run_properties is not None:
            vertical_element = run_properties.find("w:vertAlign", namespaces=NS)
            if vertical_element is not None:
                vertical = vertical_element.get(_q("w", "val"))
        run_pieces: list[str] = []
        for child in run.iterchildren():
            if child.tag in {_q("w", "t"), _q("w", "instrText")}:
                run_pieces.append(child.text or "")
            elif child.tag == _q("w", "tab"):
                run_pieces.append("\t")
            elif child.tag in {_q("w", "br"), _q("w", "cr")}:
                run_pieces.append("\n")
            elif child.tag == _q("w", "footnoteReference"):
                note_id = child.get(_q("w", "id"), "")
                if note_id:
                    footnotes.append(note_id)
                    run_pieces.append(f"[^{note_id}]")
        run_text = "".join(run_pieces)
        if run_text:
            spans.append(
                InlineSpan(
                    text=run_text,
                    bold=bold,
                    italic=italic,
                    superscript=vertical == "superscript",
                    subscript=vertical == "subscript",
                )
            )
            pieces.append(run_text)
    return "".join(pieces), spans, footnotes


def _on(properties: etree._Element | None, local_name: str) -> bool:
    if properties is None:
        return False
    element = properties.find(f"w:{local_name}", namespaces=NS)
    if element is None:
        return False
    return element.get(_q("w", "val"), "true").casefold() not in {"false", "0", "off"}


def _paragraph_style(element: etree._Element) -> str | None:
    style = element.find("w:pPr/w:pStyle", namespaces=NS)
    return style.get(_q("w", "val")) if style is not None else None


def _is_bold_paragraph(spans: list[InlineSpan]) -> bool:
    visible = [span for span in spans if span.text.strip()]
    return bool(visible) and all(span.bold for span in visible)


def _media_descriptors(element: etree._Element) -> list[dict[str, str]]:
    descriptors: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for descendant in element.iter():
        if descendant.tag == _q("a", "blip"):
            rel_id = descendant.get(_q("r", "embed"))
            descriptor = {"relationship_id": rel_id or "", "type": "image"}
        elif descendant.tag == _q("v", "imagedata"):
            rel_id = descendant.get(_q("r", "id"))
            descriptor = {"relationship_id": rel_id or "", "type": "image"}
        elif descendant.tag == _q("o", "OLEObject"):
            rel_id = descendant.get(_q("r", "id"))
            descriptor = {
                "relationship_id": rel_id or "",
                "type": "ole",
                "prog_id": descendant.get("ProgID", ""),
                "draw_aspect": descendant.get("DrawAspect", ""),
            }
        else:
            continue
        key = (descriptor["relationship_id"], descriptor["type"])
        if descriptor["relationship_id"] and key not in seen:
            descriptors.append(descriptor)
            seen.add(key)
    return descriptors


def _materialize_media(
    *,
    package: ZipFile,
    descriptors: list[dict[str, str]],
    relationships: dict[str, tuple[str, str | None]],
    content_types: dict[str, str],
    document_id: str,
    body_index: int,
    start_order: int,
    formula_candidate: bool,
    report: ExtractionReport,
    asset_keys: dict[tuple[str, AssetKind], EmbeddedAsset],
) -> tuple[list[DocumentBlock], list[EmbeddedAsset]]:
    blocks: list[DocumentBlock] = []
    new_assets: list[EmbeddedAsset] = []
    for offset, descriptor in enumerate(descriptors, start=1):
        rel_id = descriptor["relationship_id"]
        relationship = relationships.get(rel_id)
        if relationship is None:
            report.issues.append(
                IngestionIssue(
                    code="missing_relationship",
                    severity=IssueSeverity.ERROR,
                    message=f"Relationship {rel_id} cannot be resolved.",
                    locator=f"word/document.xml#body[{body_index}]",
                )
            )
            continue
        package_path, _ = relationship
        if package_path not in package.namelist():
            continue
        data = package.read(package_path)
        content_type = content_types.get(package_path) or None
        is_package = descriptor["type"] == "ole" and descriptor.get("prog_id") == "Package"
        if descriptor["type"] == "image":
            kind = AssetKind.FORMULA_IMAGE if formula_candidate else AssetKind.IMAGE
        elif is_package:
            kind = AssetKind.ATTACHMENT
        else:
            kind = AssetKind.OLE_OBJECT

        key = (rel_id, kind)
        asset = asset_keys.get(key)
        if asset is None:
            filename = PurePosixPath(package_path).name
            asset = EmbeddedAsset(
                asset_id=stable_id(document_id, "asset", rel_id, kind.value),
                kind=kind,
                package_path=package_path,
                content_type=content_type,
                filename=filename,
                relationship_id=rel_id,
                data=data,
                metadata={
                    key: value
                    for key, value in descriptor.items()
                    if key not in {"relationship_id", "type"}
                },
            )
            asset_keys[key] = asset
            new_assets.append(asset)
            if kind is AssetKind.FORMULA_IMAGE:
                report.formula_image_count += 1
                report.issues.append(
                    IngestionIssue(
                        code="formula_image_requires_transcription",
                        severity=IssueSeverity.WARNING,
                        message=(
                            "Formula is stored as an image. The image was preserved; a reviewed "
                            "transcription is required before its text is used for retrieval."
                        ),
                        locator=f"word/document.xml#body[{body_index}]",
                    )
                )
            elif kind is AssetKind.IMAGE:
                report.image_count += 1
            elif kind is AssetKind.ATTACHMENT:
                report.attachment_count += 1
                _extract_native_attachment(asset, document_id, new_assets, report)
            else:
                report.ole_object_count += 1

        if kind is AssetKind.FORMULA_IMAGE:
            block_kind = BlockKind.FORMULA
            text = f"[CÔNG THỨC DẠNG ẢNH: {asset.asset_id}]"
        elif kind is AssetKind.IMAGE:
            block_kind = BlockKind.IMAGE
            text = f"[HÌNH ẢNH: {asset.asset_id}]"
        else:
            block_kind = BlockKind.ATTACHMENT
            text = f"[TỆP ĐÍNH KÈM: {asset.safe_filename}]"
        blocks.append(
            DocumentBlock(
                block_id=stable_id(document_id, "media", str(body_index), str(offset), asset.asset_id),
                kind=block_kind,
                order=start_order + len(blocks) + 1,
                text=text,
                locator=f"word/document.xml#body[{body_index}]/media[{offset}]",
                asset_ids=[asset.asset_id],
                metadata={"relationship_id": rel_id},
            )
        )
    return blocks, new_assets


def _extract_native_attachment(
    ole_asset: EmbeddedAsset,
    document_id: str,
    new_assets: list[EmbeddedAsset],
    report: ExtractionReport,
) -> None:
    try:
        import olefile
    except ImportError:
        report.issues.append(
            IngestionIssue(
                code="olefile_dependency_missing",
                severity=IssueSeverity.WARNING,
                message="OLE package was preserved but its native payload was not unpacked.",
            )
        )
        return
    try:
        ole = olefile.OleFileIO(BytesIO(ole_asset.data))
        stream_name = next(
            (parts for parts in ole.listdir() if parts and parts[-1] == "\x01Ole10Native"), None
        )
        if stream_name is None:
            return
        native = ole.openstream(stream_name).read()
        filename, payload = _parse_ole10native(native)
        if not payload:
            return
        suffix = PurePosixPath(filename).suffix.casefold()
        content_type = {
            ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".pdf": "application/pdf",
        }.get(suffix, "application/octet-stream")
        child = EmbeddedAsset(
            asset_id=stable_id(document_id, "attachment", ole_asset.asset_id, filename),
            kind=AssetKind.ATTACHMENT,
            package_path=f"{ole_asset.package_path}#Ole10Native",
            content_type=content_type,
            filename=filename,
            relationship_id=ole_asset.relationship_id,
            data=payload,
            parent_asset_id=ole_asset.asset_id,
        )
        new_assets.append(child)
        report.issues.append(
            IngestionIssue(
                code="embedded_attachment_extracted",
                severity=IssueSeverity.INFO,
                message=f"Extracted embedded attachment {filename}; recursive ingest is pending.",
            )
        )
    except (OSError, ValueError, struct.error) as exc:
        report.issues.append(
            IngestionIssue(
                code="embedded_attachment_unpack_failed",
                severity=IssueSeverity.WARNING,
                message=f"OLE package was preserved but could not be unpacked: {exc}",
            )
        )


def _parse_ole10native(data: bytes) -> tuple[str, bytes]:
    def read_c_string(position: int) -> tuple[str, int]:
        end = data.find(b"\x00", position)
        if end < 0:
            raise ValueError("unterminated Ole10Native string")
        raw = data[position:end]
        return raw.decode("cp1252", errors="replace"), end + 1

    # Some producers include a two-byte flags field after the total size; try both layouts.
    for position in (6, 4):
        try:
            filename, position = read_c_string(position)
            _, position = read_c_string(position)
            position += 8
            _, position = read_c_string(position)
            payload_size = struct.unpack_from("<I", data, position)[0]
            position += 4
            payload = data[position : position + payload_size]
            if filename and payload_size and len(payload) == payload_size:
                return PurePosixPath(filename.replace("\\", "/")).name, payload
        except (ValueError, struct.error):
            continue
    raise ValueError("unsupported Ole10Native layout")


def _table_data(table_element: etree._Element, report: ExtractionReport) -> TableData:
    rows = table_element.findall("w:tr", namespaces=NS)
    cells: list[TableCell] = []
    active_vertical: dict[int, TableCell] = {}
    max_columns = 0
    has_merged = False
    table_footnotes: list[str] = []

    for row_index, row in enumerate(rows):
        column = 0
        continued_columns: set[int] = set()
        for tc in row.findall("w:tc", namespaces=NS):
            grid_span_element = tc.find("w:tcPr/w:gridSpan", namespaces=NS)
            column_span = int(grid_span_element.get(_q("w", "val"), "1")) if grid_span_element is not None else 1
            vertical_element = tc.find("w:tcPr/w:vMerge", namespaces=NS)
            vertical_value = (
                vertical_element.get(_q("w", "val"), "continue")
                if vertical_element is not None
                else None
            )
            paragraphs = tc.findall("w:p", namespaces=NS)
            paragraph_parts: list[str] = []
            cell_spans: list[InlineSpan] = []
            for paragraph in paragraphs:
                paragraph_text, spans, footnote_ids = _paragraph_content(paragraph)
                if paragraph_text:
                    paragraph_parts.append(paragraph_text)
                cell_spans.extend(spans)
                table_footnotes.extend(footnote_ids)
                report.paragraph_count += 1
                report.footnote_reference_count += len(footnote_ids)
                report.superscript_span_count += sum(span.superscript for span in spans)
                report.subscript_span_count += sum(span.subscript for span in spans)
            nested_tables: list[TableData] = []
            for nested_element in tc.findall("w:tbl", namespaces=NS):
                report.table_count += 1
                nested = _table_data(nested_element, report)
                nested_tables.append(nested)
                paragraph_parts.append(nested.as_text())
                table_footnotes.extend(nested.footnote_ids)
            text = "\n".join(paragraph_parts).strip()

            if vertical_value == "continue" and column in active_vertical:
                origin = active_vertical[column]
                origin.row_span += 1
                if text and text not in origin.text:
                    origin.text = "\n".join(value for value in (origin.text, text) if value)
                    origin.spans.extend(cell_spans)
                    origin.nested_tables.extend(nested_tables)
                continued_columns.update(range(column, column + column_span))
                has_merged = True
                report.merged_cell_count += 1
            else:
                cell = TableCell(
                    row=row_index,
                    column=column,
                    row_span=1,
                    column_span=column_span,
                    text=text,
                    spans=cell_spans,
                    nested_tables=nested_tables,
                )
                cells.append(cell)
                if vertical_value == "restart":
                    for occupied in range(column, column + column_span):
                        active_vertical[occupied] = cell
                if column_span > 1 or vertical_value == "restart":
                    has_merged = True
                    report.merged_cell_count += 1
            column += column_span
        for active_column in tuple(active_vertical):
            if active_column not in continued_columns and active_vertical[active_column].row < row_index:
                del active_vertical[active_column]
        max_columns = max(max_columns, column)

    return TableData(
        rows=len(rows),
        columns=max_columns,
        cells=cells,
        has_merged_cells=has_merged,
        footnote_ids=list(dict.fromkeys(table_footnotes)),
    )
