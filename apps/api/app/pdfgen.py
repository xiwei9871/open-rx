"""Minimal deterministic single-page PDF writer (EasyRS-owned layout).

No external dependency: emits a valid PDF 1.4 document with one Helvetica
text block. Used for the Rx summary sheet inside the lab delivery bundle —
our own layout, not a copy of any vendor's form.
"""

_MARG_X = 56
_TOP_Y = 760


def _esc(s: str) -> str:
    return s.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def simple_pdf(title: str, lines: list[tuple[str, str]]) -> bytes:
    """Render a title + (label, value) rows as a one-page PDF."""
    body = ["BT", "/F1 16 Tf", f"{_MARG_X} {_TOP_Y} Td", f"({_esc(title)}) Tj"]
    body += ["/F1 10 Tf", "0 -28 Td"]
    for label, value in lines:
        body.append(f"({_esc(label)}: {_esc(value)}) Tj")
        body.append("0 -16 Td")
    body.append("ET")
    stream = "\n".join(body).encode("latin-1", "replace")

    objects: list[bytes] = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
         b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)
