"""Headless run of the real App through every screen and mode, at three window sizes.

Uses SDL's dummy video and audio drivers, and points TETRIS_HOME at a temp
folder so the real save files are never touched.
"""
import os
import random
import tempfile
import unittest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame  # noqa: E402

import main  # noqa: E402
from tetris import storage  # noqa: E402
from tetris import theme as T  # noqa: E402
from tetris.screens import (GAME_OVER, OPTIONS, PAUSED, PLAYING, SCORES, TITLE,  # noqa: E402
                            TITLE_ITEMS)

PLAY_KEYS = [pygame.K_LEFT, pygame.K_RIGHT, pygame.K_z, pygame.K_x, pygame.K_UP, pygame.K_c,
             pygame.K_LSHIFT, pygame.K_LCTRL, pygame.K_DOWN, pygame.K_SPACE]


class SmokeTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("TETRIS_HOME")
        os.environ["TETRIS_HOME"] = self._tmp.name
        self.app = main.App()
        self.rng = random.Random(5)

    def tearDown(self):
        pygame.quit()
        if self._old is None:
            os.environ.pop("TETRIS_HOME", None)
        else:
            os.environ["TETRIS_HOME"] = self._old
        self._tmp.cleanup()

    # ----------------------------------------------------------- helpers ----
    def frames(self, n, dt=16):
        for _ in range(n):
            self.app.step(dt)

    def press(self, key, frames=1):
        for kind in (pygame.KEYDOWN, pygame.KEYUP):
            pygame.event.post(pygame.event.Event(kind, key=key, mod=0, unicode="", scancode=0))
        self.frames(frames)

    def state(self):
        return self.app.screens.state

    def start(self, label):
        """From the title screen, pick a menu item by name."""
        self.assertEqual(self.state(), TITLE)
        while TITLE_ITEMS[self.app.screens.menu_index] != label:
            self.press(pygame.K_DOWN)
        self.press(pygame.K_RETURN)

    def play_until_over(self, limit=3000):
        """Mash random keys, with a hard drop every few frames, until the game ends."""
        for i in range(limit):
            if self.state() != PLAYING:
                return
            key = pygame.K_SPACE if i % 6 == 5 else self.rng.choice(PLAY_KEYS)
            self.press(key)
        self.fail("game never ended")

    def leave_results(self):
        self.assertEqual(self.state(), GAME_OVER)
        self.frames(60)                                 # sweep and fade: keys are ignored until done
        self.assertTrue(self.app.results_ready())
        if self.app.screens.name_entry is not None:
            for key in (pygame.K_b, pygame.K_BACKSPACE, pygame.K_q, pygame.K_UP, pygame.K_RIGHT, pygame.K_RETURN):
                self.press(key)
            self.assertIsNone(self.app.screens.name_entry)
        self.press(pygame.K_ESCAPE)
        self.assertEqual(self.state(), TITLE)

    # ------------------------------------------------------------- tests ----
    def test_every_mode_and_screen(self):
        for size in ((880, 760), (528, 456), (1600, 900)):
            pygame.display.set_mode(size, pygame.RESIZABLE)
            self.frames(3)                              # the layout reflows on the next draw
            self.assertEqual(self.app.surface.get_size(), size)

            self.start("MARATHON")
            self.frames(30)
            self.press(pygame.K_ESCAPE)                 # pause -> options -> change things -> back
            self.assertEqual(self.state(), PAUSED)
            self.press(pygame.K_DOWN)
            self.press(pygame.K_RETURN)
            self.assertEqual(self.state(), OPTIONS)
            for key in (pygame.K_RIGHT, pygame.K_DOWN, pygame.K_DOWN, pygame.K_DOWN, pygame.K_LEFT):
                self.press(key)
            self.press(pygame.K_ESCAPE)
            self.assertEqual((self.state(), self.app.screens.menu_index), (PAUSED, 1))
            self.press(pygame.K_ESCAPE)
            self.play_until_over()
            self.leave_results()

            self.start("SPRINT")
            self.app.game.lines = T.SPRINT_LINES        # next lock finishes the run
            self.press(pygame.K_SPACE)
            self.assertEqual(self.app.game.outcome, "finish")
            self.leave_results()

            self.start("ULTRA")
            self.app.game.elapsed_ms = T.ULTRA_MS - 100
            self.frames(20)
            self.assertEqual(self.app.game.outcome, "finish")
            self.leave_results()

            self.start("SCORES")
            self.assertEqual(self.state(), SCORES)
            for key in (pygame.K_RIGHT, pygame.K_RIGHT, pygame.K_LEFT, pygame.K_ESCAPE):
                self.press(key)
            self.assertEqual(self.state(), TITLE)
            self.assertEqual(TITLE_ITEMS[self.app.screens.menu_index], "SCORES")   # cursor remembered

        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, storage.SCORES_FILE)))
        self.assertTrue(os.path.exists(os.path.join(self._tmp.name, storage.SETTINGS_FILE)))

    def test_end_game_from_the_pause_menu_shows_results(self):
        self.start("MARATHON")
        self.frames(10)
        self.press(pygame.K_ESCAPE)
        self.press(pygame.K_UP)                         # wraps round to END GAME
        self.press(pygame.K_RETURN)
        self.assertEqual((self.state(), self.app.game.outcome), (GAME_OVER, "ended"))

    def test_f11_toggles_fullscreen_and_back(self):
        windowed = self.app.surface.get_size()
        self.press(pygame.K_F11)
        self.assertTrue(pygame.display.get_surface().get_flags() & pygame.FULLSCREEN)
        self.assertEqual(self.app.surface.get_size(), pygame.display.get_surface().get_size())
        self.press(pygame.K_F11)
        self.assertFalse(pygame.display.get_surface().get_flags() & pygame.FULLSCREEN)
        self.assertEqual(self.app.surface.get_size(), windowed)

    def test_focus_loss_pauses(self):
        self.start("ULTRA")
        pygame.event.post(pygame.event.Event(pygame.WINDOWFOCUSLOST))
        self.frames(1)
        self.assertEqual(self.state(), PAUSED)

    def test_a_long_frame_does_not_lock_the_piece(self):
        self.start("MARATHON")
        game = self.app.game
        while game.move_down():                         # resting on the floor, lock timer about to run
            pass
        self.app.step(min(3000, T.MAX_FRAME_MS))       # what run() hands step() after a 3 s stall
        self.assertEqual(game.pieces, 0)                # still sliding: a 50 ms frame is under the lock delay


if __name__ == "__main__":
    unittest.main()
