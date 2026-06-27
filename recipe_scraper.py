"""
Phase 2A — Recipe Scraping.

For each URL record, fetches the BBC Good Food page and extracts:
  title, ingredients, instructions, servings, cook_time_min

Strategy: JSON-LD schema.org/Recipe first (reliable); HTML fallback second.
Failed URLs are appended to output/failed_urls.log.
"""

import json
import logging
import re
from pathlib import Path

import requests

from _http import fetch, polite_sleep

FAILED_LOG = Path("output/failed_urls.log")

# ISO 8601 duration: PT1H30M → 90 minutes
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?")
_HUMAN_DURATION_RE = re.compile(
    r"(?:(\d+)\s*(?:hours?|hrs?|h))?\s*(?:(\d+)\s*(?:minutes?|mins?|m))?",
    re.I,
)

log = logging.getLogger(__name__)


# ── JSON-LD extraction ────────────────────────────────────────────────────────

def _extract_jsonld(soup) -> dict | None:
    """Return first schema.org/Recipe JSON-LD object, or None."""
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, AttributeError):
            continue
        # Handle bare object, list, or @graph wrapper
        if isinstance(data, list):
            data = next((d for d in data if d.get("@type") == "Recipe"), None)
        elif isinstance(data, dict) and "@graph" in data:
            data = next((d for d in data["@graph"] if d.get("@type") == "Recipe"), None)
        if data and data.get("@type") == "Recipe":
            return data
    return None


def _parse_duration(s: str | None) -> int | None:
    """Parse ISO 8601 or short human durations to minutes."""
    if not s:
        return None
    s = str(s).strip()
    m = _DURATION_RE.match(s)
    if m:
        total = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
        return total or None
    m = _HUMAN_DURATION_RE.fullmatch(s)
    if not m:
        return None
    total = int(m.group(1) or 0) * 60 + int(m.group(2) or 0)
    return total or None


def _parse_servings(yield_val) -> int | None:
    if yield_val is None:
        return None
    if isinstance(yield_val, list):
        yield_val = yield_val[0] if yield_val else ""
    m = re.search(r"\d+", str(yield_val))
    return int(m.group()) if m else None


