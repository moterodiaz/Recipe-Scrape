"""
Per-ingredient flavor composition calculator.
Algorithm from ARCHITECTURE_flavor_quantification.md Phase 2.
"""
from flavordb.client import fetch_entity
from flavordb.tag_canon import canonicalize


def compute_flavor_composition(entity_id: int | None, cache: dict) -> dict[str, float]:
    """
    Return normalized flavor composition dict for one ingredient entity.
    Denominator = total tag occurrences (not molecule count) — one molecule
    may carry multiple tags, so sum(counts) > molecule count.
    Returns {} on any failure (no crash).
    """
    if entity_id is None:
        return {}

    data = fetch_entity(entity_id, cache)
    if not data:
        return {}

    molecules = data.get("molecules") or []
    if not molecules:
        return {}

    tag_counts: dict[str, int] = {}
    for mol in molecules:
        fp = mol.get("flavor_profile") or ""
        if not fp:
            continue
        for raw_tag in fp.split("@"):
            tag = canonicalize(raw_tag.strip())
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

    total = sum(tag_counts.values())
    if total == 0:
        return {}

    return {tag: count / total for tag, count in tag_counts.items()}


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--entity-id", type=int, required=True)
    args = parser.parse_args()
    cache: dict = {}
    comp = compute_flavor_composition(args.entity_id, cache)
    if not comp:
        print("No composition returned (empty entity or fetch failed)")
    else:
        total = sum(comp.values())
        print(f"Tags: {len(comp)}, sum={total:.4f} (must be ~1.0)")
        for tag, pct in sorted(comp.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"  {tag:20s} {pct:.3f}")
        assert abs(total - 1.0) < 0.001, f"sum != 1.0 (got {total})"
        print("PASS")
