"""
FlavorDB2 entity name → entity_id index with fuzzy matching.
Entity index is a JSON file: {"ingredient name": entity_id_int, ...}
"""
import json
from pathlib import Path

try:
    from rapidfuzz import process as rfp, fuzz
    _HAS_RAPIDFUZZ = True
except ImportError:
    _HAS_RAPIDFUZZ = False

_INDEX_CACHE: dict[str, dict[str, int]] = {}  # path → index


def load_index(path: str) -> dict[str, int]:
    """Load name→entity_id mapping from JSON. Returns {} if file missing."""
    if path in _INDEX_CACHE:
        return _INDEX_CACHE[path]
    p = Path(path)
    if not p.exists():
        return {}
    index = json.loads(p.read_text())
    _INDEX_CACHE[path] = index
    return index


def find_entity(name: str, index: dict[str, int]) -> int | None:
    """
    Return entity_id for ingredient name.
    Exact match first; rapidfuzz WRatio fallback (score_cutoff=80).
    Returns None if no match.
    """
    if not index:
        return None
    norm = name.lower().strip()
    # exact
    if norm in index:
        return index[norm]
    # rapidfuzz fallback
    if _HAS_RAPIDFUZZ:
        result = rfp.extractOne(norm, index.keys(), scorer=fuzz.WRatio, score_cutoff=80)
        if result:
            return index[result[0]]
    # substring fallback
    for key in index:
        if norm in key or key in norm:
            return index[key]
    return None


if __name__ == "__main__":
    import sys
    idx = load_index(sys.argv[1] if len(sys.argv) > 1 else "Main/flavordb/entity_index.json")
    if not idx:
        print("Index empty or not found")
        sys.exit(1)
    test_names = ["garlic", "chicken", "olive oil", "honey", "tomato"]
    for n in test_names:
        eid = find_entity(n, idx)
        print(f"  {n!r:20s} → entity_id={eid}")
