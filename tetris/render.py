"""All drawing. Takes a game state object and paints one frame of the surface.

The renderer only READS the game. If you need something new on screen, expose
it as an attribute on your game object rather than computing it here.

Lengths are written at the authored 880x760 scale and passed through
self.px(), so a Renderer built for a bigger window draws a bigger, equally
crisp frame. Line widths (outlines, borders) are deliberately not scaled.
"""
import os

import pygame

from . import theme as T
from .layout import PREVIEW_ROWS, Layout

SHAPES = {
    "I": ("....", "IIII", "....", "...."),
    "J": ("J...", "JJJ.", "....", "...."),
    "L": ("..L.", "LLL.", "....", "...."),
    "O": (".OO.", ".OO.", "....", "...."),
    "S": (".SS.", "SS..", "....", "...."),
    "T": (".T..", "TTT.", "....", "...."),
    "Z": ("ZZ..", ".ZZ.", "....", "...."),
}

CONTROLS = [
    ("<- ->", "MOVE"),
    ("DOWN", "SOFT DROP"),
    ("SPACE", "HARD DROP"),
    ("Z / CTRL", "ROTATE CCW"),
    ("X / UP", "ROTATE CW"),
    ("C / SHIFT", "HOLD"),
    ("ESC", "PAUSE"),
]

TABLE_ROWS = 5


