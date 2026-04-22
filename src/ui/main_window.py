"""Main application window — wires all panels together."""

from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTabWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStatusBar,
)
from PySide6.QtCore import Qt, QElapsedTimer, QTimer

from .midi_panel import MidiPanel
from .ocarina_panel import OcarinaPanel
from ..tablature.font_tab import load_ocarina_fonts, generate_font_tabs
from ..tablature.renderer import FontTabRenderer
from ..ocarina.models import OcarinaType


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("OcarinaTabber")
        self.resize(1280, 800)
        load_ocarina_fonts()   # register TTF fonts before any widget is created
        self._load_stylesheet()
        # Note-tracking state for playback highlighting
        self._play_font_notes: list = []
        self._elapsed = QElapsedTimer()
        self._note_timer = QTimer(self)
        self._note_timer.setInterval(40)
        self._note_timer.timeout.connect(self._on_note_tick)
        self._play_timestamps: list = []  # ms timestamps matching _play_font_notes
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

        splitter.addWidget(sidebar_tabs)

        # ── Right content: transport bar + tab viewer ────────────────────
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 4, 0, 0)
        right_layout.setSpacing(4)

        # Transport bar
        transport = QHBoxLayout()
        self._play_btn_main = QPushButton("▶  Play")
        self._play_btn_main.setEnabled(False)
        self._play_btn_main.setFixedWidth(110)
        self._play_btn_main.setStyleSheet(
            "QPushButton { background: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 5px; }"
            "QPushButton:hover { background: #94d09a; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        self._stop_btn_main = QPushButton("⏹  Stop")
        self._stop_btn_main.setEnabled(False)
        self._stop_btn_main.setFixedWidth(110)
        self._stop_btn_main.setStyleSheet(
            "QPushButton { background: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 5px; }"
            "QPushButton:hover { background: #e07090; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        self._playback_info = QLabel("Generate tabs first, then press Play.")
        self._playback_info.setStyleSheet("color: #6c7086; font-size: 10px; padding-left: 6px;")
        transport.addWidget(self._play_btn_main)
        transport.addWidget(self._stop_btn_main)
        transport.addWidget(self._playback_info, 1)
        right_layout.addLayout(transport)

        self._tab_renderer = FontTabRenderer()
        right_layout.addWidget(self._tab_renderer)

        splitter.addWidget(right_widget)

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
        self._play_btn_main.clicked.connect(self._midi_panel.play_current_track)
        self._stop_btn_main.clicked.connect(self._midi_panel.stop_current_track)
        self._midi_panel.playback_started.connect(self._on_playback_started)
        self._midi_panel.playback_stopped.connect(self._on_playback_stopped)

    # ── Slots ─────────────────────────────────────────────────────────
    def _on_track_selected(self, midi_file, track):
        self._midi_file = midi_file
        self._track = track
        self._ocarina_panel.load_track(midi_file, track)
        self._status.showMessage(
            f"Track loaded: {track.name or 'Unnamed'} — {track.note_count} notes"
        )

    def _on_generate(self, ocarina: OcarinaType, notes: list):
        ticks_per_beat = (
            self._midi_file.ticks_per_beat
            if hasattr(self, "_midi_file") else 480
        )
        tempo = self._midi_file.tempo if hasattr(self, "_midi_file") else 500_000

        # Font-based tab generation: maps MIDI pitch → TTF glyph character
        font_notes = generate_font_tabs(
            notes, ocarina.name, ticks_per_beat, tempo=tempo,
            tempo_map=self._midi_file.tempo_map if hasattr(self, "_midi_file") else [],
            hole_count=ocarina.hole_count,
        )
        self._font_notes = font_notes
        self._play_font_notes = font_notes
        self._tab_renderer.load_tabs(font_notes)
        self._play_btn_main.setEnabled(True)
        self._playback_info.setText(f"{len(font_notes)} notes ready — press Play to start.")
        self._status.showMessage(
            f"Generated {len(font_notes)} tab frames for {ocarina.name}."
        )

        # Add export buttons to status bar dynamically
        self._add_export_actions()

    def _on_playback_started(self, midi_file, track, mode: int):
        # mode 0 = single track (compressed timing), 1 = all tracks (original timing)
        self._play_timestamps = [
            fn.compressed_start_ms if mode == 0 else fn.start_ms
            for fn in self._play_font_notes
        ]
        # ── DEBUG: show which timestamps are being used ──────────────
        mode_label = "compressed_start_ms" if mode == 0 else "start_ms"
        print(f"[playback] mode={mode} ({mode_label}), first 5 timestamps:", flush=True)
        for i, (fn, ts) in enumerate(zip(self._play_font_notes, self._play_timestamps)):
            tag = "PAUSE" if fn.is_pause else fn.note_name
            print(f"  [{i}] {tag:6s}  ts={ts:.1f}ms", flush=True)
            if i >= 4:
                break
        # ─────────────────────────────────────────────────────────────
        self._elapsed.start()
        self._note_timer.start()
        self._play_btn_main.setEnabled(False)
        self._stop_btn_main.setEnabled(True)
        label = track.name or f"Track {track.index}"
        self._playback_info.setText(f"▶ Playing: {label}")

    def _on_playback_stopped(self):
        self._dbg_first_highlight_logged = False  # reset for next playback
        self._note_timer.stop()
        self._tab_renderer.set_active_index(-1)
        self._stop_btn_main.setEnabled(False)
        self._play_btn_main.setEnabled(bool(self._play_font_notes))
        self._playback_info.setText("Stopped." if self._play_font_notes else "Generate tabs first, then press Play.")

    def _on_note_tick(self):
        if not self._play_font_notes or not self._play_timestamps:
            return
        elapsed_ms = self._elapsed.elapsed()
        idx = -1  # nothing highlighted until the first note's timestamp is reached
        for i, ts in enumerate(self._play_timestamps):
            if ts <= elapsed_ms:
                idx = i
            else:
                break
        # ── DEBUG: log first time we obtain an idx >= 0 ─────────────
        if not hasattr(self, '_dbg_first_highlight_logged'):
            self._dbg_first_highlight_logged = False
        if idx >= 0 and not self._dbg_first_highlight_logged:
            self._dbg_first_highlight_logged = True
            fn = self._play_font_notes[idx]
            print(f"[tick] FIRST HIGHLIGHT: idx={idx}  note={fn.note_name}  "
                  f"ts={self._play_timestamps[idx]:.1f}ms  elapsed={elapsed_ms}ms", flush=True)
        # ─────────────────────────────────────────────────────────────
        self._tab_renderer.set_active_index(idx)

    def _add_export_actions(self):
        # Guard: only create the File menu once
        if hasattr(self, "_file_menu"):
            return
        from PySide6.QtWidgets import QMenu
        self._file_menu = QMenu("File", self)
        export_action = self._file_menu.addAction("Export Tabs…")
        export_action.triggered.connect(self._open_export)
        self.menuBar().addMenu(self._file_menu)

    def _open_export(self):
        from .export_dialog import ExportDialog
        midi_stem = self._midi_file.path.stem if hasattr(self, "_midi_file") else "Ocarina Tabs"
        dlg = ExportDialog(self._tab_renderer.scene(), getattr(self, "_font_notes", []), self, default_title=midi_stem)
        dlg.exec()
