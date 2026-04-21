"""QGraphicsScene-based tab renderer that draws TabNote frames."""

from __future__ import annotations
from typing import List

from PySide6.QtWidgets import QGraphicsScene, QGraphicsView, QGraphicsItem
from PySide6.QtCore import Qt, QRectF, QPointF
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
)

from .generator import TabNote


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
        else:
            closed = set()
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
            border_color = QColor("#89b4fa") if hole.is_subhole else HOLE_BORDER_COLOR
            painter.setPen(QPen(border_color, 1.2))
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
