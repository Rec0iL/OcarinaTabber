"""Main application window — wires all panels together."""

from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTabWidget,
    QVBoxLayout, QStatusBar,
)
from PySide6.QtCore import Qt

from .midi_panel import MidiPanel
from .ocarina_panel import OcarinaPanel
from .canvas_editor import CanvasEditor
from ..tablature.generator import generate_tabs
from ..tablature.renderer import TabRenderer
from ..ocarina.models import OcarinaType


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OcarinaTabber")
        self.resize(1280, 800)
        self._load_stylesheet()
        self._init_ui()
        self._wire_signals()

    def _load_stylesheet(self):
        qss_path = Path(__file__).parent / "style.qss"
        if qss_path.exists():
            self.setStyleSheet(qss_path.read_text())

    def _init_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(6, 6, 6, 6)

        # Main horizontal splitter: left sidebar | right content
        splitter = QSplitter(Qt.Horizontal)

        # ── Left sidebar ──────────────────────────────────────────────
        sidebar_tabs = QTabWidget()
        sidebar_tabs.setMinimumWidth(280)
        sidebar_tabs.setMaximumWidth(380)

        self._midi_panel = MidiPanel()
        sidebar_tabs.addTab(self._midi_panel, "MIDI")

        self._ocarina_panel = OcarinaPanel()
        sidebar_tabs.addTab(self._ocarina_panel, "Ocarina")

        self._canvas_editor = CanvasEditor()
        sidebar_tabs.addTab(self._canvas_editor, "Layout Editor")

        splitter.addWidget(sidebar_tabs)

        # ── Right content: tab viewer ─────────────────────────────────
        self._tab_renderer = TabRenderer()
        splitter.addWidget(self._tab_renderer)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

        # Status bar
        self._status = QStatusBar()
        self.setStatusBar(self._status)
        self._status.showMessage("Open a MIDI file to begin.")

    def _wire_signals(self):
        self._midi_panel.track_selected.connect(self._on_track_selected)
        self._ocarina_panel.ocarina_ready.connect(self._on_generate)
        self._canvas_editor.layout_changed.connect(self._on_layout_changed)

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_track_selected(self, midi_file, track):
        self._midi_file = midi_file
        self._track = track
        self._ocarina_panel.load_track(midi_file, track)
        self._status.showMessage(
            f"Track loaded: {track.name or 'Unnamed'} — {track.note_count} notes"
        )

    def _on_generate(self, ocarina: OcarinaType, notes: list):
        # Apply custom layout from canvas editor if it matches
        custom_holes = self._canvas_editor.get_current_layout()
        if custom_holes:
            ocarina.holes = custom_holes

        self._canvas_editor.set_ocarina(ocarina)

        tab_notes = generate_tabs(
            notes, ocarina,
            ticks_per_beat=getattr(self, "_midi_file", None)
            and self._midi_file.ticks_per_beat or 480,
        )
        self._tab_renderer.load_tabs(tab_notes)
        self._status.showMessage(f"Generated {len(tab_notes)} tab frames for {ocarina.name}.")

        # Add export buttons to status bar dynamically
        self._add_export_actions()

    def _on_layout_changed(self, holes):
        self._status.showMessage(f"Layout updated — {len(holes)} holes.")

    def _add_export_actions(self):
        from .export_dialog import ExportDialog
        if not hasattr(self, "_export_dialog"):
            btn_export = self._status.findChild(type(None))
            # Just expose via menu for cleanliness
            menu_bar = self.menuBar()
            if not menu_bar.findChild(type(None), "export_menu_added"):
                file_menu = menu_bar.addMenu("File")
                file_menu.setObjectName("export_menu_added")
                export_action = file_menu.addAction("Export Tabs…")
                export_action.triggered.connect(self._open_export)

    def _open_export(self):
        from .export_dialog import ExportDialog
        dlg = ExportDialog(self._tab_renderer.scene(), self)
        dlg.exec()
