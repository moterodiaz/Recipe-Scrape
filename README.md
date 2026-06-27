# Recipe-Scrape

A Python 3.10+ scraper pipeline that pulls recipes from BBC Good Food and filters them by how well their ingredients can be sourced from a space-farming crop basket. Outputs a frozen JSON catalog for offline use.

## Pipeline

| Phase | Script | Input | Output | Purpose |
|-------|--------|-------|--------|---------|
| 1 | `bbc_url_collector.py` | BBC Good Food domain | `output/bbc_recipe_urls.json` | BFS crawl recipe URLs from category/index pages |
| 2A | `recipe_scraper.py` | Recipe URLs | Recipe records | Extract title, ingredients, instructions, servings, cook/prep time via JSON-LD (schema.org/Recipe) with HTML fallback |
| 2B | `processor.py` | Recipe records | Enriched records | Infer meal type, equipment, cooking processes, flavor/aroma profiles; convert ingredient strings to grams |
| 3 | `crop_checker.py` | Enriched records | Filtered catalog | Cross-check ingredient names against crop basket; annotate coverage score and filter by threshold |

## Key modules

**`main.py`**
Orchestrator. Runs phases 1 → 2A → 2B → optional 3. CLI flags:
- `--skip-collection` — reuse `output/bbc_recipe_urls.json`; skip Phase 1
- `--limit N` — process first N recipes (test/debug)
- `--offset N` — start processing at recipe N
- `--url URL` — scrape single recipe URL instead of collection
- `--crop-csv PATH`, `--protein-csv PATH` — pass crop/protein CSVs to Phase 3
- `--min-crop-coverage FLOAT` — filter recipes by coverage threshold (0.0–1.0)

**`bbc_url_collector.py`**
BFS crawler. Seeds from major meal categories and collections. Rate-limited via `_http.polite_sleep()`.

**`recipe_scraper.py`**
Per-recipe scraper. JSON-LD extraction is primary (highly reliable on BBC Good Food); HTML fallback used when JSON-LD absent.

**`processor.py`**
In-memory transforms:
- Regex-rule scanning for equipment, flavor/aroma profiles, cooking processes
- `extract_ingredient_name()` strips amounts/descriptors from raw ingredient strings
- `ingredient_to_grams()` (calls `gram_converter.py`) converts to weight units

**`gram_converter.py`**
Ingredient → grams converter. Handles:
- Metric weight (g, kg)
- Volume + density lookup (cups, tbsp, tsp) — ~250-entry density table from King Arthur Baking
- Piece weights (1 onion = 110g, 1 garlic clove = 5g)
- Unicode fractions

**`crop_checker.py`**
Crop coverage filter. Loads `Crop.csv` and `Protein.csv`. Matches ingredient names using exact, prefix (handles plurals), and token matching. Outputs:
- `crop_coverage` — 0.0–1.0 coverage score
- `crops_matched` — matched ingredient → crop ID mappings
- `crops_missing` — essential ingredients not found in basket
- `dispensable_skipped` — filtered ingredients (salt, oil, water, garnish, etc.)

**`_http.py`**
Shared HTTP helpers: user-agent rotation (5 realistic strings), 1–2s polite sleep, `fetch()` wrapper returning BeautifulSoup or None.

## Crop coverage scoring

```
crop_coverage = matched / essential
```

**essential** = all ingredients minus *dispensable*:
- Salt, pepper, water, oil variants
- Anything with role phrase: `"to serve"`, `"to garnish"`, `"optional"`, etc.

**matched** = essential ingredients that hit any of:
1. `_PANTRY_NAMES` — always-stocked: flour, milk, powdered milk, cheese
2. `_COMMON_CROPS` — growable but absent/aliased in CSV: garlic, onion, ginger, coriander, thyme, parsley, lime, lemon, pea
3. Exact phrase match against `Crop.csv` + `Protein.csv`
4. Token match against significant crop words (filtered through `_CROP_TOKEN_STOPWORDS` to avoid false positives)
5. Prefix match — handles plurals (`potatoes` → `potato`)

Score range: 0.0–1.0. Default filter threshold: 0.0 (no filtering).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
# Full pipeline (Phase 1 → 2A → 2B)
python main.py

# Re-process without re-scraping
python main.py --skip-collection

# Test run — first 20 URLs only
python main.py --limit 20

# With crop filter (keep recipes ≥40% coverage)
python main.py --skip-collection --crop-csv Crop.csv --protein-csv Protein.csv --min-crop-coverage 0.4

# Standalone crop cross-check on existing recipes.json
python crop_checker.py --crop-csv Crop.csv --protein-csv Protein.csv --min-coverage 0.4

# Test inference logic
python processor.py   # runs built-in self-check asserts
```

## Output files

| File | Description |
|------|-------------|
| `output/bbc_recipe_urls.json` | Phase 1 — recipe URLs with meal_type/dietary tags |
| `output/recipes.json` | Final catalog — enriched recipe records |
| `output/scrape_summary.json` | Counts by meal_type and dietary, plus timestamp |
| `output/failed_urls.log` | URLs that errored during scraping |

## Reference data

**`Crop.csv`** — 45 crops across 3 package tiers.
- 31-crop core / 66-crop / 100-crop full
- ID format: `C1`–`C45`
- Columns: ID, Name, Category, Package 1, Package 2, Package 3

**`Protein.csv`** — 22 protein sources (fish, poultry, insects, cell-culture).
- ID format: `PR*`

## Stack

- `requests` + `BeautifulSoup4` — HTTP and HTML parsing
- JSON-LD (schema.org/Recipe) — primary extraction
- HTML fallback via heading-proximity selectors
- `html.parser` (stdlib) — no lxml dependency

## Next steps

- **Fix ingredient parser bug** — `recipe_scraper.py` splits on comma after stripping quantity prefix, producing artifacts like `"skin-on"` from `"8 skin-on, bone-in chicken thighs"`. Fix: strip only leading quantity token, not everything before first comma.
- **Expand `_COMMON_CROPS`** — add rosemary, sage, cumin, basil, chilli (growable herbs/spices not yet in CSV).
- **Calibrate threshold** — smoke test (n=100) shows avg `crop_coverage` ≈ 0.55; threshold of 0.3–0.4 filters non-farmable recipes while retaining quality ones.
- **Run on full dataset** — `output/recipes_bbc_5k.json` exists; run `crop_checker.py` standalone to get full filtered catalog.
- **Extend Crop.csv** — promote garlic, onion, ginger, thyme, parsley, lime, lemon from `_COMMON_CROPS` hardcode to CSV for package-tier tracking.
