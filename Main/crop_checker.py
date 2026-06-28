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

_DISPENSABLE_NAMES = frozenset(("salt", "pepper", "black pepper", "sea salt", "water"))

# Always-stocked station pantry — loaded from Sources/Pantry.csv; fallback to 4 hardcoded names
_PANTRY_CSV = Path(__file__).parent.parent / "Sources" / "Pantry.csv"
_PANTRY_FALLBACK = frozenset(("flour", "milk", "powdered milk", "powdered cheese"))


def _load_pantry() -> frozenset:
    if not _PANTRY_CSV.exists():
        return _PANTRY_FALLBACK
    with open(_PANTRY_CSV, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader)  # header row
        return frozenset(row[0].strip().lower() for row in reader if row and row[0].strip())


_PANTRY_NAMES = _load_pantry()


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
            normalized = part.lower()
            terms.append(normalized)
            words = normalized.split()
            if len(words) > 1:
                terms.append(words[-1])  # cultivar species name is always last word
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


def _match(name: str, exact: set[str], single_terms: set[str], multi_terms: list[str]) -> bool:
    name_toks = set(name.split())
    # pantry: word-token match so "bread flour" → matches "flour" but "buttermilk" ≠ "milk"
    if any(all(t in name_toks for t in p.split()) for p in _PANTRY_NAMES):
        return True
    # exact full-term match
    if name in exact:
        return True
    # single-word crop terms: prefix match handles plurals (lentils→lentil, potatoes→potato)
    if any(
        ntok.startswith(ctok)
        for ntok in name_toks
        for ctok in single_terms
        if len(ctok) >= 4
    ):
        return True
    # multi-word crop terms: every significant token must prefix-match some ingredient token.
    # Requires >= 2 significant tokens so short/generic terms don't match on one common word.
    for mterm in multi_terms:
        sig = [t for t in mterm.split() if len(t) >= 4]
        if len(sig) < 2:
            continue
        if all(any(ntok.startswith(mtok) for ntok in name_toks) for mtok in sig):
            return True
    return False


def build_basket(
    crop_csv: str,
    protein_csv: str | None = None,
) -> tuple[set[str], set[str], list[str]]:
    """Build the (covered, single_terms, multi_terms) tuple used by in_basket / _match."""
    covered = load_crop_terms(crop_csv) | (load_protein_terms(protein_csv) if protein_csv else set())
    return covered, {t for t in covered if " " not in t}, [t for t in covered if " " in t]


def in_basket(name: str, basket: tuple[set[str], set[str], list[str]]) -> bool:
    """Return True if ingredient name matches any basket term (crop/protein/pantry)."""
    return _match(name, *basket)


def filter_strict(
    records: list[dict],
    basket: tuple[set[str], set[str], list[str]],
    min_coverage: float = 1.0,
) -> list[dict]:
    """
    Hard filter: drop any recipe that has essential ingredients not covered by
    the basket (Crop + Protein + Pantry).

    Unlike annotate_crop_coverage (which only annotates), this is a pre-processing
    gate — designed to run BEFORE gram conversion and FlavorDB enrichment so that
    no unmatched recipes waste time in those stages.

    Each surviving record gets crops_matched, crops_missing, crop_coverage, and
    dispensable_skipped fields written in-place (same as annotate_crop_coverage).

    Args:
        records:      list of dicts each with ingredient_names + ingredients fields.
        basket:       tuple from build_basket(); (covered_terms, single_terms, multi_terms).
        min_coverage: fraction of essential ingredients that must match (default 1.0 = strict).
                      Pass a lower value (e.g. 0.8) to allow partial matches through.

    Returns:
        Filtered list — only recipes that meet the min_coverage threshold.
    """
    covered_terms, single_terms, multi_terms = basket
    result = []
    for r in records:
        names = r.get("ingredient_names") or []
        raw_ingredients = r.get("ingredients") or []

        pairs = list(zip(raw_ingredients, names))
        essential = [(raw, n) for raw, n in pairs if not _is_dispensable(raw, n)]
        essential_names = [n for _, n in essential]
        dispensable_names = [n for raw, n in pairs if _is_dispensable(raw, n)]

        matched = [n for n in essential_names if _match(n, covered_terms, single_terms, multi_terms)]
        total = len(essential_names)

        coverage = round(len(matched) / total, 2) if total else 0.0

        r["crops_matched"] = matched
        r["crops_missing"] = [n for n in essential_names if n not in matched]
        r["crop_coverage"] = coverage
        r["dispensable_skipped"] = dispensable_names

        if coverage >= min_coverage:
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
    _pantry_out = filter_strict(_pantry_recs, (set(), set(), []), min_coverage=0.0)
    assert _pantry_out[0]["crop_coverage"] == 1.0, "pantry items should auto-match"

    # Self-check: pantry CSV loaded (fallback or file)
    assert len(_PANTRY_NAMES) >= 4, f"expected >=4 pantry items, got {len(_PANTRY_NAMES)}"

    # Self-check: build_basket / in_basket
    if args.protein_csv:
        _basket = build_basket(args.crop_csv, args.protein_csv)
        assert in_basket("bread flour", _basket), "bread flour should match pantry 'flour'"
        assert not in_basket("buttermilk", _basket), "buttermilk should not match basket"
        assert in_basket("chicken", _basket), "chicken should match protein basket"
        assert in_basket("potato", _basket), "potato should match crop basket"

    records = json.loads(Path(args.recipes).read_text())
    covered = crop_terms | protein_terms
    _basket = (covered, {t for t in covered if " " not in t}, [t for t in covered if " " in t])
    kept = filter_strict(records, _basket, min_coverage=args.min_coverage)
    Path(args.out).write_text(json.dumps(kept, indent=2))
    print(f"Kept {len(kept)}/{len(records)} recipes (min_coverage={args.min_coverage}) → {args.out}")
    print(f"Crop terms: {len(crop_terms)}  Protein terms: {len(protein_terms)}")
    print("Self-check passed.")
