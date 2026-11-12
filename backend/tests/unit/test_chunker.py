from backend.app.ingestion.chunker import build_chunks
from backend.app.ingestion.models import SourceDocument
from backend.app.ingestion.parser import parse_hierarchy


def test_point_chunks_include_parent_preamble() -> None:
    document = SourceDocument(
        document_id="document-1",
        source_file="sample.md",
        lines=[
            "Điều 1. Phạm vi điều chỉnh",
            "1. Điều này quy định:",
            "a) Nội dung thứ nhất.",
            "b) Nội dung thứ hai.",
        ],
    )
    root, issues = parse_hierarchy(document)
    chunks = build_chunks(document, root)

    assert not [issue for issue in issues if issue.severity.value == "error"]
    assert len(chunks) == 2
    assert chunks[0].display_text == "Nội dung thứ nhất."
    assert "Điều 1" in chunks[0].embedding_text
    assert "Khoản 1" in chunks[0].embedding_text
