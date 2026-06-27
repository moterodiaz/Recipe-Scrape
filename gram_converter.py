"""
Ingredient-to-gram converter.
Weight data: kingarthurbaking.com/learn/ingredient-weight-chart
All values are grams per 1 cup. Ranges resolve to lower bound.
"""
import re

# Source: King Arthur Baking ingredient weight chart (grams per 1 cup).
# Keys are lowercase normalized names; longer keys take priority in fuzzy match.
GRAMS_PER_CUP: dict[str, float] = {
    # Flours
    "00 pizza flour": 116,
    "all-purpose baking mix": 120,
    "all-purpose flour": 120,
    "almond flour": 96,
    "almond meal": 84,
    "amaranth flour": 103,
    "artisan bread flour": 120,
    "barley flour": 85,
    "bread flour": 120,
    "brown rice flour": 128,
    "buckwheat flour": 120,
    "cake flour": 120,
    "chickpea flour": 85,
    "coconut flour": 128,
    "durum flour": 124,
    "gluten-free all-purpose flour": 156,
    "gluten-free bread flour": 120,
    "glutinous rice flour": 120,
    "golden wheat flour": 113,
    "hazelnut flour": 89,
    "high-gluten flour": 120,
    "medium rye flour": 106,
    "oat flour": 92,
    "pastry flour": 106,
    "pumpernickel flour": 106,
    "quinoa flour": 110,
    "rice flour": 142,
    "rye flour": 106,
    "self-rising flour": 113,
    "semolina flour": 163,
    "semolina": 163,
    "sorghum flour": 138,
    "soy flour": 140,
    "spelt flour": 99,
    "teff flour": 135,
    "whole wheat flour": 113,
    "whole wheat pastry flour": 96,
    # Starches
    "cornstarch": 112,
    "potato starch": 152,
    "tapioca starch": 113,
    "tapioca flour": 113,
    # Sweeteners
    "agave syrup": 336,
    "brown sugar": 213,
    "coconut sugar": 154,
    "confectioners sugar": 113,
    "powdered sugar": 113,
    "corn syrup": 312,
    "demerara sugar": 220,
    "honey": 336,
    "maple syrup": 312,
    "maple sugar": 156,
    "molasses": 340,
    "turbinado sugar": 180,
    "raw sugar": 180,
    "white sugar": 198,
    "granulated sugar": 198,
    "sugar": 198,
    # Dairy
    "buttermilk": 227,
    "butter": 226,
    "coconut cream": 284,
    "coconut milk": 241,
    "cottage cheese": 226,
    "cream cheese": 227,
    "cream of coconut": 284,
    "creme fraiche": 226,
    "ghee": 176,
    "heavy cream": 227,
    "lard": 226,
    "mascarpone": 227,
    "mayonnaise": 226,
    "milk evaporated": 226,
    "milk": 227,
    "ricotta": 227,
    "sour cream": 227,
    "cream": 227,
    "yogurt": 227,
    # Oils / fats
    "coconut oil": 226,
    "olive oil": 200,
    "vegetable oil": 198,
    "vegetable shortening": 184,
    "oil": 198,
    # Leavening / flavoring
    "baking powder": 192,   # 4g/tsp
    "baking soda": 288,     # 3g/0.5tsp
    "espresso powder": 112,
    "kosher salt": 128,     # Diamond Crystal; Morton's is ~256
    "sea salt": 288,
    "salt": 288,            # table salt
    "vanilla extract": 224,
    # Seeds
    "caraway seeds": 144,
    "chia seeds": 148,
    "flaxseed": 140,
    "poppy seeds": 144,
    "pumpkin seeds": 160,
    "sesame seeds": 142,
    "sunflower seeds": 140,
    # Nuts & nut butters
    "almond paste": 259,
    "almond butter": 272,
    "almonds sliced": 86,
    "almonds slivered": 114,
    "almonds": 142,
    "cashews chopped": 113,
    "cashews": 113,
    "hazelnuts": 142,
    "macadamia nuts": 149,
    "peanut butter": 270,
    "peanuts": 142,
    "pecans chopped": 114,
    "pecans": 105,
    "pine nuts": 142,
    "pistachios": 120,
    "walnuts chopped": 113,
    "walnuts": 128,
    "hazelnut spread": 320,
    "tahini": 256,
    # Chocolate
    "chocolate chips mini": 177,
    "chocolate chips": 170,
    "chocolate chunks": 170,
    "chocolate chopped": 170,
    "white chocolate chips": 170,
    "cocoa powder": 84,
    "cocoa": 84,
    "cacao nibs": 120,
    # Grains / cereals
    "barley cooked": 215,
    "barley pearled": 213,
    "barley flakes": 92,
    "brown rice cooked": 170,
    "buckwheat": 170,
    "bulgur": 152,
    "bran cereal": 60,
    "cornmeal": 156,
    "cracked wheat": 149,
    "granola": 113,
    "masa harina": 93,
    "millet": 206,
    "oats rolled": 89,
    "oats quick": 89,
    "steel cut oats": 140,
    "oats": 89,
    "polenta": 163,
    "quinoa cooked": 184,
    "quinoa": 177,
    "rice": 198,
    "wheat berries": 184,
    "wheat bran": 64,
    "wheat germ": 112,
    # Breadcrumbs
    "breadcrumbs dried": 112,
    "breadcrumbs fresh": 84,
    "panko breadcrumbs": 50,
    "breadcrumbs": 112,
    "graham cracker crumbs": 100,
    "cookie crumbs": 85,
    # Dried fruit
    "apricots dried": 128,
    "blueberries dried": 156,
    "cherries dried": 142,
    "cranberries dried": 114,
    "currants": 142,
    "dates chopped": 149,
    "figs dried": 149,
    "pineapple dried": 142,
    "raisins packed": 170,
    "raisins": 149,
    # Fresh / frozen fruit
    "applesauce": 255,
    "apples": 113,
    "bananas mashed": 227,
    "berries frozen": 142,
    "blueberries": 140,
    "cherries frozen": 113,
    "cherries": 160,
    "cranberries": 99,
    "peaches": 170,
    "pears": 163,
    "pineapple crushed": 256,
    "pineapple": 170,
    "raspberries": 120,
    "strawberries": 167,
    # Vegetables
    "bell peppers": 142,
    "carrots grated": 99,
    "carrots pureed": 256,
    "carrots": 142,
    "celery": 142,
    "garlic minced": 224,
    "garlic": 149,
    "ginger fresh": 228,
    "ginger": 228,
    "leeks": 92,
    "mushrooms": 78,
    "onions": 142,
    "onion": 142,
    "scallions": 64,
    "green onions": 64,
    "shallots": 156,
    "tomato paste": 232,
    "zucchini shredded": 121,
    "zucchini": 121,
    # Condiments / other
    "basil pesto": 224,
    "coconut sweetened shredded": 85,
    "coconut unsweetened shredded": 53,
    "coconut flakes": 60,
    "coconut": 85,
    "flax meal": 100,
    "jam": 340,
    "preserves": 340,
    "lemon juice": 224,
    "lime juice": 224,
    "mashed potatoes": 213,
    "mashed sweet potatoes": 240,
    "marzipan": 290,
    "olives sliced": 142,
    "olives": 142,
    "pumpkin puree": 227,
    "sourdough starter": 227,
    "water": 227,
    # Cheese
    "parmesan cheese": 100,
    "parmesan": 100,
    "feta cheese": 114,
    "feta": 114,
    "cheddar cheese": 113,
    "mozzarella cheese": 113,
    "ricotta cheese": 227,
    "cream cheese": 227,
    "cottage cheese": 226,
    "cheese": 113,
}

