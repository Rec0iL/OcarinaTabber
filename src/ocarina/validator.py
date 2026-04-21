"""Range validation and auto-transpose logic."""

from __future__ import annotations
from typing import List, Optional, Tuple
from ..midi.parser import NoteEvent
from .models import OcarinaType


class RangeValidationResult:
    def __init__(
        self,
        in_range: bool,
        out_of_range_notes: List[NoteEvent],
        suggested_transpose: Optional[int],
    ):
        self.in_range = in_range
        self.out_of_range_notes = out_of_range_notes
        self.suggested_transpose = suggested_transpose   # semitones to shift

    def __repr__(self) -> str:
        if self.in_range:
            return "RangeValidationResult(in_range=True)"
        return (
            f"RangeValidationResult(in_range=False, "
            f"out_of_range={len(self.out_of_range_notes)} notes, "
            f"suggested_transpose={self.suggested_transpose})"
        )


def validate_range(notes: List[NoteEvent], ocarina: OcarinaType) -> RangeValidationResult:
    """Check whether all notes fall within the ocarina's playable range."""
    out_of_range = [n for n in notes if not (ocarina.min_midi <= n.pitch <= ocarina.max_midi)]
    if not out_of_range:
        return RangeValidationResult(True, [], None)

    transpose = _find_best_transpose(notes, ocarina)
    return RangeValidationResult(False, out_of_range, transpose)


def _find_best_transpose(notes: List[NoteEvent], ocarina: OcarinaType) -> Optional[int]:
    """
    Search semitone shifts in range [-24, +24] to find the one that puts
    the most notes in range; prefer the smallest absolute shift among ties.
    """
    if not notes:
        return 0

    pitches = [n.pitch for n in notes]
    melody_span = max(pitches) - min(pitches)
    oc_span = ocarina.max_midi - ocarina.min_midi

    if melody_span > oc_span:
        return None   # impossible to fit even with transposition

    best_shift = 0
    best_count = -1

    for shift in range(-24, 25):
        shifted = [p + shift for p in pitches]
        in_range_count = sum(1 for p in shifted if ocarina.min_midi <= p <= ocarina.max_midi)
        abs_shift = abs(shift)
        if in_range_count > best_count or (
            in_range_count == best_count and abs_shift < abs(best_shift)
        ):
            best_count = in_range_count
            best_shift = shift

    return best_shift


def apply_transpose(notes: List[NoteEvent], semitones: int) -> List[NoteEvent]:
    """Return a new list of NoteEvents with each pitch shifted by `semitones`."""
    return [
        NoteEvent(
            pitch=max(0, min(127, n.pitch + semitones)),
            velocity=n.velocity,
            start_tick=n.start_tick,
            duration_ticks=n.duration_ticks,
        )
        for n in notes
    ]
