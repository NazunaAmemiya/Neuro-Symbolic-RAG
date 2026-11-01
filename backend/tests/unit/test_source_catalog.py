from pathlib import Path

import pytest

from backend.app.ingestion.models import SourceFormat, SourceRole
from backend.app.ingestion.source_catalog import CorpusCatalogError, build_source_catalog


def _write(path: Path, value: bytes = b"fixture") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(value)
    return path


def test_catalog_preserves_package_identity_for_duplicate_form_names(tmp_path) -> None:
    root = tmp_path / "source_packages"
    _write(root / "Bidding_Law" / "07_2024_TT-BKHDT" / "07_2024_TT-BKHDT.doc")
    _write(
        root
        / "Bidding_Law"
        / "07_2024_TT-BKHDT"
        / "04.1A. Mẫu Kế hoạch kiểm tra định kỳ.doc",
        b"version-07",
    )
    _write(root / "Bidding_Law" / "80_2025_TT-BTC" / "80_2025_TT-BTC.docx")
    _write(
        root
        / "Bidding_Law"
        / "80_2025_TT-BTC"
        / "04.1A. Mẫu Kế hoạch kiểm tra định kỳ.doc",
        b"version-80",
    )
    _write(root / "Bidding_Law" / "80_2025_TT-BTC" / "Bảng biểu.xlsx")
    _write(root / "Bidding_Law" / "80_2025_TT-BTC" / "~$Bảng biểu.xlsx")
    _write(root / "Bidding_Law" / "80_2025_TT-BTC" / "generated.md")
    _write(root / "Bidding_Law" / "90_2025_QH15.docx")

    entries = build_source_catalog(root)

    assert len(entries) == 6
    primaries = [entry for entry in entries if entry.role is SourceRole.PRIMARY_LEGAL_DOCUMENT]
    assert len(primaries) == 3
    forms = [entry for entry in entries if entry.role is SourceRole.FORM_DOCUMENT]
    assert len(forms) == 2
    assert forms[0].source_id != forms[1].source_id
    assert forms[0].parent_document_id != forms[1].parent_document_id
    workbook = next(entry for entry in entries if entry.role is SourceRole.FORM_WORKBOOK)
    assert workbook.source_format is SourceFormat.XLSX
    assert workbook.package_id == "80_2025_TT-BTC"


def test_catalog_accepts_corpus_directory_as_root(tmp_path) -> None:
    root = tmp_path / "Bidding_Law"
    _write(root / "01_2024_TT-BKHDT" / "01_2024_TT-BKHĐT.docx")
    _write(root / "01_2024_TT-BKHDT" / "Phu luc.doc")

    entries = build_source_catalog(root)

    assert {entry.role for entry in entries} == {
        SourceRole.PRIMARY_LEGAL_DOCUMENT,
        SourceRole.APPENDIX,
    }


def test_catalog_rejects_package_without_primary_document(tmp_path) -> None:
    root = tmp_path / "source_packages"
    _write(root / "Bidding_Law" / "07_2024_TT-BKHDT" / "Mau 01.doc")

    with pytest.raises(CorpusCatalogError, match="0 primary candidates"):
        build_source_catalog(root)
