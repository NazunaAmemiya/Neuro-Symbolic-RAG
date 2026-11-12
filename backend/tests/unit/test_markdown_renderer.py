from backend.app.ingestion.markdown_renderer import render_markdown, write_markdown_view
from backend.app.ingestion.models import (
    AssetKind,
    BlockKind,
    DocumentBlock,
    EmbeddedAsset,
    SourceDocument,
    SourceFormat,
    SourceRole,
    TableCell,
    TableData,
)


def test_markdown_view_uses_portable_paths_and_copies_assets(tmp_path) -> None:
    asset = EmbeddedAsset(
        asset_id="image-1",
        kind=AssetKind.IMAGE,
        package_path="xl/media/image1.png",
        content_type="image/png",
        filename="image 1.png",
        relationship_id=None,
        data=b"image-bytes",
    )
    document = SourceDocument(
        document_id="source-1",
        source_file="form.xlsx",
        source_relative_path="Bidding_Law/07_2024_TT-BKHDT/form.xlsx",
        package_id="07_2024_TT-BKHDT",
        parent_document_id="primary-1",
        source_role=SourceRole.FORM_WORKBOOK,
        source_format=SourceFormat.XLSX,
        metadata={"source_hash": "abc123"},
        assets=[asset],
        blocks=[
            DocumentBlock(
                block_id="sheet-1",
                kind=BlockKind.WORKSHEET,
                order=1,
                text="[TRANG TÍNH] Bieu 01",
                locator="workbook/sheet[1]",
                metadata={
                    "sheet": "Bieu 01",
                    "sheet_index": 1,
                    "merged_ranges": ["A1:C1"],
                    "data_validations": [
                        {"ranges": "B4", "type": "list", "formula1": '"Có,Không"'}
                    ],
                },
            ),
            DocumentBlock(
                block_id="row-1",
                kind=BlockKind.TABLE,
                order=2,
                text="A1: BIỂU SỐ 01 | [CÔNG THỨC: C1]",
                locator="workbook/sheet[1]/row[1]",
                metadata={
                    "sheet": "Bieu 01",
                    "row": 1,
                    "cells": [
                        {
                            "coordinate": "A1",
                            "value": "BIỂU SỐ 01",
                            "number_format": "General",
                        },
                        {
                            "coordinate": "C1",
                            "formula": "=SUM(A1:B1)",
                            "cached_value": 42,
                            "number_format": "0",
                        },
                    ],
                },
            ),
            DocumentBlock(
                block_id="image-block",
                kind=BlockKind.IMAGE,
                order=3,
                text="[HÌNH ẢNH]",
                locator="xl/media/image1.png",
                asset_ids=["image-1"],
            ),
        ],
    )

    path = write_markdown_view(document, tmp_path / "markdown")
    content = path.read_text(encoding="utf-8")

    assert path.relative_to(tmp_path / "markdown").as_posix() == (
        "Bidding_Law/07_2024_TT-BKHDT/form.xlsx.md"
    )
    assert "source_path: \"Bidding_Law/07_2024_TT-BKHDT/form.xlsx\"" in content
    assert str(tmp_path) not in content
    assert "=SUM(A1:B1)" in content
    assert "| 42 | `0` |" in content
    assert "_assets/source-1/image-1-image%201.png" in content
    assert (
        path.parent / "_assets" / "source-1" / "image-1-image 1.png"
    ).read_bytes() == b"image-bytes"


def test_markdown_table_preserves_row_and_column_spans() -> None:
    table = TableData(
        rows=2,
        columns=2,
        has_merged_cells=True,
        cells=[TableCell(row=0, column=0, row_span=2, column_span=2, text="Nội dung")],
    )
    document = SourceDocument(
        document_id="source-2",
        source_file="form.docx",
        blocks=[
            DocumentBlock(
                block_id="table-1",
                kind=BlockKind.TABLE,
                order=1,
                text="Nội dung",
                locator="word/document.xml#table[1]",
                table=table,
            )
        ],
    )

    content = render_markdown(document)

    assert 'rowspan="2"' in content
    assert 'colspan="2"' in content
