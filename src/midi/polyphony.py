"""Polyphony reduction: converts chord clusters to a monophonic melody line."""

from __future__ import annotations
from typing import List
from .parser import NoteEvent


def reduce_to_monophonic(notes: List[NoteEvent], strategy: str = "highest") -> List[NoteEvent]:
    """
    Given a list of NoteEvents (possibly polyphonic), return a monophonic sequence.

    Strategies:
      'highest' — keep the highest-pitched note in each simultaneous cluster (melody).
      'lowest'  — keep the bass voice.
    """
    if not notes:
        return []

    # Group notes that start at the same tick (chords)
    groups: dict[int, List[NoteEvent]] = {}
    for note in notes:
        groups.setdefault(note.start_tick, []).append(note)

    monophonic: List[NoteEvent] = []
    for tick in sorted(groups):
        cluster = groups[tick]
        if strategy == "highest":
            chosen = max(cluster, key=lambda n: n.pitch)
        else:
            chosen = min(cluster, key=lambda n: n.pitch)
        monophonic.append(chosen)

    # Remove overlaps: if a note extends into the next note's start, trim it.
    result: List[NoteEvent] = []
    for i, note in enumerate(monophonic):
        if i + 1 < len(monophonic):
            next_start = monophonic[i + 1].start_tick
            trimmed_duration = min(note.duration_ticks, next_start - note.start_tick)
            result.append(NoteEvent(
                pitch=note.pitch,
                velocity=note.velocity,
                start_tick=note.start_tick,
                duration_ticks=max(trimmed_duration, 1),
            ))
        else:
            result.append(note)

    return result