# Fix 1: unicode fraction substitution applied at entry point
_UNICODE_FRAC_MAP: dict[str, str] = {
    "¼": "0.25", "½": "0.5", "¾": "0.75",
    "⅓": "0.333", "⅔": "0.667",
    "⅛": "0.125", "⅜": "0.375", "⅝": "0.625", "⅞": "0.875",
}
_UNICODE_FRAC_RE = re.compile("|".join(re.escape(k) for k in _UNICODE_FRAC_MAP))


def _sub_unicode_fractions(s: str) -> str:
    return _UNICODE_FRAC_RE.sub(lambda m: _UNICODE_FRAC_MAP[m.group()], s)


# Volume units → cups multiplier (longest first for greedy parsing)
_TO_CUPS: dict[str, float] = {
    "tablespoons": 1 / 16, "tablespoon": 1 / 16,
    "teaspoons": 1 / 48,   "teaspoon": 1 / 48,
    "tbsps": 1 / 16, "tbsp": 1 / 16, "tbs": 1 / 16,
    "tsps": 1 / 48,  "tsp": 1 / 48,
    "cups": 1.0, "cup": 1.0,
    "pints": 2.0, "pint": 2.0, "pt": 2.0,
    "quarts": 4.0, "quart": 4.0, "qt": 4.0,
    "gallons": 16.0, "gallon": 16.0,
    "sticks": 0.5, "stick": 0.5,
    "fl oz": 0.125, "floz": 0.125,
}

