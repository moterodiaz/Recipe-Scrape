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
    # Tier 2: universal condiments (only salt/pepper/water/oil, not cheese/butter)
    if name.lower() in _DISPENSABLE_NAMES:
        return True
    return False


def load_crop_terms(csv_path: str) -> set[str]:
    """Return normalized crop name terms from the Name column (index 1)."""
    exact: set[str] = set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # group-header row
        next(reader)  # column-header row
        for row in reader:
            if len(row) < 2 or not row[0].startswith("C"):
                continue
            for term in _parse_crop_name(row[1]):
                exact.add(term)
    return exact


def _match(name: str, exact: set[str], tokens: set[str]) -> bool:
    if name in exact:
        return True
    return any(tok in tokens for tok in name.split() if len(tok) >= 4)


def annotate_crop_coverage(
    records: list[dict], crop_terms: set[str], min_coverage: float = 0.0
) -> list[dict]:
    # ponytail: crop_tokens built once, O(1) per-ingredient lookup via set membership
    crop_tokens = {tok for term in crop_terms for tok in term.split() if len(tok) >= 4}
    result = []
    for r in records:
        names = r.get("ingredient_names") or []
        raw_ingredients = r.get("ingredients") or []

        # Zip raw + cleaned; filter out dispensable ingredients (garnish, condiments, etc)
        pairs = list(zip(raw_ingredients, names))
        essential = [(raw, n) for raw, n in pairs if not _is_dispensable(raw, n)]
        essential_names = [n for _, n in essential]
        dispensable_names = [n for raw, n in pairs if _is_dispensable(raw, n)]

        matched = [n for n in essential_names if _match(n, crop_terms, crop_tokens)]
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
    parser.add_argument("--min-coverage", type=float, default=0.0)
    parser.add_argument("--out", default="output/recipes_filtered.json")
    args = parser.parse_args()

    crop_terms = load_crop_terms(args.crop_csv)

    assert "basil" in crop_terms, "basil missing from crop terms"
    assert "spinach" in crop_terms, "spinach missing from crop terms"
    assert "carrot" in crop_terms, "carrot missing from crop terms"

    # Self-check: dispensable logic
    assert _is_dispensable("50g parmesan, to serve", "parmesan"), "parmesan with 'to serve' should be dispensable"
    assert not _is_dispensable("500g parmesan", "parmesan"), "parmesan without role phrase should not be dispensable"
    assert _is_dispensable("1 tsp salt", "salt"), "salt should always be dispensable"
    assert _is_dispensable("2 tbsp butter, to garnish", "butter"), "butter with role phrase should be dispensable"

    records = json.loads(Path(args.recipes).read_text())
    kept = annotate_crop_coverage(records, crop_terms, args.min_coverage)
    Path(args.out).write_text(json.dumps(kept, indent=2))
    print(f"Kept {len(kept)}/{len(records)} recipes (min_coverage={args.min_coverage}) → {args.out}")
    print(f"Crop terms loaded: {len(crop_terms)}")
    print("Self-check passed.")
