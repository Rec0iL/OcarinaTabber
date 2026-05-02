"""Two-point ocarina calibration dialog.

Asks the user to play the lowest and highest note of their ocarina.
Measures the detected frequency, computes the offset from the expected
frequency, and exposes the averaged correction in semitones.

The calibration_done signal carries the result so the caller can store it
and pass it to PitchDetector.set_calibration().
"""

from __future__ import annotations

import math
from typing import Optional

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QFont, QPainter
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QProgressBar, QFrame, QGraphicsScene, QGraphicsView,
)

from ..midi.pitch_detector import PitchDetector
from ..tablature.font_tab import FontNote, ocarina_font_family
from ..tablature.renderer import FontTabItem, FONT_FRAME_W, FONT_FRAME_H

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_CAPTURE_SAMPLES = 15   # rolling buffer size — capture once full


def _midi_to_name(midi: int) -> str:
    return _NOTE_NAMES[midi % 12] + str((midi // 12) - 1)


def _midi_to_freq(midi: int) -> float:
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


class CalibrationDialog(QDialog):
    """Step-through calibration using two reference notes."""

    # Emitted when calibration finishes; carries the correction in semitones.
    calibration_done = Signal(float)

    def __init__(
        self,
        low_note: FontNote,
        high_note: FontNote,
        device_index: Optional[int] = None,
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Ocarina Calibration")
        self.setMinimumWidth(420)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        self._steps = [low_note, high_note]
        self._step = 0
        self._offsets: list[float] = []
        self._freq_buffer: list[float] = []
        self._result_semitones: float = 0.0
        self._finished = False

        self._detector = PitchDetector(device_index=device_index, parent=self)
        self._detector.raw_freq_detected.connect(self._on_raw_freq)

        self._update_timer = QTimer(self)
        self._update_timer.setInterval(100)
        self._update_timer.timeout.connect(self._refresh_display)

        self._build_ui()
        self._update_step_ui()

        self._detector.start()
        self._update_timer.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # Step indicator
        self._step_lbl = QLabel()
        self._step_lbl.setStyleSheet("color: #cba6f7; font-weight: bold; font-size: 13px;")
        layout.addWidget(self._step_lbl)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #45475a;")
        layout.addWidget(sep)

        # Instruction
        self._instruction_lbl = QLabel()
        self._instruction_lbl.setWordWrap(True)
        self._instruction_lbl.setStyleSheet("color: #cdd6f4; font-size: 12px;")
        layout.addWidget(self._instruction_lbl)

        # Expected note: glyph view + text side by side
        note_row = QHBoxLayout()
        note_row.setSpacing(12)

        self._glyph_scene = QGraphicsScene()
        self._glyph_view = QGraphicsView(self._glyph_scene)
        self._glyph_view.setFixedSize(FONT_FRAME_W + 4, FONT_FRAME_H + 4)
        self._glyph_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._glyph_view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._glyph_view.setStyleSheet("background: #1e1e2e; border: 1px solid #44475a; border-radius: 6px;")
        self._glyph_view.setRenderHint(QPainter.Antialiasing)
        self._glyph_item = None
        note_row.addWidget(self._glyph_view)

        self._expected_lbl = QLabel()
        self._expected_lbl.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._expected_lbl.setStyleSheet(
            "color: #a6e3a1; font-size: 20px; font-weight: bold; padding: 8px;"
        )
        note_row.addWidget(self._expected_lbl, 1)

        layout.addLayout(note_row)

        # Live feedback
        self._heard_lbl = QLabel("Waiting for signal…")
        self._heard_lbl.setAlignment(Qt.AlignCenter)
        self._heard_lbl.setStyleSheet("color: #89b4fa; font-size: 12px; padding: 4px;")
        layout.addWidget(self._heard_lbl)

        # Sample progress bar
        self._progress = QProgressBar()
        self._progress.setRange(0, _CAPTURE_SAMPLES)
        self._progress.setValue(0)
        self._progress.setTextVisible(False)
        self._progress.setFixedHeight(8)
        self._progress.setStyleSheet(
            "QProgressBar { background: #313244; border-radius: 4px; }"
            "QProgressBar::chunk { background: #a6e3a1; border-radius: 4px; }"
        )
        layout.addWidget(self._progress)

        self._progress_lbl = QLabel("Hold the note steady to capture…")
        self._progress_lbl.setAlignment(Qt.AlignCenter)
        self._progress_lbl.setStyleSheet("color: #6c7086; font-size: 10px;")
        layout.addWidget(self._progress_lbl)

        # Result summary (hidden until done)
        self._summary_lbl = QLabel()
        self._summary_lbl.setWordWrap(True)
        self._summary_lbl.setAlignment(Qt.AlignCenter)
        self._summary_lbl.setStyleSheet(
            "color: #f9e2af; font-size: 13px; font-weight: bold; padding: 8px;"
        )
        self._summary_lbl.hide()
        layout.addWidget(self._summary_lbl)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #45475a;")
        layout.addWidget(sep2)

        # Buttons
        btn_row = QHBoxLayout()

        self._capture_btn = QPushButton("Capture note")
        self._capture_btn.setEnabled(False)
        self._capture_btn.setStyleSheet(
            "QPushButton { background: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 6px 14px; }"
            "QPushButton:hover { background: #94d09a; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        self._capture_btn.clicked.connect(self._capture)
        btn_row.addWidget(self._capture_btn)

        self._retry_btn = QPushButton("Retry")
        self._retry_btn.setEnabled(False)
        self._retry_btn.setStyleSheet(
            "QPushButton { background: #45475a; color: #cdd6f4; padding: 6px 14px; }"
            "QPushButton:hover { background: #585b70; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        self._retry_btn.clicked.connect(self._retry_step)
        btn_row.addWidget(self._retry_btn)

        btn_row.addStretch()

        self._skip_btn = QPushButton("Skip calibration")
        self._skip_btn.setStyleSheet(
            "QPushButton { background: #313244; color: #6c7086; padding: 6px 14px; }"
            "QPushButton:hover { background: #45475a; color: #cdd6f4; }"
        )
        self._skip_btn.clicked.connect(self._skip)
        btn_row.addWidget(self._skip_btn)

        self._ok_btn = QPushButton("Apply & Close")
        self._ok_btn.hide()
        self._ok_btn.setStyleSheet(
            "QPushButton { background: #cba6f7; color: #1e1e2e; font-weight: bold; padding: 6px 14px; }"
            "QPushButton:hover { background: #b89de0; }"
        )
        self._ok_btn.clicked.connect(self._apply_and_close)
        btn_row.addWidget(self._ok_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    def _update_step_ui(self) -> None:
        note = self._steps[self._step]
        midi = note.midi_pitch
        name = _midi_to_name(midi)
        freq = _midi_to_freq(midi)
        label = "lowest" if self._step == 0 else "highest"
        self._step_lbl.setText(f"Step {self._step + 1} of {len(self._steps)}")
        self._instruction_lbl.setText(
            f"Play the <b>{label}</b> note on your ocarina and hold it steady."
        )
        self._expected_lbl.setText(f"{name}\n{freq:.1f} Hz")
        # Render the ocarina fingering glyph via FontTabItem (same as main renderer)
        self._glyph_scene.clear()
        self._glyph_item = FontTabItem(note, 0)
        self._glyph_scene.addItem(self._glyph_item)
        self._glyph_scene.setSceneRect(0, 0, FONT_FRAME_W, FONT_FRAME_H)
        self._glyph_view.fitInView(self._glyph_scene.sceneRect(), Qt.KeepAspectRatio)
        self._heard_lbl.setText("Waiting for signal…")
        self._progress.setValue(0)
        self._progress_lbl.setText("Hold the note steady to capture…")
        self._freq_buffer.clear()
        self._capture_btn.setEnabled(False)
        self._retry_btn.setEnabled(False)

    def _retry_step(self) -> None:
        self._update_step_ui()

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_raw_freq(self, freq: float) -> None:
        """Buffer incoming raw frequencies; only accept if near the expected pitch."""
        if self._finished:
            return
        expected_midi = self._steps[self._step].midi_pitch
        detected_midi_float = 69.0 + 12.0 * math.log2(freq / 440.0)
        # Only accept frequencies within ±3 semitones of the expected note
        if abs(detected_midi_float - expected_midi) > 3.0:
            return
        self._freq_buffer.append(freq)
        if len(self._freq_buffer) > _CAPTURE_SAMPLES:
            self._freq_buffer.pop(0)

    def _refresh_display(self) -> None:
        if self._finished or not self._freq_buffer:
            return
        avg_freq = sum(self._freq_buffer) / len(self._freq_buffer)
        expected_midi = self._steps[self._step].midi_pitch
        expected_freq = _midi_to_freq(expected_midi)
        # Cents deviation from expected (positive = sharp, negative = flat)
        cents = 1200.0 * math.log2(avg_freq / expected_freq)
        detected_name = _midi_to_name(round(69.0 + 12.0 * math.log2(avg_freq / 440.0)))
        sign = "+" if cents >= 0 else ""
        self._heard_lbl.setText(
            f"Hearing: {avg_freq:.1f} Hz  ({detected_name})  {sign}{cents:.0f} ¢"
        )
        # Color: green near target, yellow/red further away
        if abs(cents) < 20:
            self._heard_lbl.setStyleSheet("color: #a6e3a1; font-size: 12px; padding: 4px;")
        elif abs(cents) < 60:
            self._heard_lbl.setStyleSheet("color: #f9e2af; font-size: 12px; padding: 4px;")
        else:
            self._heard_lbl.setStyleSheet("color: #f38ba8; font-size: 12px; padding: 4px;")

        count = len(self._freq_buffer)
        self._progress.setValue(count)
        if count >= _CAPTURE_SAMPLES:
            self._capture_btn.setEnabled(True)
            self._retry_btn.setEnabled(True)
            self._progress_lbl.setText("Ready — press Capture when the reading looks stable.")
        else:
            self._progress_lbl.setText(f"Collecting… {count}/{_CAPTURE_SAMPLES} samples")

    def _capture(self) -> None:
        if not self._freq_buffer:
            return
        avg_freq = sum(self._freq_buffer) / len(self._freq_buffer)
        expected_midi = self._steps[self._step].midi_pitch
        detected_midi_float = 69.0 + 12.0 * math.log2(avg_freq / 440.0)
        offset = expected_midi - detected_midi_float   # positive when ocarina is flat
        self._offsets.append(offset)

        cents = offset * 100.0
        sign = "+" if cents >= 0 else ""
        print(
            f"[calibration] step {self._step + 1}: expected midi={expected_midi} "
            f"({_midi_to_name(expected_midi)}), detected={detected_midi_float:.3f}, "
            f"offset={offset:+.3f} st ({sign}{cents:.0f} ¢)",
            flush=True,
        )

        self._step += 1
        if self._step >= len(self._steps):
            self._finish()
        else:
            self._update_step_ui()

    def _finish(self) -> None:
        self._finished = True
        self._update_timer.stop()
        self._detector.stop()

        self._result_semitones = sum(self._offsets) / len(self._offsets)
        total_cents = self._result_semitones * 100.0
        sign = "+" if total_cents >= 0 else ""
        direction = "flat" if total_cents > 0 else "sharp"

        self._step_lbl.setText("Calibration complete")
        self._instruction_lbl.setText(
            f"Your ocarina plays <b>{abs(total_cents):.0f} cents {direction}</b> of concert pitch."
        )
        self._glyph_view.hide()
        self._expected_lbl.hide()
        self._heard_lbl.hide()
        self._progress.hide()
        self._progress_lbl.hide()
        self._summary_lbl.setText(
            f"Correction: {sign}{total_cents:.0f} cents will be applied during Listen mode."
        )
        self._summary_lbl.show()
        self._capture_btn.hide()
        self._retry_btn.hide()
        self._skip_btn.hide()
        self._ok_btn.show()

        print(
            f"[calibration] result: {sign}{total_cents:.1f} ¢ "
            f"({self._result_semitones:+.3f} semitones)",
            flush=True,
        )

    def _skip(self) -> None:
        self._result_semitones = 0.0
        self._detector.stop()
        self._update_timer.stop()
        self.calibration_done.emit(0.0)
        self.reject()

    def _apply_and_close(self) -> None:
        self.calibration_done.emit(self._result_semitones)
        self.accept()

    # ------------------------------------------------------------------
    def closeEvent(self, event) -> None:
        self._detector.stop()
        self._update_timer.stop()
        super().closeEvent(event)
