"""MIDI file parser: loads tracks and extracts note events with timing."""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
import mido


@dataclass
class NoteEvent:
    """A single note-on event with MIDI pitch, velocity, tick time, and duration."""
    pitch: int           # MIDI note number (0-127)
    velocity: int        # 0-127
    start_tick: int      # Absolute tick of note-on
    duration_ticks: int  # Length in ticks
    # Convenience properties
    @property
    def note_name(self) -> str:
        names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        octave = (self.pitch // 12) - 1
        return f"{names[self.pitch % 12]}{octave}"


@dataclass
class TrackInfo:
    index: int
    name: str
    channel: Optional[int]   # None if mixed channels
    note_count: int
    min_pitch: int
    max_pitch: int
    notes: List[NoteEvent] = field(default_factory=list)

    def __str__(self) -> str:
        ch = f"Ch{self.channel}" if self.channel is not None else "Multi-ch"
        return f"Track {self.index}: {self.name or 'Unnamed'} [{ch}] — {self.note_count} notes"


@dataclass
class MidiFile:
    path: Path
    ticks_per_beat: int
    tempo: int              # microseconds per beat (default 500000 = 120 BPM)
    tracks: List[TrackInfo]

    @property
    def bpm(self) -> float:
        return 60_000_000 / self.tempo


def load_midi(path: str | Path) -> MidiFile:
    """Parse a MIDI file and return structured track information."""
    path = Path(path)
    mid = mido.MidiFile(str(path))

    tempo = 500_000  # default 120 BPM
    # Scan for tempo in any track
    for track in mid.tracks:
        for msg in track:
            if msg.type == "set_tempo":
                tempo = msg.tempo
                break

    tracks: List[TrackInfo] = []
    for idx, raw_track in enumerate(mid.tracks):
        notes = _extract_notes(raw_track)
        if not notes:
            continue

        name = raw_track.name.strip() if raw_track.name else ""
        channels = {n.velocity for n in notes}  # reuse velocity field as proxy; get real channels below
        channels = _get_channels(raw_track)
        channel = next(iter(channels)) if len(channels) == 1 else None
        pitches = [n.pitch for n in notes]

        tracks.append(TrackInfo(
            index=idx,
            name=name,
            channel=channel,
            note_count=len(notes),
            min_pitch=min(pitches),
            max_pitch=max(pitches),
            notes=notes,
        ))

    return MidiFile(path=path, ticks_per_beat=mid.ticks_per_beat, tempo=tempo, tracks=tracks)


def _get_channels(raw_track) -> set:
    channels = set()
    for msg in raw_track:
        if hasattr(msg, "channel"):
            channels.add(msg.channel)
    return channels or {0}


def _extract_notes(raw_track) -> List[NoteEvent]:
    """Convert raw MIDI messages to absolute-tick NoteEvent list."""
    pending: dict[int, list] = {}   # pitch -> [(start_tick, velocity)]
    notes: List[NoteEvent] = []
    abs_tick = 0

    for msg in raw_track:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            pending.setdefault(msg.note, []).append((abs_tick, msg.velocity))
        elif msg.type == "note_off" or (msg.type == "note_on" and msg.velocity == 0):
            if msg.note in pending and pending[msg.note]:
                start_tick, velocity = pending[msg.note].pop(0)
                duration = abs_tick - start_tick
                notes.append(NoteEvent(
                    pitch=msg.note,
                    velocity=velocity,
                    start_tick=start_tick,
                    duration_ticks=max(duration, 1),
                ))

    return sorted(notes, key=lambda n: n.start_tick)
