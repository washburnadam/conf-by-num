"""Polite, cached, resumable downloader (PLAN.md §3.2 step 1.2).

- identifiable User-Agent, delay between requests, retries with backoff, robots.txt respected
- every response cached gzipped under data/cache/html/<sha1>.html.gz (never re-fetched unless refresh=True)
- every request logged to data/fetch_log.csv
- decodes as UTF-8 (legacy lesson: latin-1 caused mojibake)
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import time
import urllib.robotparser
from datetime import datetime, timezone
from pathlib import Path

import requests

USER_AGENT = "ConferenceByTheNumbers/0.1 (personal research; contact: washburnadam@gmail.com)"


class Fetcher:
    def __init__(self, cache_dir: str | Path, log_path: str | Path, delay: float = 1.5,
                 retries: int = 4, base_url: str = "https://www.churchofjesuschrist.org"):
        self.cache = Path(cache_dir)
        self.cache.mkdir(parents=True, exist_ok=True)
        self.log_path = Path(log_path)
        self.delay, self.retries = delay, retries
        self.s = requests.Session()
        self.s.headers["User-Agent"] = USER_AGENT
        self._last = 0.0
        self.robots = urllib.robotparser.RobotFileParser(base_url.rstrip("/") + "/robots.txt")
        try:
            self.robots.read()
        except Exception:  # noqa: BLE001 — if robots can't be read we stay conservative
            self.robots = None

    def cache_path(self, url: str) -> Path:
        return self.cache / (hashlib.sha1(url.encode("utf-8")).hexdigest() + ".html.gz")

    def _log(self, url: str, status, nbytes: int, cached: bool, note: str = "") -> None:
        new = not self.log_path.exists()
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time_utc", "url", "status", "bytes", "cached", "note"])
            w.writerow([datetime.now(timezone.utc).isoformat(timespec="seconds"), url, status, nbytes, cached, note])

    def get(self, url: str, refresh: bool = False) -> str | None:
        cp = self.cache_path(url)
        if cp.exists() and not refresh:
            text = gzip.decompress(cp.read_bytes()).decode("utf-8")
            self._log(url, "cache", len(text), True)
            return text
        if self.robots is not None and not self.robots.can_fetch(USER_AGENT, url):
            self._log(url, "robots-disallowed", 0, False)
            return None
        for attempt in range(self.retries):
            wait = self.delay - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            try:
                r = self.s.get(url, timeout=30)
            except requests.RequestException as e:
                self._log(url, "error", 0, False, str(e)[:200])
                time.sleep(2 ** attempt * self.delay)
                continue
            if r.status_code == 200:
                text = r.content.decode("utf-8", errors="replace")
                cp.write_bytes(gzip.compress(text.encode("utf-8")))
                self._log(url, 200, len(r.content), False)
                return text
            self._log(url, r.status_code, len(r.content), False)
            if r.status_code in (404, 410):
                return None
            time.sleep(2 ** attempt * self.delay)
        return None
