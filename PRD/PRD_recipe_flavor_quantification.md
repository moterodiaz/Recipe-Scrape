# Product Requirements Document: Recipe Flavor Profile Quantification System

**Version:** 1.0  
**Last Updated:** June 28, 2026  
**Status:** Active Development

---

## Executive Summary

This system quantifies the flavor profile of any recipe by integrating three key components: (1) ingredient unit normalization to a standard gram scale; (2) molecular flavor composition mapping via FlavorDB2; and (3) weighted aggregation based on ingredient mass. The result is a mathematically rigorous, quantitative flavor signature for every recipe in our dataset.

---

## 1. Overall Workflow

```
Recipe Data (from Spoonacular)
    ↓
Downselection Criteria Applied
    ↓
[PARALLEL PATH 1]          [PARALLEL PATH 2]
Recipe Ingredients List   Pre-load Ingredient 
                          Flavor Modules from FlavorDB2
    ↓                          ↓
Unit Conversion            Flavor Profile Cache Ready
(grams normalization)      (background process)
    ↓                          ↓
───────────────────────────────────
    ↓
Passed Recipe Ready with:
  - All ingredients in grams
  - Pre-loaded flavor module for each ingredient
    ↓
Weighted Flavor Aggregation
    ↓
Final Recipe Flavor Profile
(per-molecule quantities weighted by ingredient mass)
```

---

## 2. Phase 1: Recipe Downselection

Recipes are filtered based on must-have and nice-to-have criteria:

### Must-Have Criteria
- Ingredients list present and non-empty
- Individual ingredient amounts (numeric quantity)
- Valid units of measurement (volume, mass, or countable items)
- Meal classification (breakfast, lunch, dinner, snack, etc.)
- Dietary tags (vegetarian, vegan, gluten-free, etc.)

### Nice-to-Have Criteria
- Process/cooking method information
- Nutritional data
- Flavor tags or cuisines
- Preparation time
- Difficulty level

### Data Sources

#### Primary: Food52 Web Scraping (Current)
**URL:** `https://www.food52.com/recipes`  
**Method:** Web scraping (BeautifulSoup / Selenium)  
**Coverage:**
- Ingredients: Yes (not all guaranteed in grams; must convert via RapidAPI)
- Units: Yes (various formats; normalized in Phase 3)
- Processes: Inferred from cooking instructions via NLP
- Meal classification: Via navbar categories (Breakfast, Lunch, Dinner, Desserts, etc.)
- Dietary tags: Via category tags (Vegetarian, Vegan, Gluten-Free, etc.)
- Nutritional data: Limited (not reliably available)
- Flavor metrics: Not available

**Advantages:**
- No API authentication required
- Rich recipe metadata (difficulty, prep time, author notes)
- Well-structured HTML
- Ethical concerns lower (transparent web scraping vs. API ToS violation risk)

**Constraints:**
- Ingredients not in standardized grams; must convert
- Process extraction requires NLP inference
- Requires respectful rate limiting (1 request per 2 seconds recommended)
- May need User-Agent headers and session management

---

#### Alternative: CoSyLab RecipeDB
**URLs:**  
- RecipeDB (Original): `https://cosylab.iiitd.edu.in/recipedb/`
- RecipeDB2 (Updated): `https://cosylab.iiitd.edu.in/recipedb2/`

**Data Coverage (118,171 recipes):**
- **6 continents, 26 geo-cultural regions, 74 countries**
- **20,262 diverse ingredients**
- **268 cooking processes** (heat, boil, simmer, bake, etc.)
- **Linked to:**
  - FlavorDB (flavor molecules from natural ingredients)
  - USDA nutritional profiles
  - DietRx (disease associations from MEDLINE)

**Available Data Per Recipe:**
- Recipe name and instructions
- Ingredient list with quantities and units
- Cooking processes/techniques
- Cuisine origin (geo-cultural region)
- Dietary classifications
- Estimated nutritional profile (calculated by CoSyLab)
- Flavor profile (inherited from FlavorDB linkage)

**Access Method:**

