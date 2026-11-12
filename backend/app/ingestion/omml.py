"""Preserve Office Math equations and produce reviewable LaTeX candidates.

OMML is structured source data. This converter intentionally handles common
constructs and keeps the original XML whenever a candidate needs correction.
"""

from __future__ import annotations

from hashlib import sha256

from lxml import etree

MATH_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
INLINE_MATH_OPERATORS = {"+", "-", "−", "×", "÷", "=", "·", "*", "/"}


def math_id(element: etree._Element) -> str:
    return math_hash(element)[:16]


def math_hash(element: etree._Element) -> str:
    return sha256(etree.tostring(element, method="c14n")).hexdigest()


def math_marker(element: etree._Element) -> str:
    return f"[CÔNG THỨC OMML: {math_id(element)}]"


def to_latex(element: etree._Element) -> str:
    """Best-effort transcription; callers must mark it as unverified."""

    return _convert(element).strip()


def inline_math_component(element: etree._Element) -> str | None:
    """Return a plain operator when OMML only carries one inline component."""

    value = to_latex(element).strip()
    return value if value in INLINE_MATH_OPERATORS else None


def _child(element: etree._Element, name: str) -> etree._Element | None:
    return element.find(f"{{{MATH_NS}}}{name}")


def _part(element: etree._Element, name: str) -> str:
    child = _child(element, name)
    return _convert(child) if child is not None else ""


def _convert(element: etree._Element | None) -> str:
    if element is None:
        return ""
    tag = etree.QName(element).localname
    if tag == "t":
        return element.text or ""
    if tag == "r":
        value = "".join(_convert(child) for child in element if etree.QName(child).localname == "t")
        if value.strip() in INLINE_MATH_OPERATORS:
            return value.strip()
        props = element.find(f"{{{WORD_NS}}}rPr/{{{WORD_NS}}}vertAlign")
        vertical = props.get(f"{{{WORD_NS}}}val") if props is not None else None
        if vertical == "subscript":
            return f"_{{{value}}}"
        if vertical == "superscript":
            return f"^{{{value}}}"
        return value
    if tag == "f":
        return f"\\frac{{{_part(element, 'num')}}}{{{_part(element, 'den')}}}"
    if tag in {"sSub", "sSup", "sSubSup"}:
        base = _part(element, "e")
        sub = f"_{{{_part(element, 'sub')}}}" if tag in {"sSub", "sSubSup"} else ""
        sup = f"^{{{_part(element, 'sup')}}}" if tag in {"sSup", "sSubSup"} else ""
        return f"{base}{sub}{sup}"
    if tag == "nary":
        props = _child(element, "naryPr")
        char = _child(props, "chr") if props is not None else None
        symbol = char.get(f"{{{MATH_NS}}}val", "∑") if char is not None else "∑"
        operator = {"∑": "\\sum", "∏": "\\prod", "∫": "\\int"}.get(symbol, symbol)
        sub, sup, expression = (_part(element, key) for key in ("sub", "sup", "e"))
        return f"{operator}_{{{sub}}}^{{{sup}}} {expression}".strip()
    if tag == "rad":
        degree = _part(element, "deg")
        expression = _part(element, "e")
        return f"\\sqrt[{degree}]{{{expression}}}" if degree else f"\\sqrt{{{expression}}}"
    if tag == "d":
        props = _child(element, "dPr")
        opening = _child(props, "begChr") if props is not None else None
        closing = _child(props, "endChr") if props is not None else None
        left = opening.get(f"{{{MATH_NS}}}val", "(") if opening is not None else "("
        right = closing.get(f"{{{MATH_NS}}}val", ")") if closing is not None else ")"
        return f"{left}{_part(element, 'e')}{right}"
    if tag == "func":
        return f"{_part(element, 'fName')}({_part(element, 'e')})"
    if tag in {"oMath", "oMathPara", "e", "num", "den", "sub", "sup", "deg", "fName"}:
        return "".join(
            _convert(child) for child in element if etree.QName(child).namespace == MATH_NS
        )
    # Unknown constructs remain in the saved OMML XML and require review.
    return "".join(_convert(child) for child in element if etree.QName(child).namespace == MATH_NS)
