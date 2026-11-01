from docx import Document

from backend.app.ingestion.docx_reader import extract_docx
from backend.app.ingestion.models import BlockKind


def test_merged_table_is_represented_without_duplicate_cells(tmp_path) -> None:
    path = tmp_path / "merged.docx"
    document = Document()
    table = document.add_table(rows=2, cols=3)
    table.cell(0, 0).text = "A"
    table.cell(0, 0).merge(table.cell(0, 1))
    table.cell(0, 2).text = "B"
    table.cell(0, 2).merge(table.cell(1, 2))
    table.cell(1, 0).text = "C"
    table.cell(1, 1).text = "D"
    document.save(path)

    extracted = extract_docx(path)
    table_block = next(block for block in extracted.blocks if block.kind is BlockKind.TABLE)

    assert table_block.table is not None
    assert table_block.table.has_merged_cells is True
    assert len(table_block.table.cells) == 4
    assert any(cell.column_span == 2 for cell in table_block.table.cells)
    assert any(cell.row_span == 2 for cell in table_block.table.cells)
