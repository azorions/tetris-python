"""Screen state machine, input routing and the options model.

Only PLAYING advances the game clock. Input is dispatched by state; never
poll keys globally.
"""
import pygame

from .game import MODES

TITLE, PLAYING, PAUSED, OPTIONS, GAME_OVER, SCORES = (
    "TITLE", "PLAYING", "PAUSED", "OPTIONS", "GAME_OVER", "SCORES")

MODE_ITEMS = {MODES[m].label: m for m in MODES}          # MARATHON / SPRINT / ULTRA
TITLE_ITEMS = [*MODE_ITEMS, "OPTIONS", "SCORES", "QUIT"]
PAUSE_ITEMS = ["RESUME", "OPTIONS", "END GAME"]
SCORE_MODES = list(MODES)                               # tables on the SCORES screen, in order

UP = (pygame.K_UP, pygame.K_w)
DOWN = (pygame.K_DOWN, pygame.K_s)
LEFT = (pygame.K_LEFT, pygame.K_a)
RIGHT = (pygame.K_RIGHT, pygame.K_d)
ENTER = (pygame.K_RETURN, pygame.K_KP_ENTER)
CONFIRM = ENTER + (pygame.K_SPACE,)

# (label, Settings attribute, [(shown value, stored value)]). The first choice is the default.
OPTION_DEFS = [
    ("GHOST PIECE", "ghost", [("ON", True), ("OFF", False)]),
    ("SCREEN SHAKE", "shake", [("FULL", 1.0), ("HALF", 0.5), ("OFF", 0.0)]),
    ("PARTICLES", "particles", [("ON", True), ("OFF", False)]),
    ("SCANLINES", "scanlines", [("26%", 66), ("12%", 31), ("OFF", 0)]),
    ("START LEVEL", "start_level", [(f"{n:02d}", n) for n in range(1, 16)]),
    ("SOUND FX", "sfx", [("100%", 1.0), ("50%", 0.5), ("OFF", 0.0)]),
    ("MUSIC", "music", [("100%", 1.0), ("50%", 0.5), ("OFF", 0.0)]),
]


class Settings:
    """Option values. main.py saves them to ~/.tetris/settings.json."""

    def __init__(self):
        for _, key, choices in OPTION_DEFS:
            setattr(self, key, choices[0][1])

    def rows(self):
        return [(label, choices[self._index(key, choices)][0]) for label, key, choices in OPTION_DEFS]

    def cycle(self, row: int, step: int):
        _, key, choices = OPTION_DEFS[row]
        setattr(self, key, choices[(self._index(key, choices) + step) % len(choices)][1])

    def to_dict(self):
        return {key: getattr(self, key) for _, key, _ in OPTION_DEFS}

    def load(self, data):
        """Take saved values, ignoring unknown keys and anything that isn't one of the choices."""
        if not isinstance(data, dict):
            return
        for _, key, choices in OPTION_DEFS:
            i = _find(choices, data.get(key))
            if i is not None:
                setattr(self, key, choices[i][1])

    def _index(self, key, choices):
        i = _find(choices, getattr(self, key))
        return 0 if i is None else i


def _find(choices, value):
    """Index of value among an option's choices. Type-strict, so a saved 1 never passes for True."""
    for i, (_, v) in enumerate(choices):
        if type(v) is type(value) and v == value:
            return i
    return None


