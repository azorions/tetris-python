# Tetris GUI — implementation notes

Drop-in GUI shell for `azorions/tetris-python`. Boots and plays as-is; the rules
module is a placeholder you are meant to replace.

## Layout

    main.py                 window, reflow-to-window layout, frame loop, juice wiring
    tetris/theme.py         every colour, size and duration (single source of truth)
    tetris/layout.py        every rect, derived from theme sizes and the window size
    tetris/render.py        all drawing; reads the game, never mutates it
    tetris/screens.py       state machine (TITLE/PLAYING/PAUSED/OPTIONS/GAME_OVER/SCORES) + input routing
    tetris/juice.py         shake, particles, floating combo text
    tetris/game.py          PLACEHOLDER rules — replace this
    assets/fonts/           Press Start 2P goes here

## Getting it running

    pip install -r requirements.txt
    python main.py

## Replacing game.py

The renderer only reads this surface:

| Attribute / method | Meaning |
| --- | --- |
| `grid[row][col]` | piece letter (`"I"`…`"Z"`) or `None` |
| `piece.kind`, `piece_cells()`, `ghost_cells()` | active piece and its hard-drop projection, as `(col,row)` pairs |
| `queue` | next three piece letters |
| `hold`, `can_hold` | hold slot; dims to 30% when spent |
| `score`, `lines`, `level`, `tetrises` | HUD numbers |
| `flash_rows` | rows currently flashing white mid-clear |
| `clock_text()` | `"MM:SS"` |
| `high_scores` | list of `(name, score)`, already sorted |
| `events` | queue the GUI drains each frame |

Emit these events and the juice happens for free:

    ("lock",)                     -> 2px shake
    ("harddrop", rows)            -> shake scaled by rows fallen
    ("clear", row, colors)        -> particle burst tinted per cell (letters or RGB)
    ("cleared", n, points)        -> combo text + tetris shake; n=0 (no clear) resets the combo
    ("levelup", n)                -> level flourish
    ("over",)                     -> GAME_OVER screen, name entry if top five

## How the screen follows the window size

The design is authored at 880x760 (`T.SURFACE_W/H`). Every frame, `App.draw`
calls `fit_to_window()`. When the window size has changed, it builds a
window-sized surface and a new `Renderer`. That renderer's `Layout` scales
every length by `min(window_w / 880, window_h / 760)` and rounds each one to
whole pixels: cells, gaps, panels, font sizes and text offsets. The frame is
then blitted 1:1, so nothing is stretched. Blocks keep 1px outlines and text
is rendered fresh at the new size. The scale never drops below
`layout.MIN_SCALE` (0.6, which gives 12px cells); smaller windows clip.

When you add drawing code, write lengths at the 880x760 scale and wrap them in
`self.px(...)`. Leave line widths unscaled.

## Things deliberately left to you

- Sound (no audio in the spec yet — hook `drain_events` in `main.py`).
- Persisting settings and high scores to `~/.tetris/`.
- SRS wall kicks are simplified in the placeholder (`KICKS` in `game.py`).
