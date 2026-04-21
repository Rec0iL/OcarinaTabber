"""Export dialog — saves the tabs as A4 PDF."""

from __future__ import annotations
from typing import List

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QPushButton,
    QLabel, QFileDialog, QMessageBox, QLineEdit,
)
from PySide6.QtCore import Qt


class ExportDialog(QDialog):
    def __init__(self, scene, tab_notes: List, parent=None, default_title: str = "Ocarina Tabs"):
        super().__init__(parent)
        self._scene = scene
        self._tab_notes = tab_notes
        self._default_title = default_title
        self.setWindowTitle("Export Tabs")
        self.setMinimumWidth(360)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Title:"))
        self._title_edit = QLineEdit(self._default_title)
        title_row.addWidget(self._title_edit)
        layout.addLayout(title_row)

        layout.addWidget(QLabel("Click below to export as A4 PDF:"))

        btn_pdf = QPushButton("Export as PDF (A4)")
        btn_pdf.clicked.connect(self._export_pdf)
        layout.addWidget(btn_pdf)

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
            from ..export.pdf import export_pdf_a4
            export_pdf_a4(
                self._tab_notes,
                path,
                title=self._title_edit.text().strip() or "Ocarina Tabs",
            )
            QMessageBox.information(self, "Export", f"PDF saved to:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", str(e))