# Weight / volume units → grams multiplier (Fix 2: ml/l/cl added)
_TO_GRAMS_DIRECT: dict[str, float] = {
    "kilograms": 1000.0, "kilogram": 1000.0, "kg": 1000.0,
    "grams": 1.0, "gram": 1.0, "g": 1.0,
    "milligrams": 0.001, "milligram": 0.001, "mg": 0.001,
    "pounds": 453.592, "pound": 453.592, "lbs": 453.592, "lb": 453.592,
    "ounces": 28.3495, "ounce": 28.3495, "oz": 28.3495,
    # ponytail: density ≈ 1 g/ml; fine for milk/stock/water/wine at kitchen scale
    "millilitres": 1.0, "milliliters": 1.0, "ml": 1.0,
    "centilitres": 10.0, "centiliters": 10.0, "cl": 10.0,
    "litres": 1000.0, "liters": 1000.0, "l": 1000.0,
}

# Fix 3: piece weights (average grams per single item)
_PIECE_WEIGHTS: dict[str, float] = {
    # Proteins
    "chicken breast": 175, "chicken thigh": 110, "chicken wing": 90,
    "chicken leg": 130, "chicken drumstick": 110,
    "egg": 50, "sausage": 60, "pork chop": 180, "lamb chop": 150,
    "salmon fillet": 170, "cod fillet": 140, "haddock fillet": 140,
    "prawn": 7, "shrimp": 7, "mussel": 20, "scallop": 30,
    # Alliums
    "onion": 110, "red onion": 110, "white onion": 110, "brown onion": 110,
    "shallot": 25, "garlic clove": 5, "clove garlic": 5,
    "leek": 90, "spring onion": 15, "scallion": 15,
    # Vegetables
    "carrot": 60, "potato": 200, "sweet potato": 230,
    "tomato": 120, "cherry tomato": 15, "plum tomato": 90,
    "bell pepper": 150, "pepper": 150, "chilli": 15, "chili": 15,
    "cucumber": 300, "courgette": 200, "zucchini": 200,
    "aubergine": 250, "eggplant": 250, "parsnip": 120,
    "beetroot": 150, "turnip": 150, "radish": 15,
    "celery stalk": 40, "celery stick": 40,
    "head broccoli": 400, "head cauliflower": 600, "head lettuce": 400,
    "head garlic": 50,
    # Fruit
    "avocado": 200, "lemon": 60, "lime": 50, "orange": 130,
    "apple": 180, "banana": 120, "pear": 170, "peach": 150,
    "plum": 70, "mango": 300,
    # Bakery / carbs
    "naan": 100, "tortilla": 50, "wrap": 50, "pitta": 60, "pita": 60,
    "slice bread": 30, "bread roll": 60,
    # Generic countable units
    "can": 400, "tin": 400, "jar": 350,
    "pack": 250, "packet": 250, "bag": 250,
    "bunch": 30, "handful": 30,
    "sprig": 2, "pinch": 0.5,
    "thumb": 25, "thumb-sized piece": 25, "knob": 15,
}

# Piece unit tokens — words that signal "N × piece of X"
_PIECE_UNITS = frozenset({
    "breast", "breasts", "thigh", "thighs", "leg", "legs",
    "drumstick", "drumsticks", "wing", "wings", "fillet", "fillets",
    "clove", "cloves", "stalk", "stalks", "sprig", "sprigs",
    "bunch", "bunches", "handful", "handfuls",
    "pinch", "pinches", "head", "heads",
    "can", "cans", "tin", "tins", "jar", "jars",
    "pack", "packs", "packet", "packets", "bag", "bags",
    "slice", "slices", "piece", "pieces",
    "knob", "thumb",
})

