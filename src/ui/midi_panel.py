"""MIDI file upload panel, track selector, and per-track player."""

from __future__ import annotations
import os
import shutil
import tempfile
from pathlib import Path
from typing import Optional

import mido as _mido

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QListWidget, QListWidgetItem, QFileDialog, QFrame, QCheckBox, QComboBox,
    QSlider, QScrollArea,
)
from PySide6.QtCore import Signal, Qt, QProcess, QTimer

from ..midi.parser import load_midi, MidiFile, TrackInfo
from ..tablature.font_tab import PAUSE_THRESHOLD_S

# Soundfont path used by fluidsynth
_SOUNDFONT = "/usr/share/soundfonts/FluidR3_GM.sf2"


def _find_player() -> Optional[tuple]:
    """Return (binary, base_args) for the first available MIDI player."""
    if shutil.which("fluidsynth") and Path(_SOUNDFONT).exists():
        return ("fluidsynth", ["-a", "pulseaudio", "-q", _SOUNDFONT])
    if shutil.which("timidity"):
        return ("timidity", ["-Os", "-q"])
    return None


def _dbg(msg: str):
    print(f"[MidiPanel] {msg}", flush=True)


class MidiPanel(QWidget):
    """Upload a MIDI file and select a track, with per-track playback."""
    track_selected    = Signal(object, object)      # (MidiFile, TrackInfo)
    playback_started  = Signal(object, object, int, float)  # (MidiFile, TrackInfo, mode:0=single/1=all, speed_factor)
    playback_stopped  = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._midi_file: Optional[MidiFile] = None
        self._player_process: Optional[QProcess] = None
        self._temp_midi_path: Optional[str] = None
        self._track_volumes: dict[int, int] = {}  # track_index -> 0..200 (100 = unity)
        self._speed_pct: int = 100  # playback speed percentage (25–150)
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(500)
        self._poll_timer.timeout.connect(self._poll_playback)
        self._init_ui()
        player = _find_player()
        if player:
            _dbg(f"MIDI player found: {player[0]}")
        else:
            _dbg("WARNING: no MIDI player found. Install fluidsynth:  sudo pacman -S fluidsynth")

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)

        # File picker row
        row = QHBoxLayout()
        self._path_label = QLabel("No file loaded")
        self._path_label.setStyleSheet("color: #6c7086; font-size: 11px;")
        self._path_label.setWordWrap(True)
        row.addWidget(self._path_label, 1)

        btn = QPushButton("Open MIDI…")
        btn.setFixedWidth(110)
        btn.clicked.connect(self._open_file)
        row.addWidget(btn)
        layout.addLayout(row)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #45475a;")
        layout.addWidget(sep)

        lbl = QLabel("Tracks")
        lbl.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        layout.addWidget(lbl)

        self._track_list = QListWidget()
        self._track_list.setStyleSheet(
            "QListWidget { background: #181825; border: none; }"
            "QListWidget::item { padding: 4px; color: #cdd6f4; }"
            "QListWidget::item:selected { background: #313244; }"
        )
        self._track_list.itemClicked.connect(self._on_track_clicked)
        layout.addWidget(self._track_list)

        self._info_label = QLabel("")
        self._info_label.setStyleSheet("color: #a6e3a1; font-size: 10px;")
        layout.addWidget(self._info_label)

        # ── Player transport ──────────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #45475a;")
        layout.addWidget(sep2)

        player_lbl = QLabel("Preview Track")
        player_lbl.setStyleSheet("color: #cdd6f4; font-weight: bold;")
        layout.addWidget(player_lbl)

        transport = QHBoxLayout()

        self._play_btn = QPushButton("▶  Play")
        self._play_btn.setEnabled(False)
        self._play_btn.setStyleSheet(
            "QPushButton { background: #a6e3a1; color: #1e1e2e; font-weight: bold; padding: 5px 10px; }"
            "QPushButton:hover { background: #94d09a; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        self._play_btn.clicked.connect(self._play_selected_track)
        transport.addWidget(self._play_btn)

        self._stop_btn = QPushButton("⏹  Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.setStyleSheet(
            "QPushButton { background: #f38ba8; color: #1e1e2e; font-weight: bold; padding: 5px 10px; }"
            "QPushButton:hover { background: #e07090; }"
            "QPushButton:disabled { background: #313244; color: #6c7086; }"
        )
        self._stop_btn.clicked.connect(self._stop_playback)
        transport.addWidget(self._stop_btn)

        layout.addLayout(transport)

        # Play mode selector
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Mode:"))
        self._play_mode_combo = QComboBox()
        self._play_mode_combo.addItems(["Selected track", "All tracks"])
        self._play_mode_combo.setStyleSheet("color: #cdd6f4; background: #313244;")
        mode_row.addWidget(self._play_mode_combo, 1)
        layout.addLayout(mode_row)

        self._ocarina_sound_cb = QCheckBox("Play as Ocarina sound")
        self._ocarina_sound_cb.setChecked(True)
        self._ocarina_sound_cb.setStyleSheet("color: #cdd6f4; font-size: 10px;")
        layout.addWidget(self._ocarina_sound_cb)

        # ── Playback speed slider ─────────────────────────────────────
        speed_row = QHBoxLayout()
        speed_lbl = QLabel("Speed:")
        speed_lbl.setStyleSheet("color: #cdd6f4; font-size: 10px;")
        speed_row.addWidget(speed_lbl)

        self._speed_slider = QSlider(Qt.Horizontal)
        self._speed_slider.setRange(25, 150)
        self._speed_slider.setValue(100)
        self._speed_slider.setTickPosition(QSlider.TicksBelow)
        self._speed_slider.setTickInterval(25)
        self._speed_slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 4px; background: #313244; border-radius: 2px; }"
            "QSlider::handle:horizontal { width: 10px; height: 10px; margin: -3px 0;"
            "  background: #cba6f7; border-radius: 5px; }"
            "QSlider::sub-page:horizontal { background: #cba6f7; border-radius: 2px; }"
        )
        speed_row.addWidget(self._speed_slider, 1)

        self._speed_val_label = QLabel("100%")
        self._speed_val_label.setFixedWidth(36)
        self._speed_val_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._speed_val_label.setStyleSheet("color: #cba6f7; font-size: 10px;")
        speed_row.addWidget(self._speed_val_label)
        layout.addLayout(speed_row)

        def _on_speed_changed(val: int):
            self._speed_pct = val
            self._speed_val_label.setText(f"{val}%")
            if val < 100:
                self._speed_val_label.setStyleSheet("color: #89b4fa; font-size: 10px;")
            elif val > 100:
                self._speed_val_label.setStyleSheet("color: #f9e2af; font-size: 10px;")
            else:
                self._speed_val_label.setStyleSheet("color: #cba6f7; font-size: 10px;")

        self._speed_slider.valueChanged.connect(_on_speed_changed)

        # ── Per-track volume section (visible only in All-tracks mode) ──
        self._vol_section = QWidget()
        vol_section_layout = QVBoxLayout(self._vol_section)
        vol_section_layout.setContentsMargins(0, 4, 0, 0)
        vol_section_layout.setSpacing(2)

        vol_lbl = QLabel("Track Volumes")
        vol_lbl.setStyleSheet("color: #cdd6f4; font-weight: bold; font-size: 10px;")
        vol_section_layout.addWidget(vol_lbl)

        hint = QLabel("Drag past 100% to boost beyond original volume")
        hint.setStyleSheet("color: #6c7086; font-size: 9px;")
        vol_section_layout.addWidget(hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(140)
        scroll.setStyleSheet(
            "QScrollArea { background: #181825; border: 1px solid #45475a; }"
            "QScrollBar:vertical { background: #1e1e2e; width: 8px; }"
            "QScrollBar::handle:vertical { background: #45475a; border-radius: 4px; }"
        )
        self._vol_inner = QWidget()
        self._vol_inner.setStyleSheet("background: #181825;")
        self._vol_inner_layout = QVBoxLayout(self._vol_inner)
        self._vol_inner_layout.setContentsMargins(4, 2, 4, 2)
        self._vol_inner_layout.setSpacing(1)
        self._vol_inner_layout.addStretch()
        scroll.setWidget(self._vol_inner)
        vol_section_layout.addWidget(scroll)

        self._vol_section.setVisible(False)
        layout.addWidget(self._vol_section)
        self._play_mode_combo.currentIndexChanged.connect(self._on_mode_changed)

        self._player_status = QLabel("Select a track and press Play")
        self._player_status.setStyleSheet("color: #6c7086; font-size: 10px;")
        self._player_status.setWordWrap(True)
        layout.addWidget(self._player_status)
        layout.addStretch()

    # ── Mode / volume helpers ─────────────────────────────────────────
    def _on_mode_changed(self, index: int):
        self._vol_section.setVisible(index == 1)

    def _populate_track_volumes(self):
        """Rebuild the per-track volume sliders from the current MIDI file."""
        # Clear old rows (keep the trailing stretch)
        while self._vol_inner_layout.count() > 1:
            item = self._vol_inner_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        self._track_volumes.clear()
        if not self._midi_file:
            return

        for track in self._midi_file.tracks:
            self._track_volumes[track.index] = 100

            row = QWidget()
            row.setStyleSheet("background: transparent;")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(6)

            name = track.name or f"Track {track.index}"
            tl = QLabel(name)
            tl.setFixedWidth(110)
            tl.setStyleSheet("color: #cdd6f4; font-size: 10px;")
            tl.setToolTip(str(track))
            rl.addWidget(tl)

            slider = QSlider(Qt.Horizontal)
            slider.setRange(0, 200)
            slider.setValue(100)
            slider.setStyleSheet(
                "QSlider::groove:horizontal { height: 4px; background: #313244; border-radius: 2px; }"
                "QSlider::handle:horizontal { width: 10px; height: 10px; margin: -3px 0;"
                "  background: #89b4fa; border-radius: 5px; }"
                "QSlider::sub-page:horizontal { background: #89b4fa; border-radius: 2px; }"
            )
            rl.addWidget(slider, 1)

            pct_label = QLabel("100%")
            pct_label.setFixedWidth(36)
            pct_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            pct_label.setStyleSheet("color: #a6e3a1; font-size: 10px;")
            rl.addWidget(pct_label)

            # Capture track.index in closure
            def _on_vol_changed(val, idx=track.index, lbl=pct_label):
                self._track_volumes[idx] = val
                lbl.setText(f"{val}%")
                # Tint label red when muted, yellow when boosted
                if val == 0:
                    lbl.setStyleSheet("color: #f38ba8; font-size: 10px;")
                elif val > 100:
                    lbl.setStyleSheet("color: #f9e2af; font-size: 10px;")
                else:
                    lbl.setStyleSheet("color: #a6e3a1; font-size: 10px;")

            slider.valueChanged.connect(_on_vol_changed)

            self._vol_inner_layout.insertWidget(
                self._vol_inner_layout.count() - 1, row
            )

    # ── File loading ──────────────────────────────────────────────────
    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Open MIDI File", "", "MIDI Files (*.mid *.midi)"
        )
        if not path:
            return
        self._stop_playback()
        _dbg(f"Loading: {path}")
        try:
            self._midi_file = load_midi(path)
        except Exception as e:
            self._path_label.setText(f"Error: {e}")
            _dbg(f"ERROR loading: {e}")
            return

        self._path_label.setText(Path(path).name)
        _dbg(f"Loaded OK — {len(self._midi_file.tracks)} tracks, "
             f"BPM={self._midi_file.bpm:.1f}, tpb={self._midi_file.ticks_per_beat}")
        self._populate_tracks()

    def _populate_tracks(self):
        self._track_list.clear()
        if not self._midi_file:
            return
        for track in self._midi_file.tracks:
            item = QListWidgetItem(str(track))
            item.setData(Qt.UserRole, track)
            self._track_list.addItem(item)
        self._info_label.setText(
            f"BPM: {self._midi_file.bpm:.1f}  |  "
            f"Ticks/beat: {self._midi_file.ticks_per_beat}  |  "
            f"{len(self._midi_file.tracks)} tracks with notes"
        )
        self._populate_track_volumes()

    def _on_track_clicked(self, item: QListWidgetItem):
        track: TrackInfo = item.data(Qt.UserRole)
        if self._midi_file:
            self._play_btn.setEnabled(True)
            _dbg(f"Track selected: {track}")
            self.track_selected.emit(self._midi_file, track)

    # ── Playback ──────────────────────────────────────────────────────
    def _make_temp_midi(self, track: TrackInfo) -> Optional[str]:
        """Write a temp .mid file containing only the selected track/channel.

        Long silence gaps are compressed to PAUSE_THRESHOLD_S seconds so
        playback timing matches the compressed_start_ms values in FontNote.
        When "Play as Ocarina sound" is ticked, strips program_change messages
        and prepends GM program 79 (Ocarina).
        """
        use_ocarina = self._ocarina_sound_cb.isChecked()
        _GM_OCARINA = 79
        try:
            raw = _mido.MidiFile(str(self._midi_file.path))
            _dbg(f"Raw MIDI: {len(raw.tracks)} tracks, type={raw.type}, ch={track.channel}")
            out = _mido.MidiFile(ticks_per_beat=raw.ticks_per_beat)

            is_type0 = raw.type == 0
            ch = track.channel  # None means multi-channel track

            if is_type0:
                src = raw.tracks[0]
                filtered = _mido.MidiTrack()
                for msg in src:
                    if msg.is_meta:
                        filtered.append(msg)
                    elif use_ocarina and msg.type == 'program_change':
                        pass
                    elif ch is None or (hasattr(msg, 'channel') and msg.channel == ch):
                        filtered.append(msg)
                if use_ocarina:
                    pc_ch = ch if ch is not None else 0
                    filtered.insert(0, _mido.Message('program_change', channel=pc_ch, program=_GM_OCARINA, time=0))
                filtered = self._compress_pauses(filtered, raw.ticks_per_beat, self._midi_file.tempo)
                filtered = self._scale_track_tempo(filtered, self._speed_pct)
                out.tracks.append(filtered)
                _dbg(f"  type-0: filtered to ch={ch}, {len(filtered)} msgs")
            else:
                # When the selected track is NOT raw.tracks[0], emit a separate
                # meta track so fluidsynth gets accurate tempo/time-sig info.
                # We recompute the delta times from absolute positions because
                # raw.tracks[0] may interleave non-meta messages between meta
                # events; keeping the original deltas would place tempo changes
                # at wrong ticks and corrupt playback timing.
                if track.index != 0:
                    meta_track = _mido.MidiTrack()
                    _abs_tick = 0
                    _prev_meta_abs = 0
                    for msg in raw.tracks[0]:
                        _abs_tick += msg.time
                        if msg.is_meta:
                            meta_track.append(msg.copy(time=_abs_tick - _prev_meta_abs))
                            _prev_meta_abs = _abs_tick
                    meta_track = self._scale_track_tempo(meta_track, self._speed_pct)
                    out.tracks.append(meta_track)
                    out.type = 1  # two-track → valid Format-1
                    _dbg(f"  meta track 0: {len(meta_track)} msgs")

                if track.index < len(raw.tracks):
                    src_track = raw.tracks[track.index]
                    note_track = _mido.MidiTrack()
                    for msg in src_track:
                        if use_ocarina and msg.type == 'program_change':
                            pass
                        else:
                            note_track.append(msg)
                    if use_ocarina:
                        pc_ch = ch if ch is not None else 0
                        note_track.insert(0, _mido.Message('program_change', channel=pc_ch, program=_GM_OCARINA, time=0))
                    note_track = self._compress_pauses(note_track, raw.ticks_per_beat, self._midi_file.tempo)
                    note_track = self._scale_track_tempo(note_track, self._speed_pct)
                    out.tracks.append(note_track)
                    _dbg(f"  track {track.index}: {len(note_track)} msgs (ocarina={use_ocarina})")

            fd, path = tempfile.mkstemp(suffix=".mid")
            os.close(fd)
            out.save(path)
            _dbg(f"Temp MIDI saved: {path}")
            return path
        except Exception as e:
            _dbg(f"ERROR building temp MIDI: {e}")
            self._player_status.setText(f"Error preparing MIDI: {e}")
            return None

    def _make_full_midi(self, track: TrackInfo) -> Optional[str]:
        """Build a temp MIDI with ALL tracks.

        If 'Play as Ocarina sound' is checked, only the *selected* track's
        channel is remapped to GM 79; all other channels keep their original
        instruments.  No pause compression — other tracks fill the silence.
        Per-track volume percentages from the volume sliders are applied via
        velocity scaling (0-100 % scales down, >100 % boosts, clamped to 127).
        """
        use_ocarina = self._ocarina_sound_cb.isChecked()
        _GM_OCARINA = 79
        try:
            raw = _mido.MidiFile(str(self._midi_file.path))
            ch = track.channel

            # Build a set of raw-track indices that have volume/ocarina overrides
            # _track_volumes maps TrackInfo.index → pct (TrackInfo.index == raw track index)
            volumes = dict(self._track_volumes)  # copy

            out = _mido.MidiFile(ticks_per_beat=raw.ticks_per_beat, type=raw.type)
            for raw_idx, raw_track in enumerate(raw.tracks):
                vol_pct = volumes.get(raw_idx, 100)
                factor = vol_pct / 100.0

                is_selected_track = any(
                    not msg.is_meta and hasattr(msg, 'channel')
                    and (ch is None or msg.channel == ch)
                    for msg in raw_track
                )

                new_track = _mido.MidiTrack()
                pc_inserted = not use_ocarina or not is_selected_track

                for msg in raw_track:
                    # Strip existing program_change on selected channel when ocarina is on
                    if use_ocarina and is_selected_track and not msg.is_meta \
                            and msg.type == 'program_change' \
                            and (ch is None or (hasattr(msg, 'channel') and msg.channel == ch)):
                        continue

                    # Insert ocarina PC before first non-meta msg on selected channel
                    if not pc_inserted and not msg.is_meta:
                        new_track.append(_mido.Message(
                            'program_change',
                            channel=ch if ch is not None else 0,
                            program=_GM_OCARINA, time=0,
                        ))
                        pc_inserted = True

                    # Apply velocity scaling to note_on / note_off messages
                    if not msg.is_meta and factor != 1.0 \
                            and msg.type in ('note_on', 'note_off') \
                            and hasattr(msg, 'velocity'):
                        new_vel = int(msg.velocity * factor)
                        new_vel = max(0, min(127, new_vel))
                        new_track.append(msg.copy(velocity=new_vel))
                    else:
                        new_track.append(msg)

                out.tracks.append(new_track)

            fd, path = tempfile.mkstemp(suffix=".mid")
            os.close(fd)
            out.save(path)
            _dbg(f"Full MIDI saved: {path}")
            return path
        except Exception as e:
            _dbg(f"ERROR building full MIDI: {e}")
            self._player_status.setText(f"Error preparing MIDI: {e}")
            return None

    @staticmethod
    def _scale_track_tempo(track: "_mido.MidiTrack", speed_pct: int) -> "_mido.MidiTrack":
        """Return a copy of *track* with set_tempo meta messages scaled for *speed_pct*.

        Speed < 100 slows playback (larger tempo value = more µs per beat).
        Speed > 100 speeds up (smaller tempo value).
        """
        if speed_pct == 100:
            return track
        factor = 100.0 / speed_pct
        new_track = _mido.MidiTrack()
        for msg in track:
            if msg.is_meta and msg.type == 'set_tempo':
                new_tempo = max(1, int(msg.tempo * factor))
                new_track.append(msg.copy(tempo=new_tempo))
            else:
                new_track.append(msg)
        return new_track

    @staticmethod
    def _compress_pauses(track, ticks_per_beat: int, tempo: int) -> "_mido.MidiTrack":
        """Return a copy of *track* with silence gaps > PAUSE_THRESHOLD_S compressed.

        Uses the same threshold as font_tab.generate_font_tabs so that
        compressed_start_ms in FontNote stays in sync with actual playback.
        """
        threshold_ticks = int(PAUSE_THRESHOLD_S * 1_000_000 / tempo * ticks_per_beat)

        # Convert delta times → absolute times
        abs_times, t = [], 0
        for msg in track:
            t += msg.time
            abs_times.append(t)

        # Walk messages, compressing gaps between note-off and note-on
        cum_remove = 0
        last_off_adj = 0   # adjusted abs-time of last note-off
        new_abs_times = []
        for msg, orig_abs in zip(track, abs_times):
            adjusted = orig_abs - cum_remove
            is_on  = not msg.is_meta and msg.type == 'note_on'  and msg.velocity > 0
            is_off = not msg.is_meta and (
                msg.type == 'note_off' or (msg.type == 'note_on' and msg.velocity == 0)
            )
            if is_on:
                gap = adjusted - last_off_adj
                if gap > threshold_ticks:
                    cum_remove += gap - threshold_ticks
                    adjusted = orig_abs - cum_remove
            new_abs_times.append(adjusted)
            if is_off:
                last_off_adj = adjusted

        # Convert back to delta times
        new_track = _mido.MidiTrack()
        prev = 0
        for msg, new_abs in zip(track, new_abs_times):
            new_track.append(msg.copy(time=max(0, new_abs - prev)))
            prev = new_abs

        # ── DEBUG: show first note timing before/after compression ──
        print(f"[compress] threshold_ticks={threshold_ticks}  cum_remove_final={cum_remove}", flush=True)
        n_shown = 0
        for orig_abs, new_abs_t, msg in zip(abs_times, new_abs_times, track):
            if not msg.is_meta and msg.type == 'note_on' and msg.velocity > 0:
                ms_orig = orig_abs * (tempo / 1000.0) / ticks_per_beat
                ms_new  = new_abs_t * (tempo / 1000.0) / ticks_per_beat
                print(f"  note_on pitch={msg.note}  orig_tick={orig_abs}({ms_orig:.0f}ms)  "
                      f"new_tick={new_abs_t}({ms_new:.0f}ms)", flush=True)
                n_shown += 1
                if n_shown >= 3:
                    break
        # ───────────────────────────────────────────────────────────

        return new_track

    def _play_selected_track(self):
        self._stop_playback()
        item = self._track_list.currentItem()
        if not item or not self._midi_file:
            return
        track: TrackInfo = item.data(Qt.UserRole)
        mode = self._play_mode_combo.currentIndex()  # 0 = single, 1 = all

        player = _find_player()
        if not player:
            msg = "No MIDI player found. Install fluidsynth:  sudo pacman -S fluidsynth"
            _dbg(msg)
            self._player_status.setText(msg)
            return

        midi_path = self._make_temp_midi(track) if mode == 0 else self._make_full_midi(track)
        if not midi_path:
            return
        self._temp_midi_path = midi_path

        binary, base_args = player
        cmd_args = base_args + [midi_path]
        _dbg(f"Launching: {binary} {' '.join(cmd_args)}")

        self._player_process = QProcess(self)
        self._player_process.setProcessChannelMode(QProcess.MergedChannels)
        self._player_process.readyReadStandardOutput.connect(self._on_process_output)
        self._player_process.finished.connect(self._on_playback_finished)
        self._player_process.errorOccurred.connect(self._on_process_error)
        self._player_process.start(binary, cmd_args)
        speed_factor = self._speed_pct / 100.0

        if not self._player_process.waitForStarted(3000):
            err = self._player_process.errorString()
            _dbg(f"ERROR: {binary} failed to start — {err}")
            self._player_status.setText(f"{binary} failed to start: {err}")
            self._cleanup_temp()
            return

        _dbg(f"{binary} started (PID {self._player_process.processId()})")
        self._play_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        label = track.name or f"Track {track.index}"
        self._player_status.setText(f"▶ Playing: {label}  [{binary}]")
        self._poll_timer.start()
        self.playback_started.emit(self._midi_file, track, mode, speed_factor)

    def _on_process_output(self):
        if not self._player_process:
            return
        data = self._player_process.readAllStandardOutput().data().decode(errors="replace")
        for line in data.splitlines():
            line = line.strip()
            if line:
                _dbg(f"  player> {line}")

    def _on_process_error(self, error):
        names = {
            QProcess.FailedToStart: "FailedToStart",
            QProcess.Crashed: "Crashed",
            QProcess.Timedout: "Timedout",
            QProcess.WriteError: "WriteError",
            QProcess.ReadError: "ReadError",
            QProcess.UnknownError: "UnknownError",
        }
        label = names.get(error, str(error))
        _dbg(f"QProcess error: {label}")
        self._player_status.setText(f"Player error: {label}")

    def _stop_playback(self):
        self._poll_timer.stop()
        if self._player_process and self._player_process.state() != QProcess.NotRunning:
            _dbg("Stopping player process")
            self._player_process.kill()
            self._player_process.waitForFinished(1000)
        self._cleanup_temp()
        self._play_btn.setEnabled(self._track_list.currentItem() is not None)
        self._stop_btn.setEnabled(False)
        self._player_status.setText("Stopped.")

    def _on_playback_finished(self, exit_code: int = 0, exit_status=None):
        self._poll_timer.stop()
        _dbg(f"Player exited — code={exit_code}")
        if self._player_process:
            self._on_process_output()
        self._cleanup_temp()
        self._play_btn.setEnabled(self._track_list.currentItem() is not None)
        self._stop_btn.setEnabled(False)
        self._player_status.setText(
            "Playback finished." if exit_code == 0 else f"Player exited with code {exit_code}"
        )
        self.playback_stopped.emit()

    def _poll_playback(self):
        if self._player_process and self._player_process.state() == QProcess.NotRunning:
            self._on_playback_finished()

    def _cleanup_temp(self):
        if self._temp_midi_path:
            try:
                os.unlink(self._temp_midi_path)
                _dbg(f"Temp removed: {self._temp_midi_path}")
            except OSError as e:
                _dbg(f"Cleanup failed: {e}")
            self._temp_midi_path = None

    def closeEvent(self, event):
        self._stop_playback()
        super().closeEvent(event)

    # ── Public transport API (called by main window) ──────────────────
    def play_current_track(self) -> None:
        """Start playback of the currently selected track."""
        self._play_selected_track()

    def stop_current_track(self) -> None:
        """Stop any active playback."""
        self._stop_playback()
        # Emit stopped in case _on_playback_finished doesn't fire
        # (e.g. process was already dead — harmless if emitted twice)
        self.playback_stopped.emit()