The RecipeDB web interface is JavaScript-rendered (React-based), but data may be accessible via:
1. **Direct API inspection** — examine network requests in browser to find JSON endpoints
2. **JSON API** — likely pattern: `https://cosylab.iiitd.edu.in/recipedb/recipes_json?id={RECIPE_ID}`
3. **Data export** — contact authors for bulk data access (academic use)
4. **GitHub data** — check `cosylabiiit/Recipedb-companion-data` repo for companion datasets

**Advantages:**
- Pre-parsed ingredient quantities (reduces conversion burden)
- Integrated with FlavorDB (direct molecular flavor data available)
- Ingredients already mapped to 20,262 known ingredient entities
- High-quality, peer-reviewed dataset (published in NAR, 2020)
- Nutritional profiles pre-calculated (USDA integration)
- No ToS concerns (academic resource, CC license)

**Constraints:**
- **No public API documented** — access method TBD (may require direct contact with authors)
- Recipes not in grams by default; units vary
- License: Academic/non-commercial use (check CC-BY-NC-SA terms)
- Potentially harder to scrape (React SPA; no static HTML)

**Recommendation for Integration:**
For now, **proceed with Food52 scraping (primary)**. After validating workflow:
1. Attempt to contact CoSyLab authors (bagler@iiitd.ac.in) for RecipeDB bulk access or API details
2. If available, RecipeDB becomes primary (superior metadata + pre-integrated FlavorDB)
3. Keep Food52 as fallback/supplementary source

---

## 3. Phase 2: Parallel Ingredient Flavor Module Pre-loading

**Timing:** Runs in background parallel to recipe downselection  
**Trigger:** Once recipes are downselected and ingredient names are extracted  
**Goal:** Have flavor profile data ready before any recipe begins aggregation

### 3.1 FlavorDB2 Data Fetch & Cache

```
For each unique ingredient in downselected recipes:
  1. Normalize name to FlavorDB2 entity name
     (fuzzy matching against 936 known ingredients)
  
  2. Fetch ingredient data from FlavorDB2 API:
     URL: https://cosylab.iiitd.edu.in/flavordb2/entities_json?id={ENTITY_ID}
     
     Returns:
     {
       entity_id,
       entity_alias_readable,
       category_readable,
       natural_source_name,
       molecules: [
         {
           pubchem_id,
           common_name,
           flavor_profile (e.g., "spicy@meaty@woody"),
           molecular_weight,
           cas_number,
           aroma_threshold_value,
           taste_threshold_value,
           regulatory_status
         },
         ...
       ]
     }
  
  3. Parse molecule list and extract unique flavor descriptors
  
  4. Calculate per-ingredient flavor composition as percentages:
     
     For ingredient A with molecules containing flavor tags:
       - omega: appears in 15 molecules → 15/150 = 10%
       - delta: appears in 75 molecules → 75/150 = 50%
       - zeta: appears in 60 molecules → 60/150 = 40%
     
     Result: { "omega": 0.10, "delta": 0.50, "zeta": 0.40 }
       (always sums to 100% = 1.0)
  
  5. Cache ingredient flavor module:
     {
       ingredient_name: "chicken",
       flavordb_id: 42,
       flavor_composition: { "spicy": 0.05, "meaty": 0.45, "fatty": 0.30, ... },
       all_molecules: [ {...molecule data...}, ... ],
       flavor_tags: ["spicy", "meaty", "fatty", ...]
     }
```

### 3.2 Flavor Composition Calculation

Each ingredient's flavor profile is expressed as **normalized percentages** of flavor tag occurrence:

**Definition:**  
For a given ingredient, count how many molecules contain each flavor tag (from the `flavor_profile` field in FlavorDB2). The percentage for each tag is:

```
% of tag X = (count of molecules with tag X) / (total molecule count for ingredient)
```

**Constraint:**  
All percentages for an ingredient must sum to exactly 100%.

**Example: Chicken**
```
Chicken has 150 associated molecules in FlavorDB2
Flavor tag distribution:
  - meaty: 67 molecules → 67/150 = 44.7%
  - fatty: 45 molecules → 45/150 = 30.0%
  - sulfurous: 15 molecules → 15/150 = 10.0%
  - sweet: 12 molecules → 12/150 = 8.0%
  - umami: 11 molecules → 11/150 = 7.3%

Sum: 100% ✓

Cached flavor_composition: {
  "meaty": 0.447,
  "fatty": 0.300,
  "sulfurous": 0.100,
  "sweet": 0.080,
  "umami": 0.073
}
```

