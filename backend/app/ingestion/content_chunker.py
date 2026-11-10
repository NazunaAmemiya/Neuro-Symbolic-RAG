from __future__ import annotations

from .models import ContentChunk, DocumentBlock, SourceDocument, stable_id


def build_content_chunks(
    document: SourceDocument, max_characters: int = 4000
) -> list[ContentChunk]:
    """Chunk appendices and forms without pretending that they are legal provisions."""

    chunks: list[ContentChunk] = []
    pending: list[DocumentBlock] = []
    pending_size = 0
    current_sheet: str | None = None

    def flush() -> None:
        nonlocal pending, pending_size
        if not pending:
            return
        text = "\n".join(block.text for block in pending if block.text).strip()
        start = pending[0].order
        end = pending[-1].order
        block_ids = [block.block_id for block in pending]
        asset_ids = list(
            dict.fromkeys(asset_id for block in pending for asset_id in block.asset_ids)
        )
        role_label = document.source_role.value
        package_context = (
            f"Văn bản cha: {document.parent_document_id}\n"
            if document.parent_document_id
            else ""
        )
        embedding_text = f"{package_context}Loại nguồn: {role_label}\n{text}".strip()
        chunks.append(
            ContentChunk(
                chunk_id=stable_id(document.document_id, "content-chunk", str(start), str(end)),
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
                metadata={"sheet": current_sheet} if current_sheet else {},
            )
        )
        pending = []
        pending_size = 0

    for block in document.blocks:
        sheet = block.metadata.get("sheet")
        if sheet and str(sheet) != current_sheet:
            flush()
            current_sheet = str(sheet)
        block_size = len(block.text)
        if pending and pending_size + block_size > max_characters:
            flush()
        pending.append(block)
        pending_size += block_size
    flush()
    return chunks
