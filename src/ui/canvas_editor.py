"""Drag-and-drop canvas editor for custom ocarina hole layouts."""

from __future__ import annotations
from typing import List, Optional, Callable

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QGraphicsScene, QGraphicsView, QGraphicsEllipseItem,
    QGraphicsTextItem, QGraphicsItem, QInputDialog, QColorDialog,
    QSizePolicy, QFrame,
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont

from ..ocarina.models import HoleLayout, OcarinaType


CANVAS_W = 420
CANVAS_H = 320
HOLE_DISPLAY_R = 18
THUMB_DISPLAY_R = 13
SUB_HOLE_DISPLAY_R = 11       # sub-holes are physically smaller than main holes
BODY_COLOR  = QColor("#313244")
HOLE_OPEN   = QColor("#cdd6f4")
HOLE_CLOSED = QColor("#1e1e2e")
BORDER_CLR  = QColor("#6c7086")
SUBHOLE_BORDER = QColor("#89b4fa")  # blue tint to distinguish sub-holes
LABEL_CLR   = QColor("#1e1e2e")    # dark — readable on the light hole fill


class DraggableHole(QGraphicsEllipseItem):
    """A movable, selectable hole circle on the canvas."""

    def __init__(self, hole: HoleLayout, radius: float):
        r = radius
        super().__init__(-r, -r, r * 2, r * 2)
        self._hole = hole
        self._radius = r
        self.setFlags(
            QGraphicsItem.ItemIsMovable |
            QGraphicsItem.ItemIsSelectable |
            QGraphicsItem.ItemSendsGeometryChanges
        )
        self.setPos(hole.x * CANVAS_W, hole.y * CANVAS_H)
        self._refresh_style()

        self._label = QGraphicsTextItem(hole.label, self)
        self._label.setDefaultTextColor(LABEL_CLR)
        font = QFont("Segoe UI", 7, QFont.Bold)
        self._label.setFont(font)
        bw = self._label.boundingRect().width()
        bh = self._label.boundingRect().height()
        self._label.setPos(-bw / 2, -bh / 2)
        self._label.setFlag(QGraphicsItem.ItemIgnoresParentOpacity, True)

    def _refresh_style(self):
        border = SUBHOLE_BORDER if self._hole.is_subhole else BORDER_CLR
        self.setPen(QPen(border, 1.5))
        self.setBrush(QBrush(HOLE_OPEN))

    @property
    def hole(self) -> HoleLayout:
        return self._hole

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged and self.scene():
            # Clamp within canvas
            x = max(self._radius, min(CANVAS_W - self._radius, self.pos().x()))
            y = max(self._radius, min(CANVAS_H - self._radius, self.pos().y()))
            self.setPos(x, y)
            # Update normalized position on the model
            self._hole.x = x / CANVAS_W
            self._hole.y = y / CANVAS_H
        return super().itemChange(change, value)


class HoleCanvasScene(QGraphicsScene):
    layout_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(0, 0, CANVAS_W, CANVAS_H, parent)
        self._hole_items: List[DraggableHole] = []
        # Body silhouette
        self._draw_body()

    def _draw_body(self):
        pen = QPen(QColor("#585b70"), 2)
        brush = QBrush(BODY_COLOR)
        self.addRect(30, 20, CANVAS_W - 60, CANVAS_H - 40, pen, brush)

    def load_holes(self, holes: List[HoleLayout]):
        # Remove old hole items
        for item in self._hole_items:
            self.removeItem(item)
        self._hole_items.clear()

        for hole in holes:
            if hole.is_thumb:
                r = THUMB_DISPLAY_R
            elif hole.is_subhole:
                r = SUB_HOLE_DISPLAY_R
            else:
                r = HOLE_DISPLAY_R
            item = DraggableHole(hole, r)
            self.addItem(item)
            self._hole_items.append(item)

    def get_holes(self) -> List[HoleLayout]:
        return [item.hole for item in self._hole_items]


class CanvasEditor(QWidget):
    """
    Full drag-and-drop ocarina hole layout editor widget.
    Emits `layout_changed` whenever the user moves a hole.
    """
    layout_changed = Signal(list)  # emits List[HoleLayout]

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ocarina: Optional[OcarinaType] = None
        self._init_ui()

    def _init_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        # Toolbar
        toolbar = QHBoxLayout()
        self._lbl_title = QLabel("Hole Layout Editor")
        self._lbl_title.setStyleSheet("color: #cdd6f4; font-weight: bold; font-size: 13px;")
        toolbar.addWidget(self._lbl_title)
        toolbar.addStretch()

        btn_reset = QPushButton("Reset to Preset")
        btn_reset.setToolTip("Restore holes to the default positions for the selected ocarina type")
        btn_reset.clicked.connect(self._reset_to_preset)
        toolbar.addWidget(btn_reset)

        root.addLayout(toolbar)

        # Canvas view
        self._scene = HoleCanvasScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.Antialiasing)
        self._view.setFixedSize(CANVAS_W + 4, CANVAS_H + 4)
        self._view.setStyleSheet("background: #181825; border: 1px solid #45475a;")
        self._view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        root.addWidget(self._view, alignment=Qt.AlignHCenter)

        hint = QLabel("Drag holes to match your ocarina's physical layout.")
        hint.setStyleSheet("color: #6c7086; font-size: 10px;")
        root.addWidget(hint, alignment=Qt.AlignHCenter)

    def set_ocarina(self, ocarina: OcarinaType):
        self._ocarina = ocarina
        self._scene.load_holes(list(ocarina.holes))
        self._lbl_title.setText(f"Hole Layout — {ocarina.name}")
        self.layout_changed.emit(self._scene.get_holes())

    def _reset_to_preset(self):
        if self._ocarina:
            self._scene.load_holes(list(self._ocarina.holes))
            self.layout_changed.emit(self._scene.get_holes())

    def get_current_layout(self) -> List[HoleLayout]:
        return self._scene.get_holes()