class Renderer:
    def __init__(self, root_dir=".", size=(T.SURFACE_W, T.SURFACE_H)):
        self.w, self.h = size
        self.layout = Layout(self.w, self.h)
        self.px = self.layout.px
        self.fonts = {}
        self.root = root_dir
        self._load_fonts()
        self._well = self._build_well()
        self._veil = pygame.Surface((self.w, self.h))   # scrim: one surface, alpha set per use
        self._veil.fill(T.WELL_BG)
        self._crt = None                                # vignette + scanlines, built on first use
        self._crt_alpha = None

    # ------------------------------------------------------------- fonts ----
    def _load_fonts(self):
        px = self.px
        path = os.path.join(self.root, T.FONT_PIXEL)
        have = os.path.exists(path)
        for size in (T.SIZE_LABEL, T.SIZE_MENU, T.SIZE_COMBO, T.SIZE_HEADING,
                     T.SIZE_TITLE, 40, 12):
            self.fonts[("pixel", size)] = (
                pygame.font.Font(path, px(size)) if have
                else pygame.font.SysFont("couriernew", px(size + 2), bold=True)
            )
        for size in (T.MONO_SMALL, T.MONO_BODY, T.MONO_STAT):
            self.fonts[("mono", size)] = pygame.font.SysFont("couriernew", px(size + 2), bold=True)

    def pixel(self, size):
        return self.fonts[("pixel", size)]

    def mono(self, size):
        return self.fonts[("mono", size)]

    def text(self, surf, s, font, color, pos, center=False, right=False):
        img = font.render(str(s), T.ANTIALIAS, color)
        r = img.get_rect()
        if center:
            r.center = pos
        elif right:
            r.midright = pos
        else:
            r.topleft = pos
        surf.blit(img, r)
        return r

    # ------------------------------------------------------------ pieces ----
    @staticmethod
    def block(surf, rect, color, kind="locked"):
        """Outline-only block with a phosphor glow. kind: locked|active|ghost."""
        if kind == "ghost":
            ghost = pygame.Surface(rect.size, pygame.SRCALPHA)
            pygame.draw.rect(ghost, (*color, 77), ghost.get_rect(), width=T.BLOCK_OUTLINE)
            surf.blit(ghost, rect.topleft)
            return
        if T.BLOCK_FILL_ALPHA:
            fill = pygame.Surface(rect.size, pygame.SRCALPHA)
            fill.fill((*color, T.BLOCK_FILL_ALPHA))
            surf.blit(fill, rect.topleft)
        spread = T.GLOW_SPREAD_ACTIVE if kind == "active" else T.GLOW_SPREAD
        if spread:
            # Additive bloom. BLEND_RGB_ADD ignores alpha, so each ring's colour is
            # pre-scaled; the opaque black background adds nothing.
            glow = pygame.Surface((rect.w + spread * 2, rect.h + spread * 2))
            for i in range(1, spread + 1):              # i = px outside the outline
                k = T.GLOW_ALPHA * ((spread - i + 1) / spread) ** 2 / 255
                pygame.draw.rect(glow, [int(c * k) for c in color],
                                 pygame.Rect(spread - i, spread - i, rect.w + i * 2, rect.h + i * 2),
                                 width=1)
            surf.blit(glow, (rect.x - spread, rect.y - spread), special_flags=pygame.BLEND_RGB_ADD)
        pygame.draw.rect(surf, color, rect, width=T.BLOCK_OUTLINE)

    def mini_piece(self, surf, kind, origin, dim=False):
        L = self.layout
        ox, oy = origin
        step = L.preview_cell + L.preview_gap
        for row, line in enumerate(SHAPES[kind][:PREVIEW_ROWS]):
            for col, ch in enumerate(line):
                r = pygame.Rect(ox + col * step, oy + row * step, L.preview_cell, L.preview_cell)
                if ch == ".":
                    pygame.draw.rect(surf, T.GRID_LINE, r, width=1)
                else:
                    color = T.PIECE[ch]
                    if dim:
                        color = tuple(c // 3 for c in color)
                    self.block(surf, r, color)

    # ------------------------------------------------------------ chrome ----
    def panel(self, surf, rect, label):
        pygame.draw.rect(surf, T.PANEL_BORDER, rect, width=2)
        pad = self.layout.panel_pad
        self.text(surf, label, self.pixel(T.SIZE_LABEL), T.LABEL_DIM, (rect.x + pad, rect.y + pad))

    def _build_well(self):
        """Well background, border and empty-cell grid: static, so drawn once per window size."""
        L = self.layout
        well = pygame.Surface(L.well.size)
        well.fill(T.WELL_BG)
        pygame.draw.rect(well, T.WELL_BORDER, well.get_rect(), width=2)
        for row in range(T.ROWS):
            for col in range(T.COLS):
                pygame.draw.rect(well, T.GRID_LINE, L.cell_rect(col, row).move(-L.well.x, -L.well.y), width=1)
        return well

    def board(self, surf, game, sweep=None, lock_flash=None):
        """The well and everything in it.

        sweep (0-1) greys the stack out from the bottom after a top-out.
        lock_flash = (cells, k) brightens a just-locked piece while k fades from 1 to 0.
        """
        L = self.layout
        surf.blit(self._well, L.well.topleft)
        pitch = L.cell + L.cell_gap
        falling = game.collapse_rows                    # rows above these slide down, easing in
        ease = game.collapse_progress ** 2
        dead_from = T.ROWS - int(sweep * T.ROWS) if sweep is not None else T.ROWS
        for row in range(T.ROWS):
            dy = round(sum(r > row for r in falling) * pitch * ease) if falling else 0
            for col in range(T.COLS):
                ch = game.grid[row][col]
                if ch:
                    color = T.DEAD if row >= dead_from else T.PIECE[ch]
                    self.block(surf, L.cell_rect(col, row).move(0, dy), color)
        for row in game.flash_rows:                     # solid white during CLEAR_FLASH_MS
            for col in range(T.COLS):
                pygame.draw.rect(surf, T.WHITE, L.cell_rect(col, row))
        if lock_flash and not falling:
            cells, k = lock_flash
            lift = [int(150 * k)] * 3
            for col, row in cells:
                surf.fill(lift, L.cell_rect(col, row), special_flags=pygame.BLEND_RGB_ADD)
        if game.piece:
            if game.show_ghost:
                for col, row in game.ghost_cells():
                    if row >= 0:
                        self.block(surf, L.cell_rect(col, row), T.PIECE[game.piece.kind], "ghost")
            for col, row in game.piece_cells():
                if row >= 0:
                    self.block(surf, L.cell_rect(col, row), T.PIECE[game.piece.kind], "active")
        self.text(surf, f"BOARD {T.COLS} x {T.ROWS} . CELL {L.cell} PX",
                  self.mono(T.MONO_SMALL), T.LABEL_DIM, L.well_caption.center, center=True)

    def _table(self, surf, rows, left, right, y, pitch, name_dx):
        """A five-row name/value table; missing rows show as dim dashes."""
        font = self.mono(T.MONO_BODY)
        for i in range(TABLE_ROWS):
            filled = i < len(rows)
            name, value = rows[i] if filled else ("---", "-")
            self.text(surf, i + 1, font, T.LABEL_DIM, (left, y))
            self.text(surf, name, font, T.LABEL_DIM if filled else T.KEYCAP_BG, (left + name_dx, y))
            self.text(surf, value, font, T.BODY if filled else T.KEYCAP_BG, (right, y + self.px(7)), right=True)
            y += pitch

    def panels(self, surf, game):
        L, px = self.layout, self.px
        pad = L.panel_pad
        self.panel(surf, L.hold, "HOLD")
        if game.hold:
            self.mini_piece(surf, game.hold, L.preview_origin(L.hold), dim=not game.can_hold)

        self.panel(surf, L.controls, "CONTROLS")
        y = L.controls.y + pad + L.label_block
        for key, label in CONTROLS:
            cap = self.mono(T.MONO_SMALL).render(key, T.ANTIALIAS, T.PANEL_BG)
            bg = cap.get_rect(topleft=(L.controls.x + pad, y)).inflate(px(10), px(4))
            pygame.draw.rect(surf, T.KEYCAP_BG, bg)
            surf.blit(cap, cap.get_rect(center=bg.center))
            self.text(surf, label, self.mono(T.MONO_SMALL), T.LABEL_DIM,
                      (L.controls.right - pad, bg.centery), right=True)
            y += L.controls_pitch

        self.panel(surf, L.scores, game.table_label)
        rows = [(name, game.record_text(value)) for name, value in game.high_scores[:TABLE_ROWS]]
        self._table(surf, rows, L.scores.x + pad, L.scores.right - pad,
                    L.scores.y + pad + L.label_block, L.scores_pitch, px(26))

        self.panel(surf, L.next, "NEXT")
        for slot, kind in enumerate(game.queue[:3]):
            self.mini_piece(surf, kind, L.preview_origin(L.next, slot))

        pygame.draw.rect(surf, T.PANEL_BORDER, L.stats, width=2)
        y = L.stats.y + pad
        for label, value in game.hud():
            self.text(surf, label, self.pixel(T.SIZE_LABEL), T.LABEL_DIM, (L.stats.x + pad, y))
            self.text(surf, value, self.mono(T.MONO_STAT), T.BODY, (L.stats.x + pad, y + L.stats_value_dy))
            y += L.stats_pitch

        self.panel(surf, L.gravity, "GRAVITY")
        bar = pygame.Rect(L.gravity.x + pad, L.gravity.y + pad + px(9 + 10),
                          L.gravity.w - pad * 2, px(8))
        pygame.draw.rect(surf, (18, 26, 31), bar)
        slowest, fastest = T.gravity_ms(1), T.gravity_ms(99)
        frac = (slowest - T.gravity_ms(game.level)) / (slowest - fastest)
        fill = pygame.Rect(bar.x, bar.y, int(bar.w * max(0.04, frac)), bar.h)
        pygame.draw.rect(surf, T.ACCENT, fill)
        self.text(surf, f"{T.gravity_ms(game.level)} MS / ROW", self.mono(T.MONO_SMALL),
                  T.LABEL_DIM, (bar.x, bar.bottom + px(7)))

    # ---------------------------------------------------------- overlays ----
    def menu(self, surf, title, items, index, title_color=None, sub=None):
        px = self.px
        cx, cy = self.w // 2, self.h // 2
        extra = max(0, len(items) - 4) * px(15)         # longer menus grow upwards too, staying centred
        y = cy - px(80) - extra
        self.text(surf, title, self.pixel(T.SIZE_TITLE), title_color or T.ACCENT, (cx, y), center=True)
        y += px(74)
        for i, item in enumerate(items):
            if i == index:
                img = self.pixel(T.SIZE_MENU).render(f"> {item}", T.ANTIALIAS, T.PANEL_BG)
                bg = img.get_rect(center=(cx, y)).inflate(px(20), px(10))
                pygame.draw.rect(surf, T.HILITE, bg)
                surf.blit(img, img.get_rect(center=(cx, y)))
            else:
                self.text(surf, item, self.pixel(T.SIZE_MENU), T.LABEL_DIM, (cx, y), center=True)
            y += px(30)
        if sub:
            self.text(surf, sub, self.mono(T.MONO_SMALL), T.LABEL_DIM, (cx, cy + px(150) + extra), center=True)

    def scrim(self, surf, alpha=209):
        self._veil.set_alpha(alpha)
        surf.blit(self._veil, (0, 0))

    def options(self, surf, rows, index):
        px = self.px
        cx, cy = self.w // 2, self.h // 2
        self.text(surf, "OPTIONS", self.pixel(T.SIZE_HEADING), T.ACCENT, (cx, cy - px(130)), center=True)
        y = cy - px(70)
        for i, (label, value) in enumerate(rows):
            color = T.HILITE if i == index else T.LABEL_DIM
            prefix = "> " if i == index else "  "
            self.text(surf, prefix + label, self.mono(T.MONO_BODY), color, (cx - px(150), y))
            self.text(surf, value, self.mono(T.MONO_BODY), T.BODY, (cx + px(150), y + px(7)), right=True)
            y += px(28)
        self.text(surf, "LEFT / RIGHT CHANGE . ESC BACK", self.mono(T.MONO_SMALL),
                  T.LABEL_DIM, (cx, y + px(24)), center=True)

    def scores(self, surf, mode_label, rows):
        """The SCORES screen for one mode; rows are (name, value text)."""
        px = self.px
        cx, cy = self.w // 2, self.h // 2
        self.text(surf, "HIGH SCORES", self.pixel(T.SIZE_HEADING), T.ACCENT, (cx, cy - px(150)), center=True)
        self.text(surf, f"<  {mode_label}  >", self.pixel(T.SIZE_MENU), T.HILITE, (cx, cy - px(112)), center=True)
        y = cy - px(70)
        self._table(surf, rows, cx - px(150), cx + px(150), y, px(28), px(30))
        self.text(surf, "LEFT / RIGHT MODE . ENTER / ESC BACK", self.mono(T.MONO_SMALL),
                  T.LABEL_DIM, (cx, y + px(28) * TABLE_ROWS + px(24)), center=True)

    def game_over(self, surf, game, name_entry, cursor):
        px = self.px
        cx, cy = self.w // 2, self.h // 2
        color = T.ACCENT if game.outcome == "finish" else T.DANGER
        self.text(surf, game.headline(), self.pixel(T.SIZE_HEADING), color, (cx, cy - px(130)), center=True)
        y = cy - px(84)
        for label, value in game.results():
            self.text(surf, label, self.mono(T.MONO_BODY), T.LABEL_DIM, (cx - px(105), y))
            self.text(surf, value, self.mono(T.MONO_BODY), T.BODY, (cx + px(105), y + px(7)), right=True)
            y += px(24)
        if name_entry is not None:
            self.text(surf, "NEW HIGH SCORE - ENTER NAME", self.pixel(T.SIZE_MENU),
                      T.HILITE, (cx, y + px(26)), center=True)
            for i, ch in enumerate(name_entry):
                x = cx + (i - 1) * px(36)
                active = i == cursor
                self.text(surf, ch, self.pixel(T.SIZE_HEADING),
                          T.ACCENT if active else T.BODY, (x, y + px(70)), center=True)
                pygame.draw.rect(surf, T.ACCENT if active else T.WELL_BORDER,
                                 pygame.Rect(x - px(12), y + px(84), px(24), 2))
            self.text(surf, "TYPE A-Z OR UP / DOWN . ENTER SAVE", self.mono(T.MONO_SMALL),
                      T.LABEL_DIM, (cx, y + px(110)), center=True)
        else:
            self.text(surf, "ENTER - PLAY AGAIN . ESC - TITLE", self.mono(T.MONO_SMALL),
                      T.LABEL_DIM, (cx, y + px(30)), center=True)

    def level_up(self, surf, level, t):
        """Non-blocking flourish over live play: scale in, hold, fade."""
        if t < T.LEVELUP_IN_MS:
            scale, alpha = 1.4 - 0.4 * (t / T.LEVELUP_IN_MS), 255
        elif t < T.LEVELUP_IN_MS + T.LEVELUP_HOLD_MS:
            scale, alpha = 1.0, 255
        else:
            k = (t - T.LEVELUP_IN_MS - T.LEVELUP_HOLD_MS) / T.LEVELUP_OUT_MS
            scale, alpha = 1.0, max(0, int(255 * (1 - k)))
        cx, cy = self.layout.well.center
        img = self.pixel(40).render(f"{level:02d}", T.ANTIALIAS, T.ACCENT)
        img = pygame.transform.scale_by(img, scale)
        img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=(cx, cy)))
        cap = self.pixel(T.SIZE_MENU).render("SPEED UP", T.ANTIALIAS, T.HILITE)
        cap.set_alpha(alpha)
        surf.blit(cap, cap.get_rect(center=(cx, cy + self.px(46))))

    def combo(self, surf, floating):
        """Line-clear callout over the top of the well: kicker, headline, then points."""
        scale, alpha = floating.scale_alpha()
        well = self.layout.well
        cx, cy = well.centerx, well.y + well.h // 4
        room = well.w - self.px(16)
        for size in (T.SIZE_COMBO, 12, T.SIZE_MENU):    # step down until the headline fits the well
            img = self.pixel(size).render(floating.text, T.ANTIALIAS, floating.color)
            if img.get_width() <= room:
                break
        img = pygame.transform.scale_by(img, scale)
        img.set_alpha(alpha)
        surf.blit(img, img.get_rect(center=(cx, cy)))
        for line, dy in ((floating.kicker, -self.px(24)), (floating.sub, self.px(26))):   # px() is for lengths: >= 0
            if line:
                small = self.pixel(T.SIZE_MENU).render(line, T.ANTIALIAS, T.BODY)
                small.set_alpha(alpha)
                surf.blit(small, small.get_rect(center=(cx, cy + dy)))

    # ------------------------------------------------------------- crt ----
    def _build_scanlines(self, alpha):
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        for y in range(0, self.h, 3):
            pygame.draw.line(s, (0, 0, 0, alpha), (0, y), (self.w, y))
        return s

    def _build_vignette(self):
        s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        steps = self.px(70)
        for i in range(steps):                          # i = px in from the edge: darkest at the rim
            a = int(T.VIGNETTE_ALPHA * (1 - i / steps) ** 3)
            pygame.draw.rect(s, (0, 0, 0, a),
                             pygame.Rect(i, i, self.w - i * 2, self.h - i * 2), width=1)
        return s

    def crt(self, surf, scanline_alpha=T.SCANLINE_ALPHA):
        """Vignette plus scanlines, pre-combined into one overlay and rebuilt only when the setting changes."""
        if self._crt is None or scanline_alpha != self._crt_alpha:
            self._crt = self._build_vignette()
            if scanline_alpha:
                self._crt.blit(self._build_scanlines(scanline_alpha), (0, 0))
            self._crt_alpha = scanline_alpha
        surf.blit(self._crt, (0, 0))
