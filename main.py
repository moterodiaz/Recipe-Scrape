"""
Orchestrator — BBC Good Food recipe scraper pipeline.

Usage:
    python main.py                    # full run: collect URLs → scrape → process
    python main.py --skip-collection  # skip Phase 1, reuse output/bbc_recipe_urls.json
    python main.py --limit 50         # cap URL count for testing
    python main.py --url URL          # scrape a single recipe URL
"""

import argparse
import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from bbc_url_collector import collect_bbc_urls
from recipe_scraper import scrape_all
from processor import process_record

BBC_URL_FILE = Path("output/bbc_recipe_urls.json")
OUTPUT_FILE = Path("output/recipes.json")
SUMMARY_FILE = Path("output/scrape_summary.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _make_id(title: str, url: str) -> str:
    slug = _SLUG_RE.sub("-", title.lower()).strip("-")
    return slug if slug else hashlib.md5(url.encode()).hexdigest()[:12]


def _assemble(raw: dict) -> dict:
    return {
        "id": _make_id(raw.get("title", ""), raw["url"]),
        "url": raw["url"],
        "title": raw.get("title", ""),
        "meal_type": raw.get("meal_type"),
        "recipe_category": raw.get("recipe_category"),
        "cuisine_type": raw.get("cuisine_type", []),
        "keywords": raw.get("keywords", []),
        "dietary": raw.get("dietary", []),
        "ingredients": raw.get("ingredients", []),
        "ingredient_names": raw.get("ingredient_names", []),
        "ingredient_grams": raw.get("ingredient_grams", []),
        "equipment": raw.get("equipment", []),
        "cooking_processes": raw.get("cooking_processes", []),
        "flavor_profile": raw.get("flavor_profile", []),
        "aroma_profile": raw.get("aroma_profile", []),
        "crops_matched": raw.get("crops_matched", []),
        "crops_missing": raw.get("crops_missing", []),
        "crop_coverage": raw.get("crop_coverage", None),
        "dispensable_skipped": raw.get("dispensable_skipped", []),
        "instructions_raw": raw.get("instructions", ""),
        "servings": raw.get("servings"),
        "prep_time_min": raw.get("prep_time_min"),
        "cook_time_min": raw.get("cook_time_min"),
        "total_time_min": raw.get("total_time_min"),
    }


def _write_summary(records: list[dict]):
    meal_counts: dict[str, int] = {}
    diet_counts: dict[str, int] = {}
    for r in records:
        mt = r.get("meal_type")
        if mt:
            meal_counts[mt] = meal_counts.get(mt, 0) + 1
        for d in r.get("dietary", []):
            diet_counts[d] = diet_counts.get(d, 0) + 1

    summary = {
        "total": len(records),
        "by_meal_type": meal_counts,
        "by_dietary": diet_counts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    SUMMARY_FILE.write_text(json.dumps(summary, indent=2))
    log.info("Summary → %s", summary)


def main():
    parser = argparse.ArgumentParser(description="BBC Good Food recipe scraper")
    parser.add_argument("--skip-collection", action="store_true", help="Reuse existing bbc_recipe_urls.json")
    parser.add_argument("--limit", type=int, default=0, help="Cap number of URLs to scrape (0 = all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip this many collected URLs before applying --limit")
    parser.add_argument("--max-pages", type=int, default=500, help="Max index pages crawled in Phase 1")
    parser.add_argument("--target-urls", type=int, default=1000, help="Target URL count for collection")
    parser.add_argument("--url", help="Scrape a single recipe URL")
    parser.add_argument("--crop-csv", default=None, help="Path to crop CSV; enables Phase 3 crop cross-check")
    parser.add_argument("--min-crop-coverage", type=float, default=0.0, help="Exclude recipes below this crop coverage (0–1)")
    args = parser.parse_args()

    Path("output").mkdir(exist_ok=True)

    # Phase 1
    if args.url:
        url_records = [{"url": args.url, "meal_type": None, "dietary": []}]
        log.info("Scraping single URL: %s", args.url)
    elif args.skip_collection:
        if not BBC_URL_FILE.exists():
            raise FileNotFoundError(f"{BBC_URL_FILE} not found — run without --skip-collection first")
        url_records = json.loads(BBC_URL_FILE.read_text())
        log.info("Loaded %d URLs from %s", len(url_records), BBC_URL_FILE)
    else:
        url_records = collect_bbc_urls(max_urls=args.target_urls, max_pages=args.max_pages)

    if args.offset:
        url_records = url_records[args.offset:]
        log.info("Skipped first %d URLs", args.offset)

    if args.limit:
        url_records = url_records[: args.limit]
        log.info("Capped to %d URLs", len(url_records))

    # Phase 2A
    scraped = scrape_all(url_records)

    # Phase 2B
    for record in scraped:
        process_record(record)

    # Phase 3 — crop cross-check (optional)
    if args.crop_csv:
        from crop_checker import load_crop_terms, annotate_crop_coverage
        crop_terms = load_crop_terms(args.crop_csv)
        before = len(scraped)
        scraped = annotate_crop_coverage(scraped, crop_terms, min_coverage=args.min_crop_coverage)
        log.info("Crop filter: kept %d / %d recipes (min_coverage=%.2f)", len(scraped), before, args.min_crop_coverage)

    records = [_assemble(r) for r in scraped]
    OUTPUT_FILE.write_text(json.dumps(records, indent=2))
    log.info("Wrote %d records → output/recipes.json", len(records))

    _write_summary(records)


if __name__ == "__main__":
    main()
