"""Shared HTTP helpers — user-agent rotation and polite delay."""

import random
import time

import requests
from bs4 import BeautifulSoup

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:126.0) Gecko/20100101 Firefox/126.0",
]


def polite_sleep():
    time.sleep(random.uniform(1.0, 2.0))


def fetch(session: requests.Session, url: str, log) -> BeautifulSoup | None:
    """GET url; return BeautifulSoup or None on non-200 / error."""
    try:
        resp = session.get(url, headers={"User-Agent": random.choice(USER_AGENTS), "Accept-Language": "en-US,en;q=0.9"}, timeout=20)
        if resp.status_code != 200:
            log.warning("HTTP %s → %s", resp.status_code, url)
            return None
        return BeautifulSoup(resp.text, "html.parser")
    except Exception as exc:
        log.error("Fetch error %s: %s", url, exc)
        return None
