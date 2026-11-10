from backend.app.ingestion.models import NodeKind, ProvisionScope, SourceDocument
from backend.app.ingestion.normalizer import normalize_document
from backend.app.ingestion.parser import parse_hierarchy


def _walk(node):
    result = [node]
    for child in node.children:
        result.extend(_walk(child))
    return result


def test_nfc_normalization_recovers_decomposed_article_heading() -> None:
    document = SourceDocument(
        document_id="doc",
        source_file="sample.docx",
        lines=["Điều 71. Ký kết hợp đồng", "1. Nội dung."],
    )
    root, _ = parse_hierarchy(normalize_document(document))
    articles = [node for node in _walk(root) if node.kind is NodeKind.ARTICLE]

    assert [(node.label, node.scope) for node in articles] == [
        ("71", ProvisionScope.SOURCE)
    ]


def test_quoted_inserted_article_is_not_a_source_article() -> None:
    document = SourceDocument(
        document_id="doc",
        source_file="amending-law.docx",
        lines=[
            "Điều 1. Sửa đổi, bổ sung",
            "1. Bổ sung Điều 29a và Điều 29b như sau:",
            "“Điều 29a. Đặt hàng",
            "1. Nội dung của điều được bổ sung.”.",
            "Điều 2. Hiệu lực thi hành",
        ],
    )
    root, _ = parse_hierarchy(normalize_document(document))
    articles = [node for node in _walk(root) if node.kind is NodeKind.ARTICLE]

    assert [(node.label, node.scope) for node in articles] == [
        ("1", ProvisionScope.SOURCE),
        ("29a", ProvisionScope.AMENDED),
        ("2", ProvisionScope.SOURCE),
    ]
