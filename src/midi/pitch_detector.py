"""Real-time microphone pitch detector using autocorrelation.

Runs in a background QThread so the UI stays responsive.
Emits ``pitch_detected(midi_note: int)`` whenever a stable note is found
above the silence gate.

Pitch detection algorithm
--------------------------
Uses normalized autocorrelation (via rfft for efficiency).  Works well
for monophonic instruments such as an ocarina.  The silence gate (RMS < 0.02)
prevents spurious emissions during quiet passages.

Requires: sounddevice, numpy
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np
from PySide6.QtCore import QThread, Signal


# ---------------------------------------------------------------------------
# Pure-function helpers
# ---------------------------------------------------------------------------

def _freq_to_midi(freq_hz: float) -> int:
    """Return the nearest MIDI note number for *freq_hz*."""
    return round(69.0 + 12.0 * math.log2(freq_hz / 440.0))


def _detect_pitch(
    samples: np.ndarray,
    sample_rate: int,
    min_freq: float = 100.0,   # lowest expected note (~G2)
    max_freq: float = 2100.0,  # highest expected note (~C7)
    rms_gate: float = 0.02,    # silence threshold
    confidence: float = 0.50,  # minimum normalized autocorrelation peak
) -> float:
    """Return dominant frequency in Hz, or 0.0 if none found / silence.

    Uses normalized autocorrelation computed efficiently via rfft so it
    runs comfortably within a 2048-sample callback at 44 100 Hz.
    """
    rms = float(np.sqrt(np.mean(samples ** 2)))
    if rms < rms_gate:
        return 0.0

    n = len(samples)
    # Zero-pad to 2n for linear (not circular) autocorrelation
    fft = np.fft.rfft(samples, n=n * 2)
    acorr = np.fft.irfft(fft * np.conj(fft))[:n]
    # Normalise so the maximum possible value is 1.0
    if acorr[0] < 1e-10:
        return 0.0
    acorr /= acorr[0]

    min_lag = max(1, int(sample_rate / max_freq))
    max_lag = min(n - 1, int(sample_rate / min_freq))
    if min_lag >= max_lag:
        return 0.0

    segment = acorr[min_lag:max_lag]
    peak_offset = int(np.argmax(segment))
    lag = peak_offset + min_lag

    if acorr[lag] < confidence:
        return 0.0

    return float(sample_rate) / float(lag)


# ---------------------------------------------------------------------------
# Device enumeration helper (called from the UI thread before start)
# ---------------------------------------------------------------------------

def list_input_devices() -> list[tuple[int, str]]:
    """Return ``[(device_index, name), ...]`` for all input devices.

    Returns an empty list when *sounddevice* is not installed.
    """
    try:
        import sounddevice as sd  # noqa: PLC0415
    except ImportError:
        return []

    devices = []
    for i, dev in enumerate(sd.query_devices()):
        if dev["max_input_channels"] > 0:
            devices.append((i, dev["name"]))
    return devices


# ---------------------------------------------------------------------------
# Background detector thread
# ---------------------------------------------------------------------------

class PitchDetector(QThread):
    """Background QThread that streams mic audio and emits detected MIDI pitches.

    Usage::

        detector = PitchDetector(device_index=0)
        detector.pitch_detected.connect(my_slot)
        detector.start()
        # … later …
        detector.stop()
    """

    pitch_detected    = Signal(int)    # calibrated MIDI note number
    raw_freq_detected  = Signal(float)  # raw detected frequency in Hz (no calibration)

    def __init__(
        self,
        device_index: Optional[int] = None,
        sample_rate: int = 44100,
        block_size: int = 2048,
        parent=None,
    ):
        super().__init__(parent)
        self._device = device_index
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._running = False
        self._last_midi: int = -1
        self._calibration_semitones: float = 0.0  # positive = ocarina plays flat

    def set_calibration(self, semitones: float) -> None:
        """Set the tuning correction in semitones applied before emitting pitch_detected."""
        self._calibration_semitones = semitones

    # ------------------------------------------------------------------
    def run(self) -> None:
        try:
            import sounddevice as sd  # noqa: PLC0415
        except ImportError:
            print(
                "[PitchDetector] 'sounddevice' not installed.\n"
                "  Install it with:  pip install sounddevice",
                flush=True,
            )
            return

        NOTE_NAMES = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]

        self._running = True
        self._last_midi = -1
        try:
            # Use the device's native sample rate to avoid PaErrorCode -9997
            dev_info = sd.query_devices(self._device, kind="input")
            sample_rate = int(dev_info["default_samplerate"])
            print(f"[PitchDetector] opened device '{dev_info['name']}' @ {sample_rate} Hz", flush=True)
            with sd.InputStream(
                device=self._device,
                channels=1,
                samplerate=sample_rate,
                blocksize=self._block_size,
                dtype="float32",
            ) as stream:
                while self._running:
                    data, _overflowed = stream.read(self._block_size)
                    samples = data[:, 0].astype(np.float64)
                    rms = float(np.sqrt(np.mean(samples ** 2)))
                    freq = _detect_pitch(samples, sample_rate)
                    if freq > 0.0:
                        self.raw_freq_detected.emit(freq)
                        # Apply calibration offset then round to nearest MIDI note
                        midi_float = 69.0 + 12.0 * math.log2(freq / 440.0) + self._calibration_semitones
                        midi = round(midi_float)
                        note_name = NOTE_NAMES[midi % 12] + str((midi // 12) - 1)
                        cal_tag = f" cal={self._calibration_semitones:+.2f}st" if self._calibration_semitones else ""
                        print(
                            f"[mic] {freq:7.1f} Hz  midi={midi:3d}  {note_name:<4s}  rms={rms:.4f}{cal_tag}",
                            flush=True,
                        )
                        if midi != self._last_midi:
                            self._last_midi = midi
                            self.pitch_detected.emit(midi)
                    else:
                        # Print silence line at reduced rate (every ~10 blocks)
                        if not hasattr(self, "_silence_ctr"):
                            self._silence_ctr = 0
                        self._silence_ctr += 1
                        if self._silence_ctr >= 10:
                            self._silence_ctr = 0
                            print(f"[mic] silence  rms={rms:.4f}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[PitchDetector] stream error: {exc}", flush=True)

    def stop(self) -> None:
        """Request the run loop to exit and block until the thread finishes."""
        self._running = False
        self.wait(2000)
