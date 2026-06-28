"""
BBC Good Food URL collection.

Starts from recipe index/category pages, follows BBC Good Food recipe/category/
collection links, and collects concrete recipe URLs.
"""

import json
import logging
import re
from collections import deque
from pathlib import Path
from urllib.parse import urljoin, urlparse, urlunparse

import requests

from _http import fetch, polite_sleep

BASE_URL = "https://www.bbcgoodfood.com"
OUTPUT_PATH = Path("output/bbc_recipe_urls.json")

SEED_PATHS = [
    "/recipes",
    "/recipes/category/all-recipes",
    "/recipes/category/breakfast-recipes",
    "/recipes/category/lunch-recipes",
    "/recipes/category/dinner-recipes",
    "/recipes/category/dessert-recipes",
    "/recipes/category/snack-recipes",
    "/recipes/collection/easy-dinner-recipes",
    "/recipes/collection/healthy-dinner-recipes",
    "/recipes/collection/vegetarian-dinner-recipes",
    "/recipes/collection/chicken-recipes",
    "/recipes/collection/pasta-recipes",
    "/recipes/collection/vegan-recipes",
]

RECIPE_PATH_RE = re.compile(r"^/recipes/[a-z0-9][a-z0-9-]*$")
INDEX_PATH_RE = re.compile(r"^/recipes(?:/(?:category|collection)/[a-z0-9-]+)?$")
PAGED_INDEX_RE = re.compile(r"^/recipes(?:/(?:category|collection)/[a-z0-9-]+)?/(?:\d+)$")
NON_RECIPE_SLUGS = {"category", "collection", "collections", "search", "recipes"}

log = logging.getLogger(__name__)


def _clean_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", "", ""))


def _is_recipe_url(url: str) -> bool:
    parsed = urlparse(url)
    path = parsed.path.rstrip("/") or "/"
    return (
        parsed.netloc == "www.bbcgoodfood.com"
        and path.rsplit("/", 1)[-1] not in NON_RECIPE_SLUGS
        and bool(RECIPE_PATH_RE.match(path))
    )


def _is_index_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.netloc != "www.bbcgoodfood.com":
        return False
    path = parsed.path.rstrip("/") or "/"
    return bool(INDEX_PATH_RE.match(path) or PAGED_INDEX_RE.match(path))


def _links_from_page(soup, current_url: str) -> tuple[list[str], list[str]]:
    recipe_urls: list[str] = []
    index_urls: list[str] = []
    seen_recipes: set[str] = set()
    seen_indexes: set[str] = set()

    for a in soup.find_all("a", href=True):
        url = _clean_url(urljoin(current_url, a["href"]))
        if _is_recipe_url(url) and url not in seen_recipes:
            seen_recipes.add(url)
            recipe_urls.append(url)
        elif _is_index_url(url) and url not in seen_indexes:
            seen_indexes.add(url)
            index_urls.append(url)

    return recipe_urls, index_urls


def collect_bbc_urls(max_urls: int = 1000, max_pages: int = 250) -> list[dict]:
    """Collect BBC Good Food recipe URLs by crawling recipe index pages."""
    catalog: dict[str, dict] = {}
    queue = deque(_clean_url(urljoin(BASE_URL, path)) for path in SEED_PATHS)
    visited: set[str] = set()

    with requests.Session() as session:
        while queue and len(visited) < max_pages and len(catalog) < max_urls:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)
            log.info("Collecting BBC URLs from %s", url)

            soup = fetch(session, url, log)
            if soup is None:
                continue

            recipe_urls, index_urls = _links_from_page(soup, url)
            for recipe_url in recipe_urls:
                if len(catalog) >= max_urls:
                    break
                catalog.setdefault(
                    recipe_url,
                    {"url": recipe_url, "meal_type": None, "dietary": []},
                )

            for index_url in index_urls:
                if index_url not in visited:
                    queue.append(index_url)

            polite_sleep()

    records = list(catalog.values())
    _out = Path("output/bbc_recipe_urls.json")
    _out.parent.mkdir(parents=True, exist_ok=True)
    _out.write_text(json.dumps(records, indent=2))
    log.info("Wrote %d BBC URLs from %d pages -> %s", len(records), len(visited), _out)
    return records
