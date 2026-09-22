"""Synthesized sound. Every effect and the music loop are generated at startup
from pulse, triangle and noise waves, so the game ships no audio files and
needs no numpy: samples are built with the array module.

The build runs on a background thread so the window opens straight away;
effects are ready within a fraction of a second and the music a little later.
If no audio device can be opened, Audio quietly does nothing.
"""
import operator
import random
import threading
from array import array

import pygame

from . import theme as T

NOTE_INDEX = {"C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5, "F#": 6, "G": 7,
              "G#": 8, "A": 9, "A#": 10, "B": 11}

# Korobeiniki, the public-domain folk tune, as bars of (note, eighths); None rests.
TUNE_A = [
    [("E5", 2), ("B4", 1), ("C5", 1), ("D5", 2), ("C5", 1), ("B4", 1)],
    [("A4", 2), ("A4", 1), ("C5", 1), ("E5", 2), ("D5", 1), ("C5", 1)],
    [("B4", 3), ("C5", 1), ("D5", 2), ("E5", 2)],
    [("C5", 2), ("A4", 2), ("A4", 2), (None, 2)],
    [(None, 1), ("D5", 2), ("F5", 1), ("A5", 2), ("G5", 1), ("F5", 1)],
    [("E5", 3), ("C5", 1), ("E5", 2), ("D5", 1), ("C5", 1)],
    [("B4", 2), ("B4", 1), ("C5", 1), ("D5", 2), ("E5", 2)],
    [("C5", 2), ("A4", 2), ("A4", 2), (None, 2)],
]
TUNE_B = [
    [("E5", 4), ("C5", 4)],
    [("D5", 4), ("B4", 4)],
    [("C5", 4), ("A4", 4)],
    [("G#4", 4), ("B4", 2), (None, 2)],
    [("E5", 4), ("C5", 4)],
    [("D5", 4), ("B4", 4)],
    [("C5", 2), ("E5", 2), ("A5", 4)],
    [("G#5", 6), (None, 2)],
]
ROOTS_A = ["E", "A", "E", "A", "D", "C", "E", "A"]      # chord root under each bar
ROOTS_B = ["A", "E", "A", "E", "A", "E", "A", "E"]
BASS_NOTES = {"E": ("E2", "E3"), "A": ("A2", "A3"), "D": ("D2", "D3"), "C": ("C2", "C3")}


def note_hz(name):
    """Scientific pitch to Hz: "A4" -> 440.0, "G#5" -> 830.6."""
    midi = 12 * (int(name[-1]) + 1) + NOTE_INDEX[name[:-1]]
    return 440.0 * 2 ** ((midi - 69) / 12)


def concat(parts):
    out = array("h")
    for part in parts:
        out.extend(part)
    return out


def mix(*tracks):
    """Tracks laid over each other from the same start, clipped to 16 bits."""
    total = [0] * max(len(t) for t in tracks)
    for track in tracks:
        for i, v in enumerate(track):
            total[i] += v
    return array("h", (max(-32768, min(32767, v)) for v in total))


def to_stereo(mono):
    out = array("h", bytes(4 * len(mono)))
    out[0::2] = mono
    out[1::2] = mono
    return out


def _wave(kind, phase, duty):
    """One sample of a zero-mean waveform (a pulse's high and low levels are set so its average is 0)."""
    if kind == "square":
        return 2 * (1 - duty) if phase < duty else -2 * duty
    return 4.0 * abs(phase - 0.5) - 1.0                         # triangle


