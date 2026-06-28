"""
Flavor enrichment pipeline (Phases 2+, 3, 4).

Stage layout (called from main.py):

    Stage 1  load_recipedb_jsonl()      → raw records, ingredient_names extracted,
                                          NO gram conversion yet.
    Stage 2  crop_checker.filter_strict() → drop recipes with unmatched ingredients
                                           (called from main.py, not here).
    Stage 2+ prewarm_flavordb_cache()   → fetch FlavorDB entries for every ingredient
                                          term in Crop/Protein/Pantry CSVs; builds cache.
    Stage 3  convert_to_grams()         → gram conversion on surviving recipes only.
    Stage 4  enrich_all()               → weighted flavor profiles using pre-warmed cache.
"""
import json
import logging
import re
from pathlib import Path

from flavordb.entity_index import load_index, find_entity
from flavordb.flavor_module import compute_flavor_composition
from flavor_aggregator import compute_recipe_flavor_profile
from crop_checker import build_basket, in_basket, load_crop_terms, load_protein_terms, _load_pantry

log = logging.getLogger(__name__)

CACHE_PATH = "output/flavordb_cache.json"
INDEX_PATH = "Main/flavordb/entity_index.json"

_SLUG_RE = re.compile(r"[^a-z0-9]+")

# ── cache helpers ─────────────────────────────────────────────────────────────

def load_cache(path: str = CACHE_PATH) -> dict:
    p = Path(path)
    if p.exists():
        return json.loads(p.read_text())
    return {}


def save_cache(cache: dict, path: str = CACHE_PATH) -> None:
    Path(path).parent.mkdir(exist_ok=True)
    Path(path).write_text(json.dumps(cache, indent=2))


# ── Stage 1 — RecipeDB loader (no gram conversion) ───────────────────────────

def load_recipedb_jsonl(path: str) -> list[dict]:
    """
    Stage 1 entry point.

    Load RecipeDB JSONL and convert to internal record format.
    Extracts ingredient_names from the structured ingredient_name field.
    Does NOT run gram conversion — that is deferred to Stage 3 (convert_to_grams)
    so that only crop-filtered recipes pay the conversion cost.
    """
    records = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            ings_raw: list[dict] = raw.get("Ingredients") or []

            phrases = [i.get("ingredient_Phrase", "") for i in ings_raw]
            names = [i.get("ingredient_name", "") for i in ings_raw]

            rid = str(raw.get("Recipe_id", ""))
            title = raw.get("Recipe_title", "")
            slug = _SLUG_RE.sub("-", title.lower()).strip("-") or rid

            dietary = []
            for flag in ("vegan", "pescetarian", "ovo_vegetarian", "lacto_vegetarian", "ovo_lacto_vegetarian"):
                val = raw.get(flag)
                try:
                    if float(val or 0) > 0:
                        dietary.append(flag.replace("_", "-"))
                except (ValueError, TypeError):
                    pass

            processes_raw = raw.get("Processes") or ""
            processes = [p.strip() for p in processes_raw.split(";") if p.strip()] if processes_raw else []

            records.append({
                "id": slug,
                "url": raw.get("url", ""),
                "title": title,
                "meal_type": None,
                "recipe_category": None,
                "cuisine_type": [raw["Region"]] if raw.get("Region") else [],
                "keywords": [],
                "dietary": dietary,
                "ingredients": phrases,
                # ingredient_names populated from structured field; gram conversion deferred.
                "ingredient_names": names,
                "ingredient_grams": [],   # filled by Stage 3
                "equipment": [],
                "cooking_processes": processes,
                "flavor_profile": [],
                "aroma_profile": [],
                "servings": raw.get("Servings"),
                "prep_time_min": raw.get("prep_time"),
                "cook_time_min": raw.get("cook_time"),
                "total_time_min": raw.get("total_time"),
                "source": "recipedb",
                "recipedb_id": rid,
                "energy_kcal": raw.get("Energy(kcal)"),
            })
    log.info("Stage 1: loaded %d raw records from %s", len(records), path)
    return records


