"""Regression tests for OOXML pictures embedded inside Word table cells."""

from __future__ import annotations

import copy
import struct
import zlib
from io import BytesIO

from docx import Document
from lxml import etree

from backend.app.ingestion.docx_reader import extract_docx
from backend.app.ingestion.markdown_renderer import write_markdown_view
from backend.app.ingestion.models import BlockKind


def _tiny_png(rgb: bytes = b"\xff\xff\xff") -> bytes:
    def chunk(tag: bytes, payload: bytes) -> bytes:
        body = tag + payload
        return struct.pack(">I", len(payload)) + body + struct.pack(">I", zlib.crc32(body))

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00" + rgb))
        + chunk(b"IEND", b"")
    )


def test_table_media_remains_in_correct_cells_including_reused_image(tmp_path) -> None:
    source = tmp_path / "pictures.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=2)
    first = table.cell(0, 0).paragraphs[0]
    first.add_run("Before ")
    first.add_run().add_picture(BytesIO(_tiny_png()), width=100000)
    first.add_run(" After")
    table.cell(0, 1).text = "Right cell"
    second = table.cell(1, 1).paragraphs[0]
    second.add_run().add_picture(BytesIO(_tiny_png()), width=100000)
    doc.save(source)

    extracted = extract_docx(source)
    table_block = next(block for block in extracted.blocks if block.kind is BlockKind.TABLE)
    image_blocks = [block for block in extracted.blocks if block.kind is BlockKind.IMAGE]
    assert table_block.table is not None
    assert len(image_blocks) == 1  # Word reused the same relationship for identical PNGs.
    first_cell = next(c for c in table_block.table.cells if (c.row, c.column) == (0, 0))
    second_cell = next(c for c in table_block.table.cells if (c.row, c.column) == (1, 1))
    assert first_cell.asset_ids == second_cell.asset_ids == image_blocks[0].asset_ids
    assert [part.kind for part in first_cell.content] == ["text", "image", "text"]

    markdown_path = write_markdown_view(extracted, tmp_path / "markdown")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert markdown.count("<img ") == 2
    assert "Before <img " in markdown
    assert "alt=\"Hình ảnh\"> After</td>" in markdown
    assert "<td>Right cell</td>" in markdown
    assert "![Hình ảnh]" not in markdown
    assert image_blocks[0].metadata["rendered_in_table"] is True
    assert len(extracted.assets) == 1


def test_picture_in_vertical_merge_continuation_maps_to_origin_cell(tmp_path) -> None:
    source = tmp_path / "merged-pictures.docx"
    doc = Document()
    table = doc.add_table(rows=2, cols=1)
    table.cell(0, 0).merge(table.cell(1, 0))
    table.cell(0, 0).text = "First row"
    paragraph = doc.add_paragraph()
    paragraph.add_run().add_picture(BytesIO(_tiny_png()), width=100000)
    drawing_run = copy.deepcopy(paragraph.runs[0]._r)
    paragraph._p.getparent().remove(paragraph._p)
    # Insert an image directly into w:tc with w:vMerge continue.
    continuation_tc = table.rows[1]._tr.tc_lst[0]
    continuation_tc.find("{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p").append(
        drawing_run
    )
    doc.save(source)

    extracted = extract_docx(source)
    table_block = next(block for block in extracted.blocks if block.kind is BlockKind.TABLE)
    assert table_block.table is not None
    assert len(table_block.table.cells) == 1
    cell = table_block.table.cells[0]
    assert cell.row_span == 2
    assert len(cell.asset_ids) == 1
    markdown_path = write_markdown_view(extracted, tmp_path / "markdown")
    markdown = markdown_path.read_text(encoding="utf-8")
    assert 'rowspan="2"' in markdown
    assert markdown.count("<img ") == 1


def test_image_inside_nested_table_remains_in_inner_cell(tmp_path) -> None:
    source = tmp_path / "nested-pictures.docx"
    doc = Document()
    outer = doc.add_table(rows=1, cols=1)
    inner = outer.cell(0, 0).add_table(rows=1, cols=1)
    inner.cell(0, 0).paragraphs[0].add_run().add_picture(BytesIO(_tiny_png()), width=100000)
    doc.save(source)

    extracted = extract_docx(source)
    table_block = next(block for block in extracted.blocks if block.kind is BlockKind.TABLE)
    assert table_block.table is not None
    nested = table_block.table.cells[0].nested_tables[0]
    assert len(nested.cells[0].asset_ids) == 1
    markdown = write_markdown_view(extracted, tmp_path / "markdown").read_text(encoding="utf-8")
    assert markdown.count("<table>") == 2
    assert markdown.count("<img ") == 1
    assert "![Hình ảnh]" not in markdown


