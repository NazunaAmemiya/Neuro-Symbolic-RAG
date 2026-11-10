from __future__ import annotations

import re
from collections import defaultdict

from .models import (
    BlockKind,
    DocumentBlock,
    IngestionIssue,
    IssueSeverity,
    LegalNode,
    NodeKind,
    ProvisionScope,
    SourceDocument,
    stable_id,
)

_QUOTE_PREFIX = r'^[\s\"\'“‘]*'
_HEADING_PATTERNS: tuple[tuple[NodeKind, re.Pattern[str]], ...] = (
    (NodeKind.PART, re.compile(_QUOTE_PREFIX + r"PHẦN\s+(.+)$", re.IGNORECASE)),
    (NodeKind.CHAPTER, re.compile(_QUOTE_PREFIX + r"CHƯƠNG\s+(.+)$", re.IGNORECASE)),
    (NodeKind.SECTION, re.compile(_QUOTE_PREFIX + r"MỤC\s+(.+)$", re.IGNORECASE)),
    (
        NodeKind.ARTICLE,
        re.compile(_QUOTE_PREFIX + r"Điều\s+(\d+[A-Za-zĐđ]?)\.?\s*(.*)$", re.IGNORECASE),
    ),
    (NodeKind.CLAUSE, re.compile(_QUOTE_PREFIX + r"(\d+)\.\s+(.+)$")),
    (NodeKind.POINT, re.compile(_QUOTE_PREFIX + r"([a-zđ])\)\s+(.+)$", re.IGNORECASE)),
    (
        NodeKind.APPENDIX,
        re.compile(
            _QUOTE_PREFIX + r"(PHỤ\s+LỤC(?:\s+[A-Z0-9IVX.-]+)?)\s*(.*)$",
            re.IGNORECASE,
        ),
    ),
)
_LEVELS = {
    NodeKind.DOCUMENT: 0,
    NodeKind.PART: 1,
    NodeKind.CHAPTER: 2,
    NodeKind.SECTION: 3,
    NodeKind.ARTICLE: 4,
    NodeKind.CLAUSE: 5,
    NodeKind.POINT: 6,
    NodeKind.APPENDIX: 1,
}
_AMENDMENT_CUE = re.compile(
    r"\b(bổ\s+sung|sửa\s+đổi|thay\s+thế|bãi\s+bỏ)\b.*"
    r"\b(như\s+sau|sau\s+đây)\b",
    re.IGNORECASE,
)
_POINT_ORDER = {
    letter: index
    for index, letter in enumerate(
        ("a", "b", "c", "d", "đ", "e", "g", "h", "i", "k", "l", "m", "n", "o", "p", "q", "r", "s", "t", "u", "v", "x", "y"),
        start=1,
    )
}


def parse_hierarchy(document: SourceDocument) -> tuple[LegalNode, list[IngestionIssue]]:
    """Build a legal tree while keeping quoted/amended provisions in a separate scope."""

    root = LegalNode(
        node_id=stable_id(document.document_id, "root"),
        kind=NodeKind.DOCUMENT,
        label=document.source_file,
        title=document.source_file,
        parent_id=None,
        start_order=1,
        end_order=max(1, len(document.blocks)),
    )
    source_stack = [root]
    amended_stack: list[LegalNode] = []
    issues: list[IngestionIssue] = []
    occurrences: defaultdict[tuple[str, str, str, str], int] = defaultdict(int)
    amendment_active = False
    amendment_pending = False

    legal_heading_kinds = {
        NodeKind.PART,
        NodeKind.CHAPTER,
        NodeKind.SECTION,
        NodeKind.ARTICLE,
        NodeKind.CLAUSE,
        NodeKind.POINT,
    }

    for block in document.blocks:
        text = block.text.strip()
        if amendment_pending and _opens_quotation(text):
            amendment_active = True
            amendment_pending = False
        heading = _match_heading(block) if text else None

        if heading is None:
            active = amended_stack[-1] if amendment_active and amended_stack else source_stack[-1]
            active.body_block_ids.append(block.block_id)
            active.end_order = max(active.end_order, block.order)
            if active is root and text:
                issues.append(
                    IngestionIssue(
                        code="root_level_content",
                        severity=IssueSeverity.INFO,
                        message=(
                            "Content is outside a recognized legal provision and was preserved."
                        ),
                        locator=block.locator,
                        block_id=block.block_id,
                    )
                )
        else:
            kind, label, title = heading
            quoted_inside_source_provision = (
                _opens_quotation(text)
                and kind in legal_heading_kinds
                and any(node.kind is NodeKind.ARTICLE for node in source_stack)
            )
            if quoted_inside_source_provision:
                amendment_active = True
            use_amended_scope = amendment_active and kind in legal_heading_kinds

            if use_amended_scope:
                parent = _amended_parent(kind, source_stack, amended_stack)
                _trim_stack(amended_stack, kind)
                scope = ProvisionScope.AMENDED
            else:
                parent = _source_parent(kind, source_stack)
                if parent is None:
                    source_stack[-1].body_block_ids.append(block.block_id)
                    issues.append(
                        IngestionIssue(
                            code="heading_without_legal_parent",
                            severity=IssueSeverity.INFO,
                            message=(
                                f"Potential {kind.value} heading has no valid parent; "
                                "preserved as text."
                            ),
                            locator=block.locator,
                            block_id=block.block_id,
                        )
                    )
                    heading = None
                    parent = source_stack[-1]
                scope = ProvisionScope.SOURCE

            if heading is not None:
                key = (parent.node_id, kind.value, scope.value, label.casefold())
                occurrences[key] += 1
                node = LegalNode(
                    node_id=stable_id(
                        document.document_id,
                        parent.node_id,
                        kind.value,
                        scope.value,
                        label,
                        str(occurrences[key]),
                    ),
                    kind=kind,
                    label=label,
                    title=title,
                    parent_id=parent.node_id,
                    start_order=block.order,
                    end_order=block.order,
                    scope=scope,
                )
                parent.children.append(node)
                if scope is ProvisionScope.AMENDED:
                    amended_stack.append(node)
                else:
                    _trim_stack(source_stack, kind)
                    source_stack.append(node)
                    amended_stack.clear()

        if _AMENDMENT_CUE.search(text):
            amendment_pending = True
            amended_stack.clear()
        if amendment_active and _closes_quotation(text):
            amendment_active = False
            amendment_pending = False
            amended_stack.clear()

    _validate_sequences(root, issues)
    return root, issues


