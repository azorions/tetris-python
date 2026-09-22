"""Tetris rules: SRS rotation, 7-bag, lock delay, guideline scoring and the three modes.

Pure Python with no pygame import, so it can be unit-tested headless.

API the GUI reads:
    grid[row][col] -> piece letter or None
    piece (.kind) / piece_cells() / ghost_cells()     piece is None while a clear animates
    flash_rows -> rows flashing white; collapse_rows / collapse_progress -> rows falling shut
    queue -> list[str]   hold -> str|None   can_hold -> bool
    score, lines, level, tetrises, tspins, pieces, high_scores, table_label, show_ghost
    mode, over, outcome ("topout" | "finish" | "ended"), headline()
    clock_text() -> "MM:SS"   hud() / results() -> [(label, value)]   record_text(value)
    events -> list of
        ("move",) | ("rotate",) | ("hold",) | ("lock", cells) | ("harddrop", rows)
        | ("clear", row, colors) | ("cleared", n, points, info) | ("levelup", n)
        | ("over",) | ("finish",)
    where info = {"tspin": None|"mini"|"full", "b2b": bool, "combo": int, "perfect": bool}
"""
import random
from typing import NamedTuple

from . import theme as T

# Spawn orientation of each piece inside its BOX x BOX square (SRS).
SHAPES = {
    "I": [(0, 1), (1, 1), (2, 1), (3, 1)],
    "J": [(0, 0), (0, 1), (1, 1), (2, 1)],
    "L": [(2, 0), (0, 1), (1, 1), (2, 1)],
    "O": [(0, 0), (1, 0), (0, 1), (1, 1)],
    "S": [(1, 0), (2, 0), (0, 1), (1, 1)],
    "T": [(1, 0), (0, 1), (1, 1), (2, 1)],
    "Z": [(0, 0), (1, 0), (1, 1), (2, 1)],
}
BOX = {"I": 4, "O": 2, "J": 3, "L": 3, "S": 3, "T": 3, "Z": 3}

# SRS wall kicks: the (dx, dy) tests tried in order for each (from, to) rotation
# state, 0 = spawn, 1 = R, 2, 3 = L. These are the Tetris-wiki tables with y
# negated, because row numbers grow downwards here.
KICKS_JLSTZ = {
    (0, 1): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (1, 0): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
    (1, 2): [(0, 0), (1, 0), (1, 1), (0, -2), (1, -2)],
    (2, 1): [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)],
    (2, 3): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
    (3, 2): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (3, 0): [(0, 0), (-1, 0), (-1, 1), (0, -2), (-1, -2)],
    (0, 3): [(0, 0), (1, 0), (1, -1), (0, 2), (1, 2)],
}
KICKS_I = {
    (0, 1): [(0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)],
    (1, 0): [(0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)],
    (1, 2): [(0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)],
    (2, 1): [(0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)],
    (2, 3): [(0, 0), (2, 0), (-1, 0), (2, -1), (-1, 2)],
    (3, 2): [(0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)],
    (3, 0): [(0, 0), (1, 0), (-2, 0), (1, 2), (-2, -1)],
    (0, 3): [(0, 0), (-1, 0), (2, 0), (-1, -2), (2, 1)],
}

# T-spin corners around the T's centre, clockwise from top-left, and for each
# rotation state the two "front" corners on the side the T points at.
CORNERS = [(-1, -1), (1, -1), (1, 1), (-1, 1)]
FRONT = {0: (0, 1), 1: (1, 2), 2: (2, 3), 3: (3, 0)}


class Mode(NamedTuple):
    label: str
    blurb: str
    lower_is_better: bool = False   # Sprint ranks times, fastest first


MODES = {
    "marathon": Mode("MARATHON", "ENDLESS . FASTER EVERY 10 LINES"),
    "sprint": Mode("SPRINT", f"CLEAR {T.SPRINT_LINES} LINES AS FAST AS YOU CAN", lower_is_better=True),
    "ultra": Mode("ULTRA", "SCORE ALL YOU CAN IN 2 MINUTES"),
}


def fmt_time(ms, centis=False) -> str:
    """"MM:SS", or "MM:SS.cc" with centiseconds."""
    ms = max(0, int(ms))
    s = ms // 1000
    text = f"{s // 60:02d}:{s % 60:02d}"
    return f"{text}.{ms % 1000 // 10:02d}" if centis else text


def record_text(mode, value) -> str:
    """A high-score table value as shown on screen: a time for Sprint, points otherwise."""
    return fmt_time(value, centis=True) if MODES[mode].lower_is_better else f"{value:,}"


