from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from hashlib import sha256
from pathlib import PurePosixPath
from typing import Any


class BlockKind(StrEnum):
    PARAGRAPH = "paragraph"
    TABLE = "table"
    IMAGE = "image"
    FORMULA = "formula"
    ATTACHMENT = "attachment"
    WORKSHEET = "worksheet"


class AssetKind(StrEnum):
    IMAGE = "image"
    FORMULA_IMAGE = "formula_image"
    OLE_OBJECT = "ole_object"
    ATTACHMENT = "attachment"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class SourceRole(StrEnum):
    PRIMARY_LEGAL_DOCUMENT = "primary_legal_document"
    APPENDIX = "appendix"
    FORM_DOCUMENT = "form_document"
    FORM_WORKBOOK = "form_workbook"
    SUPPLEMENTAL = "supplemental"


class SourceFormat(StrEnum):
    DOC = "doc"
    DOCX = "docx"
    XLSX = "xlsx"
    MARKDOWN = "md"
    TEXT = "txt"


def stable_id(*parts: str) -> str:
    """Create reproducible identifiers without depending on an ingest run."""

    value = "|".join(part.strip().casefold() for part in parts)
    return sha256(value.encode("utf-8")).hexdigest()[:24]


@dataclass(slots=True)
class InlineSpan:
    text: str
    bold: bool = False
    italic: bool = False
    superscript: bool = False
    subscript: bool = False


@dataclass(slots=True)
class TableCell:
    row: int
    column: int
    row_span: int
    column_span: int
    text: str
    spans: list[InlineSpan] = field(default_factory=list)
    nested_tables: list[TableData] = field(default_factory=list)


@dataclass(slots=True)
class TableData:
    rows: int
    columns: int
    cells: list[TableCell]
    has_merged_cells: bool
    footnote_ids: list[str] = field(default_factory=list)

    def as_text(self) -> str:
        lines = ["[BẢNG]"]
        by_row: dict[int, list[TableCell]] = {}
        for cell in self.cells:
            by_row.setdefault(cell.row, []).append(cell)
        for row_number in sorted(by_row):
            values = []
            for cell in sorted(by_row[row_number], key=lambda item: item.column):
                suffix = ""
                if cell.row_span > 1 or cell.column_span > 1:
                    suffix = f" [gộp {cell.row_span}x{cell.column_span}]"
                values.append(f"{cell.text}{suffix}".strip())
            lines.append(" | ".join(values))
        return "\n".join(lines).strip()


@dataclass(slots=True)
class EmbeddedAsset:
    asset_id: str
    kind: AssetKind
    package_path: str
    content_type: str | None
    filename: str
    relationship_id: str | None
    data: bytes = field(repr=False)
    parent_asset_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("data", None)
        payload["size_bytes"] = len(self.data)
        payload["kind"] = self.kind.value
        return payload

    @property
    def safe_filename(self) -> str:
        name = PurePosixPath(self.filename.replace("\\", "/")).name
        return name or f"{self.asset_id}.bin"


@dataclass(slots=True)
class DocumentBlock:
    block_id: str
    kind: BlockKind
    order: int
    text: str
    locator: str
    spans: list[InlineSpan] = field(default_factory=list)
    table: TableData | None = None
    asset_ids: list[str] = field(default_factory=list)
    footnote_ids: list[str] = field(default_factory=list)
    style_name: str | None = None
    is_bold: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["kind"] = self.kind.value
        return payload


@dataclass(slots=True)
class IngestionIssue:
    code: str
    severity: IssueSeverity
    message: str
    locator: str | None = None
    block_id: str | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "locator": self.locator,
            "block_id": self.block_id,
        }


@dataclass(slots=True)
class ExtractionReport:
    paragraph_count: int = 0
    table_count: int = 0
    image_count: int = 0
    formula_image_count: int = 0
    ole_object_count: int = 0
    attachment_count: int = 0
    footnote_reference_count: int = 0
    merged_cell_count: int = 0
    superscript_span_count: int = 0
    subscript_span_count: int = 0
    worksheet_count: int = 0
    formula_cell_count: int = 0
    data_validation_count: int = 0
    nonempty_cell_count: int = 0
    issues: list[IngestionIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["issues"] = [issue.to_dict() for issue in self.issues]
        return payload


@dataclass(slots=True)
class SourceDocument:
    document_id: str
    source_file: str
    blocks: list[DocumentBlock] = field(default_factory=list)
    assets: list[EmbeddedAsset] = field(default_factory=list)
    footnotes: dict[str, str] = field(default_factory=dict)
    report: ExtractionReport = field(default_factory=ExtractionReport)
    package_id: str | None = None
    parent_document_id: str | None = None
    source_role: SourceRole = SourceRole.PRIMARY_LEGAL_DOCUMENT
    source_format: SourceFormat = SourceFormat.DOCX
    source_relative_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    # Kept for lightweight text/Markdown fixtures and backwards-compatible tests.
    lines: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.lines and not self.blocks:
            self.blocks = [
                DocumentBlock(
                    block_id=stable_id(self.document_id, "paragraph", str(index)),
                    kind=BlockKind.PARAGRAPH,
                    order=index,
                    text=line,
                    locator=f"line:{index}",
                )
                for index, line in enumerate(self.lines, start=1)
            ]
        elif self.blocks and not self.lines:
            self.lines = [block.text for block in self.blocks]

    def block_map(self) -> dict[str, DocumentBlock]:
        return {block.block_id: block for block in self.blocks}
