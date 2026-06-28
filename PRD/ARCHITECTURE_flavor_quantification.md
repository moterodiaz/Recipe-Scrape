# Architecture Plan: Recipe Flavor Quantification Integration

**Source PRD:** `PRD/PRD_recipe_flavor_quantification.md`  
**Target Repo:** Recipe-Scrape (BBC Good Food scraper pipeline)  
**Author:** Orchestrator + Reviewer Council (Architect · Skeptic · Pragmatist · Critic)  
**Date:** 2026-06-28  
**Status:** Ready for `developer-core` / `developer-refactor` execution via Claude Code CLI

---

## Orchestrator Intake Assessment

The repo is an existing, working pipeline:

```
bbc_url_collector.py  →  recipe_scraper.py  →  processor.py  →  output/recipes.json
                                                     ↑
                                               gram_converter.py (offline lookup table)
```

The PRD calls for **three new capabilities** layered on top of this:

1. **FlavorDB2 entity matching + molecule fetch** — maps each ingredient name to a FlavorDB2 entity, fetches its molecule list, derives a `flavor_composition` dict (% per flavor tag).
2. **Weighted flavor aggregation** — combines per-ingredient compositions using mass weights from `gram_converter.py` (already working) to produce a `recipe_flavor_profile`.
3. **Quality metrics + structured output** — unit conversion success rate, FlavorDB match rate, entropy score, top-5 flavors.

`gram_converter.py` already solves Phase 3 (unit normalization) offline. The RapidAPI unit converter is **not needed** unless gram_converter misses an ingredient — treat it as optional fallback only.

---

## Reviewer Council — Round 1

### Architect Review

**Position:** The current architecture is a clean sequential pipeline. Flavor quantification should be added as a new Phase (Phase 4) with its own module, not patched into `processor.py`, which is already doing too many things.

**Findings:**
- `processor.py` currently conflates flavor inference (regex keyword scan) with equipment inference, cooking process inference, meal type inference, and gram conversion. Adding FlavorDB API calls here would violate single-responsibility and make the module untestable in isolation.
- `gram_converter.py`'s `ingredient_to_grams()` returns `None` for unrecognized ingredients — the PRD's weighted aggregation must handle `None` gracefully (skip from mass total, flag in `data_quality`).
- The existing `flavor_profile` field in `processor.py` is a **label list from regex**, not a quantified composition. The new system produces a **float dict**. These are architecturally different things. They must be stored in separate fields (`flavor_profile` = existing labels, `flavor_profile_quantified` = new weighted dict) to avoid breaking downstream consumers of `output/recipes.json`.
- FlavorDB2 entity IDs are not known a priori — the system needs a name→ID mapping step before fetching molecules. The PRD assumes fuzzy matching against 936 known entities but provides no entity index. An entity index must be pre-fetched and cached.

**Blocker:** The entity index (name→ID lookup table) must be built before any ingredient matching can happen. Without it the FlavorDB2 fetch loop cannot resolve IDs. This is a prerequisite, not an implementation detail.

**Surprise:** The PRD's normalization constraint ("flavor_composition sums to 1.0") is violated if a molecule has multiple flavor tags. The PRD counts tag occurrence per molecule, not per molecule-tag pair — if one molecule has `"spicy@meaty"` that counts as +1 for spicy AND +1 for meaty, so the sum over all tags exceeds the molecule count. The normalization step (divide each tag count by **total tag occurrences**, not by molecule count) must be explicit.

---

### Skeptic Review

**Position:** The PRD is sound in principle, but three PRD elements should be challenged before implementation.

**Challenges:**
- **RapidAPI unit converter**: `gram_converter.py` already handles the vast majority of unit conversions offline with a 525-line lookup table and regex parser. The RapidAPI call adds cost, rate limits, and a hard external dependency for marginal gain. Simpler alternative: extend `gram_converter.py`'s `GRAMS_PER_CUP` and `_PIECE_WEIGHTS` tables for any gaps found in practice, only falling back to RapidAPI for ingredients that return `None` after two lookup passes.
- **Redis cache (TTL 30 days)**: The PRD mandates Redis. At current scale (a few thousand recipes), SQLite or a JSON file cache is simpler and has zero ops overhead. The FlavorDB2 entity catalog is ~936 entities — the entire dataset fits in a single JSON file loaded at startup. Redis is over-engineered for this scale.
- **"Flavor intensity score"**: The PRD mentions `flavor_intensity_score: 0.72` in the output spec but never defines the formula. Do not implement it until the formula is specified. Reserve the field as `null` in output.

