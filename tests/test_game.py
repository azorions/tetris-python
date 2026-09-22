"""Rules engine: SRS kicks, T-spins, scoring, lock delay, clears and modes.

Run from the repo root:  python -m unittest discover -s tests -v
"""
import random
import unittest

from tetris import theme as T
from tetris.game import KICKS_I, KICKS_JLSTZ, MODES, Game, Piece, fmt_time, record_text

# Boards are drawn bottom-aligned: the last string is row 19. X = filled.
TSD = [
    "...X......",   # row 17: overhang over the slot's left corner
    "XXX...XXXX",   # row 18
    "XXXX.XXXXX",   # row 19
]
TSD_NO_LINES = [
    "...X......",
    "XXX...XXX.",
    "XXXX.XXXX.",
]
MINI = [
    "...X.X....",   # both top corners covered...
    "XXX...XXXX",
    "XXX..XXXXX",   # ...but the bottom-left corner is open
]
KICK5 = [
    "....X.....",   # row 15: blocks kick tests 2 and 3
    "..........",
    "XXXX.XXXXX",   # (5,17) blocks tests 1 and 4
    "XXXX..XXXX",
    "XXXX..XXXX",   # (5,19) open: the corners alone would only make a mini
]


def make_game(art=(), mode="marathon", level=1, seed=1):
    g = Game(mode=mode, level=level, rng=random.Random(seed))
    set_board(g, art)
    return g


def set_board(g, art):
    g.grid = [[None] * T.COLS for _ in range(T.ROWS)]
    top = T.ROWS - len(art)
    for i, line in enumerate(art):
        assert len(line) == T.COLS, line
        g.grid[top + i] = ["Z" if ch == "X" else None for ch in line]


def place(g, kind, x, y, rot=0):
    """Replace the falling piece with a fresh one at (x, y) in rotation state rot."""
    g._start_piece(kind)
    g.piece.x, g.piece.y, g.piece.rot = x, y, rot
    g._lowest_y = y
    return g.piece


def finish_clear(g):
    g.update(T.CLEAR_FLASH_MS)
    g.update(T.CLEAR_COLLAPSE_MS)


def cleared(g):
    """The latest ("cleared", n, points, info) event."""
    return [e for e in g.events if e[0] == "cleared"][-1]


def drop(g):
    g.hard_drop()
    if g._phase:
        finish_clear(g)
    return cleared(g)


def tetris_ready(g):
    """Four rows open in column 9 (plus a stray block, so it's no perfect clear) and a vertical I above."""
    set_board(g, ["X........."] + ["XXXXXXXXX."] * 4)
    place(g, "I", 7, 0, rot=1)


def single_ready(g, junk=True):
    """Row 19 open in columns 0-3 and a flat I above them."""
    set_board(g, ([".........X"] if junk else []) + ["....XXXXXX"])
    place(g, "I", 0, 0)


def no_clear(g):
    """A lock that clears nothing (resets the combo, leaves back-to-back alone)."""
    set_board(g, [])
    place(g, "O", 4, 0)
    g.hard_drop()


class RotationTest(unittest.TestCase):
    def test_kick_tables_are_the_srs_tables(self):
        self.assertEqual(KICKS_JLSTZ[(0, 1)], [(0, 0), (-1, 0), (-1, -1), (0, 2), (-1, 2)])
        self.assertEqual(KICKS_I[(0, 1)], [(0, 0), (-2, 0), (1, 0), (-2, 1), (1, -2)])
        for table in (KICKS_JLSTZ, KICKS_I):
            self.assertEqual(len(table), 8)
            for (a, b), tests in table.items():     # undoing a rotation uses the negated kicks
                self.assertEqual(table[(b, a)], [(-x, -y) for x, y in tests])

    def test_o_spawns_centred_and_never_rotates(self):
        self.assertEqual(sorted({x for x, _ in Piece("O").cells()}), [4, 5])
        g = make_game()
        place(g, "O", 4, 18)
        g.update(1)                                     # grounded: the lock timer is running
        self.assertFalse(g.rotate(1))
        self.assertEqual(g._lock_resets, 0)

    def test_i_kicks_off_the_right_wall(self):
        g = make_game()
        place(g, "I", 7, 5, rot=1)                      # vertical in column 9
        self.assertEqual({x for x, _ in g.piece_cells()}, {9})
        self.assertTrue(g.rotate(1))
        self.assertEqual(g._last_kick, 1)               # flat would poke through the wall: shifted left
        self.assertEqual(sorted(x for x, _ in g.piece_cells()), [6, 7, 8, 9])

    def test_counter_clockwise_goes_to_state_l(self):
        g = make_game()
        place(g, "T", 3, 5)
        self.assertTrue(g.rotate(-1))
        self.assertEqual(g.piece.rot, 3)


