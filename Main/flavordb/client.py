"""
FlavorDB2 HTTP client.
Rate limit: 1 req/sec (academic server, no documented limit).
"""
import json
import time
import urllib.request
import urllib.error

_BASE = "https://cosylab.iiitd.edu.in/flavordb2/entities_json"
_RATE = 1.1  # seconds between requests


def fetch_entity(entity_id: int, cache: dict) -> dict | None:
    """
    Fetch entity from FlavorDB2. Writes to cache[entity_id] on success.
    Returns None on 404 or any error (caller should skip, not crash).
    """
    if entity_id in cache:
        return cache[entity_id]

    url = f"{_BASE}?id={entity_id}"
    try:
        with urllib.request.urlopen(url, timeout=12) as resp:
            data = json.loads(resp.read())
        cache[entity_id] = data
        return data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            cache[entity_id] = None  # mark 404 so we don't retry
        return None
    except Exception:
        return None
    finally:
        time.sleep(_RATE)
