"""QGraphicsScene-based tab renderer that draws TabNote frames."""

from __future__ import annotations
from typing import List

from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsObject
from PySide6.QtCore import Qt, QRectF, QPointF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPainterPath
)

from .generator import TabNote
from .font_tab import FontNote


# ---------------------------------------------------------------------------
# Duration symbol renderer (QPainter, no font required)
# ---------------------------------------------------------------------------

def _draw_duration_symbol(
    painter: QPainter,
    cx: float,
    cy: float,
    label: str,
    color: QColor,
) -> None:
    """Draw a musical duration symbol centred at (cx, cy) using QPainter.

    All sizes are in the caller's logical coordinate space, so they scale
    correctly under any painter transform (e.g. PDF export at 300 DPI).

    label values from ticks_to_duration_label:
        "whole"  → hollow head, no stem
        "half"   → hollow head + stem
        "quarter"→ filled head + stem
        "eighth" → filled head + stem + 1 flag
        "16th"   → filled head + stem + 2 flags
    """
    # Map unicode label strings produced by ticks_to_duration_label
    if label in ("\U0001D15D\U0001D165",):          # 𝅝𝅗𝅥  whole
        filled, has_stem, flags = False, False, 0
    elif label in ("\U0001D15D",):                   # 𝅝    sixteenth
        filled, has_stem, flags = True,  True,  2
    elif label in ("\U0001D158\U0001D165",):         # 𝅗𝅥   half
        filled, has_stem, flags = False, True,  0
    elif label == "\u266A":                          # ♪    eighth
        filled, has_stem, flags = True,  True,  1
    elif label == "\u2669":                          # ♩    quarter
        filled, has_stem, flags = True,  True,  0
    else:
        # Fallback: quarter note
        filled, has_stem, flags = True, True, 0

    head_rx = 5.0
    head_ry = 3.5
    stem_h  = 14.0

    # Shift head slightly left when there is a stem so the stem tip stays centred
    hx = cx - 1.5 if has_stem else cx
    hy = cy

    pen = QPen(color, 1.2)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QBrush(color) if filled else Qt.NoBrush)
    painter.drawEllipse(QPointF(hx, hy), head_rx, head_ry)

    if not has_stem:
        return

    sx = hx + head_rx - 0.5          # x of stem (right edge of head)
    top_y = hy - stem_h
    painter.drawLine(QPointF(sx, hy - head_ry + 1), QPointF(sx, top_y))

    painter.setBrush(Qt.NoBrush)
    for i in range(flags):
        fy = top_y + i * 5.0
        path = QPainterPath()
        path.moveTo(sx, fy)
        path.cubicTo(sx + 9, fy + 3, sx + 7, fy + 9, sx + 2, fy + 11)
        painter.drawPath(path)

def _draw_pause_banner(
    painter: QPainter,
    w: float,
    h: float,
    colors: dict,
    active: bool,
    pause_duration_s: float = 0.0,
) -> None:
    """Draw a wide pause banner indicating a long silence between notes."""
    pause_color  = QColor("#f9e2af") if active else colors["pause"]
    border_color = QColor("#f9e2af") if active else colors["border"]

    painter.setPen(QPen(border_color, 2.0 if active else 1.0))
    painter.setBrush(QBrush(colors["bg"]))
    painter.drawRoundedRect(0, 0, w, h, 6, 6)

    # Pause-button icon: two vertical rounded bars centred in the banner
    bar_w = 7.0
    bar_h = h * 0.48
    cx, cy = w / 2, h / 2 - 4
    painter.setPen(Qt.NoPen)
    painter.setBrush(QBrush(pause_color))
    painter.drawRoundedRect(QRectF(cx - 11, cy - bar_h / 2, bar_w, bar_h), 3, 3)
    painter.drawRoundedRect(QRectF(cx + 4,  cy - bar_h / 2, bar_w, bar_h), 3, 3)

    # Duration label below the icon
    font = QFont("Segoe UI", -1)
    font.setPixelSize(11)
    painter.setFont(font)
    painter.setPen(pause_color)
    lbl = f"~{pause_duration_s:.0f}s pause" if pause_duration_s >= 1.0 else "pause"
    painter.drawText(QRectF(0, cy + bar_h / 2 + 4, w, 16), Qt.AlignCenter, lbl)