# ── Stage 2+ — Pre-warm FlavorDB cache from CSV allowlists ───────────────────

def prewarm_flavordb_cache(
    crop_csv: str | None = "Sources/Crop.csv",
    protein_csv: str | None = "Sources/Protein.csv",
    entity_index_path: str = INDEX_PATH,
) -> dict:
    """
    Stage 2+ entry point.

    Collect every ingredient term from Crop.csv, Protein.csv, and Pantry.csv,
    then fetch their FlavorDB entries into the shared cache.

    This runs concurrently with Stage 2 (the filter) — it has no dependency on
    the filtered record list. The resulting cache is used by Stage 4 (enrich_all).

    Returns the populated cache dict (also saved to CACHE_PATH).
    """
    # Collect all unique terms from all three sources
    all_terms: set[str] = set()

    if crop_csv and Path(crop_csv).exists():
        all_terms |= load_crop_terms(crop_csv)
        log.info("Stage 2+: loaded %d crop terms from %s", len(all_terms), crop_csv)

    protein_count = 0
    if protein_csv and Path(protein_csv).exists():
        protein_terms = load_protein_terms(protein_csv)
        protein_count = len(protein_terms)
        all_terms |= protein_terms
        log.info("Stage 2+: loaded %d protein terms from %s", protein_count, protein_csv)

    pantry_terms = _load_pantry()
    all_terms |= pantry_terms
    log.info(
        "Stage 2+: total allowlist terms to pre-warm: %d (%d crop + %d protein + %d pantry)",
        len(all_terms), len(all_terms) - protein_count - len(pantry_terms), protein_count, len(pantry_terms),
    )

    entity_index = load_index(entity_index_path)
    if not entity_index:
        log.warning(
            "FlavorDB entity index not found at %s — skipping pre-warm. "
            "Run: python Main/flavordb/build_index.py",
            entity_index_path,
        )
        return {}

    cache = load_cache()
    pre_existing = len(cache)
    fetched = 0

    for term in sorted(all_terms):
        entity_id = find_entity(term, entity_index)
        if entity_id is None:
            continue
        key = str(entity_id)
        if key not in cache:
            comp = compute_flavor_composition(entity_id, cache)
            if comp:
                fetched += 1

    save_cache(cache)
    log.info(
        "Stage 2+: FlavorDB cache pre-warm complete. "
        "Pre-existing: %d, newly fetched: %d, total: %d entries → %s",
        pre_existing, fetched, len(cache), CACHE_PATH,
    )
    return cache


# ── Stage 3 — Gram conversion (batch, post-filter) ───────────────────────────

def convert_to_grams(records: list[dict]) -> list[dict]:
    """
    Stage 3 entry point.

    Run gram conversion on every filtered record. Operates on the ingredient
    phrase strings stored in record["ingredients"].

    Every recipe that reaches this stage undergoes conversion — there are no
    exceptions. If a phrase cannot be converted, the raw phrase string is stored
    as a fallback (consistent with prior behaviour) and a warning is logged.

    Returns the same list (in-place mutation of ingredient_grams).
    """
    from gram_converter import ingredient_to_grams

    total_phrases = 0
    total_failed = 0

    for record in records:
        phrases = record.get("ingredients") or []
        grams = []
        for phrase in phrases:
            total_phrases += 1
            g = ingredient_to_grams(phrase)
            if g is not None:
                grams.append(g)
            else:
                total_failed += 1
                log.debug("Gram conversion failed for phrase: %r", phrase)
                grams.append(phrase)  # fallback: store raw string
        record["ingredient_grams"] = grams

    success_rate = (total_phrases - total_failed) / total_phrases if total_phrases else 0.0
    log.info(
        "Stage 3: gram conversion complete. %d / %d phrases converted (%.1f%%).",
        total_phrases - total_failed, total_phrases, success_rate * 100,
    )
    return records


# ── Stage 4 — per-record FlavorDB enrichment ─────────────────────────────────

