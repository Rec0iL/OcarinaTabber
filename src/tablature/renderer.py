"""QGraphicsScene-based font tab renderer."""

from __future__ import annotations
from typing import List

from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsItem, QGraphicsObject
from PySide6.QtCore import Qt, QRectF, QPointF, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QPainterPath
)

from .font_tab import FontNote, ocarina_font_family


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


FONT_FRAME_W = 100
FONT_FRAME_H = 150
# Glyph pixel size — expressed in the frame's logical coordinate space so it
# scales correctly when the painter is transformed (e.g. for PDF export).
# Leaves ~22px for the note label at top and ~18px for the duration at bottom.
OCARINA_GLYPH_PX = FONT_FRAME_H - 44
FONT_STYLE = 1              # 1 or 2 for the two available font styles
PAUSE_BANNER_H = 60         # height of between-section pause banner frames
# Extra vertical space added before the first row and between every row so that
# the 1.18× active-highlight zoom never clips against adjacent rows or the
# scene edge.  (1.18 - 1) * FONT_FRAME_H / 2 ≈ 13.5 px; 18 px gives a margin.
FRAME_VPAD = 18

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
        ocarina_font = QFont(ocarina_font_family(note.hole_count, self._font_style))
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
        # Smooth-scroll animation targeting the vertical scrollbar value
        self._scroll_anim = QPropertyAnimation(self.verticalScrollBar(), b"value", self)
        self._scroll_anim.setDuration(400)
        self._scroll_anim.setEasingCurve(QEasingCurve.InOutCubic)
        # Scene-y of the last row we triggered a scroll for (-1 = none yet)
        self._scroll_target_row = -1.0

    def set_font_style(self, style: int) -> None:
        """Switch between font variant 1 and 2."""
        self._font_style = max(1, min(2, style))

    def load_tabs(self, font_notes: List[FontNote], cols: int = 8):
        self._scene.clear()
        self._items: List[FontTabItem] = []
        self._scroll_target_row = -1.0
        gap = 8
        row_step = FONT_FRAME_H + FRAME_VPAD * 2 + gap  # includes top+bottom pad per row
        banner_w = cols * (FONT_FRAME_W + gap) - gap

        col = 0
        cur_y = FRAME_VPAD  # top padding before first row

        for i, fn in enumerate(font_notes):
            if fn.is_pause:
                # Force a line break before the pause banner
                if col > 0:
                    cur_y += row_step
                    col = 0
                item = FontTabItem(fn, i, self._font_style,
                                   frame_w=banner_w, frame_h=PAUSE_BANNER_H)
                item.setPos(0, cur_y)
                self._scene.addItem(item)
                self._items.append(item)
                cur_y += PAUSE_BANNER_H + FRAME_VPAD + gap
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
                    cur_y += row_step

        total_w = cols * (FONT_FRAME_W + gap)
        total_h = (cur_y + FONT_FRAME_H + FRAME_VPAD) if col > 0 else cur_y
        self._scene.setSceneRect(0, 0, total_w, max(total_h, FONT_FRAME_H + FRAME_VPAD * 2))

    def set_active_index(self, idx: int) -> None:
        """Highlight frame at *idx* and scroll to keep the active note visible.

        Pass ``-1`` to clear all highlights.
        """
        for i, item in enumerate(self._items):
            item.set_active(i == idx)

        if idx < 0 or idx >= len(self._items):
            return

        item = self._items[idx]
        item_scene_y = item.pos().y()

        # Only scroll when the active note enters a new row.  Guarding here
        # prevents the animation from restarting on every note and accumulating
        # an ever-growing delta.
        if item_scene_y == self._scroll_target_row:
            return
        self._scroll_target_row = item_scene_y

        # Absolute scrollbar target: put this row's padded top at the viewport
        # top.  Using an absolute value (target_scene * scale) means the result
        # is always the same regardless of where the viewport currently is or
        # whether an animation is in progress.
        scale = self.transform().m22()
        target = int((item_scene_y - FRAME_VPAD - self.sceneRect().top()) * scale)
        sb = self.verticalScrollBar()
        target = max(sb.minimum(), min(target, sb.maximum()))

        if target == sb.value():
            return

        self._scroll_anim.stop()
        self._scroll_anim.setStartValue(sb.value())
        self._scroll_anim.setEndValue(target)
        self._scroll_anim.start()

    def wheelEvent(self, event) -> None:
        """Shift+wheel zooms in/out; plain wheel scrolls normally."""
        if event.modifiers() & Qt.ShiftModifier:
            factor = 1.15 if event.angleDelta().y() > 0 else 1.0 / 1.15
            self.scale(factor, factor)
            event.accept()
        else:
            super().wheelEvent(event)