class ScreenManager:
    def __init__(self, app):
        self.app = app
        self.state = TITLE
        self.menu_index = 0
        self.option_index = 0
        self.score_mode = 0             # which table the SCORES screen shows
        self.return_to = TITLE          # where ESC from OPTIONS goes back to
        self.name_entry = None
        self.name_cursor = 0
        self._cursor = {}               # menu position per screen, restored when coming back to it

    def go(self, state):
        self._cursor[self.state] = self.menu_index
        back = state == TITLE or (state == PAUSED and self.state == OPTIONS)
        self.state = state
        self.menu_index = self._cursor.get(state, 0) if back else 0

    # -------------------------------------------------------- key events ----
    def key(self, event):
        fn = getattr(self, f"_key_{self.state.lower()}", None)
        if fn:
            fn(event)

    def _menu_move(self, event, items):
        if event.key in UP + DOWN:
            step = -1 if event.key in UP else 1
            self.menu_index = (self.menu_index + step) % len(items)
            self.app.sfx("menu_move")

    def _key_title(self, event):
        self._menu_move(event, TITLE_ITEMS)
        if event.key not in CONFIRM:
            return
        choice = TITLE_ITEMS[self.menu_index]
        self.app.sfx("menu_select")
        if choice in MODE_ITEMS:
            self.app.new_game(MODE_ITEMS[choice])
            self.go(PLAYING)
        elif choice == "OPTIONS":
            self.return_to = TITLE
            self.go(OPTIONS)
        elif choice == "SCORES":
            self.go(SCORES)
        elif choice == "QUIT":
            self.app.running = False

    def _key_scores(self, event):
        if event.key in LEFT + RIGHT:
            step = -1 if event.key in LEFT else 1
            self.score_mode = (self.score_mode + step) % len(SCORE_MODES)
            self.app.sfx("menu_move")
        elif event.key in CONFIRM + (pygame.K_ESCAPE,):
            self.app.sfx("menu_select")
            self.go(TITLE)

    def _key_playing(self, event):
        g, k = self.app.game, event.key
        if k == pygame.K_ESCAPE:
            self.go(PAUSED)
            self.app.sfx("pause")
        elif k in LEFT:
            g.move(-1)
        elif k in RIGHT:
            g.move(1)
        elif k in DOWN:
            g.soft_drop()
        elif k == pygame.K_SPACE:
            g.hard_drop()
        elif k in (pygame.K_z, pygame.K_LCTRL, pygame.K_RCTRL):
            g.rotate(-1)
        elif k in (pygame.K_x, pygame.K_UP, pygame.K_w):
            g.rotate(1)
        elif k in (pygame.K_c, pygame.K_LSHIFT, pygame.K_RSHIFT):
            g.swap_hold()

    def _key_paused(self, event):
        self._menu_move(event, PAUSE_ITEMS)
        if event.key == pygame.K_ESCAPE:
            self.go(PLAYING)
        elif event.key in ENTER:
            choice = PAUSE_ITEMS[self.menu_index]
            self.app.sfx("menu_select")
            if choice == "RESUME":
                self.go(PLAYING)
            elif choice == "OPTIONS":
                self.return_to = PAUSED
                self.go(OPTIONS)
            else:
                self.app.game.abandon()         # its ("over",) event opens the results this frame

    def _key_options(self, event):
        s = self.app.settings
        if event.key == pygame.K_ESCAPE:
            self.app.save_settings()
            self.app.sfx("menu_select")
            self.go(self.return_to)
        elif event.key in UP + DOWN:
            step = -1 if event.key in UP else 1
            self.option_index = (self.option_index + step) % len(OPTION_DEFS)
            self.app.sfx("menu_move")
        elif event.key in LEFT + RIGHT:
            s.cycle(self.option_index, -1 if event.key in LEFT else 1)
            self.app.apply_settings()
            self.app.sfx("menu_move")

    def _key_game_over(self, event):
        if not self.app.results_ready():
            return                              # the sweep and fade are still playing
        if self.name_entry is not None:
            self._edit_name(event)
            return
        if event.key in ENTER:
            self.app.sfx("menu_select")
            self.app.new_game(self.app.game.mode)
            self.go(PLAYING)
        elif event.key == pygame.K_ESCAPE:
            self.app.sfx("menu_select")
            self.go(TITLE)

    def _edit_name(self, event):
        chars, k = self.name_entry, event.key
        if pygame.K_a <= k <= pygame.K_z:       # type the letter straight in and move on
            chars[self.name_cursor] = chr(k - pygame.K_a + ord("A"))
            self.name_cursor = min(2, self.name_cursor + 1)
        elif k == pygame.K_BACKSPACE:
            self.name_cursor = max(0, self.name_cursor - 1)
        elif k == pygame.K_LEFT:
            self.name_cursor = (self.name_cursor - 1) % 3
        elif k == pygame.K_RIGHT:
            self.name_cursor = (self.name_cursor + 1) % 3
        elif k in (pygame.K_UP, pygame.K_DOWN):
            step = 1 if k == pygame.K_UP else -1
            c = chars[self.name_cursor]
            chars[self.name_cursor] = chr((ord(c) - 65 + step) % 26 + 65)
        elif k in ENTER:
            self.app.commit_high_score("".join(chars))
            self.name_entry = None
            self.app.sfx("menu_select")
            return
        else:
            return
        self.app.sfx("menu_move")

    def begin_name_entry(self):
        self.name_entry = ["A", "A", "A"]
        self.name_cursor = 0
