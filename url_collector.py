"""
Phase 1 — URL Collection.

Crawls each Food52 category page, paginates until empty, collects recipe URLs,
deduplicates by URL while merging meal_type and dietary tags.

Output: output/recipe_urls.json
  [{"url": "https://food52.com/recipes/NNNNN-slug", "meal_type": "dinner", "dietary": ["vegan"]}, ...]
"""

import json
import logging
import re
from pathlib import Path

import requests

from _http import fetch, polite_sleep

# slug → tag dict (meal_type xor dietary key present, never both)
CATEGORY_MAP: dict[str, dict] = {
    "/recipes/dinner":     {"meal_type": "dinner"},
    "/recipes/breakfast":  {"meal_type": "breakfast"},
    "/recipes/lunch":      {"meal_type": "lunch"},
    "/recipes/snacks":     {"meal_type": "snack"},
    "/recipes/desserts":   {"meal_type": "dessert"},
    "/recipes/drinks":     {"meal_type": "drink"},
    "/recipes/vegan":      {"dietary": "vegan"},
    "/recipes/vegetarian": {"dietary": "vegetarian"},
}

BASE_URL = "https://food52.com"
OUTPUT_PATH = Path("output/recipe_urls.json")

# 4+ digit ID required — avoids matching category slugs like /recipes/5-ingredients-or-fewer
RECIPE_PATH_RE = re.compile(r"^/recipes/\d{4,}-")

log = logging.getLogger(__name__)


def _extract_recipe_paths(soup) -> list[str]:
    """
    Pull recipe paths from a listing page.

    GUESSED SELECTOR: `a[href]` filtered by RECIPE_PATH_RE.
    Food52 category pages render <a href="/recipes/NNNNN-slug"> cards.
    This regex filter is the stable contract — class names may be hashed.
    """
    seen: set[str] = set()
    results: list[str] = []
    for a in soup.find_all("a", href=RECIPE_PATH_RE):
        path = a["href"].split("?")[0]
        if path not in seen:
            seen.add(path)
            results.append(path)
    return results


def _crawl_category(session: requests.Session, slug: str, max_pages: int = 500) -> list[str]:
    """Paginate through one category; stop when a page returns no recipe links."""
    all_paths: list[str] = []
    for page in range(1, max_pages + 1):
        url = f"{BASE_URL}{slug}?page={page}"
        log.info("Fetching %s", url)
        soup = fetch(session, url, log)
        if soup is None:
            break
        paths = _extract_recipe_paths(soup)
        if not paths:
            log.info("No recipes on page %d of %s — done", page, slug)
            break
        all_paths.extend(paths)
        polite_sleep()
    return all_paths


def collect_urls(max_pages: int = 500) -> list[dict]:
    """
    Phase 1 entry point.
    max_pages: cap per-category page count (lower for test runs).
    Returns and writes list of {url, meal_type, dietary} records.
    """
    # url → {meal_type: str|None, dietary: set[str]}
    catalog: dict[str, dict] = {}

    with requests.Session() as session:
        for slug, tags in CATEGORY_MAP.items():
            paths = _crawl_category(session, slug, max_pages=max_pages)
            log.info("%d recipe paths in %s", len(paths), slug)
            for path in paths:
                url = f"{BASE_URL}{path}"
                entry = catalog.setdefault(url, {"url": url, "meal_type": None, "dietary": set()})
                if "meal_type" in tags:
                    entry["meal_type"] = tags["meal_type"]
                if "dietary" in tags:
                    entry["dietary"].add(tags["dietary"])

    records = [
        {"url": e["url"], "meal_type": e["meal_type"], "dietary": sorted(e["dietary"])}
        for e in catalog.values()
    ]

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(records, indent=2))
    log.info("Wrote %d URLs → %s", len(records), OUTPUT_PATH)
    return records


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    collect_urls()
