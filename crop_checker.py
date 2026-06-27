"""Phase 3 — cross-check recipe ingredient_names against growable crop list."""

import argparse
import csv
import json
import re
from pathlib import Path

_DISPENSABLE_ROLE_PHRASES = frozenset((
    "to serve", "to garnish", "for garnish", "as garnish",
    "to finish", "for finishing", "for serving", "to taste",
    "optional", "if desired", "for decoration", "to decorate",
))

_DISPENSABLE_NAMES = frozenset(("salt", "pepper", "black pepper", "sea salt", "water", "oil"))

# Always-stocked station pantry — counts as matched regardless of crop/protein CSVs
_PANTRY_NAMES = frozenset(("flour", "milk", "powdered milk", "powdered cheese"))

# Growable crops absent from or only partially named in Crop.csv:
#   onion  — C24 is "green onion" only; plain onion is the same genus
#   garlic — not in CSV; allium, trivially growable
#   ginger — not in CSV; rhizome crop
#   coriander — same plant as cilantro (C30); UK/recipe name differs
#   thyme, parsley — herbs, not yet in CSV
#   lime, lemon — citrus; not in CSV but referenced constantly
#   pea — 3-char token filtered by len>=4 guard; C7/C38 cover pea varieties
_COMMON_CROPS = frozenset((
    "onion", "garlic", "ginger", "coriander",
    "thyme", "parsley", "lime", "lemon", "pea",
))

# Generic adjectives embedded in multi-word crop names that collide with culinary terms.
# "caster sugar" via C7 "dwarf grey sugar pea", "extra virgin olive oil" via C10, etc.
_CROP_TOKEN_STOPWORDS = frozenset({
    "dwarf", "extra", "fresh", "sweet", "golden", "hybrid",
    "mini", "early", "hull", "sugar", "seed", "yellow",
})


def _parse_crop_name(raw: str) -> list[str]:
    """Normalize one CSV Name entry into base terms."""
    terms = []
    for part in re.split(r"\s*/\s*", raw):
        part = part.strip()
        if not part or re.match(r"^\d", part):  # drop numeric cultivar codes
            continue
        part = re.sub(r",\s*'[^']*'.*$", "", part)   # "Basil, 'Dark Opal'" → "Basil"
        parens = re.findall(r"\(([^)]+)\)", part)
        part = re.sub(r"\([^)]+\)", "", part)
        part = re.sub(r"['\"]", "", part).strip(" ,-")
        if part:
            terms.append(part.lower())
        for p in parens:
            p = p.strip()
            if p and not re.match(r"^[A-Z][a-z]+ [a-z]+$", p):  # skip Latin binomials
                terms.append(p.lower())
    return terms


def _is_dispensable(raw: str, name: str) -> bool:
    """Check if ingredient is non-essential (garnish, condiment, seasoning)."""
    raw_lower = raw.lower()
    # Tier 1: explicit role phrases in raw ingredient string
    if any(phrase in raw_lower for phrase in _DISPENSABLE_ROLE_PHRASES):
        return True
    name_lower = name.lower()
    # Tier 2: exact-match condiments
    if name_lower in _DISPENSABLE_NAMES:
        return True
    # Tier 3: token-level for salt/oil variants ("fine sea salt", "olive oil", "rapeseed oil")
    name_toks = set(name_lower.split())
    if "salt" in name_toks or "oil" in name_toks:
        return True
    return False


def load_crop_terms(csv_path: str) -> set[str]:
    """Return normalized crop name terms from the Name column (index 1)."""
    exact: set[str] = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # descriptive preamble row 1
        next(reader)  # descriptive preamble row 2
        next(reader)  # column-header row (ID,Name,Category,Package 1,Package 2,Package 3)
        for row in reader:
            if len(row) < 2 or not row[0].startswith("C"):
                continue
            for term in _parse_crop_name(row[1]):
                exact.add(term)
    return exact


def load_protein_terms(csv_path: str) -> set[str]:
    """Return normalized protein name terms from Protein.csv Name column (index 1)."""
    exact: set[str] = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # column-header row
        for row in reader:
            if len(row) < 2 or not row[0].startswith("PR"):
                continue
            for term in _parse_crop_name(row[1]):
                exact.add(term)
    return exact


def _match(name: str, exact: set[str], tokens: set[str]) -> bool:
    name_toks = set(name.split())
    # pantry: word-token match so "bread flour" → matches "flour" but "buttermilk" ≠ "milk"
    if any(all(t in name_toks for t in p.split()) for p in _PANTRY_NAMES):
        return True
    # common crops: any word in ingredient name starts with a common crop term
    if any(ntok.startswith(ctok) for ntok in name_toks for ctok in _COMMON_CROPS):
        return True
    if name in exact:
        return True
    # Exact token match
    if any(tok in tokens for tok in name_toks if len(tok) >= 4):
        return True
    # Prefix match — ingredient word starts with crop term handles plurals
    # e.g. "potatoes" startswith "potato", "carrots" startswith "carrot"
    return any(
        ntok.startswith(ctok)
        for ntok in name_toks if len(ntok) >= 4
        for ctok in tokens if len(ctok) >= 4
    )


