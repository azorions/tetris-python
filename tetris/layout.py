"""Every rectangle in the GUI, derived from theme constants and the window size.

The design is authored at T.SURFACE_W x T.SURFACE_H. Layout scales every length
by how much the window differs from that and rounds to whole pixels, so the
screen reflows instead of being stretched: cells, panels and text grow while
outlines stay 1px. Nothing here touches pygame state, so you can unit-test the
layout at any window size.
"""
import pygame

from . import theme as T

MIN_SCALE = 0.6                 # cells never shrink below 12px; smaller windows clip

# Lengths at scale 1.0 (the authored 880x760 design).
COL_GAP = 26
PANEL_W = 196
PANEL_PAD = 12
PANEL_GAP = 12
WELL_PAD = 8
WELL_BORDER = 2                 # a line width: not scaled

LABEL_BLOCK = 9 + 12            # panel label glyph height + gap beneath it
CAPTION_H = 12 + 14             # board caption + gap above it

# Row rhythm inside panels. The *_H values are the rendered heights of the
# mono fonts (keycap incl. its 2px padding), so panels hug their content.
CONTROL_ROWS = 7
CONTROLS_PITCH = 22
KEYCAP_H = 16
SCORE_ROWS = 5
SCORES_PITCH = 20
SCORE_H = 15
STATS_PITCH = 48                # SCORE / LEVEL / LINES / TIME
STATS_VALUE_DY = 14             # value sits this far below its label
STAT_VALUE_H = 28
GRAVITY_H = 72
NEXT_SLOT_GAP = 8

PREVIEW_COLS = 4
PREVIEW_ROWS = 2                # every shape fits in the top two rows of its box


class Layout:
    """Computed for one window size; rebuilt when the window is resized."""

    def __init__(self, width: int = T.SURFACE_W, height: int = T.SURFACE_H):
        self.width, self.height = width, height
        self.scale = max(MIN_SCALE, min(width / T.SURFACE_W, height / T.SURFACE_H))
        px = self.px

        self.cell = px(T.CELL)
        self.cell_gap = px(T.CELL_GAP)
        self.preview_cell = px(T.PREVIEW_CELL)
        self.preview_gap = px(T.PREVIEW_GAP)
        self.panel_pad = px(PANEL_PAD)
        self.label_block = px(LABEL_BLOCK)
        self.controls_pitch = px(CONTROLS_PITCH)
        self.scores_pitch = px(SCORES_PITCH)
        self.stats_pitch = px(STATS_PITCH)
        self.stats_value_dy = px(STATS_VALUE_DY)
        self.next_slot_gap = px(NEXT_SLOT_GAP)
        self.preview_w = self.preview_cell * PREVIEW_COLS + self.preview_gap * (PREVIEW_COLS - 1)
        self.preview_h = self.preview_cell * PREVIEW_ROWS + self.preview_gap * (PREVIEW_ROWS - 1)

        well_pad = px(WELL_PAD)
        well_inner_w = T.COLS * self.cell + (T.COLS - 1) * self.cell_gap
        well_inner_h = T.ROWS * self.cell + (T.ROWS - 1) * self.cell_gap
        well_w = well_inner_w + (well_pad + WELL_BORDER) * 2
        well_h = well_inner_h + (well_pad + WELL_BORDER) * 2

        panel_w, panel_gap, col_gap = px(PANEL_W), px(PANEL_GAP), px(COL_GAP)
        hold_h = self._panel_h(self.preview_h)
        controls_h = self._panel_h(self.controls_pitch * (CONTROL_ROWS - 1) + px(KEYCAP_H))
        scores_h = self._panel_h(self.scores_pitch * (SCORE_ROWS - 1) + px(SCORE_H))
        next_h = self._panel_h(self.preview_h * 3 + self.next_slot_gap * 2)
        stats_h = self.panel_pad * 2 + self.stats_pitch * 3 + self.stats_value_dy + px(STAT_VALUE_H)
        gravity_h = px(GRAVITY_H)

        left_h = hold_h + controls_h + scores_h + panel_gap * 2
        right_h = next_h + stats_h + gravity_h + panel_gap * 2
        well_col_h = well_h + px(CAPTION_H)

        content_w = panel_w * 2 + well_w + col_gap * 2
        x0 = (width - content_w) // 2
        y0 = (height - max(left_h, right_h, well_col_h)) // 2   # centre the tallest column

        self.left_x = x0
        self.well_x = x0 + panel_w + col_gap
        self.right_x = self.well_x + well_w + col_gap
        self.top = y0

        self.well = pygame.Rect(self.well_x, y0, well_w, well_h)
        self.well_inner = pygame.Rect(
            self.well.x + WELL_BORDER + well_pad,
            self.well.y + WELL_BORDER + well_pad,
            well_inner_w, well_inner_h,
        )
        self.well_caption = pygame.Rect(self.well.x, self.well.bottom + px(14), well_w, px(12))

        # left column, stacked top-down
        self.hold = pygame.Rect(self.left_x, y0, panel_w, hold_h)
        self.controls = pygame.Rect(self.left_x, self.hold.bottom + panel_gap, panel_w, controls_h)
        self.scores = pygame.Rect(self.left_x, self.controls.bottom + panel_gap, panel_w, scores_h)

        # right column
        self.next = pygame.Rect(self.right_x, y0, panel_w, next_h)
        self.stats = pygame.Rect(self.right_x, self.next.bottom + panel_gap, panel_w, stats_h)
        self.gravity = pygame.Rect(self.right_x, self.stats.bottom + panel_gap, panel_w, gravity_h)

    def px(self, n: float) -> int:
        """A length from the 880x760 design at this window's scale, in whole pixels."""
        return max(1, round(n * self.scale)) if n > 0 else 0

    def _panel_h(self, content_h: int) -> int:
        return content_h + self.label_block + self.panel_pad * 2

    def cell_rect(self, col: int, row: int) -> pygame.Rect:
        """Screen rect of one playfield cell."""
        return pygame.Rect(
            self.well_inner.x + col * (self.cell + self.cell_gap),
            self.well_inner.y + row * (self.cell + self.cell_gap),
            self.cell, self.cell,
        )

    def preview_origin(self, panel: pygame.Rect, slot: int = 0) -> tuple:
        """Top-left of a mini preview grid inside a panel; slot stacks them in NEXT."""
        x = panel.x + (panel.w - self.preview_w) // 2
        y = panel.y + self.panel_pad + self.label_block + slot * (self.preview_h + self.next_slot_gap)
        return x, y
