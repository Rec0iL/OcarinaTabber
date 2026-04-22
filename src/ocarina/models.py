"""Ocarina type definitions and tuning presets."""

from __future__ import annotations
from dataclasses import dataclass
from typing import Dict


@dataclass
class OcarinaType:
    name: str             # e.g. "12-hole Alto C"
    hole_count: int       # 4, 6, 7, 12, ...
    root_midi: int        # MIDI note of the lowest playable pitch
    range_semitones: int  # how many semitones it can play

    @property
    def min_midi(self) -> int:
        return self.root_midi

    @property
    def max_midi(self) -> int:
        return self.root_midi + self.range_semitones - 1


# Standard tuning roots
TUNING_ROOTS: Dict[str, int] = {
    "Soprano C": 72,  # C5
    "Soprano G": 67,  # G4
    "Alto C":    60,  # C4 (middle C)
    "Alto F":    65,  # F4
    "Tenor C":   48,  # C3
    "Bass C":    36,  # C2
}


def build_ocarina_presets() -> Dict[str, OcarinaType]:
    presets: Dict[str, OcarinaType] = {}
    for tuning_name, root_midi in TUNING_ROOTS.items():
        # 12-hole: lowest note is 9 semitones above the key root (A for Alto C)
        root12 = root_midi + 9
        presets[f"12-hole {tuning_name}"] = OcarinaType(
            name=f"12-hole {tuning_name}", hole_count=12,
            root_midi=root12, range_semitones=21,
        )
        presets[f"7-hole {tuning_name}"] = OcarinaType(
            name=f"7-hole {tuning_name}", hole_count=7,
            root_midi=root_midi, range_semitones=13,
        )
        presets[f"6-hole {tuning_name}"] = OcarinaType(
            name=f"6-hole {tuning_name}", hole_count=6,
            root_midi=root_midi, range_semitones=13,
        )
        presets[f"4-hole {tuning_name}"] = OcarinaType(
            name=f"4-hole {tuning_name}", hole_count=4,
            root_midi=root_midi, range_semitones=8,
        )
    return presets


OCARINA_PRESETS: Dict[str, OcarinaType] = build_ocarina_presets()
