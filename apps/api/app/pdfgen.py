"""Prescription summary PDF (EasyRS-owned layout, not a vendor form copy).

ReportLab-based. Latin-1 lines render in Helvetica; any line containing a
character outside Latin-1 falls back to the built-in CID font STSong-Light
(Adobe-GB1, covers CJK + Latin) so Unicode text is never silently mangled
to '?'.
"""
import io

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas

_CID_REGISTERED = False
_MARG_X = 56
_TOP_Y = 770
_LINE = 15


def _latin1_ok(s: str) -> bool:
    try:
        s.encode("latin-1")
        return True
    except UnicodeEncodeError:
        return False


def _font_for(s: str) -> str:
    global _CID_REGISTERED
    if _latin1_ok(s):
        return "Helvetica"
    if not _CID_REGISTERED:
        pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
        _CID_REGISTERED = True
    return "STSong-Light"


def prescription_pdf(title: str, sections: list[tuple[str, list[str]]],
                     footer: str) -> bytes:
    """Render a title, then labelled sections of plain text lines."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    width, height = 612, 792
    y = _TOP_Y

    def line(text: str, size: int = 10) -> None:
        nonlocal y
        if y < 60:  # crude but safe pagination
            c.showPage()
            y = _TOP_Y
        c.setFont(_font_for(text), size)
        c.drawString(_MARG_X, y, text)
        y -= _LINE

    c.setFont("Helvetica-Bold", 14)
    c.drawString(_MARG_X, y, title if _latin1_ok(title) else title)
    y -= 24
    for heading, rows in sections:
        c.setFont("Helvetica-Bold", 11)
        c.drawString(_MARG_X, y, heading)
        y -= _LINE + 2
        for r in rows:
            line(r)
        y -= 6
    c.setFont(_font_for(footer), 8)
    c.drawString(_MARG_X, y - 4, footer)
    c.showPage()
    c.save()
    return buf.getvalue()
