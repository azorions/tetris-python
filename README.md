# tetris-python
A pygame-based Tetris with wall kicks, ghost piece, hold, combos, and some juice
(screen shake, particles, CRT scanlines). It also has SRS rotation with T-spins,
three game modes, synthesized sound and music, and saved high scores.

## Requirements
- Python 3.8+
- [pygame-ce](https://pyga.me/) (≥2.4) — installed via `requirements.txt`

## Running

```powershell
# 1. (Recommended) create and activate a virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate          # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the game
python main.py
```

## Controls

| Key | Action |
| --- | --- |
| `←` / `A`, `→` / `D` | Move left / right (hold to auto-shift) |
| `↓` / `S` | Soft drop |
| `Space` | Hard drop |
| `↑` / `W` / `X` | Rotate clockwise |
| `Z` / `Ctrl` | Rotate counter-clockwise |
| `C` / `Shift` | Hold piece |
| `Esc` | Pause |
| `F11` | Fullscreen |
| `↑` / `↓` + `Enter` | Navigate / confirm menus |

The window is resizable — the layout reflows to fit. The game pauses itself when
the window loses focus, and it runs from any folder (`python path/to/main.py`).

## Modes

- **Marathon**: endless. The speed goes up every 10 lines from the start level you pick in Options.
- **Sprint**: clear 40 lines as fast as you can. Ranked by time.
- **Ultra**: score as much as you can in 2 minutes.

Each mode has its own top-5 table. When your run makes the table, type your initials (or use `↑` / `↓`), then press `Enter`.

## Scoring

Guideline scoring, multiplied by your level:

| Clear | Points |
| --- | --- |
| Single / Double / Triple / Tetris | 100 / 300 / 500 / 800 |
| T-spin with 0 / 1 / 2 / 3 lines | 400 / 800 / 1200 / 1600 |
| Mini T-spin with 0 / 1 / 2 lines | 100 / 200 / 400 |
| Back-to-back Tetris or T-spin | ×1.5 |
| Combo (clears in a row) | +50 × combo |
| Perfect clear (empty board after the clear) | +800 / 1200 / 1800 / 2000 |

Soft drop scores 1 point per cell and hard drop scores 2.

## Options

Ghost piece, screen shake, particles, scanlines, start level, sound effects volume and music volume.

## Saves

Settings and high scores are saved in `~/.tetris/` (`settings.json`, `scores.json`).
Set the `TETRIS_HOME` environment variable to keep them somewhere else.

## Tests

```powershell
python -m unittest discover -s tests -v
```

The tests cover the rules engine, the save files, and a headless run through every screen at three window sizes.
Implementation notes for contributors are in [HANDOFF.md](HANDOFF.md).