_STRIP_WORDS = frozenset({
    "fresh", "frozen", "canned", "packed", "cooked", "raw", "organic",
    "unsalted", "salted", "sweetened", "large", "small", "medium", "extra",
    "light", "melted", "softened", "drained", "rinsed", "peeled", "pitted",
    "trimmed", "finely", "coarsely", "thinly", "roughly", "diced",
    "boneless", "skinless", "skin-on", "bone-in",
    # sliced/chopped/minced/grated/shredded/crushed/mashed/pureed intentionally NOT stripped —
    # they appear in GRAMS_PER_CUP keys and affect density (e.g. almonds sliced 86 vs whole 142)
    "a", "an", "the", "of", "or", "and", "to", "taste",
})

_ALL_UNITS = sorted([*_TO_CUPS, *_TO_GRAMS_DIRECT], key=len, reverse=True)
_QTY_RE = re.compile(r"^(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)")
_EXPLICIT_GRAMS_RE = re.compile(
    r"(?:about\s+)?(\d+\s+\d+/\d+|\d+/\d+|\d+(?:\.\d+)?)\s*(kilograms?|kg|grams?|g)\b",
    re.I,
)
_PIECE_KEYS = sorted(_PIECE_WEIGHTS, key=len, reverse=True)


def _parse_qty(s: str) -> tuple[float, str]:
    s = s.strip()
    m = _QTY_RE.match(s)
    if not m:
        return 1.0, s
    raw = m.group(1)
    rest = s[m.end():].strip()
    if " " in raw and "/" in raw:
        whole, frac = raw.split(None, 1)
        n, d = frac.split("/")
        return float(whole) + int(n) / int(d), rest
    if "/" in raw:
        n, d = raw.split("/")
        return int(n) / int(d), rest
    return float(raw), rest


def _parse_unit(s: str) -> tuple[str | None, str]:
    sl = s.lower().lstrip()
    offset = len(s) - len(s.lstrip())
    for u in _ALL_UNITS:
        if sl.startswith(u):
            after = sl[len(u):]
            if not after or not after[0].isalpha():
                return u, s[offset + len(u):].strip().lstrip(".,( ")
    return None, s


def _normalize_name(s: str) -> str:
    s = re.sub(r"\([^)]*\)", " ", s).lower()
    s = re.sub(r"[^\w\s-]", " ", s)
    tokens = [t for t in s.split() if t not in _STRIP_WORDS and len(t) > 1]
    return " ".join(tokens)


_DENSITY_KEYS = sorted(GRAMS_PER_CUP, key=len, reverse=True)


def _lookup_density(name: str) -> float | None:
    """Grams/cup for ingredient name.
    Order: exact → token-set subset → substring → token overlap."""
    norm = _normalize_name(name)
    if norm in GRAMS_PER_CUP:
        return GRAMS_PER_CUP[norm]
    norm_tokens = set(norm.split())
    for key in _DENSITY_KEYS:
        if set(key.split()) <= norm_tokens:
            return GRAMS_PER_CUP[key]
    for key in _DENSITY_KEYS:
        if key in norm:
            return GRAMS_PER_CUP[key]
    for key in _DENSITY_KEYS:
        if any(t in norm_tokens for t in key.split() if len(t) > 3):
            return GRAMS_PER_CUP[key]
    return None


def _lookup_piece(name: str) -> float | None:
    """Grams per piece for whole/countable ingredients.
    Order: exact → token-set subset → substring."""
    norm = _normalize_name(name)
    if norm in _PIECE_WEIGHTS:
        return _PIECE_WEIGHTS[norm]
    norm_tokens = set(norm.split())
    for key in _PIECE_KEYS:
        if set(key.split()) <= norm_tokens:
            return _PIECE_WEIGHTS[key]
    for key in _PIECE_KEYS:
        if key in norm:
            return _PIECE_WEIGHTS[key]
    return None


