# OcarinaTabber

A desktop application that converts MIDI files into custom ocarina tablature.

## Features

- **MIDI import** — load any `.mid` / `.midi` file, inspect all tracks, and select the one you want
- **Ocarina configuration** — supports 6-hole and 12-hole ocarinas in multiple tunings (Soprano C/G, Alto C/F, Tenor C, Bass C)
- **Range validation & auto-transpose** — checks whether the selected melody fits the ocarina's playable range and offers a one-click transpose to the nearest fitting key
- **Polyphony reduction** — ocarinas are monophonic; chords are automatically reduced to a single voice (highest note for melody, lowest for bass — your choice)
- **Drag-and-drop layout editor** — customise the physical hole positions on a canvas to match your specific ocarina before generating tabs
- **Tab viewer** — displays generated fingering frames in a scrollable grid with note names and duration symbols
- **Export** — save the full tab sheet as a **PDF** or high-resolution **PNG**

## Requirements

- Python 3.10+
- Dependencies listed in `requirements.txt`

## Installation

```bash
git clone https://github.com/Rec0iL/OcarinaTabber.git
cd OcarinaTabber
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running

```bash
python main.py
```

## Project Structure

```
OcarinaTabber/
├── main.py                        # Entry point
├── requirements.txt
└── src/
    ├── midi/
    │   ├── parser.py              # MIDI loading, track extraction, NoteEvent
    │   └── polyphony.py           # Chord → monophonic reduction
    ├── ocarina/
    │   ├── models.py              # OcarinaType, HoleLayout, Fingering, presets
    │   └── validator.py           # Range check + auto-transpose logic
    ├── tablature/
    │   ├── generator.py           # NoteEvent → TabNote with fingering mapping
    │   └── renderer.py            # QGraphicsScene tab frame renderer
    └── ui/
        ├── style.qss              # Dark theme (Catppuccin Mocha)
        ├── main_window.py         # QMainWindow shell
        ├── midi_panel.py          # File picker + track list
        ├── ocarina_panel.py       # Type/tuning selector, validation, transpose
        ├── canvas_editor.py       # Drag-and-drop hole layout editor
        └── export_dialog.py       # PDF + PNG export
```

## Hole Layout (12-hole)

The 12-hole ocarina has:
- **8 main finger holes** (4 per hand)
- **2 sub-holes** (S1, S2) — played by the **middle finger** of each hand; they sit next to holes 2 and 6 and are covered together with them
- **2 thumb holes** (T1, T2) on the back face

In the tab frames, sub-holes are rendered smaller with a blue border to distinguish them from main holes.

## License

MIT