### 3.3 Error Handling & Fallbacks

- **Ingredient not in FlavorDB2:** Apply fuzzy matching (Levenshtein distance or semantic similarity)
- **No molecules found:** Mark as "unmapped" and flag for manual review
- **Missing flavor_profile field:** Use molecular_weight or chemical_structure as proxy (lower priority)
- **HTTP 404 on entity fetch:** Log and continue with next ingredient

### 3.4 Storage

Cached ingredient flavor modules stored in:
- **Development:** In-memory dictionary / pickle file
- **Production:** Redis cache (fast retrieval; TTL = 30 days)
- **Fallback:** SQLite table with pre-computed compositions

---

## 4. Phase 3: Unit Normalization to Grams

**API:** RapidAPI Food Unit of Measurement Converter  
**Endpoint:** `https://rapidapi.com/smilebot/api/food-unit-of-measurement-converter`

### 4.1 Conversion Process

For each ingredient in a recipe:

```
Input: { ingredient_name, amount, unit }
  e.g., { "chicken breast", 2, "cups" }

1. Call Unit Conversion API:
   POST /convert
   {
     "foodName": "chicken breast",
     "value": 2,
     "unit": "cup"
   }

2. API Response:
   {
     "ingredient": "chicken breast",
     "originalValue": 2,
     "originalUnit": "cup",
     "gramValue": 284,
     "gram": "g"
   }

3. Store normalized result:
   {
     ingredient: "chicken breast",
     original: { amount: 2, unit: "cup" },
     grams: 284,
     unit: "g"
   }
```

### 4.2 Handling Unmappable Units

- **Countable items** (e.g., "2 eggs", "1 onion"): Use ingredient-specific average weight
  - Standard egg: 50g
  - Medium onion: 150g
  - Large clove garlic: 5g
- **Fractional units** (e.g., "1/2 tsp"): Convert to decimal and pass to API
- **Non-standard units** (e.g., "handfuls", "pinches"): Use ingredient-specific mapping or flag for manual entry

### 4.3 Data Quality Checks

- Verify gram value is non-negative and within reasonable bounds
  - Min: 1g (for spices, extracts)
  - Max: 5000g (flag if exceeded; likely data entry error)
- Flag recipes where >30% of ingredients fail unit conversion
- Log all conversion failures for debugging

---

## 5. Phase 4: Weighted Flavor Aggregation

Once all ingredients are in grams and flavor modules are cached, compute the recipe's composite flavor profile.

### 5.1 Weighted Sum Algorithm

**Input:**
- Ingredient 1: mass = 5g, flavor_composition = { "spicy": 0.10, "meaty": 0.50, ... }
- Ingredient 2: mass = 15g, flavor_composition = { "sweet": 0.30, "fatty": 0.40, ... }
- Ingredient 3: mass = 10g, flavor_composition = { "umami": 0.60, "salty": 0.20, ... }

**Step 1: Normalize masses to proportions**
```
Total mass = 5 + 15 + 10 = 30g

Weights:
- Ingredient 1: 5/30 = 0.167 (16.7%)
- Ingredient 2: 15/30 = 0.500 (50.0%)  ← Ingredient 2 dominates
- Ingredient 3: 10/30 = 0.333 (33.3%)
```

**Step 2: Apply weights to each ingredient's flavor composition**
```
For each flavor tag, compute weighted contribution:

flavor_value_recipe = Σ (ingredient_weight × ingredient_flavor_composition[flavor])

Example for "sweet":
  sweet_value = (0.167 × 0.00) + (0.500 × 0.30) + (0.333 × 0.00)
              = 0 + 0.15 + 0
              = 0.15 (15%)

Example for "umami":
  umami_value = (0.167 × 0.00) + (0.500 × 0.00) + (0.333 × 0.60)
              = 0 + 0 + 0.20
              = 0.20 (20%)
```