**Blocker:** RapidAPI is described as mandatory but is not. Implementing it as a required step creates a runtime API-key dependency that blocks offline use. Gate it behind an `--use-rapidapi` flag.

**Surprise:** FlavorDB2's `flavor_profile` field is a freeform string (`"spicy@meaty@woody"`) — not a controlled vocabulary. The same flavor may appear as "spicy", "spice", "hot", "pungent" across different entities. The normalization layer must include a flavor tag canonicalization map, or the aggregated recipe profiles will have dozens of near-duplicate tags that fragment the distribution.

---

### Pragmatist Review

**Position:** This is shippable in two passes: Pass 1 (core FlavorDB fetch + weighted aggregation, no caching, offline gram_converter), Pass 2 (caching layer + quality metrics dashboard). Don't block Pass 1 on cache infrastructure.

**Findings:**
- The FlavorDB2 API (`cosylab.iiitd.edu.in`) is an academic server with no SLA. If it's down or slow, the entire pipeline blocks. Mitigation: add a `--skip-flavordb` flag that runs the pipeline without flavor quantification and marks all records with `flavor_profile_quantified: null`.
- There is no documented FlavorDB2 entity index endpoint in the PRD. The PRD says "fuzzy matching against 936 known ingredients" but doesn't say where the 936 entities come from. Before any code is written, the developer agent must verify the entity list endpoint exists and is accessible.
- The output spec in Section 5.2 uses `recipe_id: "spoonacular_42857"` — but this repo generates IDs from title slugs (`_make_id()` in `main.py`), not Spoonacular IDs. The output schema must use the repo's existing ID format.
- Missing: a `--flavor-only` flag to re-process an existing `output/recipes.json` and add quantified flavor profiles without re-scraping. This is operationally critical — re-scraping 1000 recipes to add flavor data would be wasteful.

**Blocker:** FlavorDB2 entity index access must be confirmed before any implementation begins. If the listing endpoint doesn't exist, the fuzzy matching strategy has no corpus to match against.

**Surprise:** The real operational risk is that `gram_converter.py` returns `None` for unusual ingredients, dropping them from the mass total silently. If 3 of 10 ingredients fail gram conversion, the mass weights are computed over 7 ingredients — the resulting profile is for a different recipe than was scraped. This must be flagged in `data_quality.unit_conversion_success_rate`, and recipes below 70% success rate should have `flavor_profile_quantified` set to null.

---

### Critic Review

**Position:** The most serious risks are in the FlavorDB fetch loop and the normalization math, both of which can produce silently wrong output.

**Findings:**
- **Silent wrong normalization**: If `gram_converter.py` returns `None` for an ingredient and that ingredient is excluded from the mass total, but its FlavorDB module was fetched and cached, the weighted aggregation silently ignores a real flavor contributor. Example: `1 tbsp fish sauce` (strong umami) — if fish sauce gram conversion returns `None`, it gets 0 weight in the aggregation, underrepresenting umami. Exclude such ingredients from **both** the gram total **and** the FlavorDB aggregation, and log them in `unmapped_ingredients`.
- **Tag sum invariant**: The PRD states "all percentages must sum to 100%". But if all of an ingredient's molecules have no `flavor_profile` tag, `flavor_composition` is `{}` and contributes nothing to the recipe sum. After aggregation, the recipe sum may be < 1.0 if some ingredients have empty compositions. The final normalization step must guard against `sum == 0` before dividing (ZeroDivisionError).
- **Concurrent fetch race**: If flavor module pre-loading is parallelized (as the PRD proposes), shared mutable state in the ingredient cache dict must be thread-safe. Use `threading.Lock` on the cache write path.
- **HTTP 429 from FlavorDB2**: The academic server may rate-limit aggressive parallel fetches. Without a rate limiter, 200 parallel ingredient fetches will likely trigger 429s, and the error handler logs and continues — silently producing an incomplete flavor profile.

