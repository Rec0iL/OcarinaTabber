"""Shared tablature helpers used by the font-based pipeline."""

from __future__ import annotations

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_note_name(midi: int) -> str:
    octave = (midi // 12) - 1
    return f"{NOTE_NAMES[midi % 12]}{octave}"


def ticks_to_duration_label(ticks: int, ticks_per_beat: int) -> str:
    ratio = ticks / ticks_per_beat  # 1.0 = quarter note
    if ratio < 0.3:
        return "\U0001D15D"        # sixteenth
    elif ratio < 0.7:
        return "\u266A"            # eighth
    elif ratio < 1.4:
        return "\u2669"            # quarter
    elif ratio < 2.8:
        return "\U0001D158\U0001D165"  # half
    else:
        return "\U0001D15D\U0001D165"  # whole or longer