**Step 3: Aggregate all flavor tags**
```
Recipe Flavor Profile = {
  "spicy": 0.167 × 0.10 + 0.500 × 0.05 + 0.333 × 0.02 = 0.0538 (5.4%),
  "meaty": 0.167 × 0.50 + 0.500 × 0.05 + 0.333 × 0.01 = 0.1063 (10.6%),
  "sweet": 0.150 (15.0%),
  "fatty": 0.200 (20.0%),
  "umami": 0.200 (20.0%),
  ...
}

Validation: Σ all flavor values = 100% ✓
```

### 5.2 Output Structure

**Per-recipe flavor profile:**
```json
{
  "recipe_id": "spoonacular_42857",
  "recipe_name": "Creamy Chicken & Avocado Salad",
  "ingredients": [
    { "name": "chicken breast", "original_amount": 2, "original_unit": "cup", "grams": 284 },
    { "name": "avocado", "original_amount": 1, "original_unit": "whole", "grams": 150 },
    { "name": "olive oil", "original_amount": 2, "original_unit": "tbsp", "grams": 30 }
  ],
  "total_mass_grams": 464,
  "flavor_profile": {
    "creamy": 0.245,
    "fatty": 0.198,
    "umami": 0.156,
    "buttery": 0.112,
    "green": 0.089,
    "fresh": 0.078,
    "grassy": 0.067,
    "meaty": 0.056,
    ...
  },
  "top_5_flavors": ["creamy", "fatty", "umami", "buttery", "green"],
  "flavor_intensity_score": 0.72,
  "molecules_represented": 847,
  "data_quality": {
    "unit_conversion_success_rate": 1.0,
    "ingredient_flavordb_match_rate": 1.0,
    "unmapped_ingredients": []
  }
}
```

---

## 6. Edge Cases & Handling

### 6.1 Unmapped Ingredients

**Scenario:** An ingredient in the recipe doesn't exist in FlavorDB2 (e.g., "fancy truffle oil" vs. "oil").

**Handling:**
1. Attempt fuzzy match against known ingredients (similarity threshold > 0.7)
2. If no match, check ingredient category and use category average
3. If category not available, mark as "unmapped" but continue processing
4. Log unmapped ingredient for manual review/curation

**Impact:** Recipe still produces a flavor profile; unmapped ingredients contribute 0 to flavor calculation (conservative estimate).

### 6.2 Zero-Mass or Trace Ingredients

**Scenario:** "pinch of salt" normalizes to <0.5g; or "1 coriander seed" = 0.01g.

**Handling:**
1. Set floor: all ingredients must contribute ≥0.1g to mass calculation
2. If original ≤0.1g, either:
   - Flag for user confirmation (is this intentional?)
   - Set to 0.1g and note in data_quality
   - Exclude from weighted calculation (if mass is truly negligible)

### 6.3 Missing Unit Information

**Scenario:** API returns ingredient with amount but no unit ("2 ???").

**Handling:**
1. Attempt to infer unit from ingredient type (countable, volume, mass)
2. If inference fails, prompt user for clarification
3. Use ingredient-specific average weight (fallback)
4. Flag in data_quality report

### 6.4 Ingredient Lists Longer Than Expected

**Scenario:** Recipe with 50+ ingredients (not common but possible for complex dishes).

**Handling:**
- Normalize and process all ingredients without issue (algorithm is O(n) in ingredient count)
- Flag recipes with >40 ingredients for potential data quality review
- Flavor profile remains valid; just more granular

---

## 7. Data Quality & Monitoring

### 7.1 Quality Metrics

For each recipe, track:
- **Unit conversion success rate:** % of ingredients successfully converted to grams
- **FlavorDB match rate:** % of ingredients matched to FlavorDB entities
- **Unmapped ingredient count:** Count of ingredients without flavor data
- **Mass variance:** If total recipe mass is unusually small (<50g) or large (>5000g)
- **Flavor profile entropy:** Shannon entropy of flavor distribution (low = monotone, high = diverse)

### 7.2 Logging & Alerts

- Log all API failures (Unit Conversion, FlavorDB fetch)
- Alert if unit conversion success rate <85%
- Alert if FlavorDB match rate <75%
- Flag recipes with incomplete data for re-processing

### 7.3 Caching & Performance