def _as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [v.strip() for v in re.split(r"[,|]", value) if v.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _flatten_instructions(field) -> str:
    """schema.org recipeInstructions can be str, list[str], or list[HowToStep]."""
    if isinstance(field, str):
        return field.strip()
    if isinstance(field, dict):
        if field.get("text"):
            return str(field["text"]).strip()
        if field.get("itemListElement"):
            return _flatten_instructions(field["itemListElement"])
    if isinstance(field, list):
        parts = [_flatten_instructions(item) for item in field]
        return "\n".join(p.strip() for p in parts if p.strip())
    return ""


def _scrape_jsonld(soup) -> dict | None:
    data = _extract_jsonld(soup)
    if not data:
        return None
    prep_time_min = _parse_duration(data.get("prepTime"))
    cook_time_min = _parse_duration(data.get("cookTime"))
    total_time_min = _parse_duration(data.get("totalTime"))
    if cook_time_min is None and total_time_min is not None and prep_time_min is not None:
        cook_time_min = max(total_time_min - prep_time_min, 0) or None
    return {
        "title": (data.get("name") or "").strip(),
        "ingredients": [i.strip() for i in data.get("recipeIngredient", []) if i.strip()],
        "instructions": _flatten_instructions(data.get("recipeInstructions", "")),
        "servings": _parse_servings(data.get("recipeYield")),
        "prep_time_min": prep_time_min,
        "cook_time_min": cook_time_min,
        "total_time_min": total_time_min,
        "recipe_category": data.get("recipeCategory"),
        "cuisine_type": _as_list(data.get("recipeCuisine")),
        "keywords": _as_list(data.get("keywords")),
    }


# ── HTML fallback ─────────────────────────────────────────────────────────────

def _scrape_html(soup) -> dict:
    """
    HTML fallback — used when JSON-LD is absent.

    GUESSED SELECTORS (unverified against live Food52 HTML):
    - Title: first <h1> — semantically stable across redesigns.
    - Ingredients: <ul> immediately following a heading containing "ingredient".
      Food52 likely uses a structured ingredient list; class names may be hashed.
    - Instructions: <ol> following a heading containing "instruction"/"direction"/"method".
      Numbered steps imply <ol>; fallback to <p> siblings if <ol> absent.

    # ponytail: fragile selectors; upgrade to verified CSS classes if JSON-LD coverage
    #           falls below ~90% after a sample run.
    """
    h1 = soup.find("h1")
    title = h1.get_text(strip=True) if h1 else ""

    def _is_content_heading(t, keywords):
        """True if tag is a short content heading with a keyword, not buried in a nav <li>."""
        return (
            t.name in ("h2", "h3", "h4")
            and any(kw in t.get_text(strip=True).lower() for kw in keywords)
            and t.parent.name not in ("li", "nav")
            and len(t.get_text(strip=True)) < 60
        )

    ingredients: list[str] = []
    ing_heading = soup.find(lambda t: _is_content_heading(t, ("ingredient",)))
    if ing_heading:
        ul = ing_heading.find_next("ul")
        if ul:
            ingredients = [
                " ".join(li.get_text(separator=" ", strip=True).split())
                for li in ul.find_all("li") if li.get_text(strip=True)
            ]

    instructions = ""
    inst_heading = soup.find(
        lambda t: _is_content_heading(t, ("instruction", "direction", "preparation", "method", "step"))
    )
    if inst_heading:
        ol = inst_heading.find_next("ol")
        if ol:
            steps = [li.get_text(strip=True) for li in ol.find_all("li") if li.get_text(strip=True)]
            instructions = "\n".join(steps)

    page_text = soup.get_text(" ", strip=True)

    def _extract_label_time(label: str) -> int | None:
        m = re.search(rf"\b{label}\s*:?\s*((?:\d+\s*(?:hours?|hrs?|h))?\s*(?:\d+\s*(?:minutes?|mins?|m))?)", page_text, re.I)
        return _parse_duration(m.group(1).strip()) if m else None

    prep_time_min = _extract_label_time("prep")
    cook_time_min = _extract_label_time("cook")
    total_time_min = (prep_time_min or 0) + (cook_time_min or 0) or None

    return {
        "title": title,
        "ingredients": ingredients,
        "instructions": instructions,
        "servings": None,
        "prep_time_min": prep_time_min,
        "cook_time_min": cook_time_min,
        "total_time_min": total_time_min,
        "recipe_category": None,
        "cuisine_type": [],
        "keywords": [],
    }


# ── Public API ────────────────────────────────────────────────────────────────

def scrape_recipe(session: requests.Session, url: str) -> dict | None:
    """Scrape one recipe page. Returns extracted fields or None on failure."""
    try:
        soup = fetch(session, url, log)
        if soup is None:
            raise ValueError("non-200 or fetch error")
        return _scrape_jsonld(soup) or _scrape_html(soup)
    except Exception as exc:
        log.error("Failed %s: %s", url, exc)
        FAILED_LOG.parent.mkdir(parents=True, exist_ok=True)
        with FAILED_LOG.open("a") as f:
            f.write(f"{url}\t{exc}\n")
        return None


def scrape_all(url_records: list[dict]) -> list[dict]:
    """
    Phase 2A entry point.
    Merges scraped fields into each URL record; skips failed pages.
    """
    results: list[dict] = []
    total = len(url_records)
    with requests.Session() as session:
        for i, record in enumerate(url_records, 1):
            url = record["url"]
            log.info("[%d/%d] %s", i, total, url)
            data = scrape_recipe(session, url)
            if data:
                results.append({**record, **data})
            polite_sleep()
    log.info("Scraped %d / %d successfully", len(results), total)
    return results
