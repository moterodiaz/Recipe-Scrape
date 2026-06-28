"""
Flavor tag canonicalization.
Maps freeform FlavorDB2 tag variants to a controlled vocabulary.
"""

# Sampled from FlavorDB2 molecules across ~50 entities.
# Maps raw lowercase tags → canonical form.
# ponytail: hand-built from actual API samples; expand when full index reveals more variants.
CANON_MAP: dict[str, str] = {
    # nutty variants
    "nut": "nutty",
    "nut-like": "nutty",
    "peanut": "nutty",
    "almond": "nutty",
    "walnut": "nutty",
    "roasted nut": "nutty",
    "roasted nuts": "nutty",
    "peanut butter": "nutty",
    # woody variants
    "wood": "woody",
    "wood-like": "woody",
    # herbal variants
    "herb": "herbal",
    "herbaceous": "herbal",
    # meaty variants
    "meat": "meaty",
    "meat-like": "meaty",
    "roast beef": "meaty",
    "brothy": "meaty",
    # buttery variants
    "butter": "buttery",
    "butter-like": "buttery",
    # spicy/hot variants
    "spice": "spicy",
    "spice-like": "spicy",
    "hot": "spicy",
    "peppery": "spicy",
    # smoky variants
    "smoke": "smoky",
    "smoked": "smoky",
    "tarry": "smoky",
    # earthy variants
    "earth": "earthy",
    "soil": "earthy",
    "mushroom": "earthy",
    # roasted variants
    "roast": "roasted",
    "toasted": "roasted",
    # fatty variants
    "fat": "fatty",
    "oily": "fatty",
    "greasy": "fatty",
    "waxy": "fatty",
    # sweet variants
    "sugary": "sweet",
    "honeyed": "sweet",
    "honey": "sweet",
    "caramel": "sweet",
    # fruity variants
    "fruit": "fruity",
    "fruit-like": "fruity",
    # floral variants
    "flower": "floral",
    "rose": "floral",
    "violet": "floral",
    # creamy variants
    "cream": "creamy",
    "dairy": "creamy",
    "milky": "creamy",
    # sour/acidic
    "acidic": "sour",
    "tart": "sour",
    "citrusy": "sour",
    # pungent
    "pungency": "pungent",
    "sharp": "pungent",
    # fresh/green
    "grassy": "fresh",
    "green": "fresh",
    "vegetal": "fresh",
    # fermented
    "ferment": "fermented",
    "yeasty": "fermented",
    "bready": "fermented",
    "malt": "fermented",
    "malted": "fermented",
    # sulfurous
    "sulfur": "sulfurous",
    "sulfury": "sulfurous",
    "onion": "sulfurous",
    "garlic-like": "sulfurous",
    # umami
    "savory": "umami",
    "savoury": "umami",
    "broth": "umami",
}


def canonicalize(tag: str) -> str:
    """Lowercase and map to canonical form; return original if not in map."""
    return CANON_MAP.get(tag.lower().strip(), tag.lower().strip())
