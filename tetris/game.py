"""PLACEHOLDER RULES ENGINE.

This exists so the GUI boots and you can see every screen working. Replace the
body of this module with your own implementation; the renderer only needs the
attributes and methods marked API below.

API the GUI reads:
    grid[row][col] -> piece letter or None      flash_rows -> list[int]
    piece (.kind) / piece_cells() / ghost_cells()
    queue -> list[str]   hold -> str|None   can_hold -> bool
    score, lines, level, tetrises, high_scores, show_ghost
    clock_text() -> "MM:SS"
    events -> list of ("lock",) | ("harddrop", rows) | ("clear", row, colors)
              | ("cleared", n, points) | ("levelup", n) | ("over",)
"""
import random

from . import theme as T

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
KICKS = [(0, 0), (-1, 0), (1, 0), (-2, 0), (2, 0), (0, -1)]


class Piece:
    def __init__(self, kind):
        self.kind = kind
        self.rot = 0
        self.x = 3
        self.y = 0

    def cells(self):
        cells = SHAPES[self.kind]
        size = BOX[self.kind]
        for _ in range(self.rot % 4):
            cells = [(size - 1 - cy, cx) for cx, cy in cells]
        return [(self.x + cx, self.y + cy) for cx, cy in cells]


class Game:
    def __init__(self, level=1, high_scores=None, show_ghost=True):
        self.grid = [[None] * T.COLS for _ in range(T.ROWS)]
        self.bag = []
        self.queue = [self._pull() for _ in range(3)]
        self.hold = None
        self.can_hold = True
        self.score = 0
        self.lines = 0
        self.start_level = level
        self.level = level
        self.tetrises = 0
        self.show_ghost = show_ghost
        self.high_scores = high_scores if high_scores is not None else []
        self.flash_rows = []
        self.events = []
        self.over = False
        self.elapsed_ms = 0
        self._gravity_acc = 0.0
        self._lock_acc = None
        self._lock_resets = 0
        self._lowest_y = 0
        self._pending = None            # rows waiting out the flash
        self._cleared_colors = []
        self.piece = None
        self._start_piece(self._pull())

    # ------------------------------------------------------------ helpers ----
    def _pull(self):
        if not self.bag:
            self.bag = list("IJLOSTZ")
            random.shuffle(self.bag)
        return self.bag.pop()

    def _hits(self, piece):
        for x, y in piece.cells():
            if x < 0 or x >= T.COLS or y >= T.ROWS:
                return True
            if y >= 0 and self.grid[y][x]:
                return True
        return False

    def _live(self):
        """Input only steers a falling piece: not during a clear flash, not after top-out."""
        return not self.over and self._pending is None

    def piece_cells(self):
        return self.piece.cells()

    def ghost_cells(self):
        probe = Piece(self.piece.kind)
        probe.rot, probe.x, probe.y = self.piece.rot, self.piece.x, self.piece.y
        while True:
            probe.y += 1
            if self._hits(probe):
                probe.y -= 1
                break
        return probe.cells()

    def clock_text(self):
        s = self.elapsed_ms // 1000
        return f"{s // 60:02d}:{s % 60:02d}"

    # -------------------------------------------------------------- input ----
    def move(self, dx):
        if not self._live():
            return False
        probe = self._clone(dx=dx)
        if not self._hits(probe):
            self.piece = probe
            self._reset_lock()
            return True
        return False

    def rotate(self, direction):
        if not self._live():
            return False
        for kx, ky in KICKS:
            probe = self._clone(dx=kx, dy=ky, drot=direction)
            if not self._hits(probe):
                self.piece = probe
                self._reset_lock()
                return True
        return False

    def soft_drop(self):
        if self._live() and self.move_down():
            self.score += T.SOFT_DROP_POINTS

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
            return
        self.hold, kind = self.piece.kind, self.hold
        if kind is None:
            kind = self.queue.pop(0)
            self.queue.append(self._pull())
        self._start_piece(kind)
        self.can_hold = False

    def move_down(self):
        probe = self._clone(dy=1)
        if self._hits(probe):
            return False
        self.piece = probe
        if probe.y > self._lowest_y:                    # new lowest row: fresh lock budget
            self._lowest_y = probe.y
            self._lock_acc = None
            self._lock_resets = 0
        return True

    def _clone(self, dx=0, dy=0, drot=0):
        p = Piece(self.piece.kind)
        p.rot = self.piece.rot + drot
        p.x = self.piece.x + dx
        p.y = self.piece.y + dy
        return p

    def _reset_lock(self):
        if self._lock_acc is not None and self._lock_resets < T.LOCK_RESET_MAX:
            self._lock_acc = 0.0
            self._lock_resets += 1

    # --------------------------------------------------------------- tick ----
    def update(self, dt_ms):
        if self.over:
            return
        self.elapsed_ms += dt_ms

        if self._pending is not None:                   # line-clear flash window
            self._pending -= dt_ms
            if self._pending <= 0:
                self._collapse()
            return

        grounded = self._hits(self._clone(dy=1))
        if grounded:
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
        cells = self.piece.cells()
        for x, y in cells:
            if y >= 0:
                self.grid[y][x] = self.piece.kind
        self.events.append(("lock",))
        if any(y < 0 for _, y in cells):                # lock-out: piece sticks out above the well
            self._top_out()
            return
        full = [y for y in range(T.ROWS) if all(self.grid[y])]
        if full:
            self.flash_rows = full
            self._pending = T.CLEAR_FLASH_MS
            self._cleared_colors = [list(self.grid[y]) for y in full]
        else:
            self.events.append(("cleared", 0, 0))
            self._spawn()

    def _collapse(self):
        rows = self.flash_rows
        for y, colors in zip(rows, self._cleared_colors):
            self.events.append(("clear", y, colors))
        for y in sorted(rows):
            del self.grid[y]
            self.grid.insert(0, [None] * T.COLS)
        n = len(rows)
        points = T.SCORE_TABLE[n] * self.level
        self.score += points
        if n == 4:
            self.tetrises += 1
        before = self.level
        self.lines += n
        self.level = max(self.start_level, self.lines // T.LINES_PER_LEVEL + 1)
        if self.level > before:
            self.events.append(("levelup", self.level))
        self.events.append(("cleared", n, points))
        self.flash_rows = []
        self._cleared_colors = []
        self._pending = None
        self._spawn()

    def _spawn(self):
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
        if self._hits(self.piece):                      # block-out
            self._top_out()

    def _top_out(self):
        self.over = True
        self.events.append(("over",))
