"""Font-based ocarina tablature using the Open 12 Hole Ocarina TTF fonts.

The "Open 12 Hole Ocarina" fonts (styles 1 and 2) encode ocarina fingering
diagrams as glyphs for the letters A–U.  Each letter corresponds to one
playable note on a 12-hole transverse ocarina; the glyph visually shows
which holes to cover.

Mapping origin
--------------
The website https://michaeleskin.com/tools/ocarina/index.html uses the same
approach via its ``getNoteGlyph`` function and ``theTabMap`` array.  This
module replicates that logic in Python so we can render tabs without any
manual hole-drawing code.

MIDI → font-char conversion
----------------------------
    glyph_index = (midi_pitch - 60) + key_offset
    font_char   = _TAB_MAP[glyph_index]   # 'A'–'U', or 'x' for out-of-range

Key offsets (matching the JS KEY_MAPS):
    C → 0   (lowest note A4, MIDI 69)
    F → -5  (lowest note D5, MIDI 74)
    G → -7  (lowest note E5, MIDI 76)

Font glyphs for indices 9–29 are the letters A–U; everything else is 'x'.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List

from PySide6.QtGui import QFontDatabase

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# theTabMap from the reference JS, trimmed to a workable length.
# Index 9 = 'A' (lowest note), index 29 = 'U' (highest note).
_TAB_MAP: List[str] = (
    ['x'] * 9 +                     # indices 0-8  (below playable range)
    list('ABCDEFGHIJKLMNOPQRSTU') +  # indices 9-29 (playable range)
    ['x'] * 18                       # indices 30+  (above playable range)
)

# Key offsets applied before looking up _TAB_MAP
_KEY_OFFSETS: dict[str, int] = {
    "C": 0,
    "F": -5,
    "G": -7,
}

FONTS_DIR = Path(__file__).parent.parent / "fonts"

# Silence gaps longer than this between consecutive notes trigger a pause frame
PAUSE_THRESHOLD_S = 5.0

# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------

def _tick_to_ms(tick: int, tpb: int, tempo_map: list) -> float:
    """Convert an absolute MIDI tick to milliseconds using a full tempo map.

    Parameters
    ----------
    tick:
        Absolute tick position to convert.
    tpb:
        Ticks per beat (from the MIDI file header).
    tempo_map:
        Sorted list of ``(abs_tick, tempo_us)`` tuples from the MIDI file.
        May be empty, in which case 120 BPM (500 000 µs/beat) is assumed.
    """
    ms = 0.0
    prev_tick = 0
    prev_tempo = 500_000  # 120 BPM default

    for event_tick, event_tempo in tempo_map:
        if event_tick >= tick:
            break
        ms += (event_tick - prev_tick) * (prev_tempo / 1_000.0) / tpb
        prev_tick = event_tick
        prev_tempo = event_tempo

    ms += (tick - prev_tick) * (prev_tempo / 1_000.0) / tpb
    return ms


# ---------------------------------------------------------------------------
# Font loading
# ---------------------------------------------------------------------------

_fonts_loaded = False
# Family names actually registered on this run (populated by load_ocarina_fonts)
_loaded_families: set[str] = set()
# Maps (hole_count, style) -> actual Qt family name registered for that file
_family_map: dict[tuple[int, int], str] = {}


def load_ocarina_fonts() -> None:
    """Register all ocarina TTF fonts with Qt's font database.

    Registers fonts for 12-, 7-, 6-, and 4-hole ocarinas (styles 1 and 2)
    when the corresponding .ttf files are present in the fonts directory.

    Call this once after ``QApplication`` is created, before any widget
    that uses the font is constructed.
    """
    global _fonts_loaded
    if _fonts_loaded:
        return
    for holes in (12, 7, 6, 4):
        for style in (1, 2):
            fname = f"Open-{holes}-Hole-Ocarina-{style}.ttf"
            path = FONTS_DIR / fname
            if path.exists():
                fid = QFontDatabase.addApplicationFont(str(path))
                if fid >= 0:
                    families = QFontDatabase.applicationFontFamilies(fid)
                    _loaded_families.update(families)
                    if families:
                        _family_map[(holes, style)] = families[0]
    _fonts_loaded = True


def ocarina_font_family(hole_count: int, style: int) -> str:
    """Return the Qt font family name for the given hole count and style.

    Falls back to ``'Noto Sans'`` when the dedicated ocarina font has not been
    loaded (e.g. the .ttf file is not yet present in the fonts directory).
    """
    return _family_map.get((hole_count, style), "Noto Sans")


# ---------------------------------------------------------------------------
# Core conversion helpers
# ---------------------------------------------------------------------------

def midi_to_font_char(midi_pitch: int, key: str = "C") -> str:
    """Return the ocarina font glyph character for *midi_pitch*.

    Parameters
    ----------
    midi_pitch:
        Standard MIDI note number (60 = middle C).
    key:
        Ocarina key – ``'C'``, ``'F'``, or ``'G'``.

    Returns
    -------
    str
        A single uppercase letter ``'A'``–``'U'`` when the pitch is
        within the ocarina's range, or ``'x'`` when it is out of range.
    """
    offset = _KEY_OFFSETS.get(key.upper(), 0)
    index = (midi_pitch - 60) + offset
    if index < 0 or index >= len(_TAB_MAP):
        return 'x'
    return _TAB_MAP[index]


def ocarina_key_from_name(name: str) -> str:
    """Extract the ocarina key letter from a preset name.

    Checks for ``'F'`` and ``'G'`` before ``'C'`` to avoid false matches.
    Falls back to ``'C'``.

    Examples
    --------
    >>> ocarina_key_from_name("12-hole Alto C")
    'C'
    >>> ocarina_key_from_name("12-hole Alto F")
    'F'
    >>> ocarina_key_from_name("Soprano G")
    'G'
    """
    upper = name.upper()
    for k in ("F", "G", "C"):
        if k in upper:
            return k
    return "C"


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class FontNote:
    """A single tab note ready for font-based rendering."""
    note_name: str       # e.g. "A3", "C#4"
    midi_pitch: int
    font_char: str       # 'A'–'U', or 'x' for out-of-range
    duration_label: str  # e.g. "♩", "♪"
    is_out_of_range: bool
    hole_count: int = 12              # number of holes on the ocarina (4, 6, 7, 12, …)
    start_ms: float = 0.0             # original absolute start time (ms) — use for all-tracks playback
    compressed_start_ms: float = 0.0  # start time with pauses compressed to PAUSE_THRESHOLD_S
    is_pause: bool = False             # True for synthesised pause frames
    pause_duration_s: float = 0.0     # ACTUAL silence gap in seconds (for display in the banner)


# ---------------------------------------------------------------------------
# Tab generation
# ---------------------------------------------------------------------------

def generate_font_tabs(
    notes: list,
    ocarina_name: str,
    ticks_per_beat: int,
    tempo: int = 500_000,       # microseconds per beat (500000 = 120 BPM)
    tempo_map: list | None = None,  # full [(abs_tick, tempo_us)] list
    hole_count: int = 12,       # number of holes on the ocarina
) -> List[FontNote]:
    """Convert a list of ``NoteEvent`` objects into ``FontNote`` instances.

    Parameters
    ----------
    notes:
        Monophonic list of ``NoteEvent`` objects from the MIDI parser.
    ocarina_name:
        Human-readable ocarina preset name (used to derive the key).
    ticks_per_beat:
        MIDI ticks per beat from the source file.
    tempo:
        MIDI tempo in microseconds per beat.  Used as the initial tempo
        and for the pause-gap threshold calculation (same formula as
        ``_compress_pauses`` in midi_panel.py).
    tempo_map:
        Full ``[(abs_tick, tempo_us)]`` list from the MIDI file.
        When supplied both ``start_ms`` and ``compressed_start_ms`` are
        computed with proper tempo-change support so that they stay in
        sync with the audio across the whole song.

    Returns
    -------
    List[FontNote]
        One entry per input note plus one pause-banner entry per silence
        gap that exceeds ``PAUSE_THRESHOLD_S``.
    """
    from .generator import ticks_to_duration_label, midi_to_note_name  # local import avoids circular dep

    key = ocarina_key_from_name(ocarina_name)
    _tmap = tempo_map if tempo_map else []

    # Pause-detection threshold in ticks — identical formula to _compress_pauses
    # so the two stay in sync regardless of tempo.
    threshold_ticks = int(PAUSE_THRESHOLD_S * 1_000_000 / tempo * ticks_per_beat)

    # ── Step 1: compressed start-tick for every note ─────────────────
    # Mirrors _compress_pauses: any silence gap > threshold is reduced to
    # exactly threshold ticks; all subsequent note ticks shift back by the
    # same amount (cum_remove).
    _cum_remove = 0       # ticks removed so far
    _prev_end_tick = 0    # original end-tick of previous note
    comp_ticks: List[int] = []
    for note in notes:
        gap = note.start_tick - _prev_end_tick
        if gap > threshold_ticks:
            _cum_remove += gap - threshold_ticks
        comp_ticks.append(note.start_tick - _cum_remove)
        _prev_end_tick = note.start_tick + note.duration_ticks

    # ── Step 2: compressed tempo map ─────────────────────────────────
    # When _compress_pauses shifts note ticks, it also shifts every other
    # event (including tempo changes) by the same cum_remove that was in
    # effect at that point in the track.  Reproduce that shift here so
    # _tick_to_ms on a compressed tick uses correct tempo segments.
    #
    # cum_remove at any tick T equals the cum_remove of the last note
    # with start_tick ≤ T (compression only changes at note-on boundaries).
    _compressed_tmap: list = []
    if _tmap and notes:
        _note_cr_pairs = [(n.start_tick, ct) for n, ct in zip(notes, comp_ticks)]
        for tp_tick, tp_tempo in _tmap:
            cr = 0
            for orig_t, comp_t in _note_cr_pairs:
                # Use strict less-than: a tempo event at the same tick as a
                # note_on is processed by _compress_pauses BEFORE that note_on
                # (meta events precede note events at equal ticks), so it only
                # sees the cum_remove that was in effect before that note_on's
                # gap was compressed.
                if orig_t < tp_tick:
                    cr = orig_t - comp_t   # = cum_remove at that note
                else:
                    break
            _compressed_tmap.append((tp_tick - cr, tp_tempo))
        _compressed_tmap.sort(key=lambda x: x[0])

    def _comp_ms(tick: int) -> float:
        """Compressed tick → wall-clock ms using the compressed tempo map."""
        if _compressed_tmap:
            return _tick_to_ms(tick, ticks_per_beat, _compressed_tmap)
        return tick * (tempo / 1_000.0) / ticks_per_beat

    # ── Step 3: build FontNote list ───────────────────────────────────
    result: List[FontNote] = []
    prev_end_tick = 0   # original tick, for gap detection

    for i, note in enumerate(notes):
        comp_start_tick = comp_ticks[i]
        note_start_ms_real = _tick_to_ms(note.start_tick, ticks_per_beat, _tmap)
        gap_ticks = note.start_tick - prev_end_tick

        if gap_ticks > threshold_ticks:
            # Pause banner — compressed start is threshold_ticks before
            # the following note's compressed tick.
            pause_comp_tick = comp_start_tick - threshold_ticks
            prev_end_ms_real = (
                _tick_to_ms(prev_end_tick, ticks_per_beat, _tmap)
                if _tmap else prev_end_tick * (tempo / 1_000.0) / ticks_per_beat
            )
            result.append(FontNote(
                note_name="",
                midi_pitch=-1,
                font_char="",
                duration_label="",
                is_out_of_range=False,
                hole_count=hole_count,
                start_ms=prev_end_ms_real,
                compressed_start_ms=_comp_ms(pause_comp_tick),
                is_pause=True,
                pause_duration_s=(note_start_ms_real - prev_end_ms_real) / 1000.0,
            ))

        char = midi_to_font_char(note.pitch, key)
        result.append(FontNote(
            note_name=midi_to_note_name(note.pitch),
            midi_pitch=note.pitch,
            font_char=char,
            duration_label=ticks_to_duration_label(note.duration_ticks, ticks_per_beat),
            is_out_of_range=(char == 'x'),
            hole_count=hole_count,
            start_ms=note_start_ms_real,
            compressed_start_ms=_comp_ms(comp_start_tick),
        ))
        prev_end_tick = note.start_tick + note.duration_ticks

    # ── DEBUG: print first 5 notes ──────────────────────────────────
    print("[font_tab] First notes (start_ms / compressed_start_ms):", flush=True)
    shown = 0
    for fn in result:
        if fn.is_pause:
            print(f"  [PAUSE  ] gap={fn.pause_duration_s:.2f}s  "
                  f"start_ms={fn.start_ms:.1f}  compressed={fn.compressed_start_ms:.1f}", flush=True)
        else:
            print(f"  [{fn.note_name:5s}] start_ms={fn.start_ms:.1f}  compressed={fn.compressed_start_ms:.1f}", flush=True)
        shown += 1
        if shown >= 5:
            break
    # ────────────────────────────────────────────────────────────────

    return result
