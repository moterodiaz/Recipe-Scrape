"""
Phase 2B — Equipment and flavor profile inference.

Pure in-memory transforms — no I/O. Each function is a keyword scan
over recipe text fields using pre-compiled regex rules.
"""

import re

# (pattern, equipment label) — scanned over instructions text
_EQUIPMENT_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(bak(e|ed|ing)|roast(ed|ing)?|broil(ed|ing)?|preheat\s+oven)\b", re.I), "oven"),
    (re.compile(r"\bblend(er|ed|ing)?\b", re.I), "blender"),
    (re.compile(r"\bfood\s+processor\b|\bpuls(e|ed|ing)\b", re.I), "food processor"),
    (re.compile(r"\b(simmer(ed|ing)?|boil(ed|ing)?|saut[eé](ed|ing)?|fr(y|ied|ying)|sear(ed|ing)?|heat\s+oil|pan[-\s]?fr(y|ied|ying))\b", re.I), "stovetop"),
    (re.compile(r"\b(slow\s+cooker|crockpot)\b", re.I), "slow cooker"),
    (re.compile(r"\b(instant\s+pot|pressure\s+cook)\b", re.I), "pressure cooker"),
    (re.compile(r"\bmicrowave\b", re.I), "microwave"),
    (re.compile(r"\b(grill(ed|ing)?|barbecue|char(red|ring)?)\b", re.I), "grill"),
    (re.compile(r"\bstand\s+mixer\b|\bbeat\s+with\s+mixer\b", re.I), "stand mixer"),
    (re.compile(r"\b(whisk(ed|ing)?|mix\s+by\s+hand)\b", re.I), "mixing bowl"),
    (re.compile(r"\b(sheet\s+pan|baking\s+sheet)\b", re.I), "sheet pan"),
    (re.compile(r"\bcast[\s-]iron\b", re.I), "cast iron skillet"),
    (re.compile(r"\bdutch\s+oven\b", re.I), "dutch oven"),
    (re.compile(r"\b(rolling\s+pin|roll\s+out)\b", re.I), "rolling pin"),
    # Additional obvious mappings
    (re.compile(r"\bwok\b", re.I), "wok"),
    (re.compile(r"\bair\s+fry(er|ing)?\b", re.I), "air fryer"),
    (re.compile(r"\bsteam(er|ed|ing)?\b", re.I), "steamer"),
    (re.compile(r"\b(muffin\s+(tin|pan))\b", re.I), "muffin tin"),
    (re.compile(r"\b(springform|cake\s+pan|bundt)\b", re.I), "cake pan"),
    (re.compile(r"\b(immersion\s+blender|hand\s+blender|stick\s+blender)\b", re.I), "immersion blender"),
    (re.compile(r"\btoaster\s+oven\b", re.I), "toaster oven"),
    (re.compile(r"\bdouble\s+boiler\b", re.I), "double boiler"),
]

# (pattern, flavor label) — scanned over joined ingredients + title
_FLAVOR_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(lemon|lime|vinegar|tamarind|citrus)\b", re.I), "sour"),
    (re.compile(r"\b(chil(i|e|ies|li)|jalape[nñ]o|sriracha|cayenne|pepper\s+flakes|hot\s+sauce|habanero|serrano|gochujang)\b", re.I), "spicy"),
    (re.compile(r"\b(sugar|honey|maple|caramel(ize)?|chocolate|vanilla|molasses|agave|powdered\s+sugar|confection)\b", re.I), "sweet"),
    (re.compile(r"\b(soy\s+sauce|tamari|miso|anchov(y|ies)|parmesan|parmigiano|fish\s+sauce|worcestershire|nutritional\s+yeast|mushroom|bonito)\b", re.I), "umami"),
    (re.compile(r"\b(salt(ed)?|brined|cured|pickle(d)?|capers|olives|prosciutto|feta)\b", re.I), "salty"),
    (re.compile(r"\b(butter|cream|olive\s+oil|avocado|coconut\s+milk|heavy\s+cream|cream\s+cheese|mascarpone|tahini|ghee|creme\s+fraiche)\b", re.I), "rich"),
    (re.compile(r"\b(fresh\s+(basil|mint|cilantro|parsley|dill|thyme)|herb(s)?|salad|cucumber|zest|arugula|watercress)\b", re.I), "fresh"),
    (re.compile(r"\b(smok(e|ed|y)|chipotle|bacon|char(red)?|liquid\s+smoke|smoked\s+paprika|lapsang)\b", re.I), "smoky"),
]


def infer_equipment(instructions: str) -> list[str]:
    """Scan instruction text for equipment keywords. Order preserved, no dupes."""
    found: list[str] = []
    for pattern, label in _EQUIPMENT_RULES:
        if label not in found and pattern.search(instructions):
            found.append(label)
    return found


def infer_flavor_profile(ingredients: list[str], title: str) -> list[str]:
    """Scan combined ingredient text + title for flavor keywords."""
    text = " ".join(ingredients) + " " + title
    found: list[str] = []
    for pattern, label in _FLAVOR_RULES:
        if label not in found and pattern.search(text):
            found.append(label)
    return found


def process_record(record: dict) -> dict:
    """Enrich a scraped record in-place with equipment and flavor_profile lists."""
    record["equipment"] = infer_equipment(record.get("instructions", "") or "")
    record["flavor_profile"] = infer_flavor_profile(
        record.get("ingredients", []) or [], record.get("title", "") or ""
    )
    return record


if __name__ == "__main__":
    # ponytail: minimal self-check — fails if regex rules produce wrong results
    sample = {
        "title": "Lemon Garlic Pasta",
        "ingredients": ["2 lemons, zested", "olive oil", "garlic", "soy sauce"],
        "instructions": "Preheat oven to 400F. Whisk together. Bake 20 minutes.",
    }
    result = process_record(sample)
    assert "oven" in result["equipment"], "oven not detected"
    assert "mixing bowl" in result["equipment"], "mixing bowl not detected"
    assert "sour" in result["flavor_profile"], "sour not detected"
    assert "umami" in result["flavor_profile"], "umami not detected"
    assert "rich" in result["flavor_profile"], "rich not detected"
    print("Self-check passed:", result)
