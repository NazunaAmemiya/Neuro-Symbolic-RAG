from __future__ import annotations

from hashlib import sha256
from pathlib import Path

from .doc_converter import convert_doc_to_docx
from .docx_reader import extract_docx
from .formula_ocr import FormulaOCR
from .formula_reviews import FormulaReviewIndex
from .models import SourceDocument, SourceFormat, stable_id
from .xlsx_reader import extract_xlsx

SUPPORTED_SUFFIXES = {".doc", ".docx", ".xlsx", ".md", ".txt"}


def extract_document(
    path: Path,
    *,
    conversion_dir: Path = Path("data/derived/conversions"),
    source_hash: str | None = None,
    formula_ocr: FormulaOCR | None = None,
    formula_reviews: FormulaReviewIndex | None = None,
) -> SourceDocument:
    """Extract an auditable block stream from supported legal source formats."""

    suffix = path.suffix.casefold()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported source format: {path.name}")

    if suffix == ".doc":
        digest = source_hash or sha256(path.read_bytes()).hexdigest()
        converted_path = convert_doc_to_docx(path, conversion_dir, digest)
        document = extract_docx(
            converted_path,
            formula_ocr=formula_ocr,
            formula_reviews=formula_reviews,
            review_source_hash=digest,
        )
        document.source_file = path.name
        document.source_format = SourceFormat.DOC
        try:
            converted_relative = converted_path.relative_to(conversion_dir).as_posix()
        except ValueError:
            converted_relative = converted_path.name
        document.metadata["converted_docx"] = converted_relative
        document.metadata["original_source_hash"] = digest
        return document
    if suffix == ".docx":
        return extract_docx(path, formula_ocr=formula_ocr, formula_reviews=formula_reviews)
    if suffix == ".xlsx":
        return extract_xlsx(path)

    source_bytes = path.read_bytes()
    lines = source_bytes.decode("utf-8").splitlines()

    return SourceDocument(
        document_id=stable_id("document", path.name, sha256(source_bytes).hexdigest()),
        source_file=path.name,
        lines=lines,
        source_format=SourceFormat(suffix.lstrip(".")),
    )


def find_source_documents(source_dir: Path) -> list[Path]:
    return sorted(
        path
        for path in source_dir.rglob("*")
        if path.is_file() and path.suffix.casefold() in SUPPORTED_SUFFIXES
    )