def test_alternate_content_fallback_is_linked_inside_cell_not_rendered_twice(tmp_path) -> None:
    """Word's Choice+Fallback may embed different image relationships for one picture."""
    source = tmp_path / "alternate.docx"
    doc = Document()
    cell = doc.add_table(rows=1, cols=1).cell(0, 0)
    first = cell.paragraphs[0].add_run()
    first.add_picture(BytesIO(_tiny_png()), width=100000)
    first_drawing = copy.deepcopy(first._r.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
    ))
    cell.paragraphs[0]._p.remove(first._r)
    second = cell.paragraphs[0].add_run()
    second.add_picture(BytesIO(_tiny_png(b"\x00\x00\xff")), width=100000)
    second_drawing = copy.deepcopy(second._r.find(
        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}drawing"
    ))
    cell.paragraphs[0]._p.remove(second._r)

    mc = "http://schemas.openxmlformats.org/markup-compatibility/2006"
    w = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
    alternate = etree.Element(f"{{{mc}}}AlternateContent")
    primary = etree.SubElement(alternate, f"{{{mc}}}Choice", Requires="w14")
    primary_run = etree.SubElement(primary, f"{{{w}}}r")
    primary_run.append(first_drawing)
    fallback = etree.SubElement(alternate, f"{{{mc}}}Fallback")
    fallback_run = etree.SubElement(fallback, f"{{{w}}}r")
    fallback_run.append(second_drawing)
    cell.paragraphs[0]._p.append(alternate)
    doc.save(source)

    extracted = extract_docx(source)
    table_block = next(block for block in extracted.blocks if block.kind is BlockKind.TABLE)
    assert table_block.table is not None
    content = table_block.table.cells[0].content
    assert [part.kind for part in content] == ["image", "alternate_image"]
    assert len(table_block.table.cells[0].asset_ids) == 2
    assert len(extracted.assets) == 2
    markdown = write_markdown_view(extracted, tmp_path / "markdown").read_text(encoding="utf-8")
    assert markdown.count("<img ") == 1
    assert markdown.count("Bản media dự phòng</a>") == 1
    assert "![Hình ảnh]" not in markdown


class _StubFormulaOCR:
    def recognize(self, data: bytes, filename: str) -> str:
        assert filename.endswith(".png")
        return r"x_i + y_i"


def test_formula_image_keeps_unverified_ocr_note_inside_cell(tmp_path) -> None:
    source = tmp_path / "formula-in-table.docx"
    doc = Document()
    doc.add_paragraph("Công thức tính như sau:")
    table = doc.add_table(rows=1, cols=1)
    table.cell(0, 0).paragraphs[0].add_run().add_picture(
        BytesIO(_tiny_png()), width=100000
    )
    doc.save(source)

    extracted = extract_docx(source, formula_ocr=_StubFormulaOCR())
    formula = next(block for block in extracted.blocks if block.kind is BlockKind.FORMULA)
    assert formula.metadata["ocr_status"] == "unverified"
    markdown = write_markdown_view(extracted, tmp_path / "markdown").read_text(encoding="utf-8")
    assert markdown.count("<img ") == 1
    assert "OCR chưa xác minh" in markdown
    assert "x_i + y_i" in markdown
    assert "![Công thức]" not in markdown


