from zipfile import ZipFile

from openpyxl import Workbook
from openpyxl.worksheet.datavalidation import DataValidation

from backend.app.ingestion.content_chunker import build_content_chunks
from backend.app.ingestion.models import BlockKind, SourceRole
from backend.app.ingestion.pipeline import prepare_entry_document
from backend.app.ingestion.source_catalog import build_source_catalog
from backend.app.ingestion.xlsx_reader import extract_xlsx


def _workbook(path) -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Bieu 01"
    sheet["A1"] = "BIỂU SỐ 01"
    sheet.merge_cells("A1:C1")
    sheet["A3"] = "Tổng giá gói thầu"
    sheet["B3"] = 100
    sheet["C3"] = "=B3*2"
    validation = DataValidation(type="list", formula1='"Có,Không"')
    sheet.add_data_validation(validation)
    validation.add(sheet["B4"])
    workbook.save(path)
    with ZipFile(path, "a") as package:
        package.writestr("xl/media/unreferenced-review-image.png", b"fixture-image")


def test_xlsx_reader_preserves_formula_merge_and_validation(tmp_path) -> None:
    path = tmp_path / "form.xlsx"
    _workbook(path)

    document = extract_xlsx(path)

    assert document.report.worksheet_count == 1
    assert document.report.formula_cell_count == 1
    assert document.report.merged_cell_count == 1
    assert document.report.data_validation_count == 1
    assert document.report.image_count == 1
    assert document.assets[0].package_path == "xl/media/unreferenced-review-image.png"
    sheet_block = next(block for block in document.blocks if block.kind is BlockKind.WORKSHEET)
    assert sheet_block.metadata["merged_ranges"] == ["A1:C1"]
    formula_block = next(block for block in document.blocks if "CÔNG THỨC" in block.text)
    formula_cell = next(
        cell for cell in formula_block.metadata["cells"] if cell["coordinate"] == "C3"
    )
    assert formula_cell["formula"] == "=B3*2"


def test_workbook_is_prepared_without_downstream_processing(tmp_path) -> None:
    root = tmp_path / "source_packages"
    package = root / "Bidding_Law" / "07_2024_TT-BKHDT"
    package.mkdir(parents=True)
    (package / "07_2024_TT-BKHDT.docx").write_bytes(b"primary-placeholder")
    workbook_path = package / "Mau bao cao.xlsx"
    _workbook(workbook_path)
    entry = next(
        entry
        for entry in build_source_catalog(root)
        if entry.role is SourceRole.FORM_WORKBOOK
    )

    document = prepare_entry_document(entry)

    assert document.package_id == "07_2024_TT-BKHDT"
    assert document.source_role is SourceRole.FORM_WORKBOOK
    assert document.source_relative_path == entry.relative_path

    chunks = build_content_chunks(document)
    assert chunks
    assert all(chunk.package_id == "07_2024_TT-BKHDT" for chunk in chunks)
    assert all(chunk.source_role is SourceRole.FORM_WORKBOOK for chunk in chunks)
    assert all(chunk.parent_document_id == entry.parent_document_id for chunk in chunks)
    formula_chunk = next(chunk for chunk in chunks if "C3" in chunk.display_text)
    assert "=B3*2" in formula_chunk.display_text
    payload = next(
        block
        for block in formula_chunk.metadata["blocks"]
        if block["block_id"] in formula_chunk.block_ids
    )
    assert next(cell for cell in payload["metadata"]["cells"] if cell["coordinate"] == "C3")[
        "formula"
    ] == "=B3*2"
