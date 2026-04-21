"""Converts a monophonic NoteEvent list + OcarinaType into TabNote frames."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional
from ..midi.parser import NoteEvent
from ..ocarina.models import OcarinaType, Fingering, HoleLayout


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def midi_to_note_name(midi: int) -> str:
    octave = (midi // 12) - 1
    return f"{NOTE_NAMES[midi % 12]}{octave}"


@dataclass
class TabNote:
    """A single rendered tablature frame."""
    note_name: str
    midi_pitch: int
    fingering: Optional[Fingering]          # None = out-of-range
    duration_ticks: int
    duration_label: str                     # e.g. "♩", "♪", "𝅗𝅥"
    holes: List[HoleLayout] = field(default_factory=list)   # snapshot from ocarina


# Duration label mapping (relative to a beat = quarter note)
_DURATION_LABELS = [
    (16, "𝅝"),   # sixteenth
    (32, "♪"),   # eighth
    (64, "♩"),   # quarter
    (128, "𝅗𝅥"),  # half
    (256, "𝅝𝅗𝅥"), # whole
]


def ticks_to_duration_label(ticks: int, ticks_per_beat: int) -> str:
    ratio = ticks / ticks_per_beat   # 1.0 = quarter note
    if ratio < 0.3:
        return "𝅝"       # sixteenth or shorter
    elif ratio < 0.7:
        return "♪"        # eighth
    elif ratio < 1.4:
        return "♩"        # quarter
    elif ratio < 2.8:
        return "𝅗𝅥"       # half
    else:
        return "𝅝𝅗𝅥"      # whole or longer


# NOTE: generate_tabs (hole-drawing approach) is retained for reference but
# is no longer used by the main window.  The font-based pipeline
# (see font_tab.py / FontTabRenderer) is now the active implementation.
#
# def generate_tabs(
#     notes: List[NoteEvent],
#     ocarina: OcarinaType,
#     ticks_per_beat: int,
# ) -> List[TabNote]:
#     """Map each NoteEvent to a TabNote with fingering information."""
#     tab_notes: List[TabNote] = []
#     for note in notes:
#         fingering = ocarina.get_fingering(note.pitch)
#         tab_notes.append(TabNote(
#             note_name=midi_to_note_name(note.pitch),
#             midi_pitch=note.pitch,
#             fingering=fingering,
#             duration_ticks=note.duration_ticks,
#             duration_label=ticks_to_duration_label(note.duration_ticks, ticks_per_beat),
#             holes=list(ocarina.holes),   # copy for safe rendering
#         ))
#     return tab_notes
