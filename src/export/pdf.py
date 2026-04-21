"""A4 multi-page PDF export for ocarina tabs."""

from __future__ import annotations
from typing import List, Optional

from PySide6.QtCore import QRectF, QPointF, Qt, QMarginsF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPageLayout, QPageSize,
)
from PySide6.QtPrintSupport import QPrinter

# Imported lazily to avoid circular imports at module level
# from ..tablature.renderer import TabFrameItem, FRAME_W, FRAME_H
# from ..tablature.generator import TabNote

# A4 layout constants
_COLS = 6           # tab frames per row
_FRAME_GAP_MM = 3   # gap between frames (mm)
_MARGIN_MM = 12     # page margin (mm)
_TITLE_H_MM = 10    # height reserved for header on every page


def export_pdf_a4(
    tab_notes,           # List[FontNote]
    path: str,
    title: str = "Ocarina Tabs",
) -> None:
    """Render *tab_notes* as a multi-page A4 portrait PDF at *path*.

    Each page holds a grid of FONT_FRAME_W×FONT_FRAME_H tab frames, scaled
    uniformly to fill the usable width.  The first page carries a title header.
    """
    from ..tablature.renderer import FontTabItem, FONT_FRAME_W, FONT_FRAME_H

    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)

    page_layout = QPageLayout(
        QPageSize(QPageSize.A4),
        QPageLayout.Portrait,
        QMarginsF(_MARGIN_MM, _MARGIN_MM, _MARGIN_MM, _MARGIN_MM),
        QPageLayout.Millimeter,
    )
    printer.setPageLayout(page_layout)

    painter = QPainter()
    if not painter.begin(printer):
        raise RuntimeError("Could not open PDF writer for output file.")

    # All coordinates are now in device pixels.
    page_rect = QRectF(printer.pageRect(QPrinter.DevicePixel))
    dpi = printer.resolution()               # dots per inch
    mm_to_px = dpi / 25.4

    gap_px = _FRAME_GAP_MM * mm_to_px
    title_h_px = _TITLE_H_MM * mm_to_px

    # Scale factor: make COLS frames fit exactly across the usable width
    frame_scale = (page_rect.width() - (_COLS - 1) * gap_px) / (_COLS * FONT_FRAME_W)
    scaled_fw = FONT_FRAME_W * frame_scale
    scaled_fh = FONT_FRAME_H * frame_scale

    # How many rows fit per page (every page has a header)
    rows_per_page = max(1, int((page_rect.height() - title_h_px - gap_px) / (scaled_fh + gap_px)))
    frames_per_page = _COLS * rows_per_page
    total_pages = max(1, (len(tab_notes) + frames_per_page - 1) // frames_per_page)

    def _draw_header(p: QPainter, page_num: int):
        font = QFont("Segoe UI", -1, QFont.Bold)
        font.setPixelSize(int(title_h_px * 0.65))
        p.setFont(font)
        p.setPen(QColor("#000000"))
        header_text = f"{title}  —  Page {page_num} / {total_pages}"
        p.drawText(
            QRectF(0, 0, page_rect.width(), title_h_px),
            Qt.AlignVCenter | Qt.AlignLeft,
            header_text,
        )

    def _draw_page_frames(p: QPainter, frames):
        y_offset = title_h_px + gap_px
        for i, font_note in enumerate(frames):
            col = i % _COLS
            row = i // _COLS
            x = col * (scaled_fw + gap_px)
            y = y_offset + row * (scaled_fh + gap_px)

            p.save()
            p.translate(x, y)
            p.scale(frame_scale, frame_scale)
            item = FontTabItem(font_note, 0, print_mode=True)
            item.paint(p, None, None)
            p.restore()

    # ── All pages ─────────────────────────────────────────────────────
    remaining = list(tab_notes)
    page_num = 1
    while remaining:
        if page_num > 1:
            printer.newPage()
        batch = remaining[:frames_per_page]
        remaining = remaining[frames_per_page:]
        _draw_header(painter, page_num)
        _draw_page_frames(painter, batch)
        page_num += 1

    painter.end()
