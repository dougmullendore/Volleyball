"""Thin, retrying client for the NCAA's public scoreboard and game feeds."""
from __future__ import annotations

import json
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from . import config


class FetchError(RuntimeError):
    pass


def get_bytes(url: str, retries: int | None = None, timeout: int = 60) -> bytes:
    """Download one URL, retrying on transient errors."""
    retries = config.FETCH_RETRIES if retries is None else retries
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 403, 404):
                raise FetchError(f"{e.code} {url[:120]}") from e
        except Exception as e:  # network errors, timeouts
            last = e
        time.sleep(min(60, 1.5 * 2 ** attempt) + random.random())
    raise FetchError(f"gave up on {url[:120]}: {last!r}")


def get_json(url: str):
    last = None
    for _ in range(2):  # a truncated body is worth one more try
        try:
            out = json.loads(get_bytes(url))
            if isinstance(out, dict) and out.get("errors") and not out.get("data"):
                raise FetchError(f"feed error: {str(out['errors'])[:200]}")
            return out
        except FetchError:
            raise
        except ValueError as e:
            last = e
    raise FetchError(f"bad JSON from {url[:120]}: {last!r}")


def get_many(urls: dict, threads: int | None = None):
    """Download many URLs at once. Yields (key, json_or_None, error_or_None)."""
    def one(item):
        key, url = item
        try:
            return key, get_json(url), None
        except Exception as e:
            return key, None, e

    with ThreadPoolExecutor(max_workers=threads or config.FETCH_THREADS) as pool:
        yield from pool.map(one, list(urls.items()))


def _url(kind: str, variables: dict) -> str:
    ext = json.dumps({"persistedQuery": {"version": 1, "sha256Hash": config.QUERY[kind]}}, separators=(",", ":"))
    return (config.API + "?extensions=" + urllib.parse.quote(ext)
            + "&variables=" + urllib.parse.quote(json.dumps(variables, separators=(",", ":"))))


def scoreboard_url(season: int, date: str) -> str:
    """Every match on one day. `date` is YYYY-MM-DD."""
    return _url("scoreboard", {"sportCode": config.SPORT_CODE, "division": config.DIVISION,
                               "seasonYear": season, "contestDate": date.replace("-", "/")})


def game_url(game_id: int) -> str:
    return _url("game", {"id": str(game_id), "week": None, "staticTestEnv": None})


def box_url(game_id: int) -> str:
    return _url("box", {"contestId": str(game_id), "staticTestEnv": None})


def pbp_url(game_id: int) -> str:
    return _url("pbp", {"contestId": str(game_id), "staticTestEnv": None})