def _match_heading(block: DocumentBlock) -> tuple[NodeKind, str, str] | None:
    if block.kind is not BlockKind.PARAGRAPH:
        return None
    line = block.text.replace("\n", " ").strip()
    for kind, pattern in _HEADING_PATTERNS:
        match = pattern.match(line)
        if match is None:
            continue
        if kind in {NodeKind.PART, NodeKind.CHAPTER, NodeKind.SECTION}:
            return kind, line.strip('“”"\' '), line.strip('“”"\' ')
        if kind is NodeKind.APPENDIX:
            return kind, match.group(1).strip(), match.group(2).strip('“”"\' ')
        return kind, match.group(1), match.group(2).strip('“”"\' ')
    return None


def _source_parent(kind: NodeKind, stack: list[LegalNode]) -> LegalNode | None:
    if kind is NodeKind.CLAUSE and not any(node.kind is NodeKind.ARTICLE for node in stack):
        return None
    if kind is NodeKind.POINT and not any(
        node.kind in {NodeKind.ARTICLE, NodeKind.CLAUSE} for node in stack
    ):
        return None
    candidates = [node for node in stack if _LEVELS[node.kind] < _LEVELS[kind]]
    return max(candidates, key=lambda node: _LEVELS[node.kind]) if candidates else None


def _amended_parent(
    kind: NodeKind, source_stack: list[LegalNode], amended_stack: list[LegalNode]
) -> LegalNode:
    candidates = [node for node in amended_stack if _LEVELS[node.kind] < _LEVELS[kind]]
    if candidates:
        return max(candidates, key=lambda node: _LEVELS[node.kind])
    return source_stack[-1]


def _trim_stack(stack: list[LegalNode], incoming_kind: NodeKind) -> None:
    while stack and stack[-1].kind is not NodeKind.DOCUMENT:
        if _LEVELS[stack[-1].kind] < _LEVELS[incoming_kind]:
            return
        stack.pop()


def _closes_quotation(text: str) -> bool:
    stripped = text.rstrip("”")
    return text.endswith(("”", "”;", "”.", "’;", "’.", '";', '".')) or stripped != text


def _opens_quotation(text: str) -> bool:
    return text.lstrip().startswith(("“", '"', "‘"))


def _validate_sequences(root: LegalNode, issues: list[IngestionIssue]) -> None:
    source_articles = [
        node
        for node, ancestors in _walk_with_ancestors(root)
        if node.kind is NodeKind.ARTICLE
        and node.scope is ProvisionScope.SOURCE
        and not any(ancestor.kind is NodeKind.APPENDIX for ancestor in ancestors)
    ]
    seen_articles: set[str] = set()
    previous_number: int | None = None
    for article in source_articles:
        normalized = article.label.casefold()
        if normalized in seen_articles:
            issues.append(
                IngestionIssue(
                    code="duplicate_source_article",
                    severity=IssueSeverity.WARNING,
                    message=(
                        f"Duplicate source-level Điều {article.label}; "
                        "no automatic correction applied."
                    ),
                )
            )
        seen_articles.add(normalized)
        if article.label.isdigit():
            number = int(article.label)
            if previous_number is not None and number > previous_number + 1:
                issues.append(
                    IngestionIssue(
                        code="article_sequence_gap",
                        severity=IssueSeverity.INFO,
                        message=(
                            f"Source-level article sequence jumps from {previous_number} "
                            f"to {number}."
                        ),
                    )
                )
            previous_number = number

    for parent in _walk(root):
        points = [child for child in parent.children if child.kind is NodeKind.POINT]
        previous_order = 0
        seen_points: set[str] = set()
        for point in points:
            label = point.label.casefold()
            order = _POINT_ORDER.get(label, 0)
            if label in seen_points or order <= previous_order:
                issues.append(
                    IngestionIssue(
                        code="point_sequence_anomaly",
                        severity=IssueSeverity.WARNING,
                        message=(
                            f"Point label {point.label}) is duplicated or out of order under "
                            f"{parent.kind.value} {parent.label}; source text was preserved."
                        ),
                    )
                )
            seen_points.add(label)
            previous_order = max(previous_order, order)


def _walk(node: LegalNode) -> list[LegalNode]:
    result = [node]
    for child in node.children:
        result.extend(_walk(child))
    return result


def _walk_with_ancestors(
    node: LegalNode, ancestors: tuple[LegalNode, ...] = ()
) -> list[tuple[LegalNode, tuple[LegalNode, ...]]]:
    result = [(node, ancestors)]
    for child in node.children:
        result.extend(_walk_with_ancestors(child, (*ancestors, node)))
    return result
