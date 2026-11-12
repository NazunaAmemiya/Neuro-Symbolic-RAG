from __future__ import annotations

from dataclasses import asdict

from .models import (
    BlockKind,
    DocumentBlock,
    LegalChunk,
    LegalNode,
    NodeKind,
    ProvisionScope,
    SourceDocument,
    stable_id,
)

_STANDALONE_KINDS = {BlockKind.TABLE, BlockKind.FORMULA}


def build_chunks(document: SourceDocument, root: LegalNode) -> list[LegalChunk]:
    """Create lossless legal chunks while retaining legal hierarchy context."""

    chunks: list[LegalChunk] = []
    _visit(document, root, [], {}, chunks)
    return chunks


def _visit(
    document: SourceDocument,
    node: LegalNode,
    ancestors: list[LegalNode],
    labels: dict[str, str],
    chunks: list[LegalChunk],
) -> None:
    next_labels = dict(labels)
    if node.kind is not NodeKind.DOCUMENT:
        key = node.kind.value
        if node.scope is ProvisionScope.AMENDED:
            key = f"amended_{key}"
        next_labels[key] = node.label

    first_chunk = len(chunks)
    block_map = document.block_map()
    owned = [block_map[block_id] for block_id in node.body_block_ids if block_id in block_map]
    ordinary = [block for block in owned if block.kind not in _STANDALONE_KINDS]
    if ordinary:
        chunks.append(_make_chunk(document, node, ancestors, next_labels, ordinary, "text"))
    for block in owned:
        if block.kind in _STANDALONE_KINDS:
            chunks.append(
                _make_chunk(
                    document,
                    node,
                    ancestors,
                    next_labels,
                    [block],
                    block.kind.value,
                )
            )

    for child in node.children:
        _visit(document, child, [*ancestors, node], next_labels, chunks)

    if node.heading_block_id:
        heading = block_map.get(node.heading_block_id)
        if len(chunks) == first_chunk:
            if heading is not None:
                heading_chunk = _make_chunk(
                    document, node, ancestors, next_labels, [], "heading"
                )
                heading_chunk.block_ids.append(node.heading_block_id)
                heading_chunk.source_start_order = heading.order
                heading_chunk.source_end_order = heading.order
                heading_chunk.metadata["block_kinds"] = [heading.kind.value]
                heading_chunk.metadata["source_locators"] = [heading.locator]
                chunks.append(heading_chunk)
        else:
            target = chunks[first_chunk]
            if node.heading_block_id not in target.block_ids:
                target.block_ids.insert(0, node.heading_block_id)
            if heading is not None:
                target.source_start_order = min(target.source_start_order, heading.order)


def _make_chunk(
    document: SourceDocument,
    node: LegalNode,
    ancestors: list[LegalNode],
    labels: dict[str, str],
    blocks: list[DocumentBlock],
    chunk_kind: str,
) -> LegalChunk:
    parent_nodes = [ancestor for ancestor in ancestors if ancestor.kind is not NodeKind.DOCUMENT]
    block_text = "\n".join(block.text for block in blocks if block.text).strip()
    candidates = [block_text]
    if node.kind is not NodeKind.DOCUMENT:
        candidates.insert(0, node.title)
    display_text = "\n".join(value for value in candidates if value).strip()
    if chunk_kind == "heading" and not display_text:
        display_text = node.label
    preamble = [_node_preamble(ancestor) for ancestor in parent_nodes]
    scope_note = (
        "[NỘI DUNG ĐƯỢC TRÍCH DẪN/SỬA ĐỔI]"
        if node.scope is ProvisionScope.AMENDED
        else ""
    )
    embedding_text = "\n".join(
        value for value in [*preamble, scope_note, display_text] if value
    ).strip()
    asset_ids = list(dict.fromkeys(asset_id for block in blocks for asset_id in block.asset_ids))
    orders = [block.order for block in blocks] or [node.start_order]
    metadata: dict[str, object] = {
        "chunk_kind": chunk_kind,
        "block_kinds": [block.kind.value for block in blocks],
        "source_locators": [block.locator for block in blocks],
    }
    if len(blocks) == 1 and blocks[0].kind is BlockKind.TABLE and blocks[0].table:
        metadata["table"] = asdict(blocks[0].table)
    if len(blocks) == 1 and blocks[0].kind is BlockKind.FORMULA:
        metadata["formula"] = dict(blocks[0].metadata)
    return LegalChunk(
        chunk_id=stable_id(
            document.document_id,
            "chunk",
            node.node_id,
            chunk_kind,
            ",".join(block.block_id for block in blocks),
        ),
        document_id=document.document_id,
        node_id=node.node_id,
        level=node.kind,
        scope=node.scope,
        labels=dict(labels),
        display_text=display_text,
        embedding_text=embedding_text,
        parent_ids=[ancestor.node_id for ancestor in parent_nodes],
        block_ids=[block.block_id for block in blocks],
        asset_ids=asset_ids,
        source_file=document.source_file,
        source_start_order=min(orders),
        source_end_order=max(orders),
        metadata=metadata,
    )


def _node_preamble(node: LegalNode) -> str:
    legal_labels = {
        NodeKind.ARTICLE: "Điều",
        NodeKind.CLAUSE: "Khoản",
        NodeKind.POINT: "Điểm",
    }
    scope = " (nội dung sửa đổi/trích dẫn)" if node.scope is ProvisionScope.AMENDED else ""
    label = legal_labels.get(node.kind, node.kind.value.title())
    title = f": {node.title}" if node.title else ""
    return f"{label} {node.label}{scope}{title}".strip()
