"""Ocarina type definitions, hole configurations, and tuning presets."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import json
from pathlib import Path


@dataclass
class HoleLayout:
    """Describes one hole on the ocarina body for visual display."""
    hole_id: str          # e.g. "T1", "T2", "1", "2", "S1", "S2" ...
    label: str            # display label
    x: float              # normalized x position [0..1]
    y: float              # normalized y position [0..1]
    is_thumb: bool = False
    is_subhole: bool = False  # small sub-hole played with the middle finger


@dataclass
class Fingering:
    """Maps to a set of closed holes for a given MIDI pitch offset from root."""
    semitones_from_root: int    # interval from root note
    closed_holes: List[str]     # hole_ids that are closed/covered
    note_name: str = ""         # e.g. "C5"


@dataclass
class OcarinaType:
    name: str                          # e.g. "12-hole Alto C"
    hole_count: int                    # 4, 6, 10, 11, 12
    root_midi: int                     # MIDI note of the lowest playable pitch
    range_semitones: int               # how many semitones it can play
    holes: List[HoleLayout] = field(default_factory=list)
    fingering_chart: List[Fingering] = field(default_factory=list)

    @property
    def min_midi(self) -> int:
        return self.root_midi

    @property
    def max_midi(self) -> int:
        return self.root_midi + self.range_semitones - 1

    def get_fingering(self, midi_pitch: int) -> Optional[Fingering]:
        offset = midi_pitch - self.root_midi
        for f in self.fingering_chart:
            if f.semitones_from_root == offset:
                return f
        return None


# ── Standard tuning roots ──────────────────────────────────────────────────
TUNING_ROOTS: Dict[str, int] = {
    "Soprano C":  72,  # C5
    "Soprano G":  67,  # G4
    "Alto C":     60,  # C4 (middle C)
    "Alto F":     65,  # F4
    "Tenor C":    48,  # C3
    "Bass C":     36,  # C2
}


# ── Fingering charts ────────────────────────────────────────────────────────
# 12-hole (transverse) standard fingering, offsets from root (0 = lowest note)
_FINGERINGS_12 = [
    # Hole numbering convention:
    #   T1 = left thumb (back),  T2 = right thumb (back)
    #   1-4 = right hand bottom plate (index→pinky)
    #   5-8 = left hand top plate (index→pinky)
    #   S2  = right-hand middle-finger sub-hole (paired with hole 2)
    #   S1  = left-hand middle-finger sub-hole  (paired with hole 6)
    #   Sub-holes are always covered when their parent middle-finger hole is covered.
    Fingering(0,  ["T1","T2","1","2","S2","3","4","5","6","S1","7","8"], ""),  # root
    Fingering(1,  ["T1","T2","1","2","S2","3","4","5","6","S1","7"],     ""),
    Fingering(2,  ["T1","T2","1","2","S2","3","4","5","6","S1"],         ""),
    Fingering(3,  ["T1","T2","1","2","S2","3","4","5"],                  ""),
    Fingering(4,  ["T1","T2","1","2","S2","3","4"],                      ""),
    Fingering(5,  ["T1","T2","1","2","S2","3"],                          ""),
    Fingering(6,  ["T1","T2","1","2","S2","4"],                          ""),
    Fingering(7,  ["T1","T2","1","2","S2"],                              ""),
    Fingering(8,  ["T1","T2","1","3"],                                   ""),
    Fingering(9,  ["T1","T2","1"],                                       ""),
    Fingering(10, ["T1","T2","2","S2"],                                  ""),
    Fingering(11, ["T1","T2"],                                           ""),
    Fingering(12, ["T1","1","2","S2","3","4","5","6","S1","7","8"],     ""),
    Fingering(13, ["T1","1","2","S2","3","4","5","6","S1","7"],         ""),
    Fingering(14, ["T1","1","2","S2","3","4","5","6","S1"],             ""),
    Fingering(15, ["T1","1","2","S2","3","4","5"],                      ""),
    Fingering(16, ["T1","1","2","S2","3"],                              ""),
    Fingering(17, ["T1","1","2","S2"],                                  ""),
    Fingering(18, ["T1","1"],                                           ""),
    Fingering(19, ["T2","1"],                                           ""),
    Fingering(20, ["T2"],                                               ""),
    Fingering(21, [],                                                   ""),  # all open (highest)
]

# 6-hole Pendant / Native American style
_FINGERINGS_6 = [
    Fingering(0,  ["1","2","3","4","5","6"], ""),
    Fingering(2,  ["1","2","3","4","5"],     ""),
    Fingering(4,  ["1","2","3","4"],         ""),
    Fingering(5,  ["1","2","3"],             ""),
    Fingering(7,  ["1","2"],                 ""),
    Fingering(9,  ["1"],                     ""),
    Fingering(11, [],                        ""),
    Fingering(12, ["1","2","3","4","5","6"], ""),  # second octave with breath
]


def _holes_12(root_midi: int) -> List[HoleLayout]:
    # Front face (10 finger holes + 2 sub-holes = 12 visible holes)
    # Back face has T1 (left thumb) and T2 (right thumb) shown at the bottom
    # of the canvas for reference.
    # S2 is the right-hand middle-finger sub-hole (sits just below hole 2).
    # S1 is the left-hand middle-finger sub-hole  (sits just above hole 6).
    return [
        # Thumb holes (back face, shown at bottom edge)
        HoleLayout("T1", "T1", 0.20, 0.88, is_thumb=True),
        HoleLayout("T2", "T2", 0.80, 0.88, is_thumb=True),
        # Right hand — bottom plate (index→pinky, right to left)
        HoleLayout("1",  "1",  0.78, 0.68),
        HoleLayout("2",  "2",  0.60, 0.68),
        HoleLayout("S2", "S2", 0.60, 0.80, is_subhole=True),   # middle-finger sub-hole
        HoleLayout("3",  "3",  0.42, 0.68),
        HoleLayout("4",  "4",  0.24, 0.68),
        # Left hand — top plate (index→pinky, right to left)
        HoleLayout("5",  "5",  0.78, 0.32),
        HoleLayout("6",  "6",  0.60, 0.32),
        HoleLayout("S1", "S1", 0.60, 0.20, is_subhole=True),   # middle-finger sub-hole
        HoleLayout("7",  "7",  0.42, 0.32),
        HoleLayout("8",  "8",  0.24, 0.32),
    ]


def _holes_6() -> List[HoleLayout]:
    return [
        HoleLayout("1", "1", 0.50, 0.80),
        HoleLayout("2", "2", 0.50, 0.62),
        HoleLayout("3", "3", 0.50, 0.44),
        HoleLayout("4", "4", 0.50, 0.26),
        HoleLayout("5", "5", 0.30, 0.55),
        HoleLayout("6", "6", 0.70, 0.55),
    ]


def build_ocarina_presets() -> Dict[str, OcarinaType]:
    presets: Dict[str, OcarinaType] = {}

    for tuning_name, root_midi in TUNING_ROOTS.items():
        key12 = f"12-hole {tuning_name}"
        oc12 = OcarinaType(
            name=key12,
            hole_count=12,
            root_midi=root_midi,
            range_semitones=22,
            holes=_holes_12(root_midi),
            fingering_chart=_FINGERINGS_12,
        )
        presets[key12] = oc12

        key6 = f"6-hole {tuning_name}"
        oc6 = OcarinaType(
            name=key6,
            hole_count=6,
            root_midi=root_midi,
            range_semitones=13,
            holes=_holes_6(),
            fingering_chart=_FINGERINGS_6,
        )
        presets[key6] = oc6

    return presets


OCARINA_PRESETS: Dict[str, OcarinaType] = build_ocarina_presets()
