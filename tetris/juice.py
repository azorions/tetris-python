"""Screen shake, line-clear particles, floating callouts and the title backdrop.

All of it is pure presentation: it reads events emitted by the game and never
feeds anything back into it.
"""
import math
import random

import pygame

from . import theme as T
from .game import Piece


class Shake:
    """Offsets the blit of the WHOLE authored surface. Never shake a panel."""

    def __init__(self):
        self.amp = 0.0
        self.left = 0.0
        self.total = 1.0
        self.random_dir = False

    def kick(self, spec, scale: float = 1.0, random_dir: bool = False):
        amp, ms = spec
        amp *= scale
        if amp <= self.amp * (self.left / self.total if self.total else 0):
            return                      # don't let a small kick cut a big one short
        self.amp = amp
        self.left = self.total = ms
        self.random_dir = random_dir

    def update(self, dt_ms: float):
        self.left = max(0.0, self.left - dt_ms)

    def offset(self) -> tuple:
        if self.left <= 0:
            return (0, 0)
        decay = self.left / self.total
        phase = math.sin((1 - decay) * math.pi * 4)
        dy = int(round(self.amp * decay * phase))
        dx = random.randint(-1, 1) * int(self.amp * decay) if self.random_dir else 0
        return (dx, dy)


def to_rgb(color):
    """A piece letter or an RGB/RGBA tuple as a plain (r, g, b); None if it is neither."""
    if isinstance(color, str):
        return T.PIECE.get(color)
    try:
        r, g, b = (int(c) for c in tuple(color)[:3])
    except (TypeError, ValueError):
        return None
    return tuple(max(0, min(255, c)) for c in (r, g, b))


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "color", "life")

    def __init__(self, x, y, color, scale=1.0):
        spread = random.uniform(-0.9, 0.9)      # sideways speed as a fraction of the upward speed
        speed = random.uniform(*T.PARTICLE_SPEED) * scale
        self.x, self.y = float(x), float(y)
        self.vx = speed * spread
        self.vy = -speed
        self.color = color
        self.life = float(T.PARTICLE_LIFE_MS)


class ParticleField:
    def __init__(self):
        self.items = []
        self.scale = 1.0                # layout scale: speed, gravity and chip size follow the window
        self._chips = {}                # (rgb, size) -> chip; its alpha is set per blit

    def burst_row(self, layout, row: int, colors: list):
        """One burst per cleared cell, tinted with that cell's own colour.

        colors may hold piece letters (as the grid does) or RGB/RGBA tuples;
        anything else is skipped here rather than failing later in draw().
        """
        for col, color in enumerate(colors):
            rgb = to_rgb(color) if color is not None else None
            if rgb is None:
                continue
            r = layout.cell_rect(col, row)
            for _ in range(T.PARTICLES_PER_CELL):
                self.items.append(Particle(r.centerx, r.centery, rgb, self.scale))

    def update(self, dt_ms: float):
        dt = dt_ms / 1000.0
        alive = []
        for p in self.items:
            p.life -= dt_ms
            if p.life <= 0:
                continue
            p.vy += T.PARTICLE_GRAVITY * self.scale * dt
            p.x += p.vx * dt
            p.y += p.vy * dt
            alive.append(p)
        self.items = alive

    def draw(self, surf):
        s = max(1, round(T.PARTICLE_SIZE * self.scale))
        half = s / 2
        for p in self.items:
            chip = self._chips.get((p.color, s))
            if chip is None:
                chip = self._chips[(p.color, s)] = pygame.Surface((s, s))
                chip.fill(p.color)
            chip.set_alpha(max(0, min(255, int(255 * (p.life / T.PARTICLE_LIFE_MS)))))
            surf.blit(chip, (int(p.x - half), int(p.y - half)))


class FloatingText:
    """Line-clear callout: scale in, hold, fade out. kicker is the small line above the headline."""

    def __init__(self, text, sub, color, kicker=None):
        self.text, self.sub, self.color, self.kicker = text, sub, color, kicker
        self.t = 0.0
        self.total = T.COMBO_IN_MS + T.COMBO_HOLD_MS + T.COMBO_OUT_MS

    @property
    def done(self):
        return self.t >= self.total

    def update(self, dt_ms):
        self.t += dt_ms

    def scale_alpha(self):
        if self.t < T.COMBO_IN_MS:
            k = self.t / T.COMBO_IN_MS
            return 1.3 - 0.3 * k, 255
        if self.t < T.COMBO_IN_MS + T.COMBO_HOLD_MS:
            return 1.0, 255
        k = (self.t - T.COMBO_IN_MS - T.COMBO_HOLD_MS) / T.COMBO_OUT_MS
        return 1.0, max(0, int(255 * (1 - k)))


class Drop:
    """One tetromino of the title backdrop."""
    __slots__ = ("cells", "cell", "color", "x", "y", "speed")

    def __init__(self, layout, anywhere):
        depth = random.choice((0.7, 1.0, 1.4))  # nearer pieces are bigger, brighter and faster
        kind = random.choice("IJLOSTZ")
        piece = Piece(kind).moved(drot=random.randrange(4))
        ox, oy = piece.x, piece.y
        self.cells = [(x - ox, y - oy) for x, y in piece.cells()]
        self.cell = max(4, round(layout.cell * 1.6 * depth))
        self.color = tuple(int(c * T.RAIN_GLOW * depth) for c in T.PIECE[kind])
        self.x = random.uniform(-self.cell, layout.width - self.cell * 2)
        self.y = random.uniform(-self.cell * 4, layout.height) if anywhere else -self.cell * 4.0
        self.speed = random.uniform(*T.RAIN_SPEED) * depth * layout.scale


class PieceRain:
    """Dim outlined tetrominoes drifting down behind the title screens."""

    def __init__(self):
        self.items = []
        self._size = None

    def update(self, dt_ms, layout):
        if self._size != (layout.width, layout.height):     # new window: scatter a fresh set
            self._size = (layout.width, layout.height)
            self.items = [Drop(layout, anywhere=True) for _ in range(T.RAIN_PIECES)]
        dt = dt_ms / 1000.0
        for d in self.items:
            d.y += d.speed * dt
        self.items = [d if d.y < layout.height else Drop(layout, anywhere=False) for d in self.items]

    def draw(self, surf):
        for d in self.items:
            size = d.cell - max(1, d.cell // 8)
            for cx, cy in d.cells:
                pygame.draw.rect(surf, d.color, (int(d.x + cx * d.cell), int(d.y + cy * d.cell), size, size), width=1)