HOLE_OPEN_COLOR   = QColor("#FFFFFF")
HOLE_CLOSED_COLOR = QColor("#2a2a2a")
HOLE_BORDER_COLOR = QColor("#888888")
FRAME_BG_COLOR    = QColor("#1e1e2e")
FRAME_BORDER      = QColor("#44475a")
NOTE_TEXT_COLOR   = QColor("#cdd6f4")
DURATION_COLOR    = QColor("#89b4fa")

FRAME_W = 90
FRAME_H = 130
FRAME_PADDING = 12
HOLE_RADIUS = 8
THUMB_RADIUS = 6
SUB_HOLE_RADIUS = 4     # sub-holes are physically smaller


class TabFrameItem(QGraphicsItem):
    """A single ocarina tab frame drawn as a QGraphicsItem."""

    def __init__(self, tab_note: TabNote, index: int):
        super().__init__()
        self._tab = tab_note
        self._index = index
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, FRAME_W, FRAME_H)

    def paint(self, painter: QPainter, option, widget=None):
        tab = self._tab
        w, h = FRAME_W, FRAME_H

        # Background
        painter.setPen(QPen(FRAME_BORDER, 1))
        painter.setBrush(QBrush(FRAME_BG_COLOR))
        painter.drawRoundedRect(0, 0, w, h, 6, 6)

        # Note name at top
        font = QFont("Segoe UI", 11, QFont.Bold)
        painter.setFont(font)
        painter.setPen(NOTE_TEXT_COLOR)
        painter.drawText(QRectF(0, 4, w, 20), Qt.AlignCenter, tab.note_name)

        # Duration label
        dur_font = QFont("Segoe UI", 9)
        painter.setFont(dur_font)
        painter.setPen(DURATION_COLOR)
        painter.drawText(QRectF(0, h - 20, w, 16), Qt.AlignCenter, tab.duration_label)

        # Holes
        body_top = 28
        body_h = h - 52
        body_w = w - 24

        if tab.fingering is not None:
            closed = set(tab.fingering.closed_holes)
            half_open = set(tab.fingering.half_open_holes)
        else:
            closed = set()
            half_open = set()
            # Mark as out-of-range with red tint
            painter.setPen(QPen(QColor("#f38ba8"), 1.5))
            painter.setBrush(Qt.NoBrush)
            painter.drawRoundedRect(2, 2, w - 4, h - 4, 6, 6)

        for hole in tab.holes:
            cx = 12 + hole.x * body_w
            cy = body_top + hole.y * body_h
            if hole.is_thumb:
                r = THUMB_RADIUS
            elif hole.is_subhole:
                r = SUB_HOLE_RADIUS
            else:
                r = HOLE_RADIUS
            is_closed = hole.hole_id in closed
            is_half = hole.hole_id in half_open
            border_color = QColor("#89b4fa") if hole.is_subhole else HOLE_BORDER_COLOR
            painter.setPen(QPen(border_color, 1.2))
            if is_half:
                # Draw half-open: left semicircle closed, right semicircle open
                path_closed = QPainterPath()
                path_closed.moveTo(cx, cy - r)
                path_closed.arcTo(cx - r, cy - r, r * 2, r * 2, 90, 180)
                path_closed.closeSubpath()
                painter.setBrush(QBrush(HOLE_CLOSED_COLOR))
                painter.drawPath(path_closed)
                path_open = QPainterPath()
                path_open.moveTo(cx, cy - r)
                path_open.arcTo(cx - r, cy - r, r * 2, r * 2, 90, -180)
                path_open.closeSubpath()
                painter.setBrush(QBrush(HOLE_OPEN_COLOR))
                painter.drawPath(path_open)
                painter.setBrush(Qt.NoBrush)
                painter.drawEllipse(QPointF(cx, cy), r, r)
            else:
                painter.setBrush(QBrush(HOLE_CLOSED_COLOR if is_closed else HOLE_OPEN_COLOR))
                painter.drawEllipse(QPointF(cx, cy), r, r)