def annotate_crop_coverage(
    records: list[dict],
    crop_terms: set[str],
    protein_terms: set[str] | None = None,
    min_coverage: float = 0.0,
) -> list[dict]:
    # ponytail: covered_terms built once, O(1) per-ingredient lookup via set membership
    covered_terms = crop_terms | (protein_terms or set())
    crop_tokens = {
        tok for term in covered_terms
        for tok in term.split()
        if len(tok) >= 4 and tok not in _CROP_TOKEN_STOPWORDS
    }
    result = []
    for r in records:
        names = r.get("ingredient_names") or []
        raw_ingredients = r.get("ingredients") or []

        # Zip raw + cleaned; filter out dispensable ingredients (garnish, condiments, etc)
        pairs = list(zip(raw_ingredients, names))
        essential = [(raw, n) for raw, n in pairs if not _is_dispensable(raw, n)]
        essential_names = [n for _, n in essential]
        dispensable_names = [n for raw, n in pairs if _is_dispensable(raw, n)]

        matched = [n for n in essential_names if _match(n, covered_terms, crop_tokens)]
        total = len(essential_names)

        r["crops_matched"] = matched
        r["crops_missing"] = [n for n in essential_names if n not in matched]
        r["crop_coverage"] = round(len(matched) / total, 2) if total else 0.0
        r["dispensable_skipped"] = dispensable_names

        if r["crop_coverage"] >= min_coverage:
            result.append(r)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Crop cross-check (standalone)")
    parser.add_argument("--recipes", default="output/recipes.json")
    parser.add_argument("--crop-csv", required=True)
    parser.add_argument("--protein-csv", default=None, help="Path to Protein.csv (optional)")
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--out", default="output/recipes_filtered.json")
    args = parser.parse_args()

    crop_terms = load_crop_terms(args.crop_csv)

    # Spot-checks against actual Crop.csv entries (C1, C15, C17)
    assert "potato" in crop_terms, "potato missing from crop terms"
    assert "quinoa" in crop_terms, "quinoa missing from crop terms"
    assert "lemon basil" in crop_terms, "lemon basil missing from crop terms"

    # Self-check: dispensable logic
    assert _is_dispensable("50g parmesan, to serve", "parmesan"), "parmesan with 'to serve' should be dispensable"
    assert not _is_dispensable("500g parmesan", "parmesan"), "parmesan without role phrase should not be dispensable"
    assert _is_dispensable("1 tsp salt", "salt"), "salt should always be dispensable"
    assert _is_dispensable("2 tbsp butter, to garnish", "butter"), "butter with role phrase should be dispensable"
    assert _is_dispensable("2 tsp fine sea salt", "fine sea salt"), "fine sea salt should be dispensable"
    assert _is_dispensable("1 tsp flaky sea salt", "flaky sea salt"), "flaky sea salt should be dispensable"
    assert _is_dispensable("5 tbsp olive oil", "olive oil"), "olive oil should be dispensable"
    assert _is_dispensable("2 tbsp rapeseed oil", "rapeseed oil"), "rapeseed oil should be dispensable"
    assert not _is_dispensable("200g water chestnuts", "water chestnuts"), "water chestnuts should not be dispensable"

    protein_terms: set[str] = set()
    if args.protein_csv:
        protein_terms = load_protein_terms(args.protein_csv)
        assert any("tilapia" in t for t in protein_terms), "tilapia missing from protein terms"
        assert any("chicken" in t for t in protein_terms), "chicken missing from protein terms"

    # Self-check: pantry items always match
    _pantry_recs = [{"ingredients": ["200g flour", "300ml milk"], "ingredient_names": ["flour", "milk"]}]
    _pantry_out = annotate_crop_coverage(_pantry_recs, set(), set())
    assert _pantry_out[0]["crop_coverage"] == 1.0, "pantry items should auto-match"

    records = json.loads(Path(args.recipes).read_text())
    kept = annotate_crop_coverage(records, crop_terms, protein_terms, args.min_coverage)
    Path(args.out).write_text(json.dumps(kept, indent=2))
    print(f"Kept {len(kept)}/{len(records)} recipes (min_coverage={args.min_coverage}) → {args.out}")
    print(f"Crop terms: {len(crop_terms)}  Protein terms: {len(protein_terms)}")
    print("Self-check passed.")
