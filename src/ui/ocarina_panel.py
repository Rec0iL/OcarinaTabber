"""Ocarina type/ tuning selector and range validation display."""

from __future__ import annotations
from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QPushButton, QFrame, QMessageBox,
)
from PySide6.QtCore import Signal

from ..ocarina.models import OCARINA_PRESETS, OcarinaType
from ..ocarina.validator import validate_range, apply_transpose
from ..midi.parser import NoteEvent, TrackInfo
from ..midi.polyphony import reduce_to_monophonic


class OcarinaPanel(QWidget):
    """Lets the user choose ocarina type and handles range validation."""
    ocarina_ready = Signal(object, list)   # (OcarinaType, List[NoteEvent] monophonic+transposed)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._notes: list = []
        self._ticks_per_beat: int = 480
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        lbl = QLabel("Ocarina Configuration")
        lbl.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        layout.addWidget(lbl)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Type:"))
        self._type_combo = QComboBox()
        for name in sorted(OCARINA_PRESETS):
            self._type_combo.addItem(name)
        self._type_combo.setCurrentText("12-hole Alto C")
        row1.addWidget(self._type_combo, 1)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Polyphony:"))
        self._poly_combo = QComboBox()
        self._poly_combo.addItems(["Highest note (melody)", "Lowest note (bass)"])
        row2.addWidget(self._poly_combo, 1)
        layout.addLayout(row2)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #45475a;")
        layout.addWidget(sep)

        self._range_label = QLabel("Range: —")
        self._range_label.setStyleSheet("color: #89b4fa; font-size: 10px;")
        layout.addWidget(self._range_label)

        self._validation_label = QLabel("")
        self._validation_label.setStyleSheet("font-size: 10px;")
        self._validation_label.setWordWrap(True)
        layout.addWidget(self._validation_label)

        self._transpose_btn = QPushButton("Auto-Transpose")
        self._transpose_btn.setVisible(False)
        self._transpose_btn.clicked.connect(self._do_transpose)
        layout.addWidget(self._transpose_btn)

        self._generate_btn = QPushButton("Generate Tabs →")
        self._generate_btn.setStyleSheet(
            "QPushButton { background: #89b4fa; color: #1e1e2e; font-weight: bold; padding: 6px; }"
            "QPushButton:hover { background: #74c7ec; }"
        )
        self._generate_btn.clicked.connect(self._emit_ready)
        layout.addWidget(self._generate_btn)
        layout.addStretch()

        self._type_combo.currentTextChanged.connect(self._on_type_changed)

        self._pending_transpose: Optional[int] = None
        self._transposed_notes: list = []

    def load_track(self, midi_file, track: TrackInfo):
        self._ticks_per_beat = midi_file.ticks_per_beat
        self._notes = list(track.notes)
        self._transposed_notes = []
        self._pending_transpose = None
        self._validate()

    def _get_ocarina(self) -> OcarinaType:
        return OCARINA_PRESETS[self._type_combo.currentText()]

    def _get_monophonic(self, notes: list) -> list:
        strategy = "highest" if self._poly_combo.currentIndex() == 0 else "lowest"
        return reduce_to_monophonic(notes, strategy)

    def _on_type_changed(self, _):
        self._transposed_notes = []
        self._pending_transpose = None
        self._validate()

    def _validate(self):
        if not self._notes:
            return
        oc = self._get_ocarina()
        mono = self._get_monophonic(self._notes)
        result = validate_range(mono, oc)

        self._range_label.setText(
            f"Ocarina range: {oc.min_midi} – {oc.max_midi}  "
            f"({self._note_name(oc.min_midi)} – {self._note_name(oc.max_midi)})"
        )

        if result.in_range:
            self._validation_label.setText("✓ All notes are within range.")
            self._validation_label.setStyleSheet("color: #a6e3a1; font-size: 10px;")
            self._transpose_btn.setVisible(False)
            self._pending_transpose = None
        else:
            out = len(result.out_of_range_notes)
            if result.suggested_transpose is not None:
                self._pending_transpose = result.suggested_transpose
                self._transpose_btn.setVisible(True)
                self._validation_label.setText(
                    f"⚠ {out} note(s) out of range. "
                    f"Suggested transpose: {result.suggested_transpose:+d} semitones."
                )
            else:
                self._transpose_btn.setVisible(False)
                self._validation_label.setText(
                    f"✗ {out} note(s) out of range and melody span exceeds ocarina range. "
                    "Consider a larger ocarina type."
                )
            self._validation_label.setStyleSheet("color: #f38ba8; font-size: 10px;")

    def _do_transpose(self):
        if self._pending_transpose is not None:
            mono = self._get_monophonic(self._notes)
            self._transposed_notes = apply_transpose(mono, self._pending_transpose)
            self._pending_transpose = None
            self._transpose_btn.setVisible(False)
            self._validation_label.setText(
                f"✓ Transposed. All notes now in range."
            )
            self._validation_label.setStyleSheet("color: #a6e3a1; font-size: 10px;")

    def _emit_ready(self):
        oc = self._get_ocarina()
        if self._transposed_notes:
            notes = self._transposed_notes
        else:
            notes = self._get_monophonic(self._notes)
        self.ocarina_ready.emit(oc, notes)

    @staticmethod
    def _note_name(midi: int) -> str:
        names = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
        return f"{names[midi % 12]}{(midi // 12) - 1}"