**Blocker:** ZeroDivisionError at final normalization if all ingredients have empty flavor compositions. This will crash the pipeline on any recipe where no ingredients match FlavorDB entities. Guard: `if total_flavor_sum == 0: return {}` and flag as `flavor_profile_quantified: null`.

**Surprise:** The PRD's "fuzzy match threshold > 0.7" is applied without specifying the similarity metric. Levenshtein distance and cosine similarity on token bags give very different results for ingredient names. The matching strategy must be specified before implementation.

---

## Orchestrator Synthesis — Round 1

```
## Review Round 1

**Architect:** Phase 4 must be a standalone module; entity index is a hard prerequisite.
**Skeptic:** RapidAPI and Redis are unnecessary complexity at current scale; flag both.
**Pragmatist:** FlavorDB endpoint verification must happen before Round 1 code; --flavor-only is a must.
**Critic:** ZeroDivisionError is a real crash risk; tag canonicalization is the silent correctness risk.

**Consensus:**
  1. RapidAPI is not mandatory — use gram_converter.py offline, RapidAPI behind --use-rapidapi flag
  2. Cache = JSON file on disk, not Redis, at current scale
  3. flavor_profile_quantified must be a separate field from existing flavor_profile regex labels
  4. FlavorDB entity index must be pre-fetched before ingredient matching
  5. ZeroDivisionError guard required in aggregation normalizer
  6. --skip-flavordb flag needed for pipeline resilience

**Dissent:**
  Critic: use threading.Lock for parallel pre-loading.
  Pragmatist: don't parallelize at all in Pass 1 — sequential is simpler and safe.
  Resolution: sequential fetch in Pass 1. Parallelism deferred to Pass 2 behind a flag.

  Skeptic: don't implement flavor_intensity_score.
  Architect: reserve as null.
  Resolution: output field present, value always null, TODO comment referencing PRD §11.

**Blockers:**
  1. Verify FlavorDB2 entity listing endpoint before any code
  2. Define flavor tag canonicalization map (prevents tag fragmentation)
  3. Decide fuzzy matching metric: recommendation = rapidfuzz.WRatio, score_cutoff=80

**Action:** Phase 0 (endpoint verification) dispatched to developer-core before any file changes.
```

---

## Proposed File Layout (New Files Only)

```
Recipe-Scrape/
├── flavordb/
│   ├── __init__.py            # package marker
│   ├── client.py              # FlavorDB2 HTTP fetch + retry, 1 req/sec rate limit
│   ├── entity_index.py        # Load/build name→entity_id mapping + fuzzy match
│   ├── flavor_module.py       # Per-ingredient flavor composition calculator
│   └── tag_canon.py           # Flavor tag canonicalization map
├── flavor_aggregator.py       # Weighted aggregation algorithm (Phase 4)
├── flavor_pipeline.py         # Orchestrates Phases 1→4; --flavor-only entry point
├── output/
│   └── flavordb_cache.json    # Persistent entity+molecule cache (add to .gitignore)
└── tests/
    ├── test_flavor_module.py
    └── test_flavor_aggregator.py
```

**Modified files:**

| File | Change |
|------|--------|
| `main.py` | Add `--flavor-only`, `--skip-flavordb`, `--use-rapidapi` flags; call `flavor_pipeline.enrich_all()` after Phase 2B |
| `processor.py` | No change — `process_record()` untouched |
| `requirements.txt` | Add `rapidfuzz>=3.0.0` |
| `CLAUDE.md` | Add Phase 4 documentation |

---

## Phase-by-Phase Implementation Tasks

### Phase 0 — Prerequisite Verification (no code commits)

```
Task: Verify FlavorDB2 entity listing endpoint
Agent: developer-core
Action:
  - GET https://cosylab.iiitd.edu.in/flavordb2/entities_json (no id param)
    OR inspect https://cosylab.iiitd.edu.in/flavordb2/ for entity list endpoint
  - If entity list exists: download full list, save to flavordb/entity_index.json
  - If no list endpoint: fallback = fetch entity IDs 1–1000 sequentially,
    cache 404s, build index from successful responses
  - Log: total entities found, sample of entity names
  - Do NOT write any application code until this report is complete

Expected output: Written report of endpoint behavior + sample entity list
Leave untouched: all source files
```

