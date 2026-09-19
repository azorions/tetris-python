# tetris-python
A pygame-based Tetris with wall kicks, ghost piece, hold, combos, and some juice
(screen shake, particles, CRT scanlines).

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
| `Z` | Rotate counter-clockwise |
| `C` | Hold piece |
| `Esc` | Pause |
| `↑` / `↓` + `Enter` | Navigate / confirm menus |

The window is resizable — the layout reflows to fit.