class TabRenderer(QGraphicsView):
    """Scrollable view that displays all tab frames in a horizontal flow."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setStyleSheet("background: #181825; border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

    def load_tabs(self, tab_notes: List[TabNote], cols: int = 8):
        self._scene.clear()
        gap = 10
        for i, tab_note in enumerate(tab_notes):
            col = i % cols
            row = i // cols
            item = TabFrameItem(tab_note, i)
            item.setPos(col * (FRAME_W + gap), row * (FRAME_H + gap))
            self._scene.addItem(item)

        total_w = cols * (FRAME_W + gap)
        rows = (len(tab_notes) + cols - 1) // max(cols, 1)
        total_h = rows * (FRAME_H + gap)
        self._scene.setSceneRect(0, 0, total_w, total_h)


# ── Font-based renderer ────────────────────────────────────────────────────

FONT_FRAME_W = 100
FONT_FRAME_H = 150
# Glyph pixel size — expressed in the frame's logical coordinate space so it
# scales correctly when the painter is transformed (e.g. for PDF export).
# Leaves ~22px for the note label at top and ~18px for the duration at bottom.
OCARINA_GLYPH_PX = FONT_FRAME_H - 44
FONT_STYLE = 1              # 1 or 2 for the two available font styles
PAUSE_BANNER_H = 60         # height of between-section pause banner frames

# Colour palettes
_SCREEN_COLORS = dict(
    label    = QColor("#cdd6f4"),
    duration = QColor("#89b4fa"),
    bg       = QColor("#1e1e2e"),
    border   = QColor("#44475a"),
    oor      = QColor("#f38ba8"),
    pause    = QColor("#6c7086"),
)
_PRINT_COLORS = dict(
    label    = QColor("#000000"),
    duration = QColor("#333333"),
    bg       = QColor("#ffffff"),
    border   = QColor("#888888"),
    oor      = QColor("#cc0000"),
    pause    = QColor("#aaaaaa"),
)


class FontTabItem(QGraphicsObject):
    """A tab frame rendered using the Open 12 Hole Ocarina TTF font glyph.

    Parameters
    ----------
    print_mode:
        When *True* the frame is drawn with white background and black ink,
        suitable for PDF/print output.  Defaults to *False* (dark-mode screen).
    """

    def __init__(
        self,
        font_note: FontNote,
        index: int,
        font_style: int = 1,
        print_mode: bool = False,
        frame_w: float = 0.0,
        frame_h: float = 0.0,
    ):
        super().__init__()
        self._note = font_note
        self._index = index
        self._font_style = font_style
        self._colors = _PRINT_COLORS if print_mode else _SCREEN_COLORS
        self._active = False
        self._fw = frame_w if frame_w > 0.0 else FONT_FRAME_W
        self._fh = frame_h if frame_h > 0.0 else FONT_FRAME_H
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        # Zoom from the centre of the frame
        self.setTransformOriginPoint(self._fw / 2, self._fh / 2)
        # Scale animation — reused on every activate/deactivate
        self._anim = QPropertyAnimation(self, b"scale", self)
        self._anim.setDuration(150)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_active(self, active: bool) -> None:
        """Highlight this frame as the currently playing note."""
        if self._active == active:
            return
        self._active = active
        self.setZValue(10 if active else 0)  # float to top so zoom doesn't hide under neighbours
        self.update()
        self._anim.stop()
        self._anim.setStartValue(self.scale())
        self._anim.setEndValue(1.18 if active else 1.0)
        self._anim.start()

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, self._fw, self._fh)

    def paint(self, painter: QPainter, option, widget=None):
        note = self._note
        w, h = self._fw, self._fh
        c = self._colors

        if note.is_pause:
            _draw_pause_banner(painter, w, h, c, self._active, note.pause_duration_s)
            return

        # Background
        border = c["oor"] if note.is_out_of_range else c["border"]
        pen_w = 2.5 if self._active else (1.5 if note.is_out_of_range else 1)
        border_color = QColor("#f9e2af") if self._active else border  # warm highlight when playing
        painter.setPen(QPen(border_color, pen_w))
        painter.setBrush(QBrush(c["bg"]))
        painter.drawRoundedRect(0, 0, w, h, 6, 6)

        # Note name at top — pixel size so it doesn't blow up at printer DPI
        label_font = QFont("Segoe UI", -1, QFont.Bold)
        label_font.setPixelSize(13)
        painter.setFont(label_font)
        painter.setPen(c["label"])
        painter.drawText(QRectF(0, 4, w, 18), Qt.AlignCenter, note.note_name)

        # Ocarina glyph — pixel size so it scales with any painter transform
        ocarina_font = QFont(f"Open 12 Hole Ocarina {self._font_style}")
        ocarina_font.setPixelSize(OCARINA_GLYPH_PX)
        painter.setFont(ocarina_font)
        painter.setPen(c["oor"] if note.is_out_of_range else c["label"])
        painter.drawText(
            QRectF(0, 22, w, h - 40),
            Qt.AlignCenter | Qt.AlignVCenter,
            "?" if note.is_out_of_range else note.font_char,
        )

        # Duration symbol at bottom — drawn with QPainter, no font needed
        _draw_duration_symbol(
            painter,
            cx=w / 2,
            cy=h - 10,
            label=note.duration_label,
            color=c["duration"],
        )


class FontTabRenderer(QGraphicsView):
    """Scrollable view that displays font-based ocarina tab frames."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setStyleSheet("background: #181825; border: none;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self._font_style = FONT_STYLE
        self._items: List[FontTabItem] = []
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

    def set_font_style(self, style: int) -> None:
        """Switch between font variant 1 and 2."""
        self._font_style = max(1, min(2, style))

    def load_tabs(self, font_notes: List[FontNote], cols: int = 8):
        self._scene.clear()
        self._items: List[FontTabItem] = []
        gap = 8
        banner_w = cols * (FONT_FRAME_W + gap) - gap

        col = 0
        cur_y = 0.0

        for i, fn in enumerate(font_notes):
            if fn.is_pause:
                # Force a line break before the pause banner
                if col > 0:
                    cur_y += FONT_FRAME_H + gap
                    col = 0
                item = FontTabItem(fn, i, self._font_style,
                                   frame_w=banner_w, frame_h=PAUSE_BANNER_H)
                item.setPos(0, cur_y)
                self._scene.addItem(item)
                self._items.append(item)
                cur_y += PAUSE_BANNER_H + gap
                # col stays 0 — next note starts a new row
            else:
                x = col * (FONT_FRAME_W + gap)
                item = FontTabItem(fn, i, self._font_style)
                item.setPos(x, cur_y)
                self._scene.addItem(item)
                self._items.append(item)
                col += 1
                if col >= cols:
                    col = 0
                    cur_y += FONT_FRAME_H + gap

        total_w = cols * (FONT_FRAME_W + gap)
        total_h = (cur_y + FONT_FRAME_H) if col > 0 else cur_y
        self._scene.setSceneRect(0, 0, total_w, max(total_h, FONT_FRAME_H))

    def set_active_index(self, idx: int) -> None:
        """Highlight the frame at *idx* and scroll it into view.

        Pass ``-1`` to clear all highlights.
        """
        for i, item in enumerate(self._items):
            item.set_active(i == idx)
        if 0 <= idx < len(self._items):
            self.ensureVisible(self._items[idx], 20, 20)

    def wheelEvent(self, event) -> None:
        """Shift+wheel zooms in/out; plain wheel scrolls normally."""
        if event.modifiers() & Qt.ShiftModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)
