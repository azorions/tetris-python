"""Single source of truth for colour, type and timing.

Every value here comes straight off the GUI spec sheet. Nothing else in the
codebase should hard-code a colour or a duration.
"""

# ---------------------------------------------------------------- surface ----
# Authored size. Every length in this file and in layout.py is designed at
# this size; Layout scales them to the actual window and rounds to whole
# pixels, so the screen reflows instead of stretching and outlines stay 1px.
SURFACE_W = 880
SURFACE_H = 760
FPS = 60

# ----------------------------------------------------------------- colour ----
PIECE = {
    "I": (0, 240, 240),
    "J": (76, 107, 255),
    "L": (240, 160, 0),
    "O": (240, 240, 0),
    "S": (0, 240, 0),
    "T": (160, 0, 240),
    "Z": (240, 0, 0),
}

WINDOW_BG = (7, 9, 12)
PANEL_BG = (10, 13, 17)
WELL_BG = (6, 8, 10)
GRID_LINE = (19, 27, 33)
PANEL_BORDER = (29, 38, 45)
WELL_BORDER = (42, 55, 64)
LABEL_DIM = (127, 148, 154)
BODY = (207, 227, 230)
ACCENT = (0, 240, 240)      # cyan: headings, selection glow, gravity bar
HILITE = (240, 240, 0)      # yellow: selected menu row, combo text
DANGER = (240, 0, 0)        # game over
WHITE = (255, 255, 255)
KEYCAP_BG = (85, 105, 111)

SCANLINE_ALPHA = 66         # 26% of 255; user-adjustable in options
VIGNETTE_ALPHA = 150

# ------------------------------------------------------------------- type ----
FONT_PIXEL = "assets/fonts/PressStart2P-Regular.ttf"
SIZE_TITLE = 26
SIZE_HEADING = 16
SIZE_LABEL = 9              # panel labels: HOLD, NEXT, SCORE...
SIZE_COMBO = 15
SIZE_MENU = 9
MONO_STAT = 22              # stat values
MONO_BODY = 11
MONO_SMALL = 10
ANTIALIAS = False           # pixel font must never be smoothed

# --------------------------------------------------------------- playfield ----
COLS = 10
ROWS = 20
CELL = 20
CELL_GAP = 1
BLOCK_OUTLINE = 1          # hairline outline
BLOCK_FILL_ALPHA = 14      # interior tint, 0-255. 0 = pure outline
GLOW_SPREAD = 1            # px of phosphor bloom OUTSIDE the outline
GLOW_SPREAD_ACTIVE = 2     # bloom on the falling piece
GLOW_ALPHA = 30            # bloom intensity next to the outline, 0-255; fades outward
PREVIEW_CELL = 14
PREVIEW_GAP = 2

# ---------------------------------------------------------------- timings ----
LOCK_DELAY_MS = 500
LOCK_RESET_MAX = 15
DAS_MS = 170                # delay before auto-shift kicks in
ARR_MS = 40                 # auto-shift interval, per cell
SOFT_DROP_MS = 50           # soft-drop repeat interval while DOWN is held
LINES_PER_LEVEL = 10

CLEAR_FLASH_MS = 90
CLEAR_COLLAPSE_MS = 110
COMBO_IN_MS = 120
COMBO_HOLD_MS = 380
COMBO_OUT_MS = 200
LEVELUP_IN_MS = 140
LEVELUP_HOLD_MS = 520
LEVELUP_OUT_MS = 240
GAMEOVER_SWEEP_MS = 400

SHAKE_LOCK = (2, 80)        # (pixels, ms)
SHAKE_HARDDROP = (3, 90)
SHAKE_TETRIS = (6, 180)

PARTICLES_PER_CELL = 6
PARTICLE_SIZE = 3
PARTICLE_SPEED = (60, 140)  # px/s upward burst range
PARTICLE_GRAVITY = 420      # px/s^2
PARTICLE_LIFE_MS = 400

SCORE_TABLE = {1: 100, 2: 300, 3: 500, 4: 800}
SOFT_DROP_POINTS = 1
HARD_DROP_POINTS = 2


def gravity_ms(level: int) -> int:
    """Milliseconds per row at a given level."""
    return max(80, 800 - (level - 1) * 65)


def clear_name(lines: int) -> str:
    return {1: "SINGLE", 2: "DOUBLE", 3: "TRIPLE", 4: "TETRIS"}.get(lines, "")
