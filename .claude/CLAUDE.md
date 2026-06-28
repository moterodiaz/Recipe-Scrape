# Recipe-Scrape — BBC Good Food Catalog Builder

Python 3.10+ scraper pipeline. Outputs a frozen JSON catalog for offline use.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Run

All commands run from repo root.

```bash
# Full pipeline (Phase 1 → 2A → 2B)
python Main/main.py

# Re-process without re-scraping (reuses output/bbc_recipe_urls.json)
python Main/main.py --skip-collection

# Test run — scrape only first 20 URLs
python Main/main.py --limit 20

# With crop filter
python Main/main.py --skip-collection --crop-csv Sources/Crop.csv --protein-csv Sources/Protein.csv --min-crop-coverage 0.4
```

## Test inference logic

```bash
python Main/processor.py   # runs built-in self-check asserts
```

## Output files

| File | Description |
|------|-------------|
| `output/bbc_recipe_urls.json` | Phase 1 result — URL list with meal_type/dietary tags |
| `output/recipes.json` | Final catalog — full recipe records |
| `output/scrape_summary.json` | Counts by meal_type and dietary, plus timestamp |
| `output/failed_urls.log` | URLs that errored during scraping |

## Folder layout

| Folder | Contents |
|--------|----------|
| `Main/` | All Python source files |
| `Sources/` | `Crop.csv`, `Protein.csv` reference data |
| `output/` | Generated JSON/log artifacts |
| `Logs/` | Scrape run logs |

## Stack

- `requests` + `BeautifulSoup4` — HTTP and HTML parsing
- JSON-LD (schema.org/Recipe) — primary extraction path
- HTML fallback via heading-proximity selectors (noted as guesses in code)
- `html.parser` (stdlib) — no lxml dependency

## Notes

- Rate limit: 1–2 s random delay between every request (`Main/_http.py`)
- User-agents rotate across 5 realistic browser strings
- `--limit N` is the test knob — use before a full crawl to sanity-check extraction
