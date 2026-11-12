from __future__ import annotations

import json
import struct
import zlib
from hashlib import sha256
from io import BytesIO

from docx import Document
from lxml import etree

from backend.app.ingestion.docx_reader import extract_docx
from backend.app.ingestion.formula_reviews import load_formula_reviews
from backend.app.ingestion.markdown_renderer import render_markdown
from backend.app.ingestion.models import BlockKind


class StubOCR:
    def recognize(self, data: bytes, filename: str) -> str:
        assert filename.endswith(".png")
        assert data.startswith(b"\x89PNG")
        return r"X_{i}+Y_{i}"


def test_omml_inside_table_is_preserved_and_reviewable(tmp_path) -> None:
    source = tmp_path / "math.docx"
    doc = Document()
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    cell.text = "Giá trị: "
    math = etree.fromstring(
        b'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        b"<m:f><m:num><m:r><m:t>X</m:t></m:r></m:num>"
        b"<m:den><m:r><m:t>Y</m:t></m:r></m:den></m:f></m:oMath>"
    )
    cell.paragraphs[0]._p.append(math)
    doc.save(source)

    extracted = extract_docx(source)
    formula = next(block for block in extracted.blocks if block.kind is BlockKind.FORMULA)
    table = next(block for block in extracted.blocks if block.kind is BlockKind.TABLE)
    assert extracted.report.formula_omml_count == 1
    assert formula.metadata["candidate_latex"] == r"\frac{X}{Y}"
    assert formula.metadata["review_status"] == "unverified"
    assert formula.text in table.table.cells[0].text
    assert "OCR" not in render_markdown(extracted)
    assert "Bản đọc OMML chưa xác minh" in render_markdown(extracted)

    review_path = tmp_path / "math-review.json"
    review_path.write_text(
        json.dumps(
            {
                "reviews": [
                    {
                        "source_sha256": sha256(source.read_bytes()).hexdigest(),
                        "content_sha256": formula.metadata["content_sha256"],
                        "status": "reviewed_visual",
                        "latex": r"\frac{X}{Y}",
                        "reviewer": "fixture reviewer",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    reviewed = extract_docx(source, formula_reviews=load_formula_reviews(review_path))
    reviewed_formula = next(block for block in reviewed.blocks if block.kind is BlockKind.FORMULA)
    assert reviewed_formula.metadata["review_status"] == "reviewed_visual"
    assert reviewed.report.formula_reviewed_count == 1
    assert "Bản phiên âm đã đối chiếu" in render_markdown(reviewed)


def test_image_ocr_candidate_never_replaces_source_text(tmp_path) -> None:
    source = tmp_path / "picture.docx"

    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    image = BytesIO(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )
    doc = Document()
    doc.add_paragraph("Công thức tính như sau:")
    doc.add_picture(image, width=100000)
    doc.save(source)

    extracted = extract_docx(source, formula_ocr=StubOCR())
    formula = next(block for block in extracted.blocks if block.kind is BlockKind.FORMULA)
    assert extracted.report.formula_image_count == 1
    assert extracted.report.formula_ocr_candidate_count == 1
    assert formula.metadata["ocr_candidate_latex"] == r"X_{i}+Y_{i}"
    assert formula.metadata["review_status"] == "unverified"
    assert "X_{i}" not in formula.text
    assert "OCR chưa xác minh" in render_markdown(extracted, {formula.asset_ids[0]: "image.png"})

    asset = next(asset for asset in extracted.assets if asset.asset_id == formula.asset_ids[0])
    review_path = tmp_path / "reviews.json"
    review = {
        "source_sha256": sha256(source.read_bytes()).hexdigest(),
        "content_sha256": sha256(asset.data).hexdigest(),
        "status": "reviewed_visual",
        "latex": r"X_i + Y_i",
        "reviewer": "fixture reviewer",
    }
    review_path.write_text(json.dumps({"reviews": [review]}), encoding="utf-8")
    reviewed = extract_docx(
        source,
        formula_ocr=StubOCR(),
        formula_reviews=load_formula_reviews(review_path),
    )
    reviewed_formula = next(block for block in reviewed.blocks if block.kind is BlockKind.FORMULA)
    assert reviewed_formula.metadata["review_status"] == "reviewed_visual"
    assert r"X_i + Y_i" in reviewed_formula.text
    assert reviewed.report.formula_reviewed_count == 1

    review["source_sha256"] = "0" * 64
    review_path.write_text(json.dumps({"reviews": [review]}), encoding="utf-8")
    stale = extract_docx(source, formula_reviews=load_formula_reviews(review_path))
    stale_formula = next(block for block in stale.blocks if block.kind is BlockKind.FORMULA)
    assert stale_formula.metadata["review_status"] == "unverified"
    assert r"X_i + Y_i" not in stale_formula.text

    review["source_sha256"] = sha256(source.read_bytes()).hexdigest()
    review["content_sha256"] = "0" * 64
    review_path.write_text(json.dumps({"reviews": [review]}), encoding="utf-8")
    stale_image = extract_docx(source, formula_reviews=load_formula_reviews(review_path))
    stale_image_formula = next(
        block for block in stale_image.blocks if block.kind is BlockKind.FORMULA
    )
    assert stale_image_formula.metadata["review_status"] == "unverified"


def test_inline_omml_operator_stays_in_paragraph_without_formula_block(tmp_path) -> None:
    source = tmp_path / "inline-operator.docx"
    doc = Document()
    paragraph = doc.add_paragraph("Điểm = ")
    math = etree.fromstring(
        b'<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
        b'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        b"<m:r><w:rPr><w:vertAlign w:val=\"subscript\"/></w:rPr><m:t>\xc3\x97</m:t></m:r>"
        b"</m:oMath>"
    )
    paragraph._p.append(math)
    doc.save(source)

    extracted = extract_docx(source)

    paragraph_block = next(block for block in extracted.blocks if block.kind is BlockKind.PARAGRAPH)
    assert paragraph_block.text == "Điểm = ×"
    assert not any(block.kind is BlockKind.FORMULA for block in extracted.blocks)
    assert extracted.report.formula_omml_count == 0
    assert extracted.report.formula_inline_component_count == 1


def test_legacy_quote_equation_picture_is_an_inline_component(tmp_path) -> None:
    source = tmp_path / "quote-picture.docx"

    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    image = BytesIO(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )
    doc = Document()
    paragraph = doc.add_paragraph("Công thức tính: ")
    run = paragraph.add_run()
    run.add_picture(image, width=100000)
    drawing = run._r.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing")
    blip = drawing.find(
        ".//{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
    )
    relationship_id = blip.get(
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
    )
    run._r.remove(drawing)
    pict = etree.fromstring(
        (
            '<w:pict xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            'xmlns:v="urn:schemas-microsoft-com:vml" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<v:shape><v:imagedata r:id="{relationship_id}"/></v:shape></w:pict>'
        ).encode()
    )
    shape = pict.find("{urn:schemas-microsoft-com:vml}shape")
    shape.set(
        "equationxml",
        '<m:oMath xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math">'
        "<m:r><m:t>×</m:t></m:r></m:oMath>",
    )
    run._r.append(pict)
    doc.save(source)

    extracted = extract_docx(source)

    paragraph_block = next(block for block in extracted.blocks if block.kind is BlockKind.PARAGRAPH)
    assert paragraph_block.text == "Công thức tính: ×"
    assert not any(block.kind is BlockKind.FORMULA for block in extracted.blocks)
    assert any(block.kind is BlockKind.IMAGE for block in extracted.blocks)
    assert extracted.report.formula_image_count == 0
    assert extracted.report.formula_inline_component_count == 1