class TSpinTest(unittest.TestCase):
    def test_tsd_is_a_full_t_spin_double(self):
        g = make_game(TSD)
        place(g, "T", 3, 17, rot=1)
        self.assertTrue(g.rotate(1))
        _, n, points, info = drop(g)
        self.assertEqual((n, info["tspin"], points), (2, "full", 1200))
        self.assertEqual(g.tspins, 1)

    def test_same_slot_without_rotating_is_a_plain_double(self):
        g = make_game(TSD)
        place(g, "T", 3, 17, rot=2)
        _, n, points, info = drop(g)
        self.assertEqual((n, info["tspin"], points), (2, None, 300))

    def test_only_a_rotation_as_the_last_action_counts(self):
        g = make_game()
        place(g, "T", 3, 5)
        self.assertTrue(g.rotate(1))
        self.assertTrue(g._last_rotate)
        g.move(1)
        self.assertFalse(g._last_rotate)
        g.rotate(1)
        g.soft_drop()
        self.assertFalse(g._last_rotate)

    def test_mini_t_spin_single(self):
        g = make_game(MINI)
        place(g, "T", 3, 17, rot=1)
        self.assertTrue(g.rotate(1))
        _, n, points, info = drop(g)
        self.assertEqual((n, info["tspin"], points), (1, "mini", 200))

    def test_fifth_kick_makes_it_a_full_t_spin(self):
        g = make_game(KICK5)
        place(g, "T", 4, 15)
        self.assertTrue(g.rotate(1))
        self.assertEqual((g._last_kick, g.piece.x, g.piece.y), (4, 3, 17))
        _, n, points, info = drop(g)
        self.assertEqual((n, info["tspin"], points), (2, "full", 1200))

    def test_t_spin_without_lines_scores(self):
        g = make_game(TSD_NO_LINES)
        place(g, "T", 3, 17, rot=1)
        self.assertTrue(g.rotate(1))
        _, n, points, info = drop(g)
        self.assertEqual((n, info["tspin"], points), (0, "full", 400))


