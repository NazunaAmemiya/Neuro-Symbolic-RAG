from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from zipfile import ZipFile, is_zipfile


class DocConversionError(RuntimeError):
    """Raised when a legacy Word document cannot be converted without detected loss."""


@dataclass(frozen=True, slots=True)
class DocConversionResult:
    source_path: str
    converted_path: str
    source_hash: str
    converter: str
    converter_version: str
    verification_level: str
    before_metrics: dict[str, int]
    after_metrics: dict[str, int]
    status: str


def convert_doc_to_docx(source_path: Path, output_root: Path, source_hash: str) -> Path:
    """Convert DOC with Word in a cache keyed by the immutable source hash."""

    destination_dir = output_root / source_hash[:2]
    destination = destination_dir / f"{source_hash}.docx"
    report_path = destination_dir / f"{source_hash}.conversion.json"
    if destination.exists() and report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if report.get("status") == "passed":
            _verify_docx_package(destination)
            return destination

    if os.name != "nt":
        raise DocConversionError(
            "Legacy DOC conversion requires a Windows worker with Microsoft Word installed."
        )
    powershell = shutil.which("powershell.exe") or shutil.which("powershell")
    if powershell is None:
        raise DocConversionError("PowerShell is required for Microsoft Word DOC conversion.")

    destination_dir.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["LEGAL_RAG_DOC_SOURCE"] = str(source_path.resolve())
    environment["LEGAL_RAG_DOC_TARGET"] = str(destination.resolve())
    encoded = base64.b64encode(_POWERSHELL_CONVERTER.encode("utf-16-le")).decode("ascii")
    completed = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=environment,
        timeout=300,
    )
    payload = None
    for line in reversed(completed.stdout.strip().splitlines()):
        try:
            payload = json.loads(line)
            break
        except json.JSONDecodeError:
            continue
    if payload is None:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise DocConversionError(
            f"Word conversion returned no valid report for {source_path.name}: {detail}"
        )

    _verify_docx_package(destination)
    before = {key: int(value) for key, value in payload["before"].items()}
    after = {key: int(value) for key, value in payload["after"].items()}
    changed = {key for key in before if before[key] != after.get(key)}
    status = "passed" if not changed else "failed"
    result = DocConversionResult(
        source_path=source_path.name,
        converted_path=destination.relative_to(output_root).as_posix(),
        source_hash=source_hash,
        converter="Microsoft Word",
        converter_version=str(payload["word_version"]),
        verification_level="word_structural_metrics",
        before_metrics=before,
        after_metrics=after,
        status=status,
    )
    report_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if changed:
        raise DocConversionError(
            f"DOC conversion changed structural metrics for {source_path.name}: {sorted(changed)}"
        )
    return destination


def _verify_docx_package(path: Path) -> None:
    if not path.exists() or not is_zipfile(path):
        raise DocConversionError(f"Converted output is not a DOCX package: {path}")
    with ZipFile(path) as package:
        if "word/document.xml" not in package.namelist():
            raise DocConversionError(f"Converted DOCX has no word/document.xml: {path}")


_POWERSHELL_CONVERTER = r'''
$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$source = $env:LEGAL_RAG_DOC_SOURCE
$target = $env:LEGAL_RAG_DOC_TARGET
function Get-Metrics($document) {
    $document.Repaginate()
    return [ordered]@{
        characters = $document.ComputeStatistics(3)
        characters_with_spaces = $document.ComputeStatistics(5)
        words = $document.ComputeStatistics(0)
        paragraphs = $document.Paragraphs.Count
        tables = $document.Tables.Count
        inline_shapes = $document.InlineShapes.Count
        shapes = $document.Shapes.Count
        footnotes = $document.Footnotes.Count
        endnotes = $document.Endnotes.Count
        fields = $document.Fields.Count
        comments = $document.Comments.Count
        revisions = $document.Revisions.Count
        form_fields = $document.FormFields.Count
        content_controls = $document.ContentControls.Count
        sections = $document.Sections.Count
        pages = $document.ComputeStatistics(2)
    }
}
$word = $null
$document = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = 0
    $word.AutomationSecurity = 3
    $document = $word.Documents.Open($source, $false, $true, $false)
    $before = Get-Metrics $document
    $document.SaveAs2($target, 16, $false, "", $false)
    $after = Get-Metrics $document
    [ordered]@{
        word_version = $word.Version
        before = $before
        after = $after
    } | ConvertTo-Json -Depth 4 -Compress
}
finally {
    if ($null -ne $document) { try { $document.Close(0) | Out-Null } catch {} }
    if ($null -ne $word) { try { $word.Quit() | Out-Null } catch {} }
}
'''
