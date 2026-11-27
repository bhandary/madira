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


def qr_png(payload: str, *, scale: int = 8, border: int = 4) -> bytes:
    """Return a PNG document for ``payload``. Segno draws the matrix; the PNG is stdlib."""

    text = str(payload)
    if not text:
        raise ValueError("QR payload is empty")
    code = segno.make(text, error="m", micro=False)
    modules = [[bool(int(cell) & 1) for cell in row] for row in code.matrix]
    if not modules or not modules[0]:
        raise RuntimeError("QR matrix was empty")
    quiet = max(int(border), 0)
    step = max(int(scale), 1)
    width = len(modules[0]) + quiet * 2
    height = len(modules) + quiet * 2
    pixels: list[list[int]] = []
    for y in range(height):
        row_y = y - quiet
        dark_row = modules[row_y] if 0 <= row_y < len(modules) else None
        scan = []
        for x in range(width):
            row_x = x - quiet
            dark = bool(dark_row and 0 <= row_x < len(dark_row) and dark_row[row_x])
            scan.extend([0 if dark else 255] * step)
        pixels.extend([scan] * step)
    return _png(pixels)


def _png(rows: list[list[int]]) -> bytes:
    import struct
    import zlib

    height = len(rows)
    width = len(rows[0]) if rows else 0
    if width < 1 or height < 1:
        raise RuntimeError("QR PNG was empty")

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + bytes(row) for row in rows)
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 0, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


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
