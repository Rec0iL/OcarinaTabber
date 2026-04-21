"""MIDI file upload panel and track selector."""

from __future__ import annotations
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QFrame,
)
from PySide6.QtCore import Signal, Qt

from ..midi.parser import load_midi, MidiFile, TrackInfo


class MidiPanel(QWidget):
    """Upload a MIDI file and select a track."""
    track_selected = Signal(object, object)   # (MidiFile, TrackInfo)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._midi_file: Optional[MidiFile] = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # File picker row
        row = QHBoxLayout()
        self._path_label = QLabel("No file loaded")
        self._path_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        self._path_label.setWordWrap(True)
        row.addWidget(self._path_label, 1)

        btn = QPushButton("Open MIDI…")
        btn.setFixedWidth(110)
        btn.clicked.connect(self._open_file)
        row.addWidget(btn)
        layout.addLayout(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #45475a;")
        layout.addWidget(sep)

        lbl = QLabel("Tracks")
        lbl.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        layout.addWidget(lbl)

        self._track_list = QListWidget()
        self._track_list.setStyleSheet(
            "QListWidget { background: #181825; border: none; }"
            "QListWidget::item { padding: 4px; color: #cdd6f4; }"
            "QListWidget::item:selected { background: #313244; }"
        )
        self._track_list.itemClicked.connect(self._on_track_clicked)
        layout.addWidget(self._track_list)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #a6e3a1; font-size: 10px;")
        layout.addWidget(self._info_label)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open MIDI File", "", "MIDI Files (*.mid *.midi)"
        )
        if not path:
            return
        try:
            self._midi_file = load_midi(path)
        except Exception as e:
            self._path_label.setText(f"Error: {e}")
            return

        self._path_label.setText(Path(path).name)
        self._populate_tracks()

    def _populate_tracks(self):
        self._track_list.clear()
        if not self._midi_file:
            return
        for track in self._midi_file.tracks:
            item = QListWidgetItem(str(track))
            item.setData(Qt.UserRole, track)
            self._track_list.addItem(item)
        self._info_label.setText(
            f"BPM: {self._midi_file.bpm:.1f}  |  "
            f"Ticks/beat: {self._midi_file.ticks_per_beat}  |  "
            f"{len(self._midi_file.tracks)} tracks with notes"
        )

    def _on_track_clicked(self, item: QListWidgetItem):
        track: TrackInfo = item.data(Qt.UserRole)
        if self._midi_file:
            self.track_selected.emit(self._midi_file, track)