def ingredient_to_grams(ingredient_str: str) -> float | None:
    """Parse one ingredient string and return its weight in grams.
    Returns None only for truly unrecognisable bare items."""
    # Fix 1: normalise unicode fractions before anything else
    s = _sub_unicode_fractions(ingredient_str)

    # Explicit gram/kg annotation wins (e.g. "4 chicken breasts (about 450g)")
    explicit = _EXPLICIT_GRAMS_RE.search(s)
    if explicit:
        qty, _ = _parse_qty(explicit.group(1))
        unit = explicit.group(2).lower()
        return round(qty * _TO_GRAMS_DIRECT[unit], 1)

    qty, rest = _parse_qty(s.strip())
    unit, ingredient_name = _parse_unit(rest)

    # Fix 2 + existing: direct weight / volume unit
    if unit is not None and unit in _TO_GRAMS_DIRECT:
        return round(qty * _TO_GRAMS_DIRECT[unit], 1)

    # Existing: volume → density lookup
    if unit is not None and unit in _TO_CUPS:
        density = _lookup_density(ingredient_name)
        if density is not None:
            return round(qty * _TO_CUPS[unit] * density, 1)

    # Fix 3: piece unit (e.g. "2 chicken breasts", "3 garlic cloves")
    if unit is not None and unit in _PIECE_UNITS:
        combined = f"{_normalize_name(ingredient_name)} {unit}".strip()
        pw = _lookup_piece(combined) or _lookup_piece(ingredient_name) or _PIECE_WEIGHTS.get(unit)
        if pw is not None:
            return round(qty * pw, 1)

    # Fix 4: no unit — try piece-weight table on full rest string
    if unit is None:
        pw = _lookup_piece(rest)
        if pw is not None:
            return round(qty * pw, 1)

    return None


if __name__ == "__main__":
    cases = [
        # Original cases
        ("2 cup all-purpose flour",               240.0),
        ("1/2 cup butter",                        113.0),
        ("1 cup sugar",                           198.0),
        ("1 cup buttermilk",                      227.0),
        ("2 1/2 teaspoon baking powder",          round(2.5 / 48 * 192, 1)),
        ("1/2 teaspoon baking soda",              round(0.5 / 48 * 288, 1)),
        ("1 tablespoon honey",                    round(1 / 16 * 336, 1)),
        ("8 oz cream cheese",                     round(8 * 28.3495, 1)),
        ("1 lb butter",                           453.6),
        ("1 stick butter",                        113.0),
        ("1/2 cup sliced almonds",                round(0.5 * 86, 1)),
        ("1 cup mashed bananas",                  227.0),
        ("1 tablespoon minced garlic",            round(1 / 16 * 224, 1)),
        ("1/2 cup grated carrots",                round(0.5 * 99, 1)),
        ("1 cup pureed carrots",                  256.0),
        ("1 cup shredded zucchini",               121.0),
        ("300g dried penne",                      300.0),
        ("4 cooked chicken breasts (about 450g)", 450.0),
        ("1 1/4 cup (150 grams) all purpose flour", 150.0),
        # Fix 1: unicode fractions
        ("¼ tsp salt",                            round(0.25 / 48 * 288, 1)),
        ("½ cup olive oil",                       round(0.5 * 200, 1)),
        ("¾ tsp salt",                            round(0.75 / 48 * 288, 1)),
        # Fix 2: ml / litres
        ("150ml whole milk",                      150.0),
        ("650ml milk",                            650.0),
        ("1l vegetable stock",                    1000.0),
        # Fix 3: piece units
        ("2 garlic cloves crushed",               10.0),   # 2 × 5g
        ("6 chicken thighs boneless",             660.0),  # 6 × 110g
        ("1 bunch fresh coriander",               30.0),
        ("1 can chopped tomatoes",                400.0),
        # Fix 4: unitless count
        ("1 onion finely chopped",                110.0),
        ("2 carrots peeled",                      120.0),  # 2 × 60g
        ("4 skinless chicken breasts",            700.0),  # 4 × 175g
        ("1 lemon zested",                        60.0),
    ]
    all_ok = True
    for s, expected in cases:
        got = ingredient_to_grams(s)
        ok = got == expected
        all_ok = all_ok and ok
        print(f"{'OK' if ok else 'FAIL':4} | {s:<45} → {got}g  (expected {expected}g)")
    assert all_ok, "self-check failed"
    print("All checks passed.")
