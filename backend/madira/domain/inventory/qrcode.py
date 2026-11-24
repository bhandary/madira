"""Scannable bin labels as SVG.

The drawing is a real QR code from ``segno``, which is pure Python and has no
native image library. Error correction is level M, so a printed cellar label
still scans with a small smudge or crease. The payload is stored on the bin;
this module only renders it.
"""

from __future__ import annotations

import io
from xml.sax.saxutils import escape

import segno


def qr_svg(payload: str) -> str:
    """Return an SVG document for ``payload``."""

    text = str(payload)
    if not text:
        raise ValueError("QR payload is empty")
    code = segno.make(text, error="m", micro=False)
    buffer = io.BytesIO()
    code.save(
        buffer,
        kind="svg",
        xmldecl=False,
        svgns=True,
        scale=4,
        border=4,
        dark="#1c1917",
        light="#f5f5f4",
    )
    svg = buffer.getvalue().decode("utf-8")
    start = svg.find("<svg")
    if start < 0:
        raise RuntimeError("QR SVG was empty")
    tag_end = svg.find(">", start)
    if tag_end < 0:
        raise RuntimeError("QR SVG was empty")
    desc = f"<desc>{escape(text)}</desc>"
    return svg[: tag_end + 1] + desc + svg[tag_end + 1 :]
