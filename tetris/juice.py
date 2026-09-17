"""Screen shake, line-clear particles and floating combo text.

All three are pure presentation: they read events emitted by the game and never
feed anything back into it.
"""
import random

import pygame

from . import theme as T


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
        import math
        phase = math.sin((1 - decay) * math.pi * 4)
        dy = int(round(self.amp * decay * phase))
        dx = random.randint(-1, 1) * int(self.amp * decay) if self.random_dir else 0
        return (dx, dy)


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "color", "life")

    def __init__(self, x, y, color, scale=1.0):
        angle = random.uniform(-0.9, 0.9)
        speed = random.uniform(*T.PARTICLE_SPEED) * scale
        self.x, self.y = float(x), float(y)
        self.vx = speed * angle
        self.vy = -speed
        self.color = color
        self.life = float(T.PARTICLE_LIFE_MS)


class ParticleField:
    def __init__(self):
        self.items = []
        self.scale = 1.0                # layout scale: speed, gravity and chip size follow the window

    def burst_row(self, layout, row: int, colors: list):
        """One burst per cleared cell, tinted with that cell's own colour.

        colors may hold piece letters (as the grid does) or RGB tuples.
        """
        for col, color in enumerate(colors):
            if color is None:
                continue
            rgb = T.PIECE.get(color, color)
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
        for p in self.items:
            a = max(0, min(255, int(255 * (p.life / T.PARTICLE_LIFE_MS))))
            chip = pygame.Surface((s, s), pygame.SRCALPHA)
            chip.fill((*p.color, a))
            surf.blit(chip, (int(p.x), int(p.y)))


class FloatingText:
    """Combo callout: scale in, hold, fade out."""

    def __init__(self, text, sub, color):
        self.text, self.sub, self.color = text, sub, color
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