class ScoringTest(unittest.TestCase):
    def test_clears_are_multiplied_by_level(self):
        for level in (1, 3):
            g = make_game(level=level)
            single_ready(g)
            self.assertEqual(drop(g)[2], 100 * level)
            no_clear(g)
            tetris_ready(g)
            self.assertEqual(drop(g)[2], 800 * level)

    def test_back_to_back(self):
        g = make_game()
        tetris_ready(g)
        self.assertEqual(drop(g)[2], 800)
        no_clear(g)
        tetris_ready(g)
        _, _, points, info = drop(g)
        self.assertEqual((points, info["b2b"]), (1200, True))
        no_clear(g)
        single_ready(g)                                 # an easy clear breaks the chain
        self.assertFalse(drop(g)[3]["b2b"])
        no_clear(g)
        tetris_ready(g)
        _, _, points, info = drop(g)
        self.assertEqual((points, info["b2b"]), (800, False))

    def test_t_spin_without_lines_keeps_back_to_back(self):
        g = make_game()
        tetris_ready(g)
        drop(g)
        set_board(g, TSD_NO_LINES)
        place(g, "T", 3, 17, rot=1)
        g.rotate(1)
        drop(g)
        tetris_ready(g)
        _, _, points, info = drop(g)
        self.assertEqual((points, info["b2b"]), (1200, True))

    def test_combo_bonus_grows_and_resets(self):
        g = make_game()
        points = []
        for _ in range(3):
            single_ready(g)
            _, _, p, info = drop(g)
            points.append((p, info["combo"]))
        self.assertEqual(points, [(100, 0), (150, 1), (200, 2)])
        no_clear(g)
        single_ready(g)
        self.assertEqual(drop(g)[2], 100)

    def test_perfect_clear_bonus(self):
        g = make_game()
        single_ready(g, junk=False)
        _, n, points, info = drop(g)
        self.assertTrue(info["perfect"])
        self.assertEqual((n, points), (1, 900))

    def test_drops_score_per_cell(self):
        g = make_game()
        place(g, "O", 4, 0)
        g.soft_drop()
        g.hard_drop()
        self.assertEqual(g.score, 1 + 17 * 2)          # O falls from row 1 to rows 18-19

    def test_level_rises_every_ten_lines_from_the_start_level(self):
        for start in (5, 15):
            g = make_game(level=start)
            g.lines = 9
            single_ready(g)
            drop(g)
            self.assertEqual(g.level, start + 1)
            self.assertIn(("levelup", start + 1), g.events)


class FlowTest(unittest.TestCase):
    def test_piece_is_gone_while_the_clear_animates(self):
        g = make_game()
        tetris_ready(g)
        g.hard_drop()
        self.assertIsNone(g.piece)
        self.assertEqual(g.flash_rows, [16, 17, 18, 19])
        self.assertFalse(g.move(-1) or g.rotate(1) or g.swap_hold())
        g.update(T.CLEAR_FLASH_MS)
        self.assertEqual((g.flash_rows, g.collapse_rows), ([], [16, 17, 18, 19]))
        self.assertTrue(all(c is None for row in g.grid[16:] for c in row))
        g.update(T.CLEAR_COLLAPSE_MS / 2)
        self.assertAlmostEqual(g.collapse_progress, 0.5, places=2)
        g.update(T.CLEAR_COLLAPSE_MS)
        self.assertIsNotNone(g.piece)
        self.assertEqual(g.collapse_rows, [])
        self.assertEqual(g.grid[19][0], "Z")            # the stray block fell four rows

    def test_lock_resets_run_out(self):
        g = make_game()
        place(g, "T", 3, 18)                            # flat on the floor
        g.update(1)
        for i in range(T.LOCK_RESET_MAX - 1):
            self.assertTrue(g.move(1 if i % 2 == 0 else -1))
        g.update(1)
        self.assertEqual(g.pieces, 0)                   # 14 resets: still sliding
        g.move(1)
        g.update(1)
        self.assertEqual(g.pieces, 1)                   # the 15th used the budget up

    def test_lock_delay(self):
        g = make_game()
        place(g, "T", 3, 18)
        g.update(T.LOCK_DELAY_MS - 1)
        self.assertEqual(g.pieces, 0)
        g.update(1)
        self.assertEqual(g.pieces, 1)

    def test_soft_drop_replaces_the_gravity_step(self):
        g = make_game()
        place(g, "T", 3, 5)
        g.update(T.gravity_ms(1) - 1)
        self.assertTrue(g.soft_drop())
        g.update(1)
        self.assertEqual(g.piece.y, 6)

    def test_hold_once_per_piece(self):
        g = make_game()
        first = g.piece.kind
        self.assertTrue(g.swap_hold())
        self.assertEqual(g.hold, first)
        self.assertFalse(g.swap_hold())
        g.hard_drop()
        self.assertTrue(g.can_hold)

    def test_block_out_ends_the_game(self):
        g = make_game()
        g.grid[1][3:7] = ["Z"] * 4
        g._start_piece("T")
        self.assertEqual((g.over, g.outcome), (True, "topout"))
        self.assertIn(("over",), g.events)

    def test_lock_out_ends_the_game(self):
        g = make_game()
        place(g, "T", 3, -1)                            # nub pokes out above the well
        g.grid[1][3:6] = ["Z"] * 3
        g.hard_drop()
        self.assertEqual(g.outcome, "topout")

    def test_seven_bag(self):
        g = make_game()
        g.bag = []
        pulls = [g._pull() for _ in range(14)]
        self.assertEqual(sorted(pulls[:7]), sorted("IJLOSTZ"))
        self.assertEqual(sorted(pulls[7:]), sorted("IJLOSTZ"))

    def test_ghost_lands_on_the_floor(self):
        g = make_game()
        place(g, "T", 3, 0)
        self.assertEqual(max(y for _, y in g.ghost_cells()), 19)


