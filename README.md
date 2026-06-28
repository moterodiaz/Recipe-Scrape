# Recipe-Scrape

A Python 3.10+ recipe pipeline that ingests the RecipeDB dataset, filters recipes by how well their ingredients can be sourced from a space-farming crop basket, and outputs a FlavorDB-enriched JSON catalog for offline use.

## Pipeline (Primary — RecipeDB)

| Stage | Function / Module | Input | Output | Purpose |
|-------|------------------|-------|--------|---------|
| 1 | `load_recipedb_jsonl()` — `flavor_pipeline.py` | RecipeDB JSONL | Raw records | Load structured RecipeDB data; extract `ingredient_names` from the pre-structured field; defer gram conversion |
| 2 | `filter_strict()` — `crop_checker.py` | Raw records | Filtered records | Hard crop/protein/pantry filter; drop recipes with any unmatched essential ingredient; write near-misses to `output/failed_recipes.json` |
| 2+ | `prewarm_flavordb_cache()` — `flavor_pipeline.py` | Crop/Protein/Pantry CSVs | Populated cache | Pre-fetch FlavorDB entries for every allowlist term; runs concurrently with Stage 2 |
| 3 | `convert_to_grams()` — `flavor_pipeline.py` | Filtered records | Records w/ gram weights | Gram conversion on surviving recipes only |
| 4 | `enrich_all()` — `flavor_pipeline.py` | Records w/ gram weights | Enriched records | Weighted FlavorDB flavor profiles; top-5 flavor compounds per recipe |
| 5 | `_assemble()` — `main.py` | Enriched records | `output/recipes.json` | Assemble final schema and write catalog |

## Key Modules

**`Main/main.py`**
Orchestrator. Routes to the RecipeDB pipeline (primary) or BBC scraper (legacy). CLI flags:
- `--recipedb-jsonl PATH` — primary input; path to the RecipeDB JSONL file
- `--crop-csv PATH` — enables Stage 2 ingredient filter (required for filtering)
- `--protein-csv PATH` — adds protein sources to the allowlist
- `--min-crop-coverage FLOAT` — fraction of essential ingredients that must match (default: `1.0` = strict; use `0.8` to allow up to 20% unmatched)
- `--skip-flavordb` — skip FlavorDB enrichment (faster dry-run; sets flavor fields to null)
- `--flavor-only` — re-enrich an existing `output/recipes.json` without re-running the filter
- `--limit N` — process first N records (testing)

**`Main/flavor_pipeline.py`**
Stages 1, 2+, 3, 4. Handles RecipeDB loading, FlavorDB cache pre-warming, gram conversion, and per-recipe flavor enrichment.

**`Main/crop_checker.py`**
Stage 2 filter. Loads `Sources/Crop.csv`, `Sources/Protein.csv`, and `Sources/Pantry.csv`. Matches ingredient names using:
1. Pantry word-token match (flour, milk, powdered milk, powdered cheese)
2. Exact phrase match against crop/protein terms
3. Prefix match — handles plurals (`potatoes` → `potato`)
4. Multi-token match for compound crop names

Outputs per-recipe: `crop_coverage`, `crops_matched`, `crops_missing`, `dispensable_skipped`.

**`Main/processor.py`**
In-memory transforms (used by BBC legacy path):
- Regex-rule scanning for equipment, flavor/aroma profiles, cooking processes
- `extract_ingredient_name()` — strips amounts/descriptors from raw ingredient strings
- `ingredient_to_grams()` — delegates to `gram_converter.py`

**`Main/gram_converter.py`**
Ingredient → grams converter. Handles metric weight (g, kg), volume + density lookup (~250-entry density table from King Arthur Baking), piece weights (1 onion = 110 g, 1 garlic clove = 5 g), and Unicode fractions.

**`Main/_http.py`**
Shared HTTP helpers for the BBC scraper: user-agent rotation (5 realistic strings), 1–2 s polite sleep, `fetch()` wrapper returning BeautifulSoup or None.

## Crop Coverage Scoring

```
crop_coverage = matched / essential
```

**essential** = all ingredients minus *dispensable*:
- Salt, pepper, water, oil variants
- Role phrases: `"to serve"`, `"to garnish"`, `"optional"`, etc.

**matched** = essential ingredients that hit any allowlist:
1. `Sources/Pantry.csv` — always-stocked station items (flour, milk, powdered milk, powdered cheese)
2. Exact / prefix / token match against `Sources/Crop.csv`
3. Exact / prefix / token match against `Sources/Protein.csv`

Score range: 0.0–1.0. Default filter threshold: `1.0` (strict — all essential ingredients must match).

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

All commands are run from the **repo root**.

### Full pipeline (primary path — RecipeDB)

```bash
python Main/main.py \
  --recipedb-jsonl Sources/recipedb_clean_output/recipedb_recipes_clean.jsonl \
  --crop-csv Sources/Crop.csv \
  --protein-csv Sources/Protein.csv
```

