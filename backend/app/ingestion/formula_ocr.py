"""Optional, local math OCR. Results are candidates until reviewed against DOCX."""

from __future__ import annotations

import base64
import shutil
import subprocess
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Protocol


class FormulaOCR(Protocol):
    def recognize(self, data: bytes, filename: str) -> str: ...


class Pix2TexOCR:
    """Run pix2tex locally; model weights and dependencies are installed separately."""

    def __init__(self) -> None:
        if find_spec("PIL") is None or find_spec("pix2tex") is None:
            raise RuntimeError(
                "Local formula OCR requires pix2tex and Pillow; install the formula-ocr extra"
            )
        self._model = None

    def recognize(self, data: bytes, filename: str) -> str:
        try:
            from PIL import Image
            from pix2tex.cli import LatexOCR
        except ImportError as exc:
            raise RuntimeError(
                "Install the optional formula-ocr dependencies on Python 3.11"
            ) from exc

        if self._model is None:
            self._model = LatexOCR()
        suffix = Path(filename).suffix.casefold()
        if suffix in {".wmf", ".emf"}:
            with _work_directory("formula-ocr-") as temp:
                path = _render_metafile(data, suffix, Path(temp))
                with Image.open(path) as image:
                    result = self._model(image.convert("RGB"))
        else:
            with Image.open(BytesIO(data)) as image:
                result = self._model(image.convert("RGB"))
        return str(result).strip()


def _render_metafile(data: bytes, suffix: str, directory: Path) -> Path:
    powershell = shutil.which("powershell")
    if powershell is None:
        raise RuntimeError("WMF/EMF OCR requires the Windows PowerShell GDI renderer")
    source = directory / f"source{suffix}"
    destination = directory / "preview.png"
    source.write_bytes(data)

    def quoted(path: Path) -> str:
        return "'" + str(path).replace("'", "''") + "'"

    script = (
        "Add-Type -AssemblyName System.Drawing; "
        f"$m=[System.Drawing.Imaging.Metafile]::new({quoted(source)}); "
        "$b=[System.Drawing.Bitmap]::new([Math]::Max(1,$m.Width),[Math]::Max(1,$m.Height)); "
        "$g=[System.Drawing.Graphics]::FromImage($b); "
        "$g.Clear([System.Drawing.Color]::White); "
        "$g.DrawImage($m,0,0,$b.Width,$b.Height); "
        f"$b.Save({quoted(destination)},[System.Drawing.Imaging.ImageFormat]::Png); "
        "$g.Dispose(); $b.Dispose(); $m.Dispose()"
    )
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    if result.returncode != 0 or not destination.exists():
        raise RuntimeError(f"WMF/EMF rendering failed: {result.stderr[-300:]}")
    return destination


def metafile_png(data: bytes, suffix: str) -> bytes:
    """Render a WMF/EMF preview; the original file remains the evidence."""

    with _work_directory("formula-preview-") as temp:
        return _render_metafile(data, suffix, Path(temp)).read_bytes()


def _work_directory(prefix: str) -> TemporaryDirectory[str]:
    # The project keeps all generated data under one ignored relative root.
    root = Path("data/derived/.formula-work")
    root.mkdir(parents=True, exist_ok=True)
    return TemporaryDirectory(prefix=prefix, dir=root)
