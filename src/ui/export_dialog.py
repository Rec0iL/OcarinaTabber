"""Export dialog — saves the tab scene as PDF or PNG."""

from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox, QProgressBar,
)
from PySide6.QtCore import Qt, QRectF, QMarginsF
from PySide6.QtGui import QPainter, QImage, QPageLayout, QPageSize
from PySide6.QtPrintSupport import QPrinter

try:
    from PySide6.QtPdf import QPdfWriter
    _HAS_PDF_WRITER = True
except ImportError:
    _HAS_PDF_WRITER = False


class ExportDialog(QDialog):
    def __init__(self, scene, parent=None):
        super().__init__(parent)
        self._scene = scene
        self.setWindowTitle("Export Tabs")
        self.setMinimumWidth(340)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Choose export format:"))

        self._progress = QProgressBar()
        self._progress.setVisible(False)
        layout.addWidget(self._progress)

        btn_row = QHBoxLayout()

        btn_pdf = QPushButton("Export as PDF")
        btn_pdf.clicked.connect(self._export_pdf)
        btn_row.addWidget(btn_pdf)

        btn_png = QPushButton("Export as PNG")
        btn_png.clicked.connect(self._export_png)
        btn_row.addWidget(btn_png)

        layout.addLayout(btn_row)

        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        layout.addWidget(btn_close, alignment=Qt.AlignRight)

    def _export_pdf(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PDF", "ocarina_tabs.pdf", "PDF Files (*.pdf)"
        )
        if not path:
            return
        try:
            printer = QPrinter(QPrinter.HighResolution)
            printer.setOutputFormat(QPrinter.PdfFormat)
            printer.setOutputFileName(path)
            printer.setPageOrientation(QPageLayout.Landscape)

            painter = QPainter()
            if not painter.begin(printer):
                raise RuntimeError("Could not open PDF for writing.")

            scene_rect = self._scene.sceneRect()
            page_rect = QRectF(painter.viewport())
            scale = min(
                page_rect.width() / scene_rect.width(),
                page_rect.height() / scene_rect.height(),
            )
            painter.scale(scale, scale)
            self._scene.render(painter, source=scene_rect)
            painter.end()
            QMessageBox.information(self, "Export", f"PDF saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))

    def _export_png(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save PNG", "ocarina_tabs.png", "PNG Images (*.png)"
        )
        if not path:
            return
        try:
            scene_rect = self._scene.sceneRect()
            scale = 2  # 2× for high-DPI
            img = QImage(
                int(scene_rect.width() * scale),
                int(scene_rect.height() * scale),
                QImage.Format_ARGB32,
            )
            img.fill(Qt.transparent)
            painter = QPainter(img)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.scale(scale, scale)
            self._scene.render(painter)
            painter.end()
            img.save(path, "PNG")
            QMessageBox.information(self, "Export", f"PNG saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