### Phase 1 — FlavorDB Client + Entity Index

```
Task: Build flavordb/ package (client + entity index)
Agent: developer-core
Files to create:
  - flavordb/__init__.py        (empty)
  - flavordb/client.py
      def fetch_entity(entity_id: int, cache: dict, session) -> dict | None
      - GET https://cosylab.iiitd.edu.in/flavordb2/entities_json?id={entity_id}
      - Retry once on 5xx; return None on 404
      - Enforce 1 req/sec via time.sleep()
      - Write to cache[entity_id] on success
  - flavordb/entity_index.py
      def load_index(path: str) -> dict[str, int]  # name (lower) -> entity_id
      def find_entity(name: str, index: dict) -> int | None
      - Exact match first; rapidfuzz WRatio score_cutoff=80 fallback

Expected observable output:
  python -c "from flavordb.entity_index import load_index, find_entity; \
             idx = load_index('flavordb/entity_index.json'); \
             print(find_entity('garlic', idx))"
  → Returns entity_id int (e.g., 42) or None

Leave untouched: main.py, processor.py, gram_converter.py, recipe_scraper.py
```

### Phase 2 — Flavor Module Calculator

```
Task: Per-ingredient flavor composition
Agent: developer-core
File to create: flavordb/flavor_module.py

Algorithm (exact):
  def compute_flavor_composition(entity_id, cache, session, entity_index) -> dict:
    1. Fetch entity data via client.fetch_entity()
    2. For each molecule, split flavor_profile on "@" → tag list
    3. Canonicalize each tag via tag_canon.canonicalize()
    4. Count occurrences per canonical tag across all molecules
    5. total_tag_occurrences = sum(all tag counts)
       NOTE: denominator is sum of ALL tag occurrences (not molecule count)
       because one molecule may carry multiple tags
    6. If total_tag_occurrences == 0: return {}
    7. Return: {tag: count/total for tag, count in tag_counts.items()}
       — must sum to 1.0 ± 0.001

Edge cases (must handle, not just log):
  - entity_id is None → return {}
  - No molecules in response → return {}
  - All molecules have empty/null flavor_profile → return {}
  - sum(tag_counts) == 0 → return {}  [guard against ZeroDivisionError]

Expected observable output:
  python -m flavordb.flavor_module --entity-id 42
  → Prints flavor_composition dict; prints sum (must be ~1.0)

Leave untouched: all other files
```

### Phase 3 — Tag Canonicalization

```
Task: Build flavor tag canonicalization map
Agent: developer-refactor
File to create: flavordb/tag_canon.py

Strategy:
  1. Fetch 50 entity molecule lists from FlavorDB2 client
  2. Collect all unique raw flavor tags (split on "@")
  3. Group near-duplicates; build CANON_MAP: dict[str, str]
  4. Expose: def canonicalize(tag: str) -> str
     - lowercase the tag first
     - look up in CANON_MAP; return mapped value or original if not in map

Minimum canonical tags to include (based on PRD examples):
  spicy, meaty, fatty, sweet, umami, salty, fresh, smoky, bitter,
  sour, creamy, buttery, pungent, sulfurous, fruity, floral, earthy,
  nutty, herbal, woody, roasted, fermented

Expected observable output:
  python -c "from flavordb.tag_canon import canonicalize; \
             print(canonicalize('SPICE'), canonicalize('hot'))"
  → "spicy" "spicy"

Leave untouched: all other files
```

### Phase 4 — Weighted Aggregation

