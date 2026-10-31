from __future__ import annotations

import re
import unicodedata

from .models import DocumentBlock, InlineSpan, SourceDocument

_WHITESPACE = re.compile(r"[ \t\u00a0]+")


def normalize_document(document: SourceDocument) -> SourceDocument:
    """Apply Unicode NFC and safe whitespace normalization without changing evidence."""

    blocks: list[DocumentBlock] = []
    for block in document.blocks:
        text = _normalize_text(block.text)
        spans = [
            InlineSpan(
                text=unicodedata.normalize("NFC", span.text),
                bold=span.bold,
                italic=span.italic,
                superscript=span.superscript,
                subscript=span.subscript,
            )
            for span in block.spans
        ]
        blocks.append(
            DocumentBlock(
                block_id=block.block_id,
                kind=block.kind,
                order=block.order,
                text=text,
                locator=block.locator,
                spans=spans,
                table=block.table,
                asset_ids=block.asset_ids,
                footnote_ids=block.footnote_ids,
                style_name=block.style_name,
                is_bold=block.is_bold,
                metadata=block.metadata,
            )
        )
    return SourceDocument(
        document_id=document.document_id,
        source_file=document.source_file,
        blocks=blocks,
        assets=document.assets,
        footnotes={key: _normalize_text(value) for key, value in document.footnotes.items()},
        report=document.report,
        package_id=document.package_id,
        parent_document_id=document.parent_document_id,
        source_role=document.source_role,
        source_format=document.source_format,
        source_relative_path=document.source_relative_path,
        metadata=document.metadata,
    )


def _normalize_text(value: str) -> str:
    lines = []
    for line in unicodedata.normalize("NFC", value).splitlines():
        lines.append(_WHITESPACE.sub(" ", line).strip())
    return "\n".join(lines).strip()
