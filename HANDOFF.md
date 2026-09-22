# Tetris GUI — implementation notes

## Layout

    main.py                 window, reflow-to-window layout, frame loop, juice and sound wiring
    tetris/theme.py         every colour, size, duration and score value (single source of truth)
    tetris/layout.py        every rect, derived from theme sizes and the window size
    tetris/render.py        all drawing; reads the game, never mutates it
    tetris/screens.py       state machine (TITLE/PLAYING/PAUSED/OPTIONS/GAME_OVER/SCORES), input, Settings
    tetris/juice.py         shake, particles, floating callouts, title-screen piece rain
    tetris/game.py          rules: SRS, 7-bag, lock delay, guideline scoring, Marathon/Sprint/Ultra
    tetris/storage.py       settings.json and scores.json under ~/.tetris/ (TETRIS_HOME overrides)
    tetris/audio.py         synthesized effects and music; no audio files
    assets/fonts/           Press Start 2P
    tests/                  unittest: rules, save files, headless smoke run

## Getting it running

    pip install -r requirements.txt
    python main.py
    python -m unittest discover -s tests -v

## The game object

`game.py` imports no pygame, so the rules can be tested headless. The renderer only reads this surface:

| Attribute / method | Meaning |
| --- | --- |
| `grid[row][col]` | piece letter (`"I"`…`"Z"`) or `None` |
| `piece.kind`, `piece_cells()`, `ghost_cells()` | active piece and its hard-drop projection, as `(col,row)` pairs; `piece` is `None` while a clear animates |
| `queue` | next three piece letters |
| `hold`, `can_hold` | hold slot; dims to 30% when spent |
| `hud()` | the four `(label, value)` rows of the stats panel, per mode |
| `results()`, `headline()`, `outcome` | results screen rows and title; outcome is `"topout"`, `"finish"` or `"ended"` |
| `high_scores`, `table_label`, `record_text(v)` | this mode's top-5 table (live list) and how to print its values |
| `flash_rows` | rows flashing white at the start of a clear |
| `collapse_rows`, `collapse_progress` | emptied rows, and 0→1 progress of the rows above falling shut |
| `level`, `show_ghost`, `mode` | gravity bar, ghost toggle, current mode |

Emit these events and the juice and sound happen for free:

    ("move",) ("rotate",) ("hold",)  -> sound
    ("lock", cells)                  -> 2px shake, lock flash on those cells
    ("harddrop", rows)               -> shake scaled by rows fallen
    ("clear", row, colors)           -> particle burst tinted per cell (letters or RGB/RGBA)
    ("cleared", n, points, info)     -> callout text + sound; info = {tspin, b2b, combo, perfect}
    ("levelup", n)                   -> level flourish
    ("over",) / ("finish",)          -> results screen, name entry if the run makes the table

## Rules in brief

- SRS kicks (`KICKS_JLSTZ`, `KICKS_I`) are the Tetris-wiki tables with y negated for the y-down grid.
- A T-spin needs the last successful action to be a rotation and 3 of the 4 corners around the T blocked.
  It is full if both corners it points at are blocked, or if the rotation used kick test 5; otherwise mini.
- Scoring tables live in `theme.py`. Back-to-back is ×1.5 and the combo bonus is +50×combo×level.
- Level goes up every 10 lines from the start level (Marathon only). Sprint and Ultra run at level 1.
- A clear runs for `CLEAR_FLASH_MS` (flash), then `CLEAR_COLLAPSE_MS` (rows fall); input waits for it.

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
`self.px(...)`. `px()` is for lengths and returns 0 for negative numbers, so write
an upward offset as `-self.px(24)`. Leave line widths unscaled. Static layers (the
well grid, scrim, CRT overlay) are built once per renderer, so they are rebuilt only on resize.

## Sound

`Audio` opens the mixer at 44.1 kHz, 16-bit mono (`allowedchanges=0`; without it
SDL may open stereo and mono buffers play at double speed). A background thread
builds the effects, then the Korobeiniki loop. `App.music_state()` decides play,
pause or stop each frame. With no audio device, every call is a no-op.

## Ideas not done yet

- Hidden rows above the well (guideline spawn at rows 21–22, lock-out only when fully above).
- Buffered rotate/hold during a clear (IRS/IHS), 180° rotation, rebindable keys, gamepad.
- Music tempo rising with the level.