```
Task: Recipe-level flavor profile computation
Agent: developer-core
File to create: flavor_aggregator.py

def compute_recipe_flavor_profile(
    ingredients: list[dict],
    # each: {"name": str, "grams": float | None, "flavor_composition": dict | None}
) -> dict:

Returns:
  {
    "flavor_profile_quantified": {"tag": float, ...},  # sums to 1.0 or is {}
    "top_5_flavors": ["tag", ...],
    "flavor_intensity_score": None,                    # TODO: formula TBD (PRD §11)
    "molecules_represented": int,
    "data_quality": {
      "unit_conversion_success_rate": float,
      "ingredient_flavordb_match_rate": float,
      "unmapped_ingredients": [str],
      "zero_gram_ingredients": [str]
    }
  }

Algorithm (exact — do not deviate):
  1. Filter: ingredients where grams is None or grams < 0.1
     → add name to data_quality["zero_gram_ingredients"]
     → exclude from mass total AND from weighted sum
  2. Filter: remaining ingredients where flavor_composition is {} or None
     → add name to data_quality["unmapped_ingredients"]
     → exclude from weighted sum (but DO include in mass total if grams are valid)
  3. included = ingredients passing both filters
  4. total_grams = sum(ing["grams"] for ing in included)
  5. If total_grams == 0: return {"flavor_profile_quantified": {}, ...}
  6. For each included ingredient:
       weight = ing["grams"] / total_grams
       for tag, pct in ing["flavor_composition"].items():
           recipe_flavor[tag] = recipe_flavor.get(tag, 0.0) + weight * pct
  7. total_flavor_sum = sum(recipe_flavor.values())
  8. If total_flavor_sum == 0: return {"flavor_profile_quantified": {}, ...}
  9. Normalize: recipe_flavor[tag] /= total_flavor_sum  (for all tags)
  10. top_5_flavors = [tag for tag, _ in sorted(recipe_flavor.items(),
                       key=lambda x: x[1], reverse=True)[:5]]
  11. Compute rates:
      unit_conversion_success_rate = (grams_valid_count) / len(ingredients)
      ingredient_flavordb_match_rate = (flavor_matched_count) / len(ingredients)

Self-check (run as __main__):
  fixture: chicken(400g, {meaty:0.45, fatty:0.30, umami:0.15, sweet:0.05, sulfurous:0.05})
           avocado(150g, {creamy:0.50, buttery:0.30, fresh:0.20})
  assert sum(result["flavor_profile_quantified"].values()) ≈ 1.0
  assert result["top_5_flavors"][0] == "meaty"

Leave untouched: processor.py, gram_converter.py, main.py
```

### Phase 5 — Pipeline Orchestration

```
Task: Connect all phases; add CLI flags to main.py
Agent: developer-core
File to create: flavor_pipeline.py

def load_cache(path: str = "output/flavordb_cache.json") -> dict:
  """Load entity+molecule cache from disk; return {} if file missing."""

def save_cache(cache: dict, path: str = "output/flavordb_cache.json") -> None:
  """Persist cache to disk as JSON."""

def enrich_record(
    record: dict,
    entity_index: dict,
    cache: dict,
    session,
) -> dict:
  """
  Given a fully processed record (post-processor.py), add:
    - ingredient_flavordb_ids: list[int | None]
    - flavor_profile_quantified: dict | None
    - top_5_flavors: list[str]
    - flavor_intensity_score: None
    - molecules_represented: int
    - data_quality (extended with flavordb fields)
  Mutates record in-place, returns record.
  """

def enrich_all(
    records: list[dict],
    skip_flavordb: bool = False,
    entity_index_path: str = "flavordb/entity_index.json",
) -> list[dict]:
  """
  Phase 4 entry point.
  If skip_flavordb=True: set all flavor_profile_quantified fields to None.
  Sequential fetch only (no threading in v1).
  Rate limit: enforced inside flavordb/client.py (1 req/sec).
  Loads cache at start; saves cache at end.
  """

Modify main.py:
  Add arguments to argparse:
    --skip-flavordb     action="store_true"  (default: False)
    --use-rapidapi      action="store_true"  (default: False — placeholder, logs warning if set)
    --flavor-only       action="store_true"  (loads output/recipes.json, enriches, writes back, exits)

  In main():
    After Phase 2B loop (after process_record calls):
      scraped = flavor_pipeline.enrich_all(scraped, skip_flavordb=args.skip_flavordb)

    Add --flavor-only handler before Phase 1:
      if args.flavor_only:
          records = json.loads(OUTPUT_FILE.read_text())
          enriched = flavor_pipeline.enrich_all(records, skip_flavordb=args.skip_flavordb)
          OUTPUT_FILE.write_text(json.dumps(enriched, indent=2))
          log.info("Flavor-only enrichment complete: %d records", len(enriched))
          return

Leave untouched: processor.py, gram_converter.py, recipe_scraper.py, bbc_url_collector.py
```

