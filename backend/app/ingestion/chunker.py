from __future__ import annotations

from .models import LegalChunk, LegalNode, NodeKind, ProvisionScope, SourceDocument, stable_id

_CHUNK_LEVELS = {NodeKind.ARTICLE, NodeKind.CLAUSE, NodeKind.POINT, NodeKind.APPENDIX}


def build_chunks(document: SourceDocument, root: LegalNode) -> list[LegalChunk]:
    """Create provision chunks with parent, table, formula, asset, and footnote context."""

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

    if _should_chunk(node):
        display_text, asset_ids = _node_content(document, node)
        parent_nodes = [ancestor for ancestor in ancestors if ancestor.kind is not NodeKind.DOCUMENT]
        preamble = [
            _node_preamble(document, ancestor)
            for ancestor in parent_nodes
            if ancestor.kind in {NodeKind.ARTICLE, NodeKind.CLAUSE}
        ]
        scope_note = (
            "[NỘI DUNG ĐƯỢC TRÍCH DẪN/SỬA ĐỔI]"
            if node.scope is ProvisionScope.AMENDED
            else ""
        )
        embedding_text = "\n".join(
            value for value in [*preamble, scope_note, display_text] if value
        ).strip()
        chunks.append(
            LegalChunk(
                chunk_id=stable_id(document.document_id, "chunk", node.node_id),
                document_id=document.document_id,
                node_id=node.node_id,
                level=node.kind,
                scope=node.scope,
                labels=next_labels,
                display_text=display_text,
                embedding_text=embedding_text,
                parent_ids=[ancestor.node_id for ancestor in parent_nodes],
                block_ids=list(node.body_block_ids),
                asset_ids=asset_ids,
                source_file=document.source_file,
                source_start_order=node.start_order,
                source_end_order=node.end_order,
            )
        )
        return

    for child in node.children:
        _visit(document, child, [*ancestors, node], next_labels, chunks)


def _node_content(document: SourceDocument, node: LegalNode) -> tuple[str, list[str]]:
    block_map = document.block_map()
    parts = [node.title] if node.title else []
    asset_ids: list[str] = []
    footnote_ids: list[str] = []
    for block_id in node.body_block_ids:
        block = block_map.get(block_id)
        if block is None:
            continue
        if block.text:
            parts.append(block.text)
        asset_ids.extend(block.asset_ids)
        footnote_ids.extend(block.footnote_ids)
    for note_id in dict.fromkeys(footnote_ids):
        if note_id in document.footnotes:
            parts.append(f"[^{note_id}]: {document.footnotes[note_id]}")
    return "\n".join(part for part in parts if part).strip(), list(dict.fromkeys(asset_ids))


def _should_chunk(node: LegalNode) -> bool:
    if node.kind not in _CHUNK_LEVELS:
        return False
    descendant_kinds = {descendant.kind for descendant in _descendants(node)}
    if node.kind is NodeKind.ARTICLE:
        return NodeKind.CLAUSE not in descendant_kinds
    if node.kind is NodeKind.CLAUSE:
        return NodeKind.POINT not in descendant_kinds
    return True


def _descendants(node: LegalNode) -> list[LegalNode]:
    descendants: list[LegalNode] = []
    for child in node.children:
        descendants.append(child)
        descendants.extend(_descendants(child))
    return descendants


def _node_preamble(document: SourceDocument, node: LegalNode) -> str:
    text, _ = _node_content(document, node)
    legal_labels = {
        NodeKind.ARTICLE: "Điều",
        NodeKind.CLAUSE: "Khoản",
        NodeKind.POINT: "Điểm",
    }
    scope = " (nội dung sửa đổi/trích dẫn)" if node.scope is ProvisionScope.AMENDED else ""
    return f"{legal_labels.get(node.kind, node.kind.value.title())} {node.label}{scope}: {text}".strip()
