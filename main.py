"""Entry point: window, reflow-to-window layout, frame loop, juice and sound wiring.

Run with:  python main.py
"""
import os

import pygame

from tetris import storage
from tetris import theme as T
from tetris.audio import Audio
from tetris.game import MODES, Game, record_text
from tetris.juice import FloatingText, ParticleField, PieceRain, Shake
from tetris.render import Renderer
from tetris.screens import (GAME_OVER, MODE_ITEMS, OPTIONS, PAUSED, PAUSE_ITEMS, PLAYING,
                            SCORE_MODES, SCORES, TITLE, TITLE_ITEMS, ScreenManager, Settings)

ROOT = os.path.dirname(os.path.abspath(__file__))      # assets load wherever python is started from
DAS_KEYS = {pygame.K_LEFT: -1, pygame.K_a: -1, pygame.K_RIGHT: 1, pygame.K_d: 1}
SOFT_DROP_KEYS = (pygame.K_DOWN, pygame.K_s)
TITLE_HINT = "UP / DOWN SELECT . ENTER CONFIRM . F11 FULLSCREEN"


class App:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 1, 512, allowedchanges=0)    # the synth writes 16-bit mono
        pygame.init()
        pygame.display.set_caption("TETRIS")
        self.window = pygame.display.set_mode((T.SURFACE_W, T.SURFACE_H), pygame.RESIZABLE)
        self.surface = None
        self.renderer = None
        self.clock = pygame.time.Clock()
        self.settings = Settings()
        self.settings.load(storage.load_settings())
        self.scores = storage.HighScores.load()
        self.audio = Audio()
        self.screens = ScreenManager(self)
        self.shake = Shake()
        self.particles = ParticleField()
        self.rain = PieceRain()
        self.floating = None
        self.levelup_t = None
        self.levelup_n = 0
        self.lock_flash = None          # [cells, ms since the lock]
        self.over_t = None              # ms since the game ended: drives the sweep and the results fade
        self.game = None
        self.running = True
        self._windowed_size = None      # set while fullscreen: the size to go back to
        self._held = []                 # DAS keys currently down, most recent last
        self._das = {"dir": 0, "t": 0.0, "fired": False}
        self._soft = None               # soft-drop repeat timer; None when DOWN isn't held
        self.apply_settings()
        self.fit_to_window()

    # ------------------------------------------------------------- flow ----
    def new_game(self, mode):
        self.game = Game(mode=mode, level=self.settings.start_level,
                         high_scores=self.scores.table(mode), show_ghost=self.settings.ghost)
        self.particles.items.clear()
        self.floating = None
        self.levelup_t, self.levelup_n = None, 0
        self.lock_flash = None
        self.over_t = None
        self.shake = Shake()
        self._das = {"dir": 0, "t": 0.0, "fired": False}
        self._soft = None
        self.audio.restart_music()

    def show_results(self):
        """The game ended (top-out, finish or END GAME): results screen, name entry if it ranks."""
        self.screens.go(GAME_OVER)
        self.over_t = 0.0
        self._soft = None
        self.sfx("finish" if self.game.outcome == "finish" else "gameover")
        if self.scores.qualifies(self.game.mode, self.game.record_value()):
            self.screens.begin_name_entry()

    def results_delay(self):
        """ms from the end of the game until the results are up and take keys."""
        sweep = T.GAMEOVER_SWEEP_MS if self.game.outcome == "topout" else 0
        return sweep + T.OVERLAY_FADE_MS

    def results_ready(self):
        return self.over_t is not None and self.over_t >= self.results_delay()

    def commit_high_score(self, name):
        self.scores.add(self.game.mode, name, self.game.record_value())
        self.scores.save()

    def apply_settings(self):
        if self.game:
            self.game.show_ghost = self.settings.ghost
        self.audio.set_volumes(self.settings.sfx, self.settings.music)

    def save_settings(self):
        storage.save_settings(self.settings.to_dict())

    def sfx(self, name):
        self.audio.play(name)

    def fit_to_window(self):
        """Rebuild the frame surface and layout whenever the window size changes."""
        self.window = pygame.display.get_surface()
        size = self.window.get_size()
        if min(size) <= 0 or (self.surface is not None and self.surface.get_size() == size):
            return
        self.surface = pygame.Surface(size)
        self.renderer = Renderer(root_dir=ROOT, size=size)
        self.particles.items.clear()                # their positions belong to the old layout
        self.particles.scale = self.renderer.layout.scale

    def toggle_fullscreen(self):
        """F11: fullscreen at the desktop resolution, and back to the last window size."""
        try:
            if self._windowed_size is None:
                self._windowed_size = self.window.get_size()
                pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
            else:
                pygame.display.set_mode(self._windowed_size, pygame.RESIZABLE)
                self._windowed_size = None
        except pygame.error:
            self._windowed_size = None              # the driver refused; stay as we are

    # ------------------------------------------------------------ input ----
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type in (pygame.WINDOWFOCUSLOST, pygame.WINDOWMINIMIZED):
                if self.screens.state == PLAYING:
                    self.screens.go(PAUSED)         # nothing falls while the player is away
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_F11:
                    self.toggle_fullscreen()
                    continue
                self.screens.key(event)
                if event.key in DAS_KEYS:
                    if event.key in self._held:
                        self._held.remove(event.key)
                    self._held.append(event.key)
                    if self.screens.state == PLAYING:
                        self._das = {"dir": DAS_KEYS[event.key], "t": 0.0, "fired": False}
                elif event.key in SOFT_DROP_KEYS and self.screens.state == PLAYING:
                    self._soft = 0.0
            elif event.type == pygame.KEYUP:
                if event.key in self._held:
                    self._held.remove(event.key)
                    # hand auto-shift to the other direction if it is still held
                    new_dir = DAS_KEYS[self._held[-1]] if self._held else 0
                    if new_dir != self._das["dir"]:
                        self._das = {"dir": new_dir, "t": 0.0, "fired": False}
                elif event.key in SOFT_DROP_KEYS:
                    self._soft = None

    def update_das(self, dt):
        """Hold-to-repeat: DAS_MS before the first repeat, then ARR_MS per cell.
        Soft drop repeats every SOFT_DROP_MS while held."""
        if self.screens.state != PLAYING:
            return
        if self._soft is not None:
            self._soft += dt
            while self._soft >= T.SOFT_DROP_MS:
                self._soft -= T.SOFT_DROP_MS
                self.game.soft_drop()
        if not self._das["dir"]:
            return
        self._das["t"] += dt
        threshold = T.DAS_MS if not self._das["fired"] else T.ARR_MS
        while self._das["t"] >= threshold:
            self._das["t"] -= threshold
            self._das["fired"] = True
            threshold = T.ARR_MS
            self.game.move(self._das["dir"])

    # ------------------------------------------------------------ juice ----
    def drain_events(self):
        dropped = False
        for event in self.game.events:
            name = event[0]
            if name in ("move", "rotate", "hold"):
                self.sfx(name)
            elif name == "lock":
                self.shake.kick(T.SHAKE_LOCK, self.settings.shake)
                self.lock_flash = [event[1], 0.0]
                if not dropped:                     # a hard drop already made its own thud
                    self.sfx("lock")
            elif name == "harddrop":
                dropped = True
                self.sfx("harddrop")
                rows = min(3, event[1])
                if rows:
                    self.shake.kick(T.SHAKE_HARDDROP, self.settings.shake * rows / 3)
            elif name == "clear":
                if self.settings.particles:
                    self.particles.burst_row(self.renderer.layout, event[1], event[2])
            elif name == "cleared":
                self.callout(*event[1:])
            elif name == "levelup":
                self.levelup_t, self.levelup_n = 0.0, event[1]
                self.sfx("levelup")
            elif name in ("over", "finish"):
                self.show_results()
        self.game.events.clear()

    def callout(self, lines, points, info):
        """Floating text and sound for a lock that cleared lines or was a T-spin."""
        if not lines and not info["tspin"]:
            return
        kicker, text = T.callout(lines, info)
        sub = f"+{points:,}" + (f"  COMBO {info['combo']}" if info["combo"] else "")
        color = T.ACCENT if info["perfect"] else T.TSPIN if info["tspin"] else T.HILITE
        self.floating = FloatingText(text, sub, color, kicker)
        if lines == 4:
            self.shake.kick(T.SHAKE_TETRIS, self.settings.shake, random_dir=True)
        if info["perfect"]:
            self.sfx("perfect")
        elif info["tspin"]:
            self.sfx("tspin")
        else:
            self.sfx("tetris" if lines == 4 else f"clear{lines}")

    # ----------------------------------------------------------- update ----
    def update(self, dt):
        self.update_das(dt)
        if self.screens.state == PLAYING and self.game:
            self.game.update(dt)
        if self.game:
            # drained in every state: a top-out and ESC in the same frame must still end the game
            self.drain_events()
        state = self.screens.state
        self.shake.update(dt)
        if state not in (PAUSED, OPTIONS):          # juice freezes behind the pause menu
            self.particles.update(dt)
            if self.floating:
                self.floating.update(dt)
                if self.floating.done:
                    self.floating = None
            if self.levelup_t is not None:
                self.levelup_t += dt
                if self.levelup_t > T.LEVELUP_IN_MS + T.LEVELUP_HOLD_MS + T.LEVELUP_OUT_MS:
                    self.levelup_t = None
            if self.lock_flash:
                self.lock_flash[1] += dt
                if self.lock_flash[1] >= T.LOCK_FLASH_MS:
                    self.lock_flash = None
        if state == GAME_OVER:
            self.over_t += dt
        if self.on_title_screens():
            self.rain.update(dt, self.renderer.layout)
        self.audio.update(self.music_state())

    def on_title_screens(self):
        state = self.screens.state
        return state in (TITLE, SCORES) or (state == OPTIONS and self.screens.return_to == TITLE)

    def music_state(self):
        state = self.screens.state
        if state == PLAYING:
            return "play"
        if state == PAUSED or (state == OPTIONS and self.screens.return_to == PAUSED):
            return "pause"
        return "stop"

    # ------------------------------------------------------------- draw ----
    def draw(self):
        self.fit_to_window()
        s = self.surface
        state = self.screens.state
        r = self.renderer

        if self.on_title_screens():
            s.fill(T.WINDOW_BG)
            self.rain.draw(s)
        else:
            s.fill(T.PANEL_BG)
            topout = state == GAME_OVER and self.game.outcome == "topout"
            sweep = min(1.0, self.over_t / T.GAMEOVER_SWEEP_MS) if topout else None
            flash = (self.lock_flash[0], 1 - self.lock_flash[1] / T.LOCK_FLASH_MS) if self.lock_flash else None
            r.board(s, self.game, sweep=sweep, lock_flash=flash)
            r.panels(s, self.game)
            self.particles.draw(s)
            if self.floating:
                r.combo(s, self.floating)
            if self.levelup_t is not None:
                r.level_up(s, self.levelup_n, self.levelup_t)

        if state == TITLE:
            item = TITLE_ITEMS[self.screens.menu_index]
            sub = MODES[MODE_ITEMS[item]].blurb if item in MODE_ITEMS else TITLE_HINT
            r.menu(s, "TETRIS", TITLE_ITEMS, self.screens.menu_index, sub=sub)
        elif state == SCORES:
            mode = SCORE_MODES[self.screens.score_mode]
            rows = [(name, record_text(mode, value)) for name, value in self.scores.table(mode)]
            r.scores(s, MODES[mode].label, rows)
        elif state == PAUSED:
            r.scrim(s)
            r.menu(s, "PAUSED", PAUSE_ITEMS, self.screens.menu_index)
        elif state == OPTIONS:
            r.scrim(s)
            r.options(s, self.settings.rows(), self.screens.option_index)
        elif state == GAME_OVER:
            fade = (self.over_t - self.results_delay() + T.OVERLAY_FADE_MS) / T.OVERLAY_FADE_MS
            if fade > 0:
                r.scrim(s, int(225 * min(1.0, fade)))
            if self.results_ready():
                r.game_over(s, self.game, self.screens.name_entry, self.screens.name_cursor)

        r.crt(s, self.settings.scanlines)
        self.present()

    def present(self):
        """The surface is window-sized, so it is blitted 1:1; shake nudges the whole frame."""
        dx, dy = self.shake.offset() if self.screens.state == PLAYING else (0, 0)
        k = self.renderer.layout.scale
        self.window.fill((0, 0, 0))
        self.window.blit(self.surface, (round(dx * k), round(dy * k)))
        pygame.display.flip()

    # ------------------------------------------------------------- loop ----
    def step(self, dt):
        """One frame: input, simulation, drawing. dt is in ms."""
        self.handle_events()
        self.update(dt)
        self.draw()

    def run(self):
        while self.running:
            self.step(min(self.clock.tick(T.FPS), T.MAX_FRAME_MS))
        self.save_settings()
        pygame.quit()


if __name__ == "__main__":
    App().run()