### Relax the ingredient filter (allow up to 20% unmatched essential ingredients)

```bash
python Main/main.py \
  --recipedb-jsonl Sources/recipedb_clean_output/recipedb_recipes_clean.jsonl \
  --crop-csv Sources/Crop.csv \
  --protein-csv Sources/Protein.csv \
  --min-crop-coverage 0.8
```

### Skip FlavorDB enrichment (fast dry-run)

```bash
python Main/main.py \
  --recipedb-jsonl Sources/recipedb_clean_output/recipedb_recipes_clean.jsonl \
  --crop-csv Sources/Crop.csv \
  --protein-csv Sources/Protein.csv \
  --skip-flavordb
```

### Test run — first 50 records only

```bash
python Main/main.py \
  --recipedb-jsonl Sources/recipedb_clean_output/recipedb_recipes_clean.jsonl \
  --crop-csv Sources/Crop.csv \
  --protein-csv Sources/Protein.csv \
  --limit 50 --skip-flavordb
```

### Re-enrich existing catalog without re-running the filter

```bash
python Main/main.py --flavor-only
```

### Standalone crop cross-check on any recipes JSON

```bash
python Main/crop_checker.py \
  --crop-csv Sources/Crop.csv \
  --protein-csv Sources/Protein.csv \
  --recipes output/recipes.json \
  --min-coverage 0.8 \
  --out output/recipes_filtered.json
```

### Test inference logic (self-check)

```bash
python Main/processor.py   # runs built-in assert suite
python Main/crop_checker.py --crop-csv Sources/Crop.csv --protein-csv Sources/Protein.csv
```

---

### Legacy — BBC Good Food scraper

```bash
# Scrape fresh (Phase 1 → 2A → 2B → FlavorDB enrichment)
python Main/main.py --skip-flavordb

# Re-process without re-scraping URLs
python Main/main.py --skip-collection

# Scrape a single recipe URL
python Main/main.py --url https://www.bbcgoodfood.com/recipes/...
```

## Output Files

| File | Description |
|------|-------------|
| `output/recipes.json` | Final catalog — fully enriched recipe records |
| `output/failed_recipes.json` | Near-miss recipes (1–3 unmatched essential ingredients) — useful for expanding allowlists |
| `output/scrape_summary.json` | Record count by meal type and dietary tag, plus timestamp |
| `output/flavordb_cache.json` | Cached FlavorDB flavor compositions (persisted across runs) |
| `output/bbc_recipe_urls.json` | BBC path only — collected recipe URLs with meal type / dietary tags |
| `output/failed_urls.log` | BBC path only — URLs that errored during scraping |
| `Logs/pipeline.log` | Full pipeline log for the last run |

## Source Data

**`Sources/Crop.csv`** — growable crop basket across 3 package tiers.
- 31-crop core / 66-crop / 100-crop full
- ID format: `C1`–`C100`
- Columns: ID, Name, Category, Package 1, Package 2, Package 3

**`Sources/Protein.csv`** — protein sources (fish, poultry, insects, cell-culture).
- ID format: `PR*`

**`Sources/Pantry.csv`** — always-stocked station pantry items that auto-match any recipe ingredient containing their name tokens.
- Current items: `flour`, `milk`, `powdered milk`, `powdered cheese`

**`Sources/recipedb_clean_output/recipedb_recipes_clean.jsonl`** — cleaned RecipeDB dataset (~117 MB). Primary input for the pipeline. Each line is a JSON object with `Recipe_id`, `Recipe_title`, `Ingredients` (structured with `ingredient_name` + `ingredient_Phrase`), dietary flags, and nutritional data.

## Stack

- `requests` + `BeautifulSoup4` — HTTP and HTML parsing (BBC path)
- JSON-LD (schema.org/Recipe) — primary BBC extraction
- RecipeDB JSONL — primary structured input (pre-parsed, no scraping needed)
- FlavorDB entity index — local flavor molecule lookups
- `html.parser` (stdlib) — no lxml dependency

## Next Steps

- **Powdered cheese aliases** — route hard aged cheeses (parmesan, romano, asiago, gruyere, cheddar) to the `powdered cheese` pantry token to recover ~700+ near-miss recipes.
- **Extend `Sources/Pantry.csv`** — promote commonly available shelf-stable ingredients (e.g. `grated cheese`, `shredded mozzarella`) as pantry tokens.
- **Extend `Sources/Crop.csv`** — add rosemary, sage, cumin, basil, chilli as growable herbs/spices with package-tier tracking.
- **Calibrate threshold** — `--min-crop-coverage 0.8` retains quality recipes while filtering non-farmable ones; tune based on output catalog size target.
- **FlavorDB index build** — if `Main/flavordb/entity_index.json` is missing, run `python Main/flavordb/build_index.py` before the pipeline.