def enrich_record(record: dict, entity_index: dict, cache: dict, basket=None) -> dict:
    """
    Enrich one post-conversion record with FlavorDB flavor fields (in-place).
    Expects record["ingredient_names"] and record["ingredient_grams"] to exist.
    basket: tuple from build_basket(); non-basket ingredients are skipped.
    """
    names: list[str] = record.get("ingredient_names") or []
    grams_raw: list = record.get("ingredient_grams") or []

    ing_list = []
    flavordb_ids = []

    for i, name in enumerate(names):
        raw_g = grams_raw[i] if i < len(grams_raw) else None
        grams = raw_g if isinstance(raw_g, (int, float)) else None

        # Skip FlavorDB fetch for non-basket ingredients when basket provided
        if basket is not None and not in_basket(name, basket):
            entity_id = None
            flavor_comp = {}
        else:
            entity_id = find_entity(name, entity_index)
            flavor_comp = compute_flavor_composition(entity_id, cache) if entity_id is not None else {}

        flavordb_ids.append(entity_id)
        ing_list.append({"name": name, "grams": grams, "flavor_composition": flavor_comp})

    result = compute_recipe_flavor_profile(ing_list)

    # Tag unmapped ingredients with reason for diagnostics
    if basket is not None:
        result["data_quality"]["unmapped_ingredients"] = [
            {"name": n, "reason": "not in list" if not in_basket(n, basket) else "flavordb miss"}
            for n in result["data_quality"]["unmapped_ingredients"]
        ]

    record["ingredient_flavordb_ids"] = flavordb_ids
    record["flavor_profile_quantified"] = result["flavor_profile_quantified"]
    record["top_5_flavors"] = result["top_5_flavors"]
    record["flavor_intensity_score"] = None  # ponytail: formula TBD (PRD §11)
    record["molecules_represented"] = result["molecules_represented"]
    record.setdefault("data_quality", {}).update(result["data_quality"])
    return record


# ── Stage 4 — batch entry point ───────────────────────────────────────────────

def enrich_all(
    records: list[dict],
    skip_flavordb: bool = False,
    entity_index_path: str = INDEX_PATH,
    cache: dict | None = None,
) -> list[dict]:
    """
    Stage 4 entry point. Enriches all records in-place with FlavorDB flavor data.

    If cache is provided (pre-warmed by Stage 2+), uses it directly.
    Otherwise loads from CACHE_PATH. Saves cache on completion.

    If skip_flavordb=True: sets all flavor fields to null (useful for dry runs).
    """
    if skip_flavordb:
        for r in records:
            r["flavor_profile_quantified"] = None
            r["top_5_flavors"] = []
            r["flavor_intensity_score"] = None
            r["molecules_represented"] = 0
        log.info("--skip-flavordb: flavor fields set to null for %d records", len(records))
        return records

    entity_index = load_index(entity_index_path)
    if not entity_index:
        log.warning(
            "FlavorDB entity index not found at %s. "
            "Run: python Main/flavordb/build_index.py",
            entity_index_path,
        )

    # Build basket from Crop/Protein CSVs for selective enrichment
    basket = None
    try:
        basket = build_basket("Sources/Crop.csv", "Sources/Protein.csv")
        log.info("Stage 4: basket loaded: %d terms (crop+protein+pantry)", len(basket[0]))
    except FileNotFoundError as e:
        log.warning("Basket CSVs not found (%s) — enriching all ingredients", e)

    # Use pre-warmed cache if provided, else load from disk
    if cache is None:
        cache = load_cache()
    log.info("Stage 4: FlavorDB cache: %d entities loaded", len(cache))

    for i, record in enumerate(records):
        title = record.get("title", record.get("Recipe_title", "?"))
        log.info("[%d/%d] enriching: %s", i + 1, len(records), title)
        enrich_record(record, entity_index, cache, basket=basket)

    save_cache(cache)
    log.info("Stage 4: FlavorDB cache saved (%d entries)", len(cache))
    return records