class Synth:
    """Builds 16-bit mono sample arrays at one sample rate."""

    def __init__(self, rate):
        self.rate = rate
        self._rand = random.Random(7).random

    def n(self, ms):
        return max(1, int(self.rate * ms / 1000))

    def tone(self, freq, ms, vol, wave="square", to=None, duty=0.5, attack=2, release=None):
        """A short sound effect voice. Pitch glides exponentially from freq to `to`;
        attack and release are ms of linear fade (release defaults to half the length).
        wave "noise" is sample-and-hold noise that changes value freq times a second."""
        n = self.n(ms)
        a, r = self.n(attack), self.n(ms / 2 if release is None else release)
        amp = 32767 * vol
        step = freq / self.rate
        glide = ((to or freq) / freq) ** (1 / n)
        out = array("h", bytes(2 * n))
        phase, held = 0.0, 0.0
        for i in range(n):
            phase += step
            if phase >= 1.0:
                phase -= int(phase)
                held = self._rand() * 2 - 1
            s = held if wave == "noise" else _wave(wave, phase, duty)
            out[i] = int(amp * s * min(1.0, i / a, (n - i) / r))
            step *= glide
        return out

    def note(self, freq, n, vol, wave, duty=0.5, attack=2, release=20):
        """A steady note of exactly n samples. One short block holding a whole number of
        cycles is tiled to length, so even long notes cost only a few thousand loop steps."""
        period = self.rate / freq
        cycles = min(range(1, 17), key=lambda k: abs(k * period - round(k * period)))
        size = round(cycles * period)
        amp = 32767 * vol
        block = array("h", (int(amp * _wave(wave, (i * cycles / size) % 1.0, duty)) for i in range(size)))
        out = (block * (n // size + 1))[:n]
        a, r = min(n, self.n(attack)), min(n, self.n(release))
        for i in range(a):
            out[i] = out[i] * i // a
        for i in range(r):
            out[n - 1 - i] = out[n - 1 - i] * i // r
        return out


def build_sfx(s):
    """Every sound effect, by the name the game plays it with."""
    sq, tri, noise = "square", "triangle", "noise"

    def arp(notes, ms, vol, wave=sq, duty=0.25, last=None):
        """Notes one after another; the last one rings on for `last` ms."""
        last = last or ms * 2
        parts = [s.tone(note_hz(n), ms, vol, wave, duty=duty, release=ms * 0.4) for n in notes[:-1]]
        parts.append(s.tone(note_hz(notes[-1]), last, vol, wave, duty=duty, release=last * 0.8))
        return concat(parts)

    def bed(name, ms, vol=0.16):
        return s.tone(note_hz(name), ms, vol, tri, release=ms * 0.75)

    return {
        "move": s.tone(1046, 16, 0.08, sq, duty=0.125, release=8),
        "rotate": s.tone(700, 38, 0.08, sq, to=1050, duty=0.25, release=18),
        "hold": concat([s.tone(523, 40, 0.20, tri, release=15), s.tone(784, 70, 0.20, tri, release=50)]),
        "lock": mix(s.tone(160, 60, 0.40, tri, to=80, release=45), s.tone(2400, 28, 0.07, noise, release=24)),
        "harddrop": mix(s.tone(200, 150, 0.55, tri, to=45, release=120),
                        s.tone(1600, 90, 0.12, noise, to=500, release=80)),
        "clear1": arp(["G5", "C6"], 45, 0.10),
        "clear2": arp(["E5", "G5", "C6"], 45, 0.10),
        "clear3": arp(["C5", "E5", "G5", "C6"], 45, 0.10),
        "tetris": mix(arp(["C5", "E5", "G5", "C6", "E6", "G6", "C7"], 38, 0.10, last=320), bed("C4", 560)),
        "tspin": concat([s.tone(320, 110, 0.08, sq, to=1280, duty=0.25, release=30),
                         arp(["E6", "B6"], 60, 0.20, wave=tri, last=260)]),
        "perfect": mix(arp(["C6", "E6", "G6", "C7", "E7"], 70, 0.10, last=420), bed("C5", 700)),
        "levelup": arp(["A5", "C#6", "E6", "A6"], 70, 0.10, last=260),
        "gameover": arp(["G4", "F#4", "F4", "E4"], 190, 0.10, duty=0.5, last=600),
        "finish": mix(arp(["C5", "G5", "C6", "E6", "G6", "C7"], 60, 0.10, last=450), bed("C4", 760)),
        "menu_move": s.tone(1320, 22, 0.14, tri, release=14),
        "menu_select": concat([s.tone(660, 30, 0.08, sq, duty=0.25, release=10),
                               s.tone(1320, 70, 0.08, sq, duty=0.25, release=50)]),
        "pause": concat([s.tone(880, 50, 0.20, tri, release=20), s.tone(587, 90, 0.20, tri, release=60)]),
    }


def build_music(s, bpm):
    """Korobeiniki in A-A-B form: a 25% pulse lead over a bouncing triangle octave bass."""
    eighth = round(s.rate * 30 / bpm)                   # samples per eighth note: 8820 at 44.1 kHz, 150 BPM
    leads, basses = {}, {}

    def lead(name, eighths):
        if (name, eighths) not in leads:
            n = eighths * eighth
            leads[name, eighths] = (array("h", bytes(2 * n)) if name is None
                                    else s.note(note_hz(name), n, 0.12, "square", duty=0.25, attack=3, release=30))
        return leads[name, eighths]

    def bass(name):
        if name not in basses:
            basses[name] = s.note(note_hz(name), eighth, 0.20, "triangle", attack=2, release=90)
        return basses[name]

    bars = []
    for tune, roots in ((TUNE_A, ROOTS_A), (TUNE_B, ROOTS_B)):
        for notes, root in zip(tune, roots):
            low, high = BASS_NOTES[root]
            top = concat(lead(name, eighths) for name, eighths in notes)
            bottom = concat(bass(low if i % 2 == 0 else high) for i in range(8))
            bars.append(array("h", map(operator.add, top, bottom)))    # a bar at a time: short GIL holds
    a, b = bars[:8], bars[8:]
    return concat(a + a + b)


class Audio:
    """Plays the synthesized effects and music. Without an audio device every call does nothing."""

    def __init__(self):
        self.ok = False
        self.sounds = {}
        self.sfx_volume = self.music_volume = 1.0
        self._music = None
        self._music_state = "stopped"                   # "playing" | "paused" | "stopped"
        self._built_sfx = self._built_music = None      # handed over by the build thread
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init(44100, -16, 1, 512, allowedchanges=0)
            rate, size, channels = pygame.mixer.get_init()
        except (pygame.error, TypeError):
            return
        if size != -16 or channels not in (1, 2):
            return
        self.rate, self.channels = rate, channels
        pygame.mixer.set_reserved(1)                    # channel 0 is the music's alone
        self._channel = pygame.mixer.Channel(0)
        self.ok = True
        threading.Thread(target=self._build, name="tetris-synth", daemon=True).start()

    def _build(self):
        synth = Synth(self.rate)
        self._built_sfx = build_sfx(synth)              # effects first: the menus want them right away
        self._built_music = build_music(synth, T.MUSIC_BPM)

    def _sound(self, samples):
        return pygame.mixer.Sound(buffer=to_stereo(samples) if self.channels == 2 else samples)

    def play(self, name):
        if self.ok and self.sfx_volume > 0:
            sound = self.sounds.get(name)
            if sound is not None:
                sound.play()

    def set_volumes(self, sfx, music):
        self.sfx_volume, self.music_volume = sfx, music
        self._apply_volumes()

    def _apply_volumes(self):
        for sound in self.sounds.values():
            sound.set_volume(T.SFX_VOLUME * self.sfx_volume)
        if self._music is not None:
            self._music.set_volume(T.MUSIC_VOLUME * self.music_volume)

    def restart_music(self):
        """A new game starts the tune from the top."""
        if self.ok and self._music_state != "stopped":
            self._channel.stop()
            self._music_state = "stopped"

    def update(self, want):
        """Once a frame: pick up finished sounds, then steer the music to want ("play", "pause", "stop")."""
        if not self.ok:
            return
        if self._built_sfx is not None:
            self.sounds = {name: self._sound(samples) for name, samples in self._built_sfx.items()}
            self._built_sfx = None
            self._apply_volumes()
        if want == "play" and self._music is None and self._built_music is not None:
            self._music = self._sound(self._built_music)     # ~30 ms, so only once it's first needed
            self._built_music = None
            self._apply_volumes()
        playing = want == "play" and self._music is not None and self.music_volume > 0
        if playing and self._music_state != "playing":
            if self._music_state == "paused":
                self._channel.unpause()
            else:
                self._channel.play(self._music, loops=-1)
            self._music_state = "playing"
        elif want == "pause" and self._music_state == "playing":
            self._channel.pause()
            self._music_state = "paused"
        elif not playing and want != "pause" and self._music_state != "stopped":
            self._channel.stop()
            self._music_state = "stopped"
