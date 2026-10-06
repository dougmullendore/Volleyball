"""Reading and writing the data folder (the repository's `data` branch).

Layout:
  games/<season>.csv.gz     one row per match, finished or still to come
  box/<season>.csv.gz       one row per player per match (official box score)
  rallies/<season>.csv.gz   one row per point, from the play-by-play
  manifest.json             bookkeeping: which days have been collected
  status.json               result of the most recent run
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .parse import BOX_COLS, GAME_COLS, RALLY_COLS

INT_COLS = {
    "games": ["game_id", "season", "start_epoch", "home_div", "away_div", "home_sets",
              "away_sets", "detail", "pbp_sets"],
    "box": ["game_id", "is_home", "row", "number", "starter", "sets", "k", "e", "ta", "ast",
            "sa", "se", "sv", "d", "ra", "re", "bs", "ba", "be", "bhe"],
    "rallies": ["game_id", "set", "n", "home_won", "hs", "vs", "p1", "p2", "p3", "serve_home"],
}
STR_COLS = {
    "games": ["date", "state", "home", "away", "home_name", "away_name", "home_conf",
              "away_conf", "set_scores", "venue", "city", "round"],
    "box": ["team", "first", "last", "pos"],
    "rallies": ["type"],
}
COLS = {"games": GAME_COLS, "box": BOX_COLS, "rallies": RALLY_COLS}


def _path(data: Path, table: str, season: int) -> Path:
    return Path(data) / table / f"{season}.csv.gz"


def frame(table: str, rows) -> pd.DataFrame:
    if rows and isinstance(rows[0], dict):
        rows = [[r.get(c) for c in COLS[table]] for r in rows]
    return _types(table, pd.DataFrame(rows, columns=COLS[table]))


def _types(table: str, df: pd.DataFrame) -> pd.DataFrame:
    for c in INT_COLS[table]:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    for c in STR_COLS[table]:
        df[c] = df[c].astype("string").fillna("")
    return df


def read(data: Path, table: str, season: int) -> pd.DataFrame:
    p = _path(data, table, season)
    if not p.exists():
        return frame(table, [])
    df = pd.read_csv(p, dtype={c: "string" for c in STR_COLS[table]}, keep_default_na=False,
                     na_values={c: [""] for c in COLS[table] if c not in STR_COLS[table]})
    for c in COLS[table]:
        if c not in df.columns:
            df[c] = pd.NA
    return _types(table, df[COLS[table]])


def write(data: Path, table: str, season: int, df: pd.DataFrame) -> None:
    p = _path(data, table, season)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp.gz")
    # mtime=0 keeps the file byte-identical when the contents are unchanged,
    # so git does not store a new copy every night.
    df.to_csv(tmp, index=False, compression={"method": "gzip", "mtime": 0, "compresslevel": 6})
    tmp.replace(p)


def read_json(path: Path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, obj, compact: bool = False) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        text = json.dumps(obj, separators=(",", ":"), allow_nan=False)
    else:
        text = json.dumps(obj, indent=1, allow_nan=False)
    path.write_text(text)
