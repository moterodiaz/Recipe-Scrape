"""
Recipe-level weighted flavor aggregation.
Algorithm from ARCHITECTURE_flavor_quantification.md Phase 4.
"""

def compute_recipe_flavor_profile(
    ingredients: list[dict],
    # each: {"name": str, "grams": float | None, "flavor_composition": dict | None}
) -> dict:
    """
    Returns:
    {
        "flavor_profile_quantified": {"tag": float, ...},  # sums to 1.0 or {}
        "top_5_flavors": [str, ...],
        "flavor_intensity_score": None,           # formula TBD (PRD §11)
        "molecules_represented": int,
        "data_quality": {
            "unit_conversion_success_rate": float,
            "ingredient_flavordb_match_rate": float,
            "unmapped_ingredients": [str],
            "zero_gram_ingredients": [str],
        }
    }
    """
    n = len(ingredients)
    zero_gram_names: list[str] = []
    unmapped_names: list[str] = []
    grams_valid = 0
    flavor_matched = 0

    # Step 1: partition ingredients
    included = []
    for ing in ingredients:
        g = ing.get("grams")
        fc = ing.get("flavor_composition")
        name = ing.get("name", "")

        has_grams = isinstance(g, (int, float)) and g >= 0.1
        has_flavor = bool(fc)  # non-empty dict

        if has_grams:
            grams_valid += 1
        else:
            zero_gram_names.append(name)
            continue  # exclude from mass total AND weighted sum

        if has_flavor:
            flavor_matched += 1
            included.append(ing)
        else:
            unmapped_names.append(name)
            # counted in grams_valid but excluded from weighted sum

    # Steps 2–5: weighted aggregation
    total_grams = sum(ing["grams"] for ing in included)
    recipe_flavor: dict[str, float] = {}

    if total_grams > 0:
        for ing in included:
            weight = ing["grams"] / total_grams
            for tag, pct in ing["flavor_composition"].items():
                recipe_flavor[tag] = recipe_flavor.get(tag, 0.0) + weight * pct

    # Steps 6–7: normalize
    total_flavor_sum = sum(recipe_flavor.values())
    if total_flavor_sum == 0:
        quantified: dict = {}
    else:
        quantified = {tag: v / total_flavor_sum for tag, v in recipe_flavor.items()}

    top5 = [t for t, _ in sorted(quantified.items(), key=lambda x: x[1], reverse=True)[:5]]

    return {
        "flavor_profile_quantified": quantified,
        "top_5_flavors": top5,
        "flavor_intensity_score": None,  # ponytail: formula TBD (PRD §11)
        "molecules_represented": sum(
            len(ing.get("flavor_composition", {})) for ing in included
        ),
        "data_quality": {
            "unit_conversion_success_rate": grams_valid / n if n else 0.0,
            "ingredient_flavordb_match_rate": flavor_matched / n if n else 0.0,
            "unmapped_ingredients": unmapped_names,
            "zero_gram_ingredients": zero_gram_names,
        },
    }


if __name__ == "__main__":
    # Self-check fixture from ARCHITECTURE doc
    fixture = [
        {"name": "chicken", "grams": 400.0,
         "flavor_composition": {"meaty": 0.45, "fatty": 0.30, "umami": 0.15, "sweet": 0.05, "sulfurous": 0.05}},
        {"name": "avocado", "grams": 150.0,
         "flavor_composition": {"creamy": 0.50, "buttery": 0.30, "fresh": 0.20}},
    ]
    result = compute_recipe_flavor_profile(fixture)
    fq = result["flavor_profile_quantified"]
    total = sum(fq.values())
    assert abs(total - 1.0) < 0.001, f"sum={total} != 1.0"
    assert result["top_5_flavors"][0] == "meaty", f"expected meaty, got {result['top_5_flavors']}"
    assert result["data_quality"]["unit_conversion_success_rate"] == 1.0
    print("PASS — sum=%.4f, top5=%s" % (total, result["top_5_flavors"]))
