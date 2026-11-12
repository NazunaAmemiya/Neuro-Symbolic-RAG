from backend.app.ingestion.chunker import build_chunks
from backend.app.ingestion.models import (
    BlockKind,
    DocumentBlock,
    SourceDocument,
    TableCell,
    TableData,
)
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


def test_legal_chunks_cover_every_block_and_isolate_tables() -> None:
    document = SourceDocument(
        document_id="document-2",
        source_file="sample.docx",
        blocks=[
            DocumentBlock("article", BlockKind.PARAGRAPH, 1, "Điều 1. Quy định", "p:1"),
            DocumentBlock("intro", BlockKind.PARAGRAPH, 2, "Nội dung mở đầu.", "p:2"),
            DocumentBlock("clause", BlockKind.PARAGRAPH, 3, "1. Chi tiết:", "p:3"),
            DocumentBlock(
                "table",
                BlockKind.TABLE,
                4,
                "[BẢNG]\nA | B",
                "tbl:1",
                table=TableData(1, 2, [TableCell(1, 1, 1, 1, "A"), TableCell(1, 2, 1, 1, "B")], False),
            ),
        ],
    )
    root, _ = parse_hierarchy(document)
    chunks = build_chunks(document, root)

    covered = [block_id for chunk in chunks for block_id in chunk.block_ids]
    assert sorted(covered) == sorted(block.block_id for block in document.blocks)
    table_chunk = next(chunk for chunk in chunks if chunk.metadata["chunk_kind"] == "table")
    assert table_chunk.block_ids == ["clause", "table"]
    assert table_chunk.metadata["table"]["cells"][0]["text"] == "A"


def test_heading_only_leaf_is_covered() -> None:
    document = SourceDocument(
        document_id="document-3",
        source_file="sample.docx",
        lines=["Điều 1. Phạm vi điều chỉnh"],
    )
    root, _ = parse_hierarchy(document)
    chunks = build_chunks(document, root)

    assert len(chunks) == 1
    assert chunks[0].block_ids == [document.blocks[0].block_id]
    assert chunks[0].metadata["chunk_kind"] == "heading"