- Cache FlavorDB ingredient modules for 30 days (Redis)
- Cache unit conversions for 90 days (likely constants)
- Batch unit conversion requests (up to 100 at a time) to minimize API calls
- Pre-compute ingredient flavor modules during off-peak hours

---

## 8. API Specifications

### 8.1 RapidAPI Unit Converter

**Service:** Food Unit of Measurement Converter  
**Endpoint:** `https://api.rapidapi.com/food-unit-convert`  
**Method:** POST  
**Rate Limit:** [TBD per plan]  
**Pricing:** [TBD per RapidAPI tier]

**Request:**
```json
{
  "foodName": "chicken breast",
  "value": 2,
  "unit": "cup"
}
```

**Response:**
```json
{
  "ingredient": "chicken breast",
  "originalValue": 2,
  "originalUnit": "cup",
  "gramValue": 284,
  "gram": "g",
  "success": true
}
```

## 8.3 Food52 Scraping Specifications

**Base URL:** `https://www.food52.com/recipes`

**Scraping Strategy:**

```python
# Pseudo-code for Food52 scraping
import requests
from bs4 import BeautifulSoup
import time

headers = {
    'User-Agent': 'Mozilla/5.0 (Custom Recipe Analyzer; +https://yoursite.com/bot)'
}

def scrape_food52_recipe(recipe_url):
    """
    Extract recipe data from Food52 recipe page.
    
    Returns:
    {
        'url': recipe_url,
        'title': str,
        'ingredients': [
            { 'name': str, 'amount': float, 'unit': str },
            ...
        ],
        'instructions': str,
        'prep_time_minutes': int,
        'cook_time_minutes': int,
        'servings': int,
        'categories': [str],  # e.g., ['Breakfast', 'Vegetarian']
        'difficulty': str,
        'source': 'food52'
    }
    """
    
    response = requests.get(recipe_url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.content, 'html.parser')
    
    # Extract structured data (JSON-LD schema)
    recipe_schema = soup.find('script', {'type': 'application/ld+json'})
    if recipe_schema:
        recipe_data = json.loads(recipe_schema.string)
        
        # Parse ingredients
        ingredients = []
        for ing in recipe_data.get('recipeIngredient', []):
            # e.g., "2 cups all-purpose flour"
            parsed = parse_ingredient_string(ing)
            ingredients.append(parsed)
        
        return {
            'url': recipe_url,
            'title': recipe_data.get('name'),
            'ingredients': ingredients,
            'instructions': recipe_data.get('recipeInstructions'),
            'prep_time_minutes': parse_iso_duration(recipe_data.get('prepTime')),
            'cook_time_minutes': parse_iso_duration(recipe_data.get('cookTime')),
            'servings': parse_servings(recipe_data.get('recipeYield')),
            'categories': extract_categories(soup),
            'difficulty': extract_difficulty(soup),
            'source': 'food52'
        }
    
    return None

def parse_ingredient_string(ingredient_str):
    """
    Parse "2 cups all-purpose flour" into:
    { 'name': 'all-purpose flour', 'amount': 2.0, 'unit': 'cup' }
    """
    # Regex pattern to extract amount, unit, and name
    # This is complex due to fractional amounts (e.g., "1 1/2 cups")
    pass

def scrape_all_recipes(max_recipes=None):
    """
    Iterate through Food52 recipe pages and collect recipe URLs.
    Then scrape each recipe with rate limiting.
    """
    recipe_urls = []
    
    # Food52 pagination: /recipes?page=1, /recipes?page=2, etc.
    page = 1
    while True:
        list_url = f'https://www.food52.com/recipes?page={page}'
        response = requests.get(list_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Extract recipe links from listing page
        recipe_links = soup.find_all('a', {'class': 'recipe-link'})
        if not recipe_links:
            break  # No more recipes
        
        for link in recipe_links:
            recipe_urls.append(link['href'])
        
        page += 1
        time.sleep(2)  # Rate limit: 2 seconds between requests
        
        if max_recipes and len(recipe_urls) >= max_recipes:
            break
    
    # Scrape each recipe
    scraped_recipes = []
    for url in recipe_urls:
        try:
            recipe = scrape_food52_recipe(url)
            if recipe:
                scraped_recipes.append(recipe)
        except Exception as e:
            print(f"Failed to scrape {url}: {e}")
        
        time.sleep(2)  # Rate limiting
    
    return scraped_recipes
```

