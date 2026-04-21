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
    semitones_from_root: int           # interval from root note
    closed_holes: List[str]            # hole_ids that are fully closed/covered
    note_name: str = ""                # e.g. "C5"
    half_open_holes: List[str] = field(default_factory=list)  # hole_ids that are half-open


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
# 12-hole transverse ocarina — fingering chart decoded from reference image.
#
# Hole IDs used in this codebase:
#   T1  = left thumb  (back)       T2  = right thumb (back)
#   "1" = right index              "2" = right middle
#   "3" = right ring               "4" = right pinky
#   "5" = left index               "6" = left middle
#   "7" = left ring                "8" = left pinky
#   S2  = right-middle sub-hole    S1  = left-middle sub-hole
#
# Reference uses positions 1-12 → mapped to IDs as:
#   1→S1  2→S2  3→"4"  4→"3"  5→"2"  6→"1"
#   7→"7"  8→"6"  9→"5"  10→T1  11→T2  12→"8"
#
# Root (offset 0) = A, one octave range to F (21 semitones).
# H = half-open (stored in half_open_holes; displayed as half-filled circle).
_FINGERINGS_12 = [
    # off  note   closed_holes                                         half_open
    Fingering(0,  ["S1","S2","4","3","2","1","7","6","5","T1","T2","8"], ""),  # a  ************
    Fingering(1,  ["S1",    "4","3","2","1","7","6","5","T1","T2","8"], ""),  # a# *-**********
    Fingering(2,  [    "S2","4","3","2","1","7","6","5","T1","T2","8"], ""),  # h  -***********
    Fingering(3,  [        "4","3","2","1","7","6","5","T1","T2","8"],  ""),  # c  --**********
    Fingering(4,  [           "3","2","1","7","6","5","T1","T2","8"],   "", ["4"]),  # c# --H*
    Fingering(5,  [           "3","2","1","7","6","5","T1","T2","8"],   ""),  # d  ---*********
    Fingering(6,  [        "4",  "2","1","7","6","5","T1","T2","8"],    ""),  # d# --*-********
    Fingering(7,  [              "2","1","7","6","5","T1","T2","8"],    ""),  # e  ----********
    Fingering(8,  [                 "1","7","6","5","T1","T2","8"],     ""),  # f  -----*******
    Fingering(9,  [              "2",   "7","6","5","T1","T2","8"],     ""),  # f# ----*-******
    Fingering(10, [                    "7","6","5","T1","T2","8"],      ""),  # g  ------******
    Fingering(11, [           "3",        "6","5","T1","T2","8"],       ""),  # g# ---*---*****
    Fingering(12, [                        "6","5","T1","T2","8"],      ""),  # a  -------*****
    Fingering(13, [           "3",             "5","T1","T2","8"],      ""),  # a# ---*----****
    Fingering(14, [                            "5","T1","T2","8"],      ""),  # h  --------****
    Fingering(15, [                               "T1","T2","8"],       ""),  # c  ---------***
    Fingering(16, [                 "1",           "T2","8"],           ""),  # c# -----*----**
    Fingering(17, [                                "T2","8"],           ""),  # d  ----------**
    Fingering(18, [                                "T2"],               ""),  # d# ----------*-
    Fingering(19, [                                    "8"],            ""),  # e  -----------*
    Fingering(20, [],                                                   ""),  # f  ------------
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
    # Diagonal layout matching the canvas editor screenshot:
    #   Left hand  — diagonal from top-centre going down-left:  8→7→6→5
    #   Right hand — diagonal from top-right going down-centre: 4→3→2→1
    #   S1 sits to the right of hole 6 (same row)
    #   S2 sits to the left  of hole 2 (same row)
    #   Thumb holes T1/T2 centred at the bottom
    return [
        # ── Left hand ────────────────────────────────────────────────
        HoleLayout("8",  "8",  0.43, 0.15),
        HoleLayout("7",  "7",  0.35, 0.30),
        HoleLayout("6",  "6",  0.24, 0.46),
        HoleLayout("S1", "S1", 0.36, 0.50, is_subhole=True),
        HoleLayout("5",  "5",  0.15, 0.62),
        # ── Right hand ───────────────────────────────────────────────
        HoleLayout("4",  "4",  0.87, 0.15),
        HoleLayout("3",  "3",  0.78, 0.30),
        HoleLayout("S2", "S2", 0.60, 0.44, is_subhole=True),
        HoleLayout("2",  "2",  0.74, 0.50),
        HoleLayout("1",  "1",  0.68, 0.65),
        # ── Thumb holes (back face, bottom centre) ───────────────────
        HoleLayout("T1", "T1", 0.42, 0.87, is_thumb=True),
        HoleLayout("T2", "T2", 0.56, 0.87, is_thumb=True),
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


def _holes_7() -> List[HoleLayout]:
    # 7-hole pendant ocarina (German Spielanleitung layout):
    #   Top row  — left-hand fingers (L1 L2 L3, left→right)
    #   Bottom row — right-hand fingers (R1 R2 R3, left→right)
    #   Thumb hole (T) at the back, shown below centre
    return [
        # Left hand — top row
        HoleLayout("L1", "L1", 0.22, 0.22),
        HoleLayout("L2", "L2", 0.50, 0.22),
        HoleLayout("L3", "L3", 0.78, 0.22),
        # Right hand — bottom row
        HoleLayout("R1", "R1", 0.22, 0.55),
        HoleLayout("R2", "R2", 0.50, 0.55),
        HoleLayout("R3", "R3", 0.78, 0.55),
        # Thumb hole (Daumenloch) — back face, shown at bottom
        HoleLayout("T",  "T",  0.50, 0.85, is_thumb=True),
    ]


# 7-hole pendant ocarina — chromatic fingering chart (offsets from C4)
# Notation from image:  D = Daumen (thumb T closed)
#   D3 = T+L1+L2+L3+R1+R2+R3  (all 7 closed — lowest note c)
#   D2 = T+L2+L3+R1+R2+R3     (L1 open)
#   D1 = T+L3+R1+R2+R3        (L1 L2 open)
#   D  = T+R1+R2+R3            (left hand fully open)
#   3  = R1+R2+R3              (thumb open, 3 right fingers closed)
#   2  = R2+R3
#   1  = R3
#   0  = all open              (highest note c')
# Semitones use fork/cross fingerings:
#   C# = D3 fork (R3 open)     D# = D2 fork (L3 open, "DM" in image)
#   F# = D fork (R3 open)      G# = 3 fork (R3 open)
#   A# = 2 fork (R3 open, "M" in image)
_FINGERINGS_7 = [
    Fingering(0,  ["T","L1","L2","L3","R1","R2","R3"], ""),  # c  — D3
    Fingering(1,  ["T","L1","L2","L3","R1","R2"],      ""),  # c# — D3 fork (R3 open)
    Fingering(2,  ["T","L2","L3","R1","R2","R3"],      ""),  # d  — D2
    Fingering(3,  ["T","L2","R1","R2","R3"],           ""),  # d# — DM fork (L3 open)
    Fingering(4,  ["T","L3","R1","R2","R3"],           ""),  # e  — D1
    Fingering(5,  ["T","R1","R2","R3"],                ""),  # f  — D
    Fingering(6,  ["T","R1","R2"],                     ""),  # f# — D fork (R3 open)
    Fingering(7,  ["R1","R2","R3"],                    ""),  # g  — 3
    Fingering(8,  ["R1","R2"],                         ""),  # g# — 3 fork (R3 open)
    Fingering(9,  ["R2","R3"],                         ""),  # a  — 2
    Fingering(10, ["R2"],                              ""),  # a# — M fork (R3 open)
    Fingering(11, ["R3"],                              ""),  # h  — 1
    Fingering(12, [],                                  ""),  # c' — 0 (all open)
]


def build_ocarina_presets() -> Dict[str, OcarinaType]:
    presets: Dict[str, OcarinaType] = {}

    for tuning_name, root_midi in TUNING_ROOTS.items():
        key12 = f"12-hole {tuning_name}"
        # 12-hole lowest note is A4 for Alto C, which is 9 semitones above the key's C.
        root12 = root_midi + 9
        oc12 = OcarinaType(
            name=key12,
            hole_count=12,
            root_midi=root12,
            range_semitones=21,
            holes=_holes_12(root12),
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

        key7 = f"7-hole {tuning_name}"
        oc7 = OcarinaType(
            name=key7,
            hole_count=7,
            root_midi=root_midi,
            range_semitones=13,
            holes=_holes_7(),
            fingering_chart=_FINGERINGS_7,
        )
        presets[key7] = oc7

    return presets


OCARINA_PRESETS: Dict[str, OcarinaType] = build_ocarina_presets()