### Phase 6 — Tests

```
Task: Unit tests for core algorithms
Agent: developer-test
Files to create:
  - tests/__init__.py  (empty)
  - tests/test_flavor_module.py
  - tests/test_flavor_aggregator.py

test_flavor_module.py (no network — mock client):
  - test_empty_molecule_list_returns_empty_dict()
  - test_single_molecule_single_tag_returns_1_0()
  - test_multi_tag_single_molecule_splits_correctly()
  - test_normalization_sums_to_1_within_tolerance()
  - test_unknown_entity_returns_empty_dict()

test_flavor_aggregator.py (pure computation — no mocks needed):
  - test_all_none_grams_returns_empty_profile()
  - test_single_ingredient_profile_equals_its_composition()
  - test_two_ingredients_weighted_by_mass()
  - test_profile_sums_to_1_within_float_tolerance()  [assert abs(sum - 1.0) < 0.001]
  - test_zero_gram_ingredient_excluded_from_weight()
  - test_unmapped_ingredient_excluded_from_weighted_sum()
  - test_no_crash_on_all_unmapped()  [assert result["flavor_profile_quantified"] == {}]

Run with: python -m pytest tests/ -v
Leave untouched: all application files
```

---

## Conflict Dependency Map (Orchestrator scheduling)

```
Phase 0 (verify endpoint)   →  blocks ALL other phases
Phase 1 (client + index)    →  blocks Phase 2, 4, 5    [parallel-safe with Phase 3]
Phase 3 (tag_canon)         →  blocks Phase 2          [parallel-safe with Phase 1]
Phase 2 (flavor_module)     →  blocks Phase 4, 5
Phase 4 (aggregator)        →  blocks Phase 5
Phase 5 (pipeline + main)   →  blocks Phase 6
Phase 6 (tests)             →  no downstream blockers
```

**Round structure for Claude Code CLI agent sessions:**

| Round | Agent | Task | Files touched |
|-------|-------|------|---------------|
| 1 | developer-core | Phase 0: endpoint verification | None (report only) |
| 2a | developer-core | Phase 1: flavordb/ package | flavordb/__init__.py, client.py, entity_index.py |
| 2b | developer-refactor | Phase 3: tag_canon.py | flavordb/tag_canon.py |
| 3 | developer-core | Phase 2: flavor_module.py | flavordb/flavor_module.py |
| 4 | developer-core | Phase 4: flavor_aggregator.py | flavor_aggregator.py |
| 5 | developer-core | Phase 5: pipeline + main.py | flavor_pipeline.py, main.py |
| 6 | developer-test | Phase 6: tests | tests/__init__.py, test_flavor_module.py, test_flavor_aggregator.py |
| 7 | All reviewers | Final council review | Read-only |

> Rounds 2a and 2b are safe to run in parallel — no file overlap.
> All other rounds must be strictly sequential per the dependency map.

---

## Output Schema (Extended `recipes.json` record)

Each record in `output/recipes.json` gains these new fields:

```json
{
  "id": "spicy-garlic-chicken-with-avocado",
  "url": "https://...",
  "...existing fields unchanged...": "...",

  "ingredient_flavordb_ids": [42, 17, null],

  "flavor_profile_quantified": {
    "meaty": 0.251,
    "fatty": 0.210,
    "creamy": 0.105,
    "umami": 0.083,
    "buttery": 0.062,
    "pungent": 0.031
  },
  "top_5_flavors": ["meaty", "fatty", "creamy", "umami", "buttery"],
  "flavor_intensity_score": null,
  "molecules_represented": 847,

  "data_quality": {
    "unit_conversion_success_rate": 0.833,
    "ingredient_flavordb_match_rate": 0.667,
    "unmapped_ingredients": ["fancy truffle oil"],
    "zero_gram_ingredients": []
  }
}
```

