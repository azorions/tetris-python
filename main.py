"""Entry point: window, reflow-to-window layout, frame loop, juice wiring.

Run with:  python main.py
"""
import pygame

from tetris import theme as T
from tetris.game import Game
from tetris.juice import FloatingText, ParticleField, Shake
from tetris.render import Renderer
from tetris.screens import (GAME_OVER, OPTIONS, PAUSED, PAUSE_ITEMS, PLAYING, SCORES,
                            TITLE, TITLE_ITEMS, ScreenManager, Settings)

DAS_KEYS = {pygame.K_LEFT: -1, pygame.K_a: -1, pygame.K_RIGHT: 1, pygame.K_d: 1}
SOFT_DROP_KEYS = (pygame.K_DOWN, pygame.K_s)


class App:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("TETRIS")
        self.window = pygame.display.set_mode((T.SURFACE_W, T.SURFACE_H), pygame.RESIZABLE)
        self.surface = None
        self.renderer = None
        self.clock = pygame.time.Clock()
        self.settings = Settings()
        self.screens = ScreenManager(self)
        self.shake = Shake()
        self.particles = ParticleField()
        self.floating = None
        self.levelup_t = None
        self.levelup_n = 0
        self.combo = 0
        self.high_scores = [("KRZ", 208150), ("MJP", 176020), ("DDD", 121600)]
        self.game = None
        self.running = True
        self._held = []                 # DAS keys currently down, most recent last
        self._das = {"dir": 0, "t": 0.0, "fired": False}
        self._soft = None               # soft-drop repeat timer; None when DOWN isn't held
        self.fit_to_window()

    # ------------------------------------------------------------- flow ----
    def new_game(self):
        self.game = Game(level=self.settings.start_level,
                         high_scores=self.high_scores,
                         show_ghost=self.settings.ghost)
        self.particles.items.clear()
        self.floating = None
        self.levelup_t, self.levelup_n = None, 0
        self.combo = 0
        self.shake = Shake()
        self._das = {"dir": 0, "t": 0.0, "fired": False}
        self._soft = None

    def apply_settings(self):
        if self.game:
            self.game.show_ghost = self.settings.ghost

    def commit_high_score(self, name):
        self.high_scores.append((name, self.game.score))
        self.high_scores.sort(key=lambda r: -r[1])
        del self.high_scores[5:]

    def fit_to_window(self):
        """Rebuild the frame surface and layout whenever the window size changes."""
        self.window = pygame.display.get_surface()
        size = self.window.get_size()
        if min(size) <= 0 or (self.surface is not None and self.surface.get_size() == size):
            return
        self.surface = pygame.Surface(size)
        self.renderer = Renderer(root_dir=".", size=size)
        self.particles.items.clear()                # their positions belong to the old layout
        self.particles.scale = self.renderer.layout.scale

    # ------------------------------------------------------------ input ----
    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.VIDEORESIZE:
                pass                        # draw() reflows the layout when the size changes
            elif event.type == pygame.KEYDOWN:
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
        for event in self.game.events:
            name = event[0]
            if name == "lock":
                self.shake.kick(T.SHAKE_LOCK, self.settings.shake)
            elif name == "harddrop":
                rows = min(3, event[1])
                if rows:
                    self.shake.kick(T.SHAKE_HARDDROP, self.settings.shake * rows / 3)
            elif name == "clear":
                if self.settings.particles:
                    self.particles.burst_row(self.renderer.layout, event[1], event[2])
            elif name == "cleared":
                lines, points = event[1], event[2]
                if not lines:                   # a lock that cleared nothing breaks the combo
                    self.combo = 0
                    continue
                self.combo += 1
                if lines == 4:
                    self.shake.kick(T.SHAKE_TETRIS, self.settings.shake, random_dir=True)
                label = T.clear_name(lines)
                if self.combo > 1:
                    label += f" x{self.combo}"
                self.floating = FloatingText(label, f"+{points}", T.HILITE)
            elif name == "levelup":
                self.levelup_t, self.levelup_n = 0.0, event[1]
            elif name == "over":
                self.screens.go(GAME_OVER)
                if self.game.score > (self.high_scores[-1][1] if len(self.high_scores) >= 5 else 0):
                    self.screens.begin_name_entry()
        self.game.events.clear()

    # ------------------------------------------------------------- draw ----
    def draw(self):
        self.fit_to_window()
        s = self.surface
        s.fill(T.WINDOW_BG)
        state = self.screens.state

        if state in (PLAYING, PAUSED, GAME_OVER) or (state == OPTIONS and self.screens.return_to == PAUSED):
            s.fill(T.PANEL_BG)
            self.renderer.board(s, self.game)
            self.renderer.panels(s, self.game)
            self.particles.draw(s)
            if self.floating:
                self.renderer.combo(s, self.floating)
            if self.levelup_t is not None:
                self.renderer.level_up(s, self.levelup_n, self.levelup_t)

        if state == TITLE:
            self.renderer.menu(s, "TETRIS", TITLE_ITEMS, self.screens.menu_index,
                               sub="UP / DOWN SELECT . ENTER CONFIRM")
        elif state == SCORES:
            self.renderer.scores(s, self.high_scores)
        elif state == PAUSED:
            self.renderer.scrim(s)
            self.renderer.menu(s, "PAUSED", PAUSE_ITEMS, self.screens.menu_index)
        elif state == OPTIONS:
            self.renderer.scrim(s)
            self.renderer.options(s, self.settings.rows(), self.screens.option_index)
        elif state == GAME_OVER:
            self.renderer.scrim(s, 225)
            self.renderer.game_over(s, self.game, self.screens.name_entry,
                                    self.screens.name_cursor)

        self.renderer.crt(s, self.settings.scanlines)
        self.present()

    def present(self):
        """The surface is window-sized, so it is blitted 1:1; shake nudges the whole frame."""
        dx, dy = self.shake.offset() if self.screens.state == PLAYING else (0, 0)
        k = self.renderer.layout.scale
        self.window.fill((0, 0, 0))
        self.window.blit(self.surface, (round(dx * k), round(dy * k)))
        pygame.display.flip()

    # ------------------------------------------------------------- loop ----
    def run(self):
        while self.running:
            dt = self.clock.tick(T.FPS)
            self.handle_events()
            self.update_das(dt)
            if self.screens.state == PLAYING and self.game:
                self.game.update(dt)
            if self.game:
                # drained in every state: a top-out and ESC in the same frame must still end the game
                self.drain_events()
            self.shake.update(dt)
            if self.screens.state not in (PAUSED, OPTIONS):     # juice freezes behind the pause menu
                self.particles.update(dt)
                if self.floating:
                    self.floating.update(dt)
                    if self.floating.done:
                        self.floating = None
                if self.levelup_t is not None:
                    self.levelup_t += dt
                    if self.levelup_t > T.LEVELUP_IN_MS + T.LEVELUP_HOLD_MS + T.LEVELUP_OUT_MS:
                        self.levelup_t = None
            self.draw()
        pygame.quit()


if __name__ == "__main__":
    App().run()
