from __future__ import annotations

from dataclasses import asdict

from .models import BlockKind, ContentChunk, DocumentBlock, SourceDocument, stable_id

_STANDALONE_KINDS = {BlockKind.TABLE, BlockKind.FORMULA}


def build_content_chunks(
    document: SourceDocument, max_characters: int = 4000
) -> list[ContentChunk]:
    """Chunk appendices/forms with exact block, table, formula, and parent coverage."""

    chunks: list[ContentChunk] = []
    pending: list[DocumentBlock] = []
    pending_size = 0
    current_sheet: str | None = None

    def flush(chunk_kind: str = "content_window") -> None:
        nonlocal pending, pending_size
        if not pending:
            return
        chunks.append(_make_chunk(document, pending, current_sheet, chunk_kind))
        pending = []
        pending_size = 0

    for block in document.blocks:
        sheet = block.metadata.get("sheet")
        if sheet and str(sheet) != current_sheet:
            flush()
            current_sheet = str(sheet)
        if block.kind in _STANDALONE_KINDS:
            flush()
            pending = [block]
            pending_size = len(block.text)
            flush(block.kind.value)
            continue
        block_size = len(_chunk_text(block))
        if pending and pending_size + block_size > max_characters:
            flush()
        pending.append(block)
        pending_size += block_size
    flush()
    return chunks


def _make_chunk(
    document: SourceDocument,
    blocks: list[DocumentBlock],
    sheet: str | None,
    chunk_kind: str,
) -> ContentChunk:
    rendered = [_chunk_text(block) for block in blocks]
    text = "\n".join(value for value in rendered if value).strip()
    start = blocks[0].order
    end = blocks[-1].order
    block_ids = [block.block_id for block in blocks]
    asset_ids = list(dict.fromkeys(asset_id for block in blocks for asset_id in block.asset_ids))
    role_label = document.source_role.value
    package_context = f"Văn bản cha: {document.parent_document_id}\n" if document.parent_document_id else ""
    embedding_text = f"{package_context}Loại nguồn: {role_label}\n{text}".strip()
    metadata: dict[str, object] = {
        "content_kind": chunk_kind,
        "blocks": [_block_payload(block) for block in blocks],
    }
    if sheet:
        metadata["sheet"] = sheet
    return ContentChunk(
        chunk_id=stable_id(document.document_id, "content-chunk", str(start), str(end), chunk_kind),
        document_id=document.document_id,
        package_id=document.package_id,
        parent_document_id=document.parent_document_id,
        source_role=document.source_role,
        display_text=text,
        embedding_text=embedding_text,
        block_ids=block_ids,
        asset_ids=asset_ids,
        source_file=document.source_file,
        source_start_order=start,
        source_end_order=end,
        metadata=metadata,
    )


def _chunk_text(block: DocumentBlock) -> str:
    text = block.text
    if block.kind in {BlockKind.WORKSHEET, BlockKind.TABLE}:
        formula_lines = []
        for cell in block.metadata.get("cells", []):
            if not isinstance(cell, dict) or not cell.get("formula"):
                continue
            cached = cell.get("cached_value")
            suffix = f"; kết quả lưu sẵn: {cached}" if cached is not None else ""
            formula_lines.append(f"{cell.get('coordinate')}: {cell['formula']}{suffix}")
        if formula_lines:
            text = "\n".join([text, "[BIỂU THỨC EXCEL]", *formula_lines])
    return text.strip()


def _block_payload(block: DocumentBlock) -> dict[str, object]:
    payload: dict[str, object] = {
        "block_id": block.block_id,
        "kind": block.kind.value,
        "locator": block.locator,
        "metadata": dict(block.metadata),
    }
    if block.table is not None:
        payload["table"] = asdict(block.table)
    return payload
