# BBC Good Food — Max-Scale Scrape Runbook

## What's already done

- BBC scraper pipeline fully working (`bbc_url_collector.py`, `recipe_scraper.py`, `processor.py`)
- Phase 3 crop filter with dispensable-ingredient logic (`crop_checker.py`) — garnishes/condiments excluded from coverage denominator
- Existing dataset: `output/recipes_bbc_5k.json` (5000 recipes from a capped run)

## Prerequisites

```bash
cd /path/to/Recipe-Scrape
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Crop CSV must be present: `"Untitled spreadsheet - 01a_Crop Production Items.csv"` in project root.

---

## Step 1 — BBC max-scale collection + scrape

This runs all four pipeline phases in one shot:
- Phase 1: BFS collection from BBC Good Food recipe index pages
- Phase 2A: Scrape each recipe page (JSON-LD → HTML fallback)
- Phase 2B: Infer equipment, flavor, aroma, cooking processes, gram weights
- Phase 3: Annotate crop coverage, populate `dispensable_skipped`

```bash
source .venv/bin/activate

nohup python3 main.py \
  --source bbc \
  --target-urls 50000 \
  --max-pages 15000 \
  --limit 50000 \
  --crop-csv "Untitled spreadsheet - 01a_Crop Production Items.csv" \
  --min-crop-coverage 0.0 \
  > bbc_max_scrape.log 2>&1 &

echo "PID: $!"
```

`--min-crop-coverage 0.0` keeps every recipe annotated. Downselect by threshold in Step 3.

**Time estimate**: 6–20 hours. Polite delay is 1–2s per HTTP request; queue drains when BBC BFS exhausts all reachable recipe/index pages.

### Monitor progress

```bash
# Live tail
tail -f bbc_max_scrape.log

# Quick status check
tail -5 bbc_max_scrape.log

# Count URLs collected so far (Phase 1 not yet done if this file is small)
python3 -c "import json; print(len(json.load(open('output/bbc_recipe_urls.json'))))" 2>/dev/null

# Count scraped records so far (Phase 2 in progress)
python3 -c "import json; print(len(json.load(open('output/recipes.json'))))" 2>/dev/null
```

### Expected log markers

| Phase | Log line to look for |
|---|---|
| Phase 1 done | `Wrote N BBC URLs from M pages -> output/bbc_recipe_urls.json` |
| Phase 2A done | `Scraped N / M successfully` |
| Phase 3 done | `Crop filter: kept N / M recipes (min_coverage=0.00)` |
| All done | `Wrote N records → output/recipes.json` |

---

## Step 2 — Check output quality

```bash
source .venv/bin/activate

python3 -c "
import json
recs = json.load(open('output/recipes.json'))
print(f'Total records: {len(recs)}')
print(f'With crop_coverage > 0:  {sum(1 for r in recs if (r[\"crop_coverage\"] or 0) > 0)}')
print(f'With dispensable_skipped: {sum(1 for r in recs if r[\"dispensable_skipped\"])}')
print()
print('Sample records:')
for r in recs[:5]:
    print(f'  {r[\"title\"][:55]:<55} cov={r[\"crop_coverage\"]} skip={len(r[\"dispensable_skipped\"])} dispensable')
"

# Check failed URLs
wc -l output/failed_urls.log 2>/dev/null && tail -5 output/failed_urls.log
```

---

## Step 3 — Threshold sweep and final downselect

Pick a `crop_coverage` threshold. A recipe with coverage 0.5 means half its essential (non-garnish) ingredients are growable crops.

```bash
source .venv/bin/activate

python3 -c "
import json
recs = json.load(open('output/recipes.json'))
print(f'Total: {len(recs)}')
for t in [0.0, 0.1, 0.25, 0.5, 0.6, 0.75, 0.9, 1.0]:
    n = sum(1 for r in recs if (r['crop_coverage'] or 0) >= t)
    print(f'  coverage >= {t:.2f}: {n:5d} recipes')
"
```

Once you pick a threshold T (e.g. 0.5):

```bash
python3 crop_checker.py \
  --recipes output/recipes.json \
  --crop-csv "Untitled spreadsheet - 01a_Crop Production Items.csv" \
  --min-coverage 0.5 \
  --out output/recipes_final.json

echo "Done. Final count:"
python3 -c "import json; print(len(json.load(open('output/recipes_final.json'))))"
```

---

## Resume from Phase 2 (if process dies mid-run)

Phase 1 output is saved immediately. If the process dies after Phase 1 completes:

```bash
source .venv/bin/activate

python3 main.py \
  --source bbc \
  --skip-collection \
  --crop-csv "Untitled spreadsheet - 01a_Crop Production Items.csv" \
  --min-crop-coverage 0.0 \
  2>&1 | tee bbc_resume.log
```

---

## Output files

| File | Description |
|---|---|
| `output/bbc_recipe_urls.json` | Phase 1 — all BBC recipe URLs collected |
| `output/recipes.json` | Full annotated catalog (all coverage thresholds) |
| `output/recipes_final.json` | Downselected at threshold T |
| `output/scrape_summary.json` | Counts by meal_type / dietary + timestamp |
| `output/failed_urls.log` | URLs that errored (appended each run) |

---

## Key recipe fields

| Field | Type | Notes |
|---|---|---|
| `title` | str | Recipe name |
| `crop_coverage` | float | 0.0–1.0, essential-ingredient crop match ratio |
| `dispensable_skipped` | list[str] | Ingredients excluded from coverage (garnishes, condiments) |
| `crops_matched` | list[str] | Essential ingredients that matched crop list |
| `crops_missing` | list[str] | Essential ingredients with no crop match |
| `ingredient_names` | list[str] | All cleaned ingredient names |
| `ingredients` | list[str] | Raw scraped ingredient strings |
