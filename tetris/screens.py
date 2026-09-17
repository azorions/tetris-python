"""Screen state machine and input routing.

Only PLAYING advances the gravity clock. Input is dispatched by state; never
poll keys globally.
"""
import pygame

from . import theme as T

TITLE, PLAYING, PAUSED, OPTIONS, GAME_OVER, SCORES = (
    "TITLE", "PLAYING", "PAUSED", "OPTIONS", "GAME_OVER", "SCORES")

TITLE_ITEMS = ["PLAY", "OPTIONS", "SCORES", "QUIT"]
PAUSE_ITEMS = ["RESUME", "OPTIONS", "END GAME"]

OPTION_DEFS = [
    ("GHOST PIECE", "ghost", [("ON", True), ("OFF", False)]),
    ("SCREEN SHAKE", "shake", [("FULL", 1.0), ("HALF", 0.5), ("OFF", 0.0)]),
    ("PARTICLES", "particles", [("ON", True), ("OFF", False)]),
    ("SCANLINES", "scanlines", [("26%", 66), ("12%", 31), ("OFF", 0)]),
    ("START LEVEL", "start_level", [(f"{n:02d}", n) for n in range(1, 16)]),
]


class Settings:
    """Persist to ~/.tetris/settings.json if you want it to stick."""

    def __init__(self):
        self.ghost = True
        self.shake = 1.0
        self.particles = True
        self.scanlines = 66
        self.start_level = 1
        self._idx = {key: 0 for _, key, _ in OPTION_DEFS}

    def rows(self):
        return [(label, choices[self._idx[key]][0]) for label, key, choices in OPTION_DEFS]

    def cycle(self, row: int, step: int):
        label, key, choices = OPTION_DEFS[row]
        self._idx[key] = (self._idx[key] + step) % len(choices)
        setattr(self, key, choices[self._idx[key]][1])


class ScreenManager:
    def __init__(self, app):
        self.app = app
        self.state = TITLE
        self.menu_index = 0
        self.option_index = 0
        self.return_to = TITLE          # where ESC from OPTIONS goes back to
        self.name_entry = None
        self.name_cursor = 0

    def go(self, state):
        self.state = state
        self.menu_index = 0

    # -------------------------------------------------------- key events ----
    def key(self, event):
        fn = getattr(self, f"_key_{self.state.lower()}", None)
        if fn:
            fn(event)

    def _menu_move(self, event, items):
        if event.key in (pygame.K_UP, pygame.K_w):
            self.menu_index = (self.menu_index - 1) % len(items)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.menu_index = (self.menu_index + 1) % len(items)

    def _key_title(self, event):
        self._menu_move(event, TITLE_ITEMS)
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            choice = TITLE_ITEMS[self.menu_index]
            if choice == "PLAY":
                self.app.new_game()
                self.go(PLAYING)
            elif choice == "OPTIONS":
                self.return_to = TITLE
                self.go(OPTIONS)
            elif choice == "SCORES":
                self.go(SCORES)
            elif choice == "QUIT":
                self.app.running = False

    def _key_scores(self, event):
        if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
            self.go(TITLE)

    def _key_playing(self, event):
        g = self.app.game
        if event.key == pygame.K_ESCAPE:
            self.go(PAUSED)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            g.move(-1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            g.move(1)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            g.soft_drop()
        elif event.key == pygame.K_SPACE:
            g.hard_drop()
        elif event.key == pygame.K_z:
            g.rotate(-1)
        elif event.key in (pygame.K_x, pygame.K_UP, pygame.K_w):
            g.rotate(1)
        elif event.key == pygame.K_c:
            g.swap_hold()

    def _key_paused(self, event):
        self._menu_move(event, PAUSE_ITEMS)
        if event.key == pygame.K_ESCAPE:
            self.go(PLAYING)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            choice = PAUSE_ITEMS[self.menu_index]
            if choice == "RESUME":
                self.go(PLAYING)
            elif choice == "OPTIONS":
                self.return_to = PAUSED
                self.go(OPTIONS)
            else:
                self.go(TITLE)

    def _key_options(self, event):
        s = self.app.settings
        rows = OPTION_DEFS
        if event.key == pygame.K_ESCAPE:
            self.go(self.return_to)
        elif event.key in (pygame.K_UP, pygame.K_w):
            self.option_index = (self.option_index - 1) % len(rows)
        elif event.key in (pygame.K_DOWN, pygame.K_s):
            self.option_index = (self.option_index + 1) % len(rows)
        elif event.key in (pygame.K_LEFT, pygame.K_a):
            s.cycle(self.option_index, -1)
        elif event.key in (pygame.K_RIGHT, pygame.K_d):
            s.cycle(self.option_index, 1)
        self.app.apply_settings()

    def _key_game_over(self, event):
        if self.name_entry is not None:
            self._edit_name(event)
            return
        if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.app.new_game()
            self.go(PLAYING)
        elif event.key == pygame.K_ESCAPE:
            self.go(TITLE)

    def _edit_name(self, event):
        chars = self.name_entry
        if event.key in (pygame.K_LEFT,):
            self.name_cursor = (self.name_cursor - 1) % 3
        elif event.key in (pygame.K_RIGHT,):
            self.name_cursor = (self.name_cursor + 1) % 3
        elif event.key in (pygame.K_UP, pygame.K_DOWN):
            step = 1 if event.key == pygame.K_UP else -1
            c = chars[self.name_cursor]
            chars[self.name_cursor] = chr((ord(c) - 65 + step) % 26 + 65)
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.app.commit_high_score("".join(chars))
            self.name_entry = None

    def begin_name_entry(self):
        self.name_entry = ["A", "A", "A"]
        self.name_cursor = 0