class ModeTest(unittest.TestCase):
    def test_sprint_finishes_at_forty_lines_and_stops_the_clock(self):
        g = make_game(mode="sprint", level=10)
        self.assertEqual(g.level, 1)
        g.lines = 36
        g.update(1000)
        tetris_ready(g)
        g.hard_drop()
        t = g.elapsed_ms
        finish_clear(g)
        self.assertEqual(g.elapsed_ms, t)
        self.assertEqual((g.over, g.outcome, g.level), (True, "finish", 1))
        self.assertIn(("finish",), g.events)
        self.assertEqual(g.record_value(), t)
        self.assertEqual(g.hud()[1], ("LINES", "40/40"))
        self.assertEqual(g.headline(), "COMPLETE")

    def test_unfinished_sprint_records_nothing(self):
        g = make_game(mode="sprint")
        g.abandon()
        self.assertEqual((g.outcome, g.record_value()), ("ended", None))

    def test_ultra_ends_at_two_minutes(self):
        g = make_game(mode="ultra")
        g.update(T.ULTRA_MS + 5000)
        self.assertEqual((g.over, g.outcome, g.elapsed_ms), (True, "finish", T.ULTRA_MS))
        self.assertEqual(g.hud()[0], ("TIME LEFT", "00:00"))
        self.assertEqual(g.headline(), "TIME UP")

    def test_ultra_clear_in_progress_still_scores(self):
        g = make_game(mode="ultra")
        g.elapsed_ms = T.ULTRA_MS - 10
        tetris_ready(g)
        g.hard_drop()
        finish_clear(g)
        self.assertEqual((g.over, g.lines), (True, 4))
        self.assertEqual(g.record_value(), g.score)

    def test_every_mode_fills_the_panels(self):
        for mode in MODES:
            g = make_game(mode=mode)
            self.assertEqual(len(g.hud()), 4)
            self.assertEqual(len(g.results()), 5)

    def test_formatting(self):
        self.assertEqual(fmt_time(83456, centis=True), "01:23.45")
        self.assertEqual(record_text("sprint", 83456), "01:23.45")
        self.assertEqual(record_text("marathon", 1234567), "1,234,567")


class CalloutTest(unittest.TestCase):
    def test_callout_text(self):
        info = {"tspin": None, "b2b": False, "combo": 0, "perfect": False}
        self.assertEqual(T.callout(4, info), (None, "TETRIS"))
        self.assertEqual(T.callout(4, {**info, "b2b": True}), ("BACK-TO-BACK", "TETRIS"))
        self.assertEqual(T.callout(2, {**info, "tspin": "full", "b2b": True}), ("B2B T-SPIN", "DOUBLE"))
        self.assertEqual(T.callout(0, {**info, "tspin": "mini"}), (None, "MINI T-SPIN"))
        self.assertEqual(T.callout(4, {**info, "perfect": True, "b2b": True}), ("B2B TETRIS", "PERFECT CLEAR"))


if __name__ == "__main__":
    unittest.main()