class Piece:
    def __init__(self, kind):
        self.kind = kind
        self.rot = 0
        self.x = 4 if kind == "O" else 3            # O takes the centre columns, the rest sit left of centre
        self.y = 0

    def cells(self):
        cells = SHAPES[self.kind]
        size = BOX[self.kind]
        for _ in range(self.rot % 4):
            cells = [(size - 1 - cy, cx) for cx, cy in cells]
        return [(self.x + cx, self.y + cy) for cx, cy in cells]

    def moved(self, dx=0, dy=0, drot=0):
        p = Piece(self.kind)
        p.rot, p.x, p.y = (self.rot + drot) % 4, self.x + dx, self.y + dy
        return p


class Game:
    def __init__(self, mode="marathon", level=1, high_scores=None, show_ghost=True, rng=None):
        self.mode = mode
        self.rng = rng or random.Random()
        self.goal_lines = T.SPRINT_LINES if mode == "sprint" else None
        self.time_limit = T.ULTRA_MS if mode == "ultra" else None
        self.grid = [[None] * T.COLS for _ in range(T.ROWS)]
        self.bag = []
        self.queue = [self._pull() for _ in range(3)]
        self.hold = None
        self.can_hold = True
        self.score = 0
        self.lines = 0
        self.start_level = level if mode == "marathon" else 1   # Sprint and Ultra run at one speed
        self.level = self.start_level
        self.tetrises = 0
        self.tspins = 0
        self.pieces = 0
        self.combo = -1                 # clearing pieces in a row, minus one; -1 = no chain
        self.b2b = False                # the last line clear was a tetris or a T-spin
        self.show_ghost = show_ghost
        self.high_scores = high_scores if high_scores is not None else []
        self.table_label = "BEST TIMES" if MODES[mode].lower_is_better else "HIGH SCORES"
        self.flash_rows = []
        self.collapse_rows = []
        self.collapse_progress = 0.0
        self.events = []
        self.over = False
        self.outcome = None
        self.elapsed_ms = 0
        self._clock_running = True
        self._phase = None              # None while a piece is in play, else "flash" or "collapse"
        self._phase_ms = 0.0
        self._clear = None              # (rows, tspin, perfect) of the clear being animated
        self._gravity_acc = 0.0
        self._lock_acc = None
        self._lock_resets = 0
        self._lowest_y = 0
        self._last_rotate = False       # T-spins need the last successful action to be a rotation
        self._last_kick = 0
        self.piece = None
        self._start_piece(self._pull())

    # ------------------------------------------------------------ helpers ----
    def _pull(self):
        if not self.bag:
            self.bag = list("IJLOSTZ")
            self.rng.shuffle(self.bag)
        return self.bag.pop()

    def _blocked(self, x, y):
        """Walls and floor count as blocked; the open space above the well does not."""
        if x < 0 or x >= T.COLS or y >= T.ROWS:
            return True
        return y >= 0 and self.grid[y][x] is not None

    def _hits(self, piece):
        return any(self._blocked(x, y) for x, y in piece.cells())

    def _live(self):
        """Input only steers a falling piece: not while a clear animates, not after the game ends."""
        return not self.over and self._phase is None and self.piece is not None

    def piece_cells(self):
        return self.piece.cells()

    def ghost_cells(self):
        probe = self.piece
        while not self._hits(probe.moved(dy=1)):
            probe = probe.moved(dy=1)
        return probe.cells()

    def clock_text(self):
        return fmt_time(self.elapsed_ms)

    def pps(self):
        """Pieces locked per second of play."""
        return self.pieces * 1000 / self.elapsed_ms if self.elapsed_ms else 0.0

    # ------------------------------------------------------- what to show ----
    def hud(self):
        """The four stat rows of the side panel for this mode."""
        if self.mode == "sprint":
            return [("TIME", fmt_time(self.elapsed_ms, centis=True)),
                    ("LINES", f"{min(self.lines, self.goal_lines)}/{self.goal_lines}"),
                    ("PIECES", self.pieces),
                    ("PPS", f"{self.pps():.2f}")]
        if self.mode == "ultra":
            left = self.time_limit - self.elapsed_ms
            return [("TIME LEFT", fmt_time(left + 999)),       # a countdown shows whole seconds, rounded up
                    ("SCORE", f"{self.score:,}"),
                    ("LINES", self.lines),
                    ("PPS", f"{self.pps():.2f}")]
        return [("SCORE", f"{self.score:,}"), ("LEVEL", f"{self.level:02d}"),
                ("LINES", self.lines), ("TIME", self.clock_text())]

    def results(self):
        """The stat rows of the results screen."""
        tail = [("TETRISES", self.tetrises), ("T-SPINS", self.tspins)]
        if self.mode == "sprint":
            first = (("TIME", fmt_time(self.elapsed_ms, centis=True)) if self.outcome == "finish"
                     else ("LINES", f"{self.lines}/{self.goal_lines}"))
            return [first, ("PIECES", self.pieces), ("PPS", f"{self.pps():.2f}")] + tail
        if self.mode == "ultra":
            return [("SCORE", f"{self.score:,}"), ("LINES", self.lines), ("PPS", f"{self.pps():.2f}")] + tail
        return [("SCORE", f"{self.score:,}"), ("LINES", self.lines), ("LEVEL", f"{self.level:02d}")] + tail

    def headline(self):
        if self.outcome == "finish":
            return "COMPLETE" if self.mode == "sprint" else "TIME UP"
        return "GAME OVER"

    def record_value(self):
        """What this run puts in its mode's high-score table, or None if it doesn't count."""
        if self.mode == "sprint":
            return self.elapsed_ms if self.outcome == "finish" else None
        return self.score or None

    def record_text(self, value):
        return record_text(self.mode, value)

    # -------------------------------------------------------------- input ----
    def move(self, dx):
        if not self._live():
            return False
        probe = self.piece.moved(dx=dx)
        if self._hits(probe):
            return False
        self.piece = probe
        self._last_rotate = False
        self._reset_lock()
        self.events.append(("move",))
        return True

    def rotate(self, direction):
        """direction +1 = clockwise, -1 = counter-clockwise. Tries the SRS kicks in order."""
        if not self._live() or self.piece.kind == "O":     # O is symmetric: nothing turns, no lock reset
            return False
        src = self.piece.rot
        kicks = KICKS_I if self.piece.kind == "I" else KICKS_JLSTZ
        for i, (dx, dy) in enumerate(kicks[(src, (src + direction) % 4)]):
            probe = self.piece.moved(dx, dy, direction)
            if not self._hits(probe):
                self.piece = probe
                self._last_rotate, self._last_kick = True, i
                self._track_lowest()
                self._reset_lock()
                self.events.append(("rotate",))
                return True
        return False

    def soft_drop(self):
        if self._live() and self.move_down():
            self.score += T.SOFT_DROP_POINTS
            self._gravity_acc = 0.0                     # this row replaces the next gravity step
            return True
        return False

    def hard_drop(self):
        if not self._live():
            return
        rows = 0
        while self.move_down():
            rows += 1
        self.score += rows * T.HARD_DROP_POINTS
        self.events.append(("harddrop", rows))
        self._lock()

    def swap_hold(self):
        if not self._live() or not self.can_hold:
            return False
        self.hold, kind = self.piece.kind, self.hold
        if kind is None:
            kind = self.queue.pop(0)
            self.queue.append(self._pull())
        self.can_hold = False
        self.events.append(("hold",))
        self._start_piece(kind)
        return True

    def abandon(self):
        """END GAME from the pause menu: stop here and report it like a top-out."""
        if not self.over:
            self.over = True
            self.outcome = "ended"
            self.events.append(("over",))

    def move_down(self):
        probe = self.piece.moved(dy=1)
        if self._hits(probe):
            return False
        self.piece = probe
        self._last_rotate = False
        self._track_lowest()
        return True

    def _track_lowest(self):
        if self.piece.y > self._lowest_y:               # new lowest row: fresh lock budget
            self._lowest_y = self.piece.y
            self._lock_acc = None
            self._lock_resets = 0

    def _reset_lock(self):
        if self._lock_acc is not None and self._lock_resets < T.LOCK_RESET_MAX:
            self._lock_acc = 0.0
            self._lock_resets += 1

    # --------------------------------------------------------------- tick ----
    def update(self, dt_ms):
        if self.over:
            return
        if self._clock_running:
            self.elapsed_ms += dt_ms
            if self.time_limit:
                self.elapsed_ms = min(self.elapsed_ms, self.time_limit)

        if self._phase is not None:                     # line-clear animation: flash, then collapse
            self._phase_ms -= dt_ms
            if self._phase == "collapse":
                self.collapse_progress = min(1.0, 1 - self._phase_ms / T.CLEAR_COLLAPSE_MS)
            if self._phase_ms <= 0:
                if self._phase == "flash":
                    self._end_flash()
                else:
                    self._end_collapse()
            return

        if self.time_limit and self.elapsed_ms >= self.time_limit:
            self._finish()
            return

        if self._hits(self.piece.moved(dy=1)):          # grounded
            self._lock_acc = (self._lock_acc or 0.0) + dt_ms
            if self._lock_acc >= T.LOCK_DELAY_MS or self._lock_resets >= T.LOCK_RESET_MAX:
                self._lock()
            return
        # Airborne (e.g. kicked up a row): the lock timer and reset count pause
        # rather than reset, so spinning on the floor can't stall forever.
        self._gravity_acc += dt_ms
        step = T.gravity_ms(self.level)
        while self._gravity_acc >= step:
            self._gravity_acc -= step
            if not self.move_down():
                break

    def _lock(self):
        piece, tspin = self.piece, self._tspin()
        cells = piece.cells()
        for x, y in cells:
            if y >= 0:
                self.grid[y][x] = piece.kind
        self.piece = None
        self.pieces += 1
        self.events.append(("lock", [(x, y) for x, y in cells if y >= 0]))
        if any(y < 0 for _, y in cells):                # lock-out: piece sticks out above the well
            self._top_out()
            return
        full = [y for y in range(T.ROWS) if all(self.grid[y])]
        if not full:
            self._award(0, tspin, False)
            self._next_piece()
            return
        perfect = not any(any(self.grid[y]) for y in range(T.ROWS) if y not in full)
        if self.goal_lines and self.lines + len(full) >= self.goal_lines:
            self._clock_running = False                 # Sprint: this lock sets the time
        self.flash_rows = full
        self._clear = (full, tspin, perfect)
        self._phase, self._phase_ms = "flash", T.CLEAR_FLASH_MS

    def _end_flash(self):
        rows, tspin, perfect = self._clear
        for y in rows:
            self.events.append(("clear", y, list(self.grid[y])))
            self.grid[y] = [None] * T.COLS              # emptied now; the rows above fall during the collapse
        self.flash_rows = []
        self._award(len(rows), tspin, perfect)
        self.collapse_rows = rows
        self.collapse_progress = 0.0
        self._phase, self._phase_ms = "collapse", T.CLEAR_COLLAPSE_MS

    def _end_collapse(self):
        for y in self.collapse_rows:                    # ascending, so each index is still right
            del self.grid[y]
            self.grid.insert(0, [None] * T.COLS)
        self.collapse_rows = []
        self.collapse_progress = 0.0
        self._phase = self._clear = None
        self._next_piece()

    def _tspin(self):
        """None, "mini" or "full" for the piece about to lock (guideline 3-corner rule)."""
        p = self.piece
        if p.kind != "T" or not self._last_rotate:
            return None
        cx, cy = p.x + 1, p.y + 1                       # centre of the T's 3x3 box
        blocked = [self._blocked(cx + dx, cy + dy) for dx, dy in CORNERS]
        if sum(blocked) < 3:
            return None
        a, b = FRONT[p.rot]
        return "full" if (blocked[a] and blocked[b]) or self._last_kick == 4 else "mini"

    def _award(self, n, tspin, perfect):
        """Score one lock that cleared n lines (n may be 0) and report it."""
        if tspin == "mini" and n not in T.TSPIN_MINI_TABLE:
            tspin = "full"
        table = {"full": T.TSPIN_TABLE, "mini": T.TSPIN_MINI_TABLE}.get(tspin, T.SCORE_TABLE)
        level = self.level
        points = table.get(n, 0) * level
        b2b = False
        if n:
            difficult = n == 4 or tspin is not None
            b2b = difficult and self.b2b
            self.b2b = difficult
            self.combo += 1
            if b2b:
                points = points * 3 // 2
            points += T.COMBO_POINTS * self.combo * level
            if perfect:
                points += T.PERFECT_CLEAR_TABLE[n] * level
        else:
            self.combo = -1                             # a lock that clears nothing ends the combo
        self.score += points
        if n == 4:
            self.tetrises += 1
        if tspin:
            self.tspins += 1
        self.lines += n
        if self.mode == "marathon":
            before, self.level = self.level, self.start_level + self.lines // T.LINES_PER_LEVEL
            if self.level > before:
                self.events.append(("levelup", self.level))
        self.events.append(("cleared", n, points, {"tspin": tspin, "b2b": b2b,
                                                   "combo": max(self.combo, 0), "perfect": perfect}))

    def _next_piece(self):
        if self.goal_lines and self.lines >= self.goal_lines:
            self._finish()
        elif self.time_limit and self.elapsed_ms >= self.time_limit:
            self._finish()
        else:
            kind = self.queue.pop(0)
            self.queue.append(self._pull())
            self.can_hold = True
            self._start_piece(kind)

    def _start_piece(self, kind):
        """Put a piece at the spawn point with fresh gravity and lock timers."""
        self.piece = Piece(kind)
        self._gravity_acc = 0.0
        self._lock_acc = None
        self._lock_resets = 0
        self._lowest_y = self.piece.y
        self._last_rotate, self._last_kick = False, 0
        if self._hits(self.piece):                      # block-out
            self._top_out()

    def _finish(self):
        self.over = True
        self.outcome = "finish"
        self.events.append(("finish",))

    def _top_out(self):
        self.over = True
        self.outcome = "topout"
        self.events.append(("over",))