**Parsing Ingredient Strings:**

Food52 stores ingredients as natural language strings (via Schema.org RecipeIngredient). Parsing is complex due to variations:
- "2 cups all-purpose flour"
- "1 1/2 tablespoons unsalted butter"
- "3 to 4 cloves garlic, minced"
- "Salt and pepper to taste"
- "1 (15 oz) can black beans, drained"

**Recommendation:** Use a dedicated ingredient parsing library:
- `ingredient-parser-py` (Python)
- Or send strings to RapidAPI converter as-is; API handles most natural formats

**Rate Limiting & Ethics:**
- 1 request per 2 seconds (conservative)
- Use descriptive User-Agent header
- Respect robots.txt
- Cache responses to avoid redundant requests
- Consider contacting Food52 for bulk data access or permission

**Base URL:** `https://cosylab.iiitd.edu.in/flavordb2`

**Ingredient Endpoint:**
```
GET /entities_json?id={ENTITY_ID}
```

**Molecule Endpoint:**
```
GET /molecules_json?id={PUBCHEM_ID}
```

**Rate Limit:** No documented limit (assume reasonable: 1 req/sec per IP)  
**License:** CC-BY-NC-SA 3.0 (non-commercial, academic use)

---

## 9. Data Pipeline Architecture

```
[Stage 0: Recipe Scraping & Downselection]
  - Food52 web scraper (primary)
    OR RecipeDB API (alternative, if access obtained)
  - Extract recipes meeting must-have criteria
  - Parse: name, ingredients, units, meal type, dietary tags
  - Apply downselection filters
    ↓
Downselected Recipes
    ↓
[Stage 1: Ingredient Extraction & Normalization]
  - Parse ingredient list from recipe
  - Extract: name, amount, unit
  - Deduplicate ingredient names
  - Map to FlavorDB entities (fuzzy matching)
    ↓
[Stage 2A: Unit Conversion (Parallel)]
  - Batch call RapidAPI converter
  - Request: foodName, value, unit → Response: gramValue
  - Convert all ingredients to grams
  - Handle failures (fallback to ingredient-specific averages)
  - Log conversion success rate
    ↓
[Stage 2B: Flavor Module Pre-load (Parallel)]
  - For each ingredient, fetch FlavorDB entity
  - Request: https://cosylab.iiitd.edu.in/flavordb2/entities_json?id={ENTITY_ID}
  - Parse molecules & flavor_profile tags
  - Calculate flavor_composition percentages
  - Aggregate all unique flavor tags
  - Cache in Redis (TTL: 30 days)
  - Deduplicate across recipes (avoid redundant fetches)
    ↓
[Stage 3: Weighted Aggregation]
  - Retrieve cached flavor modules for each ingredient
  - Calculate mass weights (ingredient_grams / total_grams)
  - Compute weighted sum: flavor_value = Σ (weight × flavor_composition[tag])
  - Normalize all flavor values to sum = 100%
  - Calculate secondary metrics:
    * Flavor entropy (Shannon)
    * Intensity score (using aroma/taste thresholds)
    * Top 5 flavors
    ↓
Recipe Flavor Profile (Final Output)
    ↓
[Stage 4: Data Quality Checks]
  - Verify unit conversion success rate ≥85%
  - Verify FlavorDB match rate ≥75%
  - Validate flavor profile sums to 100%
  - Flag recipes with data quality issues
    ↓
[Storage & Export]
  - Write to PostgreSQL (master database)
    - recipe_id, recipe_name, ingredients (JSON), total_mass_grams
    - flavor_profile (JSON), data_quality_flags
  - Index by recipe_id, cuisine, dietary_tags
  - Export to JSON (downstream applications)
  - Sync to data warehouse (optional)
```

---

## 10. Success Criteria

- [ ] All downselected recipes have ingredient amounts in grams
- [ ] ≥85% of ingredients matched to FlavorDB entities
- [ ] Every passed recipe has a quantified flavor profile (100+ flavor tags)
- [ ] Flavor profiles sum to exactly 100% (validation)
- [ ] Unit conversion API responds in <2s (p99)
- [ ] FlavorDB caching reduces repeat fetches by >95%
- [ ] Data quality dashboard shows real-time conversion success rates