def test_structural_audit_accepts_image_links_rendered_inside_table(tmp_path) -> None:
    import json
    from hashlib import sha256

    from scripts.audit_markdown_fidelity import audit

    source_root = tmp_path / "source"
    source = source_root / "Bidding_Law" / "fixture.docx"
    source.parent.mkdir(parents=True)
    doc = Document()
    doc.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0].add_run().add_picture(
        BytesIO(_tiny_png()), width=100000
    )
    doc.save(source)

    extracted = extract_docx(source)
    extracted.source_relative_path = "Bidding_Law/fixture.docx"
    markdown_root = tmp_path / "markdown"
    markdown = write_markdown_view(extracted, markdown_root)
    artifact_root = tmp_path / "artifacts"
    artifact_dir = artifact_root / "fixture" / extracted.document_id
    (artifact_dir / "assets").mkdir(parents=True)
    (artifact_dir / "blocks.jsonl").write_text(
        "".join(
            json.dumps(block.to_dict(), ensure_ascii=False) + "\n"
            for block in extracted.blocks
        ),
        encoding="utf-8",
    )
    (artifact_dir / "report.json").write_text(
        json.dumps({"assets": [asset.to_dict() for asset in extracted.assets]}),
        encoding="utf-8",
    )
    for asset in extracted.assets:
        (artifact_dir / "assets" / f"{asset.asset_id}-{asset.safe_filename}").write_bytes(
            asset.data
        )
    (artifact_root / "manifest.json").write_text(
        json.dumps(
            [
                {
                    "source_file": extracted.source_relative_path,
                    "source_hash": sha256(source.read_bytes()).hexdigest(),
                    "document_id": extracted.document_id,
                    "markdown_relative_path": markdown.relative_to(markdown_root).as_posix(),
                    "artifact_dir": artifact_dir.relative_to(artifact_root).as_posix(),
                }
            ]
        ),
        encoding="utf-8",
    )
    result = audit(source_root, artifact_root, markdown_root)
    assert result["failed"] == 0, result


def test_structural_audit_accepts_converted_vector_png(tmp_path) -> None:
    import json
    from hashlib import sha256

    from scripts.audit_markdown_fidelity import audit

    for ext in ("emf", "wmf"):
        root = tmp_path / ext
        source_root = root / "source"
        source = source_root / "Bidding_Law" / "fixture.docx"
        source.parent.mkdir(parents=True)

        doc = Document()
        doc.add_table(rows=1, cols=1).cell(0, 0).paragraphs[0].add_run().add_picture(
            BytesIO(_tiny_png()), width=100000
        )
        doc.save(source)

        extracted = extract_docx(source)
        extracted.source_relative_path = "Bidding_Law/fixture.docx"
        assert len(extracted.assets) == 1
        asset = extracted.assets[0]

        markdown_root = root / "markdown"
        markdown = write_markdown_view(extracted, markdown_root)

        original_name = f"{asset.asset_id}-{asset.safe_filename}"
        vector_name = f"{asset.asset_id}-image1.{ext}"
        png_name = vector_name + ".png"

        content = markdown.read_text(encoding="utf-8")
        assert original_name in content
        markdown.write_text(
            content.replace(original_name, png_name),
            encoding="utf-8",
        )

        markdown_assets = markdown.parent / "_assets" / extracted.document_id
        (markdown_assets / vector_name).write_bytes(asset.data)
        converted_png = markdown_assets / png_name
        converted_png.write_bytes(asset.data)

        artifact_root = root / "artifacts"
        artifact_dir = artifact_root / "fixture" / extracted.document_id
        (artifact_dir / "assets").mkdir(parents=True)

        (artifact_dir / "blocks.jsonl").write_text(
            "".join(
                json.dumps(block.to_dict(), ensure_ascii=False) + "\n"
                for block in extracted.blocks
            ),
            encoding="utf-8",
        )

        asset_record = asset.to_dict()
        asset_record["filename"] = f"image1.{ext}"

        (artifact_dir / "report.json").write_text(
            json.dumps({"assets": [asset_record]}),
            encoding="utf-8",
        )
        (artifact_dir / "assets" / vector_name).write_bytes(asset.data)

        (artifact_root / "manifest.json").write_text(
            json.dumps([{
                "source_file": extracted.source_relative_path,
                "source_hash": sha256(source.read_bytes()).hexdigest(),
                "document_id": extracted.document_id,
                "markdown_relative_path": markdown.relative_to(
                    markdown_root
                ).as_posix(),
                "artifact_dir": artifact_dir.relative_to(
                    artifact_root
                ).as_posix(),
            }]),
            encoding="utf-8",
        )

        result = audit(source_root, artifact_root, markdown_root)
        assert result["failed"] == 0, result

        converted_png.write_bytes(b"invalid PNG")
        broken = audit(source_root, artifact_root, markdown_root)

        assert broken["failed"] == 1, broken
        assert (
            f"missing_markdown_link:{asset.asset_id}"
            in broken["results"][0]["problems"]
        )
