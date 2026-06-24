"""
Phase 2B — Equipment and flavor profile inference.

Pure in-memory transforms — no I/O. Each function is a keyword scan
over recipe text fields using pre-compiled regex rules.
"""

import re

from gram_converter import ingredient_to_grams

_MEAL_TYPES = ("breakfast", "lunch", "dinner", "snack", "dessert", "drink")

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

_AROMA_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\b(garlic|onion|shallot|scallion|leek|chive)\b", re.I), "allium"),
    (re.compile(r"\b(lemon|lime|orange|citrus|zest)\b", re.I), "citrus"),
    (re.compile(r"\b(basil|parsley|cilantro|mint|dill|thyme|rosemary|sage|oregano|tarragon)\b", re.I), "herbal"),
    (re.compile(r"\b(cinnamon|nutmeg|cardamom|allspice|ginger)\b", re.I), "warm spice"),
    (re.compile(r"\b(cumin|coriander|turmeric|paprika|curry|garam\s+masala)\b", re.I), "earthy spice"),
    (re.compile(r"\b(chili|chile|jalape[nñ]o|sriracha|cayenne|gochujang|hot\s+sauce)\b", re.I), "chile heat"),
    (re.compile(r"\b(smok(e|ed|y)|char(red)?|grill(ed|ing)?|bacon|smoked\s+paprika)\b", re.I), "smoky"),
    (re.compile(r"\b(vanilla|chocolate|cocoa|caramel|coffee|espresso)\b", re.I), "sweet aromatic"),
    (re.compile(r"\b(parmesan|miso|soy\s+sauce|fish\s+sauce|mushroom|anchov(y|ies))\b", re.I), "savory umami"),
]

_COOKING_PROCESS_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bpreheat\b|\bbak(e|ed|ing)\b", re.I), "bake"),
    (re.compile(r"\broast(ed|ing)?\b", re.I), "roast"),
    (re.compile(r"\bbroil(ed|ing)?\b", re.I), "broil"),
    (re.compile(r"\bboil(ed|ing)?\b", re.I), "boil"),
    (re.compile(r"\bsimmer(ed|ing)?\b", re.I), "simmer"),
    (re.compile(r"\bfry|fried|frying\b", re.I), "fry"),
    (re.compile(r"\bsaut[eé](ed|ing)?\b", re.I), "saute"),
    (re.compile(r"\bsear(ed|ing)?\b", re.I), "sear"),
    (re.compile(r"\bgrill(ed|ing)?\b", re.I), "grill"),
    (re.compile(r"\bsteam(ed|ing)?\b", re.I), "steam"),
    (re.compile(r"\bblend(er|ed|ing)?\b", re.I), "blend"),
    (re.compile(r"\bpuls(e|ed|ing)\b", re.I), "pulse"),
    (re.compile(r"\bwhisk(ed|ing)?\b", re.I), "whisk"),
    (re.compile(r"\bfold\s+in\b|\bfold(ed|ing)?\b", re.I), "fold"),
    (re.compile(r"\bknead(ed|ing)?\b", re.I), "knead"),
    (re.compile(r"\bmarinat(e|ed|ing)\b", re.I), "marinate"),
    (re.compile(r"\bchill(ed|ing)?|refrigerat(e|ed|ing)\b", re.I), "chill"),
]

_LEADING_AMOUNT_RE = re.compile(
    r"^\s*(?:about\s+)?(?:\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*"
    r"(?:kg|kilograms?|g|grams?|mg|milligrams?|lb|lbs|pounds?|oz|ounces?|"
    r"cups?|tsp|tsps|teaspoons?|tbsp|tbsps|tablespoons?|sticks?|"
    r"cloves?|bunch(?:es)?|handfuls?|pinches?)?\b\s*",
    re.I,
)

_INGREDIENT_CLEAN_WORDS = re.compile(
    r"\b(optional|for serving|plus more|to taste|fresh|frozen|cooked|dried|"
    r"large|small|medium|finely|roughly|thinly|chopped|crushed|shredded|"
    r"grated|melted|softened|drained|rinsed|with a fork)\b",
    re.I,
)


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


def infer_aroma_profile(ingredients: list[str], instructions: str, title: str) -> list[str]:
    """Scan ingredients, instructions, and title for aroma families."""
    text = " ".join(ingredients) + " " + instructions + " " + title
    found: list[str] = []
    for pattern, label in _AROMA_RULES:
        if label not in found and pattern.search(text):
            found.append(label)
    return found


def infer_cooking_processes(instructions: str) -> list[str]:
    """Scan instruction text for cooking process verbs."""
    found: list[str] = []
    for pattern, label in _COOKING_PROCESS_RULES:
        if label not in found and pattern.search(instructions):
            found.append(label)
    return found


def infer_meal_type(record: dict) -> str | None:
    """Prefer scraped category tags, then fall back to title/keyword heuristics."""
    existing = record.get("meal_type")
    if existing:
        return existing

    fields = [
        record.get("recipe_category", ""),
        " ".join(record.get("keywords", []) or []),
        record.get("title", ""),
    ]
    text = " ".join(str(f).lower() for f in fields)
    for meal_type in _MEAL_TYPES:
        if re.search(rf"\b{meal_type}s?\b", text):
            return meal_type
    return None


def extract_ingredient_name(ingredient: str) -> str:
    """Best-effort ingredient name from a scraped ingredient line."""
    text = re.sub(r"\([^)]*\)", " ", ingredient)
    text = text.split(",", 1)[0]
    text = _LEADING_AMOUNT_RE.sub("", text)
    text = _INGREDIENT_CLEAN_WORDS.sub(" ", text)
    text = re.sub(r"[^A-Za-z\s-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -").lower()
    return text


def process_record(record: dict) -> dict:
    """Enrich a scraped record in-place with inferred metadata."""
    ingredients = record.get("ingredients") or []
    instructions = record.get("instructions", "") or ""
    title = record.get("title", "") or ""

    record["meal_type"] = infer_meal_type(record)
    record["equipment"] = infer_equipment(record.get("instructions", "") or "")
    record["cooking_processes"] = infer_cooking_processes(instructions)
    record["flavor_profile"] = infer_flavor_profile(ingredients, title)
    record["aroma_profile"] = infer_aroma_profile(ingredients, instructions, title)
    record["ingredient_names"] = [extract_ingredient_name(i) for i in ingredients]
    record["ingredient_grams"] = [
        grams if (grams := ingredient_to_grams(i)) is not None else i
        for i in ingredients
    ]
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
    assert "bake" in result["cooking_processes"], "bake not detected"
    assert "allium" in result["aroma_profile"], "allium aroma not detected"
    print("Self-check passed:", result)
