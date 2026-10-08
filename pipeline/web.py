"""Downloading, with retries."""
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


def get_bytes(url: str, timeout: int = 60, tries: int | None = None) -> bytes:
    last = None
    for attempt in range(tries or config.FETCH_RETRIES):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            last = e
            if e.code in (400, 403, 404):
                break
        except Exception as e:  # network errors, timeouts
            last = e
        time.sleep(min(30, 1.5 * 2 ** attempt) + random.random())
    raise FetchError(f"could not download {url[:100]}: {last!r}")


def scoreboard_url(season: int, date: str) -> str:
    """Every Division I match on one day. `date` is YYYY-MM-DD."""
    ext = json.dumps({"persistedQuery": {"version": 1, "sha256Hash": config.SCOREBOARD_QUERY}}, separators=(",", ":"))
    variables = json.dumps({"sportCode": config.SPORT_CODE, "division": config.DIVISION,
                            "seasonYear": season, "contestDate": date.replace("-", "/")}, separators=(",", ":"))
    return config.FEED + "?extensions=" + urllib.parse.quote(ext) + "&variables=" + urllib.parse.quote(variables)


def get_days(season: int, dates: list[str]):
    """Download many days at once. Yields (date, contests_or_None, error_or_None)."""
    def one(date):
        try:
            doc = json.loads(get_bytes(scoreboard_url(season, date)))
            if not isinstance(doc.get("data"), dict):
                raise FetchError(f"feed error: {str(doc.get('errors'))[:160]}")
            return date, doc["data"].get("contests") or [], None
        except Exception as e:
            return date, None, e

    with ThreadPoolExecutor(max_workers=config.FETCH_THREADS) as pool:
        yield from pool.map(one, dates)
