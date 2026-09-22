"""Save files: settings and high scores as JSON under ~/.tetris/ (TETRIS_HOME overrides it).

Loading never raises: a missing or corrupt file gives the defaults and bad
entries are dropped. Saving writes a temp file and renames it over the old
one, so a crash mid-write can't leave half a file behind.
"""
import json
import os
import sys
import tempfile
from pathlib import Path

from .game import MODES

TABLE_SIZE = 5
SCORES_FILE = "scores.json"
SETTINGS_FILE = "settings.json"


def data_dir() -> Path:
    return Path(os.environ.get("TETRIS_HOME") or Path.home() / ".tetris")


def load_json(name, default):
    try:
        with open(data_dir() / name, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(name, data) -> bool:
    folder = data_dir()
    try:
        folder.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, prefix=name + ".", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            os.replace(tmp, folder / name)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    except OSError as e:
        print(f"tetris: could not save {folder / name}: {e}", file=sys.stderr)
        return False
    return True


def load_settings() -> dict:
    data = load_json(SETTINGS_FILE, {})
    return data if isinstance(data, dict) else {}


def save_settings(values: dict) -> bool:
    return save_json(SETTINGS_FILE, values)


class HighScores:
    """Top-five (name, value) tables, one per mode. Values are points, or ms for Sprint."""

    def __init__(self, data=None):
        self.tables = {mode: [] for mode in MODES}
        if isinstance(data, dict):
            for mode, rows in data.items():
                if mode in self.tables and isinstance(rows, list):
                    for row in rows:
                        entry = _entry(row)
                        if entry:
                            self.add(mode, *entry)

    @classmethod
    def load(cls):
        return cls(load_json(SCORES_FILE, {}))

    def save(self) -> bool:
        return save_json(SCORES_FILE, {mode: [[name, value] for name, value in rows]
                                       for mode, rows in self.tables.items()})

    def table(self, mode):
        """The live list for a mode; add() updates it in place, so a game can hold on to it."""
        return self.tables[mode]

    def qualifies(self, mode, value) -> bool:
        if value is None:
            return False
        rows = self.tables[mode]
        if len(rows) < TABLE_SIZE:
            return True
        worst = rows[-1][1]
        return value < worst if MODES[mode].lower_is_better else value > worst

    def add(self, mode, name, value):
        rows = self.tables[mode]
        rows.append((name, value))
        # sort() is stable, so on a tie the older entry keeps the higher place
        rows.sort(key=lambda row: row[1] if MODES[mode].lower_is_better else -row[1])
        del rows[TABLE_SIZE:]


def _entry(row):
    """A saved [name, value] pair as (NAME, value), or None if it's malformed."""
    if not isinstance(row, (list, tuple)) or len(row) != 2:
        return None
    name, value = row
    if not (isinstance(name, str) and 1 <= len(name) <= 3 and name.isascii() and name.isalpha()):
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return name.upper(), value
