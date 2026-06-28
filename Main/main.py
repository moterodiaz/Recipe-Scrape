"""
Orchestrator — recipe scraper pipeline (BBC Good Food + RecipeDB).

Usage:
    # RecipeDB path (primary / 6-stage pipeline):
    python Main/main.py --recipedb-jsonl Sources/recipedb_clean_output/recipedb_recipes_clean.jsonl \\
        --crop-csv Sources/Crop.csv --protein-csv Sources/Protein.csv

    # Relax the ingredient filter (allow up to 20% unmatched essential ingredients):
    python Main/main.py --recipedb-jsonl ... --min-crop-coverage 0.8

    # Skip FlavorDB enrichment (faster dry-run):
    python Main/main.py --recipedb-jsonl ... --skip-flavordb

    # BBC scraper path (legacy):
    python Main/main.py --skip-collection
    python Main/main.py --limit 50
    python Main/main.py --url URL
    python Main/main.py --flavor-only        # re-enrich existing output/recipes.json
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
from flavor_pipeline import (
    load_recipedb_jsonl,
    prewarm_flavordb_cache,
    convert_to_grams,
    enrich_all,
    load_cache,
)

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
        "id": _make_id(raw.get("title", ""), raw.get("url", "")),
        "url": raw.get("url", ""),
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
        "flavor_profile_quantified": raw.get("flavor_profile_quantified", {}),
        "top_5_flavors": raw.get("top_5_flavors", []),
        "flavor_intensity_score": raw.get("flavor_intensity_score"),
        "molecules_represented": raw.get("molecules_represented", 0),
        "crops_matched": raw.get("crops_matched", []),
        "crops_missing": raw.get("crops_missing", []),
        "crop_coverage": raw.get("crop_coverage"),
        "dispensable_skipped": raw.get("dispensable_skipped", []),
        "data_quality": raw.get("data_quality", {}),
        "instructions_raw": raw.get("instructions", ""),
        "servings": raw.get("servings"),
        "prep_time_min": raw.get("prep_time_min"),
        "cook_time_min": raw.get("cook_time_min"),
        "total_time_min": raw.get("total_time_min"),
        "source": raw.get("source", "bbc"),
        "recipedb_id": raw.get("recipedb_id"),
        "energy_kcal": raw.get("energy_kcal"),
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


# ── RecipeDB 6-stage pipeline ─────────────────────────────────────────────────

def run_recipedb_pipeline(args) -> None:
    """
    Clean 6-stage pipeline for RecipeDB input.

    Stage 1  — Load JSONL; extract ingredient_names; no gram conversion yet.
    Stage 2  — Hard crop/protein/pantry filter; drop unmatched recipes.
    Stage 2+ — Pre-warm FlavorDB cache from CSV allowlists (runs alongside Stage 2).
    Stage 3  — Gram conversion on surviving recipes only (no exceptions).
    Stage 4  — FlavorDB enrichment using pre-warmed cache.
    Stage 5  — Assemble and write output/recipes.json.
    """
    # ── Stage 1: Load ────────────────────────────────────────────────────────
    log.info("=== Stage 1: Loading RecipeDB JSONL ===")
    records = load_recipedb_jsonl(args.recipedb_jsonl)
    if args.limit:
        records = records[: args.limit]
        log.info("Capped to %d records", len(records))

    # ── Stage 2: Hard crop/protein/pantry filter ──────────────────────────────
    if args.crop_csv:
        log.info("=== Stage 2: Crop/Protein/Pantry filter (min_coverage=%.2f) ===", args.min_crop_coverage)
        from crop_checker import build_basket, filter_strict
        basket = build_basket(args.crop_csv, args.protein_csv)
        before = len(records)
        all_records = records  # keep ref; filter_strict mutates each dict in place
        records = filter_strict(all_records, basket, min_coverage=args.min_crop_coverage)
        log.info(
            "Stage 2: kept %d / %d recipes (dropped %d with unmatched ingredients)",
            len(records), before, before - len(records),
        )
        # Debug: near-misses (1–3 unmatched) → Pantry.csv candidates
        near_misses = [
            {"title": r.get("title", ""), "failed_ingredients": r["crops_missing"]}
            for r in all_records
            if r.get("crop_coverage", 0) < args.min_crop_coverage
            and 1 <= len(r.get("crops_missing", [])) <= 3
        ]
        Path("output/failed_recipes.json").write_text(json.dumps(near_misses, indent=2))
        log.info("Debug: %d near-miss recipes (1-3 unmatched) → output/failed_recipes.json", len(near_misses))
    else:
        log.warning("--crop-csv not provided — skipping Stage 2 ingredient filter. All recipes pass through.")

    # ── Stage 2+: Pre-warm FlavorDB cache ────────────────────────────────────
    if not args.skip_flavordb:
        log.info("=== Stage 2+: Pre-warming FlavorDB cache from CSV allowlists ===")
        cache = prewarm_flavordb_cache(
            crop_csv=args.crop_csv,
            protein_csv=args.protein_csv,
        )
    else:
        cache = load_cache()

    # ── Stage 3: Gram conversion ─────────────────────────────────────────────
    log.info("=== Stage 3: Gram conversion (%d recipes) ===", len(records))
    records = convert_to_grams(records)

    # ── Stage 4: FlavorDB enrichment ─────────────────────────────────────────
    log.info("=== Stage 4: FlavorDB enrichment ===")
    records = enrich_all(records, skip_flavordb=args.skip_flavordb, cache=cache)

    # ── Stage 5: Assemble and write ───────────────────────────────────────────
    log.info("=== Stage 5: Assembling output ===")
    output = [_assemble(r) for r in records]
    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    log.info("Wrote %d records → %s", len(output), OUTPUT_FILE)
    _write_summary(output)


# ── BBC scraper pipeline (legacy) ─────────────────────────────────────────────

def run_bbc_pipeline(args) -> None:
    """Legacy BBC scraper pipeline."""
    # Phase 1 — URL collection / loading
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

    # Phase 2A — Scrape
    scraped = scrape_all(url_records)

    # Phase 2B — Process (extract ingredient_names, equipment, etc.)
    for record in scraped:
        process_record(record)

    # Phase 3 — Crop/Protein/Pantry filter (runs BEFORE enrichment)
    if args.crop_csv:
        from crop_checker import build_basket, filter_strict
        basket = build_basket(args.crop_csv, args.protein_csv)
        before = len(scraped)
        scraped = filter_strict(scraped, basket, min_coverage=args.min_crop_coverage)
        log.info(
            "Crop filter: kept %d / %d recipes (min_coverage=%.2f)",
            len(scraped), before, args.min_crop_coverage,
        )

    # Phase 4 — FlavorDB enrichment (only on filtered recipes)
    scraped = enrich_all(scraped, skip_flavordb=args.skip_flavordb)

    records = [_assemble(r) for r in scraped]
    OUTPUT_FILE.write_text(json.dumps(records, indent=2))
    log.info("Wrote %d records → output/recipes.json", len(records))
    _write_summary(records)


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Recipe scraper + flavor pipeline")

    # RecipeDB path
    parser.add_argument("--recipedb-jsonl", default=None, help="Load recipes from RecipeDB JSONL (primary path)")

    # Ingredient filter
    parser.add_argument("--crop-csv", default=None, help="Path to Crop.csv; enables Stage 2 ingredient filter")
    parser.add_argument("--protein-csv", default=None, help="Path to Protein.csv")
    parser.add_argument(
        "--min-crop-coverage", type=float, default=1.0,
        help="Min fraction of essential ingredients that must match the allowlists (default: 1.0 = strict)",
    )

    # FlavorDB
    parser.add_argument("--skip-flavordb", action="store_true", help="Skip FlavorDB enrichment (dry-run)")
    parser.add_argument("--flavor-only", action="store_true", help="Re-enrich existing output/recipes.json and exit")

    # BBC scraper args (legacy)
    parser.add_argument("--skip-collection", action="store_true", help="Reuse existing bbc_recipe_urls.json")
    parser.add_argument("--limit", type=int, default=0, help="Cap number of records/URLs (0 = all)")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N collected URLs")
    parser.add_argument("--max-pages", type=int, default=500, help="Max BBC index pages crawled")
    parser.add_argument("--target-urls", type=int, default=1000, help="Target BBC URL count")
    parser.add_argument("--url", help="Scrape a single BBC recipe URL")
    args = parser.parse_args()
    Path("output").mkdir(exist_ok=True)
    Path("Logs").mkdir(exist_ok=True)
    _fh = logging.FileHandler("Logs/pipeline.log", mode="w")
    _fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logging.getLogger().addHandler(_fh)

    # --flavor-only: re-enrich existing output and exit
    if args.flavor_only:
        if not OUTPUT_FILE.exists():
            raise FileNotFoundError(f"{OUTPUT_FILE} not found — run scrape first")
        records = json.loads(OUTPUT_FILE.read_text())
        records = enrich_all(records, skip_flavordb=args.skip_flavordb)
        OUTPUT_FILE.write_text(json.dumps(records, indent=2))
        log.info("--flavor-only: enriched %d records → %s", len(records), OUTPUT_FILE)
        return

    # Route to the appropriate pipeline
    if args.recipedb_jsonl:
        run_recipedb_pipeline(args)
    else:
        run_bbc_pipeline(args)


if __name__ == "__main__":
    main()
