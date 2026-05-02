"""Main application window — wires all panels together."""

from __future__ import annotations
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QSplitter, QTabWidget,
    QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QStatusBar, QComboBox,
)
from PySide6.QtCore import Qt, QElapsedTimer, QTimer

from ..midi.pitch_detector import PitchDetector, list_input_devices

from .midi_panel import MidiPanel
from .ocarina_panel import OcarinaPanel
from ..tablature.font_tab import load_ocarina_fonts, generate_font_tabs, FontNote, midi_to_font_char, ocarina_key_from_name
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
        # Mic-listen mode state
        self._pitch_detector: PitchDetector | None = None
        self._mic_cursor: int = 0          # index of the next expected note
        self._mic_active: bool = False
        self._calibration_semitones: float = 0.0
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

        # ── Mic-listen row ─────────────────────────────────────────────
        mic_row = QHBoxLayout()

        mic_lbl = QLabel("Mic:")
        mic_lbl.setStyleSheet("color: #cdd6f4; font-size: 10px;")
        mic_row.addWidget(mic_lbl)

        self._mic_combo = QComboBox()
        self._mic_combo.setStyleSheet(
            "QComboBox { background: #313244; color: #cdd6f4; font-size: 10px; padding: 2px 6px; }"
            "QComboBox::drop-down { border: none; }"
        )
        self._mic_combo.setMinimumWidth(160)
        self._mic_combo.addItem("(click ⟳ to scan)", None)
        mic_row.addWidget(self._mic_combo, 1)

        self._mic_refresh_btn = QPushButton("⟳")
        self._mic_refresh_btn.setFixedWidth(28)
        self._mic_refresh_btn.setToolTip("Scan for microphone devices")
        self._mic_refresh_btn.setStyleSheet(
            "QPushButton { background: #45475a; color: #cdd6f4; font-weight: bold; padding: 2px; }"
            "QPushButton:hover { background: #585b70; }"
        )
        self._mic_refresh_btn.clicked.connect(self._populate_mic_combo)
        mic_row.addWidget(self._mic_refresh_btn)

        self._listen_btn = QPushButton("🎙  Listen")
        self._listen_btn.setEnabled(False)
        self._listen_btn.setCheckable(True)
        self._listen_btn.setFixedWidth(110)
        self._listen_btn.setStyleSheet(
            "QPushButton { background: #89dceb; color: #1e1e2e; font-weight: bold; padding: 5px; }"
            "QPushButton:hover { background: #74c7ec; }"
            "QPushButton:checked { background: #f9e2af; color: #1e1e2e; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        mic_row.addWidget(self._listen_btn)

        self._calibrate_btn = QPushButton("🎯  Calibrate")
        self._calibrate_btn.setEnabled(False)
        self._calibrate_btn.setFixedWidth(110)
        self._calibrate_btn.setStyleSheet(
            "QPushButton { background: #cba6f7; color: #1e1e2e; font-weight: bold; padding: 5px; }"
            "QPushButton:hover { background: #b89de0; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        mic_row.addWidget(self._calibrate_btn)

        self._mic_status = QLabel("Load tabs, then press Listen.")
        self._mic_status.setStyleSheet("color: #6c7086; font-size: 10px; padding-left: 6px;")
        mic_row.addWidget(self._mic_status, 1)

        right_layout.addLayout(mic_row)

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
        self._listen_btn.toggled.connect(self._on_listen_toggled)
        self._calibrate_btn.clicked.connect(self._open_calibration)

    # ── Slots ─────────────────────────────────────────────────────────
    def _open_calibration(self) -> None:
        if not self._play_font_notes:
            return
        from .calibration_dialog import CalibrationDialog  # noqa: PLC0415
        from ..tablature.generator import midi_to_note_name  # noqa: PLC0415
        real_notes = [fn for fn in self._play_font_notes if not fn.is_pause]
        if not real_notes:
            return
        low_note = min(real_notes, key=lambda fn: fn.midi_pitch)
        # Always calibrate to the true top of the instrument (F6 = MIDI 89),
        # not just the highest note in the current track.
        _HIGH_MIDI = 89  # F6 — highest note on a 12-hole C ocarina
        hole_count = real_notes[0].hole_count
        key = ocarina_key_from_name(getattr(self, "_ocarina_name", "C"))
        high_note = FontNote(
            note_name=midi_to_note_name(_HIGH_MIDI),
            midi_pitch=_HIGH_MIDI,
            font_char=midi_to_font_char(_HIGH_MIDI, key),
            duration_label="\u2669",
            is_out_of_range=False,
            hole_count=hole_count,
        )
        # Stop listen mode before opening calibration
        if self._mic_active:
            self._stop_listen()
        device_idx = self._mic_combo.currentData()
        dlg = CalibrationDialog(low_note, high_note, device_index=device_idx, parent=self)
        dlg.calibration_done.connect(self._on_calibration_done)
        dlg.exec()

    def _on_calibration_done(self, semitones: float) -> None:
        self._calibration_semitones = semitones
        cents = semitones * 100.0
        if abs(cents) < 0.5:
            self._mic_status.setText("Calibration: none (in tune).")
        else:
            sign = "+" if cents >= 0 else ""
            direction = "flat" if cents > 0 else "sharp"
            self._mic_status.setText(
                f"Cal: {sign}{cents:.0f} ¢ ({direction}) — ready to Listen."
            )

    def _populate_mic_combo(self) -> None:
        """Enumerate input devices on demand (deferred to avoid PortAudio init at startup)."""
        self._mic_combo.clear()
        devices = list_input_devices()
        if not devices:
            self._mic_combo.addItem("(no mic found — install sounddevice)", -1)
            return
        self._mic_combo.addItem("Default input", None)
        for idx, name in devices:
            self._mic_combo.addItem(name, idx)

    def _on_listen_toggled(self, checked: bool) -> None:
        if checked:
            self._start_listen()
        else:
            self._stop_listen()

    def _start_listen(self) -> None:
        if not self._play_font_notes:
            self._listen_btn.setChecked(False)
            return
        # Stop any MIDI playback first
        self._midi_panel.stop_current_track()

        # Populate devices now if the user never hit ⟳
        if self._mic_combo.count() == 1 and self._mic_combo.itemData(0) is None \
                and self._mic_combo.itemText(0).startswith("(click"):
            self._populate_mic_combo()

        device_idx = self._mic_combo.currentData()
        self._pitch_detector = PitchDetector(device_index=device_idx, parent=self)
        self._pitch_detector.set_calibration(self._calibration_semitones)
        self._pitch_detector.pitch_detected.connect(self._on_pitch_detected)
        self._pitch_detector.start()

        self._mic_cursor = 0
        self._mic_active = True
        # Skip leading pause frames
        self._mic_cursor = self._next_real_note(self._mic_cursor)
        self._tab_renderer.set_active_index(self._mic_cursor)
        self._mic_status.setText(
            f"Listening… note 1/{self._playable_count()} — "
            f"play {self._target_note_name()}"
        )

    def _stop_listen(self) -> None:
        self._mic_active = False
        if self._pitch_detector is not None:
            self._pitch_detector.stop()
            self._pitch_detector = None
        self._tab_renderer.set_active_index(-1)
        self._mic_status.setText("Stopped.")
        self._listen_btn.setChecked(False)

    def _on_pitch_detected(self, midi_pitch: int) -> None:
        """Called from the detector thread (via Qt signal) on each new pitch."""
        if not self._mic_active or not self._play_font_notes:
            return
        if self._mic_cursor >= len(self._play_font_notes):
            self._stop_listen()
            self._mic_status.setText("Done! All notes played.")
            return

        target = self._play_font_notes[self._mic_cursor]
        if target.is_pause:
            # Auto-advance through pause frames
            self._mic_cursor = self._next_real_note(self._mic_cursor)
            self._tab_renderer.set_active_index(self._mic_cursor)

        target = self._play_font_notes[self._mic_cursor]
        if target.is_pause:
            return

        # Allow ±1 semitone tolerance
        if abs(midi_pitch - target.midi_pitch) <= 1:
            self._mic_cursor += 1
            self._mic_cursor = self._next_real_note(self._mic_cursor)
            if self._mic_cursor >= len(self._play_font_notes):
                self._tab_renderer.set_active_index(-1)
                self._mic_active = False
                self._listen_btn.setChecked(False)
                self._mic_status.setText("Done! All notes played.")
                return
            self._tab_renderer.set_active_index(self._mic_cursor)
            self._mic_status.setText(
                f"Listening… note {self._cursor_display()}/{self._playable_count()} — "
                f"play {self._target_note_name()}"
            )

    # ── Mic-mode helpers ──────────────────────────────────────────────
    def _next_real_note(self, start: int) -> int:
        """Return the first non-pause index at or after *start*."""
        i = start
        while i < len(self._play_font_notes) and self._play_font_notes[i].is_pause:
            i += 1
        return i

    def _playable_count(self) -> int:
        return sum(1 for fn in self._play_font_notes if not fn.is_pause)

    def _cursor_display(self) -> int:
        """1-based count of real notes played so far."""
        return sum(
            1 for fn in self._play_font_notes[: self._mic_cursor]
            if not fn.is_pause
        ) + 1

    def _target_note_name(self) -> str:
        if self._mic_cursor < len(self._play_font_notes):
            return self._play_font_notes[self._mic_cursor].note_name
        return "—"

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
        self._ocarina_name = ocarina.name
        font_notes = generate_font_tabs(
            notes, ocarina.name, ticks_per_beat, tempo=tempo,
            tempo_map=self._midi_file.tempo_map if hasattr(self, "_midi_file") else [],
            hole_count=ocarina.hole_count,
        )
        self._font_notes = font_notes
        self._play_font_notes = font_notes
        self._tab_renderer.load_tabs(font_notes)
        self._play_btn_main.setEnabled(True)
        self._listen_btn.setEnabled(True)
        self._calibrate_btn.setEnabled(True)
        self._mic_status.setText(f"Ready — {self._playable_count()} notes. Press Listen to start.")
        self._playback_info.setText(f"{len(font_notes)} notes ready — press Play to start.")
        self._status.showMessage(
            f"Generated {len(font_notes)} tab frames for {ocarina.name}."
        )

        # Add export buttons to status bar dynamically
        self._add_export_actions()

    def _on_playback_started(self, midi_file, track, mode: int, speed_factor: float = 1.0):
        # Stop listen mode if active — MIDI and mic modes are mutually exclusive
        if self._mic_active:
            self._stop_listen()
        # mode 0 = single track (compressed timing), 1 = all tracks (original timing)
        # speed_factor < 1 means slower; scale timestamps so highlighting stays in sync
        inv = 1.0 / speed_factor if speed_factor > 0 else 1.0
        self._play_timestamps = [
            (fn.compressed_start_ms if mode == 0 else fn.start_ms) * inv
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
