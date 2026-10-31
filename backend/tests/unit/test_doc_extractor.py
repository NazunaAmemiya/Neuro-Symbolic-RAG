from docx import Document

from backend.app.ingestion import extractors
from backend.app.ingestion.models import SourceFormat


def test_doc_extractor_uses_materialized_docx_and_keeps_original_identity(
    tmp_path, monkeypatch
) -> None:
    source = tmp_path / "legacy.doc"
    source.write_bytes(b"legacy-binary")
    converted = tmp_path / "converted.docx"
    document = Document()
    document.add_paragraph("Nội dung biểu mẫu")
    document.save(converted)

    monkeypatch.setattr(
        extractors,
        "convert_doc_to_docx",
        lambda source_path, output_root, source_hash: converted,
    )

    extracted = extractors.extract_document(source, conversion_dir=tmp_path / "derived")

    assert extracted.source_file == "legacy.doc"
    assert extracted.source_format is SourceFormat.DOC
    assert extracted.metadata["converted_docx"] == "converted.docx"
    assert any(block.text == "Nội dung biểu mẫu" for block in extracted.blocks)