> **IMPORTANT:** The existing `flavor_profile` field (list of string labels from regex in `processor.py`) is **preserved unchanged**. `flavor_profile_quantified` is additive — it does not replace the existing field.

---

## Requirements Additions

```
# Add to requirements.txt
rapidfuzz>=3.0.0
```

No other new dependencies. Redis, diskcache, and SQLite are explicitly out of scope for v1.
FlavorDB cache = plain JSON file loaded into memory at startup.

---

## Open Blockers (Resolve Before Round 1 Code)

> **CAUTION: Do not write application code until these are answered.**

1. **FlavorDB2 entity listing endpoint**: Does `GET /entities_json` (no id param) return the full entity list? Or is there a separate listing endpoint? Must be verified empirically in Phase 0.

2. **Flavor tag vocabulary scope**: The FlavorDB2 `flavor_profile` field is freeform. How many distinct raw tags appear across all ~936 entities? The developer-refactor agent must sample 50+ entities and report the full raw tag vocabulary before Phase 3 (tag_canon.py) can be completed correctly.

3. **Fuzzy match metric and threshold**: Recommendation: `rapidfuzz.process.extractOne(query, choices, scorer=WRatio, score_cutoff=80)`. Accept or modify before Phase 1 entity_index.py is implemented.

4. **FlavorDB match rate policy**: Should records below 75% match rate have `flavor_profile_quantified` set to `null` (excluded from quantified output) or included with a data_quality flag? **Recommendation: include with flag, never exclude — the base scraping data is still valid regardless of FlavorDB coverage.**

---

## Verification Plan

### Automated (developer-test runs these after Phase 6)

```bash
python -m pytest tests/ -v
python flavor_aggregator.py          # built-in self-check with fixture data
python -m flavordb.flavor_module --entity-id 42   # live API smoke test
```

### Manual Smoke Test (after Phase 5)

```bash
# 1. Single-recipe run through full pipeline
python main.py --url https://www.bbcgoodfood.com/recipes/spaghetti-bolognese-recipe --limit 1

# 2. Inspect flavor fields
python -c "
import json
r = json.load(open('output/recipes.json'))[0]
fq = r.get('flavor_profile_quantified', {})
print('Top 5:', r.get('top_5_flavors'))
print('Sum:', round(sum(fq.values()), 4) if fq else 'null')
print('Quality:', r.get('data_quality'))
"

# 3. Confirm --skip-flavordb works
python main.py --url https://www.bbcgoodfood.com/recipes/spaghetti-bolognese-recipe \
               --limit 1 --skip-flavordb

# 4. Confirm --flavor-only works on existing output
python main.py --flavor-only
```

### Success Criteria (from PRD §10, adapted to this repo)

- [ ] `flavor_profile_quantified` values sum to `1.0 ± 0.001` for all matched recipes
- [ ] No `ZeroDivisionError` on any record in a 20-recipe test run
- [ ] `--skip-flavordb` flag produces valid `recipes.json` with `flavor_profile_quantified: null`
- [ ] `--flavor-only` flag enriches existing `output/recipes.json` without re-scraping
- [ ] ≥85% of ingredients in test set successfully gram-converted (existing `gram_converter.py` baseline)
- [ ] ≥75% of ingredients matched to FlavorDB entities (target; alert if below)
- [ ] All 11 unit tests pass (`pytest tests/ -v`)

---

## Notes for Claude Code CLI Execution

This document is structured to feed directly into the orchestrator agent (`orchestrator.md`) session. Suggested invocation:

```
claude --agent orchestrator
> Use PRD/ARCHITECTURE_flavor_quantification.md as your task backlog.
> Start with Phase 0 (endpoint verification) dispatched to developer-core.
> Do not write any application code until Phase 0 report is complete.
> After each developer round, dispatch the full reviewer council in parallel.
> Treat any issue flagged by >=3 reviewers as a blocker.
```

The orchestrator's conflict detection rule applies: Rounds 2a and 2b are the only safe parallel round. All others are sequential.