---

## 11. Future Enhancements

- Molecular weight weighting (favor heavier, more impactful molecules)
- Aroma vs. taste threshold separation (some molecules are olfactory, others gustatory)
- Ingredient interactions (synergy/suppression between flavor molecules)
- Recipe-level quality scoring (how "well-balanced" is the flavor profile?)
- Recommendation engine (find recipes with specific flavor targets)

---

## 12. Appendix: Example Walkthrough

**Recipe: Spicy Garlic Chicken with Avocado**

### Downselection → Ingredients
```
chicken breast: 400g → already in grams ✓
garlic cloves: 6 → needs conversion
avocado: 1 whole → needs conversion
olive oil: 3 tbsp → needs conversion
chili flakes: 1 tsp → needs conversion
salt: 1/2 tsp → needs conversion
```

### Unit Conversion
```
API calls:
  1. garlic cloves (6) → 30g (5g × 6)
  2. avocado (1 whole) → 150g
  3. olive oil (3 tbsp) → 45g
  4. chili flakes (1 tsp) → 5g
  5. salt (1/2 tsp) → 3g

Normalized ingredients:
  - chicken breast: 400g (53.1%)
  - avocado: 150g (19.9%)
  - olive oil: 45g (6.0%)
  - garlic cloves: 30g (4.0%)
  - chili flakes: 5g (0.7%)
  - salt: 3g (0.4%)
  
  Total: 633g ✓
```

### Flavor Module Pre-load (Parallel)
```
Cached modules:
  chicken: { "meaty": 0.45, "fatty": 0.30, "umami": 0.15, ... }
  avocado: { "creamy": 0.50, "buttery": 0.30, "fresh": 0.20, ... }
  olive oil: { "fatty": 0.70, "fruity": 0.20, "peppery": 0.10 }
  garlic: { "pungent": 0.40, "sulfurous": 0.35, "sweet": 0.25 }
  chili: { "spicy": 0.60, "hot": 0.30, "peppery": 0.10 }
  salt: { "salty": 1.0 }
```

### Weighted Aggregation
```
Weights:
  chicken: 400/633 = 0.632
  avocado: 150/633 = 0.237
  olive oil: 45/633 = 0.071
  garlic: 30/633 = 0.047
  chili: 5/633 = 0.008
  salt: 3/633 = 0.005

Recipe flavor = Σ (weight × ingredient_flavor):
  meaty = 0.632 × 0.45 = 0.285
  creamy = 0.237 × 0.50 = 0.119
  fatty = 0.632 × 0.30 + 0.071 × 0.70 = 0.239
  umami = 0.632 × 0.15 = 0.095
  buttery = 0.237 × 0.30 = 0.071
  pungent = 0.047 × 0.40 = 0.019
  sulfurous = 0.047 × 0.35 = 0.016
  spicy = 0.008 × 0.60 = 0.005
  salty = 0.005 × 1.0 = 0.005
  ... (other tags)

Normalized (to 100%):
  meaty: 0.285 / total
  creamy: 0.119 / total
  fatty: 0.239 / total
  umami: 0.095 / total
  ... (continue for all tags, sum to 1.0)

Final Recipe Flavor Profile (Top 5):
  [1] meaty: 25.1%
  [2] fatty: 21.0%
  [3] creamy: 10.5%
  [4] umami: 8.3%
  [5] buttery: 6.2%
```

---

## 13. Glossary

- **Flavor tag:** Descriptive label from FlavorDB2 (e.g., "spicy", "meaty", "umami")
- **Flavor molecule:** Chemical compound in FlavorDB2 with associated taste/aroma properties
- **Flavor composition:** Normalized distribution of flavor tags for a single ingredient (%)
- **Flavor profile:** Weighted aggregation of all flavor compositions in a recipe (%)
- **FlavorDB entity:** Single ingredient record in FlavorDB2 (e.g., "chicken", "avocado")
- **Weighted sum:** Aggregation method where each ingredient's flavor contribution is scaled by its mass proportion
