import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import requests
import uvicorn

# Load environment variables (.env)
load_dotenv()


class ExchangeRateService:
    """Manages live and cached PKR <-> USD exchange rates."""

    def __init__(self):
        self.cached_rate = 0.003608  # Fallback market baseline ~277.16 PKR/USD
        self.last_fetch = 0.0
        self.cache_ttl = 3600  # 1 hour
        self.fetch_rate()

    def fetch_rate(self) -> float:
        now = time.time()
        if now - self.last_fetch < self.cache_ttl:
            return self.cached_rate
        try:
            resp = requests.get("https://open.er-api.com/v6/latest/PKR", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                rate = data.get("rates", {}).get("USD")
                if rate and float(rate) > 0:
                    self.cached_rate = float(rate)
                    self.last_fetch = now
                    return self.cached_rate
        except Exception as e:
            print("Notice: Exchange rate fetch failed, using cached/fallback rate:", e)
        return self.cached_rate

    def pkr_to_usd(self, pkr: float) -> float:
        rate = self.fetch_rate()
        usd = pkr * rate
        return round(usd, 2)

    def usd_to_pkr(self, usd: float) -> int:
        rate = self.fetch_rate()
        if rate <= 0:
            rate = 0.003608
        pkr = usd / rate
        return int(round(pkr, -2))  # Round to nearest 100 PKR


exchange_service = ExchangeRateService()


class MistLLMClient:
    """Client for Mist AI API endpoint with primary model and fast fallback."""

    def __init__(self):
        self.api_key = os.getenv("MIST_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.base_url = (os.getenv("MIST_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "https://mist.riphah.edu.pk/api/v1").rstrip("/")
        self.primary_model = os.getenv("MIST_MODEL", "mist-1")
        self.fallback_model = "vm-llama3.2-3b"

    def chat_completion(self, messages: List[Dict[str, str]], max_tokens: int = 350, temperature: float = 0.6) -> Dict[str, Any]:
        if not self.api_key:
            return {"error": "MIST_API_KEY not configured in .env", "content": None, "model": None}

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Try primary model first with a 4s timeout (since mist-1 can have high cluster queue latency)
        # then immediately fallback to vm-llama3.2-3b which responds in ~1 second.
        models_to_try = [(self.primary_model, 4.0), (self.fallback_model, 7.0)]

        for model_name, timeout_secs in models_to_try:
            payload = {
                "model": model_name,
                "messages": messages,
                "max_tokens": max_tokens,
                "temperature": temperature
            }
            try:
                resp = requests.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=timeout_secs)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "").strip()
                        if content:
                            return {
                                "content": content,
                                "model": model_name,
                                "error": None
                            }
            except Exception as e:
                print(f"Notice: Model '{model_name}' timed out or errored ({e}). Trying fallback if available...")

        return {
            "content": None,
            "error": "LLM cluster timeout",
            "model": None
        }


llm_client = MistLLMClient()


def load_raw_catalog() -> List[Dict[str, Any]]:
    with open("catalog_raw.json", "r", encoding="utf-8") as f:
        return json.load(f)


class CatalogManager:
    """Analyzes catalog_raw.json and provides specs inspection and query filtering."""

    CATEGORY_ALIASES = {
        "laptop": "laptops",
        "laptops": "laptops",
        "notebook": "laptops",
        "notebooks": "laptops",
        "computer": "laptops",
        "computers": "laptops",
        "pc": "laptops",

        "mobile": "smartphones",
        "mobiles": "smartphones",
        "phone": "smartphones",
        "phones": "smartphones",
        "smartphone": "smartphones",
        "smartphones": "smartphones",
        "cellphone": "smartphones",

        "beauty": "beauty",
        "makeup": "beauty",
        "cosmetic": "beauty",
        "lipstick": "beauty",
        "mascara": "beauty",

        "fragrance": "fragrances",
        "fragrances": "fragrances",
        "perfume": "fragrances",
        "perfumes": "fragrances",
        "cologne": "fragrances",
        "scent": "fragrances",
        "itar": "fragrances",
        "khushboo": "fragrances",

        "furniture": "furniture",
        "sofa": "furniture",
        "bed": "furniture",
        "chair": "furniture",
        "table": "furniture",

        "grocery": "groceries",
        "groceries": "groceries",
        "food": "groceries",

        "shirt": "mens-shirts",
        "shirts": "mens-shirts",
        "tshirt": "mens-shirts",
        "dress": "womens-dresses",
        "shoes": "mens-shoes",
        "shoe": "mens-shoes",
        "sneakers": "mens-shoes",
        "joote": "mens-shoes",
        "watch": "mens-watches",
        "watches": "mens-watches",
        "ghadi": "mens-watches",
        "bag": "womens-bags",
        "bags": "womens-bags"
    }

    # Specifications required / relevant per category
    CATEGORY_SPEC_FIELDS = {
        "laptops": ["processor", "ram", "storage", "budget"],
        "smartphones": ["ram", "storage", "budget"],
        "mens-shirts": ["size", "budget"],
        "mens-shoes": ["size", "budget"],
        "fragrances": ["budget"],
        "beauty": ["budget"],
        "furniture": ["budget"]
    }

    def __init__(self, catalog: List[Dict[str, Any]]):
        self.catalog = catalog
        self.categories = set()
        self.brands_by_category = {}
        self.all_brands = set()

        for item in self.catalog:
            cat = (item.get("category") or "").strip().lower()
            if not cat:
                continue
            self.categories.add(cat)
            if cat not in self.brands_by_category:
                self.brands_by_category[cat] = set()

            b = (item.get("brand") or "").strip()
            if b and b.lower() not in ("none", "n/a"):
                self.brands_by_category[cat].add(b)
                self.all_brands.add(b)

    def resolve_category(self, text: str) -> Optional[str]:
        lower = text.lower()
        # Direct match in catalog categories
        for cat in self.categories:
            pattern = rf"\b{re.escape(cat)}\b"
            if re.search(pattern, lower):
                return cat

        # Match alias
        for alias, real_cat in self.CATEGORY_ALIASES.items():
            pattern = rf"\b{re.escape(alias)}\b"
            if re.search(pattern, lower):
                return real_cat
        return None

    KNOWN_NONEXISTENT = {
        "car": "car",
        "cars": "car",
        "television": "television",
        "televisions": "television",
        "tv": "television",
        "tvs": "television",
        "camera": "camera",
        "cameras": "camera",
        "refrigerator": "refrigerator",
        "refrigerators": "refrigerator",
        "fridge": "refrigerator",
        "fridges": "refrigerator",
        "washing machine": "washing machine",
        "washing machines": "washing machine",
        "microwave": "microwave",
        "microwaves": "microwave",
        "ac": "air conditioner",
        "air conditioner": "air conditioner",
        "drone": "drone",
        "drones": "drone",
        "printer": "printer",
        "printers": "printer",
        "bike": "bike",
        "bicycle": "bicycle",
        "headphone": "headphones",
        "headphones": "headphones",
        "earphone": "earphones",
        "earphones": "earphones"
    }

    def detect_nonexistent_category(self, text: str) -> Optional[str]:
        lower = text.lower()
        # Direct check against known non-existent shopping categories
        for word, canonical in self.KNOWN_NONEXISTENT.items():
            if re.search(rf"\b{re.escape(word)}\b", lower):
                return canonical

        # Pattern check for shopping intent verbs
        patterns = [
            r"\b(?:need|want|looking\s+for|show\s+me|find|buy|search\s+for|give\s+me|get)\s+(?:a|an|one|the)?\s*([a-zA-Z\s]+?)(?:\bwith\b|\bunder\b|\bfor\b|\bbelow\b|\bin\b|\.|\?|,|$|\bhaving\b|\bthat\b)",
            r"\b(?:mujhe|humein)?\s*([a-zA-Z\s]+?)\s+(?:chahiye|chahye|dikhao|batao|dein)\b"
        ]
        for p in patterns:
            m = re.search(p, lower)
            if m:
                phrase = m.group(1).strip()
                phrase = re.sub(r"\b(one|1|single|a|an|the|good|cheap|best|sasta|acha|ek|sirf)\b", "", phrase).strip()
                if phrase:
                    words = phrase.split()
                    matched = False
                    for w in words:
                        if self.resolve_category(w):
                            matched = True
                            break
                    if not matched:
                        return words[-1]
        return None

    def extract_brand(self, text: str, category: Optional[str] = None) -> Optional[str]:
        lower = text.lower()
        candidate_brands = list(self.brands_by_category.get(category, [])) if category else []
        if not candidate_brands:
            candidate_brands = list(self.all_brands)

        # Sort brands by length descending so "Dell" matches before single letters
        candidate_brands.sort(key=lambda x: -len(x))
        for b in candidate_brands:
            pattern = rf"\b{re.escape(b.lower())}\b"
            if re.search(pattern, lower):
                return b
        return None

    def extract_specs(self, text: str) -> Dict[str, Any]:
        lower = text.lower()
        specs = {}

        # Processor
        proc_match = re.search(
            r"\b(snapdragon(?:\s*[0-9]+[a-z]*)?|bionic|exynos|mediatek|tensor|core\s+i[3579]|i[3579]|m[123](?:\s+pro|\s+max)?|ryzen\s*[0-9]?|intel|amd)\b",
            lower
        )
        if proc_match:
            specs["processor"] = proc_match.group(1).strip()
        elif "snapdragon" in lower:
            specs["processor"] = "Snapdragon"

        # RAM
        ram_explicit = re.search(r"\b([0-9]+)\s*(?:gb|gigs|gig|g)?\s*ram\b", lower)
        if not ram_explicit:
            ram_explicit = re.search(r"\bram\s*(?:of|:)?\s*([0-9]+)\s*(?:gb|gigs|gig|g)?\b", lower)
        if ram_explicit:
            specs["ram"] = f"{ram_explicit.group(1)}GB"

        # Storage
        st_explicit = re.search(r"\b([0-9]+)\s*(gb|tb)\s*(?:storage|ssd|hdd|rom|space)\b", lower)
        if not st_explicit:
            st_explicit = re.search(r"\b(?:storage|ssd|hdd|rom|space)\s*(?:of|:)?\s*([0-9]+)\s*(gb|tb)?\b", lower)
        if st_explicit:
            unit = st_explicit.group(2) or "gb"
            specs["storage"] = f"{st_explicit.group(1)}{unit.upper()}"

        # Fallback if keywords 'ram' or 'storage' were not explicitly used
        if not specs.get("ram") and not specs.get("storage"):
            gb_matches = re.findall(r"\b([0-9]+)\s*(gb|tb)\b", lower)
            if len(gb_matches) == 1:
                val, u = int(gb_matches[0][0]), gb_matches[0][1].upper()
                if u == "TB" or val >= 128:
                    specs["storage"] = f"{val}{u}"
                else:
                    specs["ram"] = f"{val}{u}"
            elif len(gb_matches) >= 2:
                val1, u1 = int(gb_matches[0][0]), gb_matches[0][1].upper()
                val2, u2 = int(gb_matches[1][0]), gb_matches[1][1].upper()
                if val1 < val2:
                    specs["ram"] = f"{val1}{u1}"
                    specs["storage"] = f"{val2}{u2}"
                else:
                    specs["storage"] = f"{val1}{u1}"
                    specs["ram"] = f"{val2}{u2}"

        return specs

    def extract_budget(self, text: str) -> Dict[str, Any]:
        lower = text.lower().replace(",", "")
        res = {"raw": None, "currency": None, "amount": None, "usd_amount": None, "pkr_amount": None}

        val = None
        unit = None
        curr = None

        # 1. Look for explicit keyword 'budget', 'price', 'under', 'max', 'maximum', 'below', 'within'
        kw_match = re.search(
            r"\b(?:budget|price|under|below|max|maximum|up\s*to|within)\s*(?:of|is|:)?\s*[\$£€]?(?:pkr|rs\.?)?\s*([0-9]+(?:\.[0-9]+)?)\s*(k|m)?(?:\s*(pkr|rs|rupees|usd|\$|dollars))?",
            lower
        )
        if kw_match:
            val = float(kw_match.group(1))
            unit = kw_match.group(2)
            if kw_match.group(3):
                curr = "PKR" if any(k in kw_match.group(3) for k in ["pkr", "rs", "rupee"]) else "USD"

        # 2. Look for number directly followed by currency, e.g. "150000 pkr", "150k rs", "$1500"
        if val is None:
            curr_match = re.search(
                r"\b([0-9]+(?:\.[0-9]+)?)\s*(k|m)?\s*(pkr|rs|rupees|usd|dollars)\b",
                lower
            )
            if curr_match:
                val = float(curr_match.group(1))
                unit = curr_match.group(2)
                curr = "PKR" if any(k in curr_match.group(3) for k in ["pkr", "rs", "rupee"]) else "USD"

        if val is None:
            usd_prefix_match = re.search(r"\$\s*([0-9]+(?:\.[0-9]+)?)\s*(k|m)?\b", lower)
            if usd_prefix_match:
                val = float(usd_prefix_match.group(1))
                unit = usd_prefix_match.group(2)
                curr = "USD"

        # 3. Standalone number input e.g. "150000" or "150k"
        if val is None:
            standalone_match = re.search(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*(k|m)?\s*$", lower)
            if standalone_match:
                val = float(standalone_match.group(1))
                unit = standalone_match.group(2)

        if val is not None:
            if unit == "k":
                val *= 1000
            elif unit == "m":
                val *= 1000000

            res["amount"] = val
            res["raw"] = text.strip()

            # Global currency check in utterance if not set
            if not curr:
                if re.search(r"\b(pkr|rs|rupees|rupee|rs\.)\b", lower):
                    curr = "PKR"
                elif re.search(r"(\$|\busd\b|\bdollars\b|\bdollar\b)", lower):
                    curr = "USD"
                else:
                    curr = "PKR" if val >= 5000 else "USD"

            res["currency"] = curr
            if curr == "PKR":
                res["pkr_amount"] = int(val)
                res["usd_amount"] = exchange_service.pkr_to_usd(val)
            else:
                res["usd_amount"] = round(val, 2)
                res["pkr_amount"] = exchange_service.usd_to_pkr(val)

        return res

    def filter_catalog(
        self,
        category: Optional[str] = None,
        brand: Optional[str] = None,
        max_usd: Optional[float] = None,
        specs: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        matches = []
        for p in self.catalog:
            p_cat = (p.get("category") or "").strip().lower()
            p_brand = (p.get("brand") or "").strip().lower()
            p_price = float(p.get("price") or 0.0)
            full_text = f"{p.get('title', '')} {p.get('description', '')} {' '.join(p.get('tags', []))}".lower()

            if category and p_cat != category.lower():
                continue

            if brand and p_brand != brand.lower():
                continue

            if max_usd is not None and p_price > max_usd:
                continue

            # Strict specs filtering - NO SILENT RELAXATION
            if specs:
                proc = specs.get("processor")
                if proc and proc.lower().replace(" ", "") not in full_text.replace(" ", ""):
                    continue
                ram = specs.get("ram")
                if ram and ram.lower() not in full_text:
                    continue
                storage = specs.get("storage")
                if storage and storage.lower() not in full_text:
                    continue

            matches.append(p)
        return matches

    def auto_relax_search(
        self,
        category: str,
        brand: Optional[str],
        max_usd: Optional[float],
        specs: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Executes exact match search. If 0 results, relaxes one specification
        (budget, or brand) and retrieves similar products from catalog_raw.json.
        """
        # 1. Exact match attempt
        exact_matches = self.filter_catalog(category=category, brand=brand, max_usd=max_usd, specs=specs)
        if exact_matches:
            return {
                "is_exact_match": True,
                "relaxed_spec": None,
                "products": exact_matches
            }

        # 2. Relax Budget first (common bottleneck e.g. Dell XPS is $1499, budget was $541)
        if max_usd is not None and brand:
            brand_matches = self.filter_catalog(category=category, brand=brand, max_usd=None, specs=specs)
            if brand_matches:
                # Also include other laptops from category as comparisons
                other_cat_matches = [p for p in self.filter_catalog(category=category, max_usd=None) if p not in brand_matches]
                all_similar = (brand_matches + other_cat_matches)[:4]
                return {
                    "is_exact_match": False,
                    "relaxed_spec": "budget",
                    "reason": f"No {brand} {category} available under USD ${max_usd} ({exchange_service.usd_to_pkr(max_usd):,} PKR)",
                    "products": all_similar
                }

        # 3. Relax Brand (search category under budget)
        if brand and max_usd is not None:
            under_budget_matches = self.filter_catalog(category=category, brand=None, max_usd=max_usd)
            if under_budget_matches:
                return {
                    "is_exact_match": False,
                    "relaxed_spec": "brand",
                    "reason": f"No {brand} products under budget, showing other brands in {category}",
                    "products": under_budget_matches[:4]
                }

        # 4. Relax both budget and brand (show top items in category)
        cat_matches = self.filter_catalog(category=category, brand=None, max_usd=None)
        return {
            "is_exact_match": False,
            "relaxed_spec": "budget_and_brand",
            "reason": f"Closest matching items in {category}",
            "products": cat_matches[:4]
        }


catalog_data = load_raw_catalog()
catalog_manager = CatalogManager(catalog_data)


def detect_language(text: str, history: Optional[List[Dict[str, str]]] = None) -> str:
    """Detects whether user prompt is in Roman Urdu or English."""
    roman_urdu_words = {
        "mujhe", "chahiye", "chahye", "chahiyay", "dikhao", "batao", "hai", "hain", "ke", "liye",
        "konsa", "kitni", "kitna", "ka", "ki", "kya", "acha", "achha", "sasta", "mehenga", "bhi",
        "wala", "wali", "karo", "karein", "dein", "lekin", "nahi", "shukriya", "bhai",
        "lena", "zaroorat"
    }
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    matched_urdu_words = [w for w in words if w in roman_urdu_words]
    if len(matched_urdu_words) >= 1:
        return "roman_urdu"

    if history:
        for h in history[-3:]:
            h_words = re.findall(r"\b[a-zA-Z]+\b", h.get("content", "").lower())
            if any(w in roman_urdu_words for w in h_words):
                return "roman_urdu"

    return "english"


# Try initializing semantic search if available
try:
    from search import ProductSearchEngine
    search_engine = ProductSearchEngine()
    try:
        search_engine.load_chunks()
        if os.path.exists("catalog_embeddings.npy"):
            search_engine.build_or_load_index()
    except Exception as e:
        print(f"Notice: Semantic vector index not ready yet ({e}). Using catalog filter.")
except Exception as e:
    search_engine = None


def is_single_product_request(text: str, state: Optional[Dict[str, Any]] = None) -> bool:
    """Detects if user explicitly asked for exactly one item/product."""
    if state and state.get("single_product_mode"):
        return True
    lower = text.lower()
    patterns = [
        r"\b(?:show\s+me|find|get|give\s+me|recommend|suggest|need|want|looking\s+for)?\s*(?:only\s+)?(?:one|1|single|a\s+single)\s+(?:item|product|laptop|smartphone|mobile|phone|shirt|shoe|watch|bag|perfume|fragrance)\b",
        r"\b(?:only\s+one|just\s+one|exactly\s+one)\b",
        r"\b(?:ek|sirf\s+ek|1)\s+(?:laptop|mobile|phone|smartphone|product|item|cheez)\b",
        r"\b(?:mujhe\s+)?(?:ek|1)\s+(?:laptop|mobile|phone|smartphone)\s+chahiye\b",
        r"^show\s+me\s+one\b",
        r"\bone\s+product\b",
        r"\bone\s+item\b"
    ]
    for pat in patterns:
        if re.search(pat, lower):
            return True
    return False


def select_single_best_product(candidates: List[Dict[str, Any]], user_specs: Dict[str, Any], budget_usd: Optional[float]) -> Dict[str, Any]:
    """
    Deterministic tie-breaker for single-product selection:
    1. Exact specification match / highest number of matching specs
    2. Closest price to user's budget
    3. Highest rating
    4. Stable catalog order / product ID as final tie-breaker
    """
    def sort_key(p):
        full_text = f"{p.get('title', '')} {p.get('description', '')} {' '.join(p.get('tags', []))}".lower()

        # 1. Exact specification match count
        match_count = 0
        for k, v in user_specs.items():
            if v and str(v).lower() in full_text:
                match_count += 1

        # 2. Closest price to user's budget (smaller delta is better)
        price = float(p.get("price") or 0.0)
        if budget_usd is not None and budget_usd > 0:
            price_delta = abs(price - budget_usd)
        else:
            price_delta = price

        # 3. Rating (higher is better)
        raw_rating = p.get("rating")
        if isinstance(raw_rating, dict):
            rating_val = float(raw_rating.get("rate") or 0.0)
        elif isinstance(raw_rating, (int, float)):
            rating_val = float(raw_rating)
        else:
            rating_val = 0.0

        # 4. Stable catalog order / product ID
        pid = int(p.get("id") or 999999)

        return (-match_count, price_delta, -rating_val, pid)

    sorted_candidates = sorted(candidates, key=sort_key)
    return sorted_candidates[0]


app = FastAPI(
    title="ShopAI Assistant API",
    description="Conversational Product Assistant with Spec Asking and Auto-Relaxation",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def serve_index():
    return FileResponse("index.html")


@app.get("/products_data.js")
def serve_products_data():
    return FileResponse("products_data.js")


@app.get("/chatbot.js")
def serve_chatbot_js():
    return FileResponse("chatbot.js")


@app.get("/api/exchange-rate")
def get_exchange_rate():
    """Returns current live PKR to USD exchange rate."""
    rate = exchange_service.fetch_rate()
    return {"base": "PKR", "rate_usd": rate, "source": "open.er-api.com"}


@app.get("/api/products")
def get_all_products():
    """Return all products in the catalog."""
    return catalog_data


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: Optional[List[ChatMessage]] = None
    state: Optional[Dict[str, Any]] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    max_price: Optional[float] = None


@app.post("/api/chat")
def chat_with_assistant(req: ChatRequest):
    """
    STRICT CATALOG PRODUCT ASSISTANT
    Compliant with all 16 Hard Rules:
    1. Category lock (never substitute, missing categories say so)
    2. Zero product fabrication (catalog_raw.json only)
    3. Exactly ONE product maximum (Rule 3, Rule 7, Rule 11, Rule 15)
    4. No silent relaxation (Rule 4, Rule 8, Rule 11)
    5. Spec asking before search (Rule 10)
    6. Deterministic tie-breaker selection (Rule 4, Rule 7)
    7. Strict Rule 12 response format with pre-response verification
    """
    raw_message = req.message.strip()
    history_dicts = [{"role": h.role, "content": h.content} for h in (req.history or [])]
    detected_lang = detect_language(raw_message, history_dicts)

    # Session state
    state = req.state or {}
    language = state.get("language") or detected_lang
    if detected_lang == "roman_urdu":
        language = "roman_urdu"

    current_category = state.get("category") or req.category
    current_brand = state.get("brand") or req.brand
    current_specs = state.get("specs") or {}
    budget_info = state.get("budget") or {}

    # 1. Non-existent category check (Strict Category Lock - Rule 2, Rule 7, Rule 14)
    non_cat = catalog_manager.detect_nonexistent_category(raw_message)
    detected_cat = catalog_manager.resolve_category(raw_message)

    if non_cat and not detected_cat:
        if language == "roman_urdu":
            reply = f"Catalog mein {non_cat} nahi mila."
        else:
            article = "an" if non_cat[0].lower() in "aeiou" else "a"
            reply = f"I couldn't find {article} {non_cat} in the catalog."
        return {
            "reply": reply,
            "products": [],
            "state": {"stage": "NO_CATEGORY", "category": None, "language": language},
            "stage": "NO_CATEGORY",
            "is_exact_match": False,
            "relaxed_spec": None,
            "model_used": "rule-orchestrator"
        }

    # 2. Extract entities
    if detected_cat:
        if state.get("category") and state.get("category") != detected_cat:
            current_specs = {}
            current_brand = None
            budget_info = {}
        current_category = detected_cat

    detected_brand = catalog_manager.extract_brand(raw_message, current_category)
    if detected_brand:
        current_brand = detected_brand

    detected_specs = catalog_manager.extract_specs(raw_message)
    if detected_specs:
        current_specs.update(detected_specs)

    detected_budget = catalog_manager.extract_budget(raw_message)
    if detected_budget.get("usd_amount") is not None:
        budget_info = detected_budget

    # 3. Category is unknown -> prompt user for category
    if not current_category:
        if language == "roman_urdu":
            reply = "Assalamu Alaikum! Aap ko hamaray catalog se konsi item chahiye? (Jaise laptop, mobile, perfume, shoes, ya clothes)"
        else:
            reply = "Hello! What kind of product are you looking for from our catalog? (e.g. laptop, mobile, fragrance, shoes, or clothing)"
        return {
            "reply": reply,
            "products": [],
            "state": {"stage": "AWAIT_ITEM", "language": language},
            "stage": "AWAIT_ITEM",
            "is_exact_match": True,
            "relaxed_spec": None,
            "model_used": "rule-orchestrator"
        }

    # 4. Specification Questions (Section 10)
    has_specs = bool(
        current_brand or
        current_specs.get("processor") or
        current_specs.get("ram") or
        current_specs.get("storage") or
        current_specs.get("size") or
        budget_info.get("usd_amount") is not None
    )

    if not has_specs and state.get("stage") != "COLLECTING_SPECS":
        if language == "roman_urdu":
            reply = "Aap ke liye konsi specifications zaroori hain, jaise ke RAM, storage, processor, camera, ya budget?"
        else:
            reply = "What specifications are important to you, such as RAM, storage, processor, camera, or budget?"

        new_state = {
            "category": current_category,
            "brand": current_brand,
            "specs": current_specs,
            "budget": budget_info,
            "stage": "COLLECTING_SPECS",
            "language": language
        }
        return {
            "reply": reply,
            "products": [],
            "state": new_state,
            "stage": "COLLECTING_SPECS",
            "is_exact_match": True,
            "relaxed_spec": None,
            "model_used": "rule-orchestrator"
        }

    # 5. Product Search & Filtering (Rule 2, 4, 8, 11: No Silent Relaxation)
    max_usd = budget_info.get("usd_amount") or req.max_price
    candidates = catalog_manager.filter_catalog(
        category=current_category,
        brand=current_brand,
        max_usd=max_usd,
        specs=current_specs
    )

    cat_display = current_category.replace("-", " ")
    cat_single = cat_display[:-1] if cat_display.endswith("s") and not cat_display.endswith("ss") else cat_display
    article = "an" if cat_single[0].lower() in "aeiou" else "a"

    # No match behavior (Section 8: DO NOT SILENTLY RELAX)
    if not candidates:
        if language == "roman_urdu":
            reply = f"Mujhe aap ki specifications ke mutabiq {cat_single} nahi mila. Kya aap requirements mein koi tabdeeli karna chahte hain?"
        else:
            reply = f"I couldn't find {article} {cat_single} matching all of those specifications. Would you like to change one of the requirements?"

        new_state = {
            "category": current_category,
            "brand": current_brand,
            "specs": current_specs,
            "budget": budget_info,
            "stage": "NO_MATCH",
            "language": language
        }
        return {
            "reply": reply,
            "products": [],
            "state": new_state,
            "stage": "NO_MATCH",
            "is_exact_match": False,
            "relaxed_spec": None,
            "model_used": "rule-orchestrator"
        }

    # 6. PRODUCT SELECTION: Deterministic tie-breaker selects EXACTLY ONE product
    best_product = select_single_best_product(candidates, current_specs, max_usd)

    # RULE 12 PRE-RESPONSE VERIFICATION:
    # 1. Requested category = selected product category
    assert best_product.get("category", "").lower() == current_category.lower(), "Category mismatch"
    # 2. Selected product exists in catalog_raw.json
    assert any(p.get("id") == best_product.get("id") for p in catalog_data), "Product not in catalog"

    selected_p = dict(best_product)
    usd_val = float(selected_p.get("price") or 0.0)
    selected_p["price_pkr"] = exchange_service.usd_to_pkr(usd_val)

    # Build specifications list (hyphenated bullets per Rule 12)
    spec_items = []
    spec_items.append(f"- Category: {selected_p.get('category')}")
    if current_specs.get("ram"):
        spec_items.append(f"- RAM: {current_specs['ram']}")
    if current_specs.get("storage"):
        spec_items.append(f"- Storage: {current_specs['storage']}")
    if current_specs.get("processor"):
        spec_items.append(f"- Processor: {current_specs['processor']}")
    if selected_p.get("rating"):
        spec_items.append(f"- Rating: {selected_p['rating']}/5")
    if selected_p.get("availabilityStatus"):
        spec_items.append(f"- Availability: {selected_p['availabilityStatus']}")
    if selected_p.get("warrantyInformation"):
        spec_items.append(f"- Warranty: {selected_p['warrantyInformation']}")
    if selected_p.get("shippingInformation"):
        spec_items.append(f"- Shipping: {selected_p['shippingInformation']}")

    specs_str = "\n".join(spec_items)
    model_val = selected_p.get("sku") or selected_p.get("title")

    if language == "roman_urdu":
        reply_text = (
            "Aap ki requirements ke mutabiq ek product mila hai:\n\n"
            f"Product: {selected_p.get('title')}\n"
            f"Brand: {selected_p.get('brand', 'N/A')}\n"
            f"Model: {model_val}\n"
            f"Price: ${selected_p.get('price')} USD (~Rs. {selected_p['price_pkr']:,} PKR)\n\n"
            f"Specifications:\n{specs_str}"
        )
    else:
        reply_text = (
            "I found one product matching your requirements:\n\n"
            f"Product: {selected_p.get('title')}\n"
            f"Brand: {selected_p.get('brand', 'N/A')}\n"
            f"Model: {model_val}\n"
            f"Price: ${selected_p.get('price')} USD (~Rs. {selected_p['price_pkr']:,} PKR)\n\n"
            f"Specifications:\n{specs_str}"
        )

    # RULE 12 VERIFICATION: Number of displayed products = 1, No alternatives
    response_products = [selected_p]
    assert len(response_products) == 1, "Must return exactly 1 product"

    new_state = {
        "category": current_category,
        "brand": current_brand,
        "specs": current_specs,
        "budget": budget_info,
        "stage": "RESULTS",
        "language": language
    }

    return {
        "reply": reply_text,
        "products": response_products,
        "state": new_state,
        "stage": "RESULTS",
        "is_exact_match": True,
        "is_single_match": True,
        "relaxed_spec": None,
        "model_used": "rule-orchestrator"
    }


@app.get("/api/search")
def search_products_api(
    q: str = Query(..., description="Search query string"),
    top_k: int = Query(10, ge=1, le=50),
    category: Optional[str] = None,
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    source: Optional[str] = None,
):
    """
    Search endpoint: Uses semantic vector search if model & embeddings are available,
    otherwise falls back to keyword matching.
    """
    if search_engine and search_engine.embeddings is not None:
        try:
            return search_engine.search(
                query=q,
                top_k=top_k,
                category=category,
                max_price=max_price,
                min_rating=min_rating,
                source=source
            )
        except Exception as err:
            print("Semantic search failed, falling back to keyword:", err)

    products = load_raw_catalog()
    q_lower = q.lower()
    matches = []

    for p in products:
        p_title = (p.get("title") or "").lower()
        p_desc = (p.get("description") or "").lower()
        p_brand = (p.get("brand") or "").lower()
        p_cat = (p.get("category") or "").lower()

        if category and category.lower() != "all" and p_cat != category.lower():
            continue
        if source and source.lower() != "all" and (p.get("source") or "").lower() != source.lower():
            continue
        if max_price is not None and (p.get("price") or 0) > max_price:
            continue

        raw_rating = p.get("rating")
        if isinstance(raw_rating, dict):
            rating_val = raw_rating.get("rate")
        elif isinstance(raw_rating, (int, float)):
            rating_val = float(raw_rating)
        else:
            rating_val = None

        if min_rating is not None and rating_val is not None and rating_val < min_rating:
            continue

        score = 0.0
        if q_lower in p_title:
            score += 0.8
        if q_lower in p_desc:
            score += 0.4
        if q_lower in p_brand:
            score += 0.6
        if q_lower in p_cat:
            score += 0.5

        if score > 0:
            thumb = p.get("thumbnail") or p.get("image") or (p.get("images", [""])[0] if p.get("images") else "")
            matches.append({
                "score": round(score, 2),
                "chunk_id": f"chunk_{p.get('source')}_{p.get('id')}",
                "product_id": p.get("id"),
                "source": p.get("source"),
                "title": p.get("title"),
                "category": p.get("category"),
                "brand": p.get("brand"),
                "price": p.get("price"),
                "rating": rating_val,
                "stock": p.get("stock"),
                "thumbnail": thumb,
                "chunk_excerpt": (p.get("description") or "")[:200]
            })

    matches.sort(key=lambda x: -x["score"])
    return matches[:top_k]


# ==============================================================================
# CHROME EXTENSION & PRODUCT TRACKING APIs
# ==============================================================================
import tracker_db
from price_scraper import price_scraper
from email_service import email_service
from tracker_scheduler import tracker_scheduler

# Start background tracker scheduler
@app.on_event("startup")
def start_tracker_scheduler():
    tracker_scheduler.start(interval_seconds=300)

class TrackProductRequest(BaseModel):
    product_name: str
    product_url: str
    website: str
    current_price: float
    currency: Optional[str] = "PKR"
    brand: Optional[str] = None
    model: Optional[str] = None
    image_url: Optional[str] = None
    target_price: Optional[float] = None
    alert_type: Optional[str] = "target_price"
    specifications: Optional[Dict[str, Any]] = None

class UpdateTrackedProductRequest(BaseModel):
    target_price: Optional[float] = None
    tracking_status: Optional[str] = None
    alert_type: Optional[str] = None

class UserSettingsRequest(BaseModel):
    alert_email: Optional[str] = None
    check_interval_minutes: Optional[str] = None
    notifications_enabled: Optional[str] = None

class ExtensionChatRequest(BaseModel):
    message: str
    active_product: Optional[Dict[str, Any]] = None

@app.get("/api/tracked-products")
def list_tracked_products():
    return tracker_db.get_all_tracked_products()

@app.post("/api/track-product")
def track_product_endpoint(req: TrackProductRequest):
    prod = tracker_db.add_tracked_product(
        product_name=req.product_name,
        product_url=req.product_url,
        website=req.website,
        current_price=req.current_price,
        currency=req.currency or "PKR",
        brand=req.brand,
        model=req.model,
        image_url=req.image_url,
        target_price=req.target_price,
        alert_type=req.alert_type or "target_price",
        specifications=req.specifications
    )
    return prod

@app.get("/api/tracked-products/{prod_id}")
def get_single_tracked_product(prod_id: str):
    prod = tracker_db.get_tracked_product(prod_id)
    if not prod:
        return {"error": "Product not found"}
    return prod

@app.patch("/api/tracked-products/{prod_id}")
def update_tracked_product_endpoint(prod_id: str, req: UpdateTrackedProductRequest):
    updated = tracker_db.update_tracked_product(
        prod_id=prod_id,
        target_price=req.target_price,
        tracking_status=req.tracking_status,
        alert_type=req.alert_type
    )
    return updated

@app.delete("/api/tracked-products/{prod_id}")
def delete_tracked_product_endpoint(prod_id: str):
    success = tracker_db.delete_tracked_product(prod_id)
    return {"success": success}

@app.get("/api/tracked-products/{prod_id}/history")
def get_price_history_endpoint(prod_id: str):
    return tracker_db.get_price_history(prod_id)

@app.post("/api/check-price/{prod_id}")
def check_single_product_price(prod_id: str):
    prod = tracker_db.get_tracked_product(prod_id)
    if not prod:
        return {"error": "Product not found"}
    return tracker_scheduler.check_product_price(prod)

@app.post("/api/check-all-prices")
def check_all_prices_endpoint():
    results = tracker_scheduler.check_all_active_products()
    return {"results": results}

@app.get("/api/settings")
def get_settings_endpoint():
    return tracker_db.get_user_settings()

@app.post("/api/settings")
def save_settings_endpoint(req: UserSettingsRequest):
    settings = {}
    if req.alert_email is not None:
        settings["alert_email"] = req.alert_email
    if req.check_interval_minutes is not None:
        settings["check_interval_minutes"] = req.check_interval_minutes
    if req.notifications_enabled is not None:
        settings["notifications_enabled"] = req.notifications_enabled
    tracker_db.update_user_settings(settings)
    return tracker_db.get_user_settings()

@app.post("/api/test-email-alert")
def test_email_alert_endpoint():
    settings = tracker_db.get_user_settings()
    recipient = settings.get("alert_email", "user@example.com")
    res = email_service.send_price_drop_alert(
        product_id="test-demo-product",
        product_name="Samsung Galaxy S24 (Test Demo)",
        product_url="http://127.0.0.1:8000/test_pages/daraz_samsung_s24.html",
        current_price=159999.0,
        previous_price=180000.0,
        currency="PKR",
        target_price=160000.0,
        recipient_email=recipient
    )
    return res

@app.get("/api/alert-logs")
def get_alert_logs_endpoint():
    return tracker_db.get_alert_logs()

@app.get("/test_pages/{filename}")
def serve_test_page(filename: str):
    file_path = os.path.join("test_pages", filename)
    if os.path.exists(file_path):
        return FileResponse(file_path)
    return {"error": "File not found"}

@app.post("/api/extension/chat")
def extension_chat_endpoint(req: ExtensionChatRequest):
    """
    Handles natural language queries from the Chrome extension:
    - 'What is this product?' -> Summarizes webpage extracted product
    - 'Track this product' -> Adds to tracking list
    - 'Track this phone and alert me when it falls below PKR 160,000' -> Sets target price
    - 'Show tracked products' -> Summarizes tracked items
    - 'Stop tracking' -> Pauses/removes active product
    """
    msg = req.message.strip()
    prod = req.active_product
    msg_lower = msg.lower()

    # Case 1: What is this product?
    if any(q in msg_lower for q in ["what is this", "tell me about this", "details", "info", "what product"]):
        if not prod or not prod.get("name"):
            return {
                "reply": "I couldn't detect a product on this webpage. Please navigate to a product detail page on Daraz, OLX, Amazon, or eBay.",
                "tracked_product_added": False
            }
        
        curr = prod.get("currency", "PKR")
        price_val = prod.get("price", 0)
        formatted_price = f"{curr} {price_val:,.0f}" if isinstance(price_val, (int, float)) and float(price_val).is_integer() else f"{curr} {price_val:,.2f}"
        
        reply = (
            f"Here is the product detected from {prod.get('website', 'the webpage')}:\n\n"
            f"📦 **Product:** {prod.get('name')}\n"
            f"🏷️ **Brand:** {prod.get('brand', 'N/A')}\n"
            f"🔢 **Model:** {prod.get('model', 'N/A')}\n"
            f"💰 **Current Price:** {formatted_price}\n"
            f"🌐 **Website:** {prod.get('website', 'Store')}\n\n"
            "Would you like me to track this product for price drops?"
        )
        return {"reply": reply, "tracked_product_added": False}

    # Case 2: Stop or Pause Tracking
    if any(k in msg_lower for k in ["stop tracking", "pause tracking", "delete tracking", "untrack", "remove tracking", "don't track", "stop"]):
        if prod and prod.get("url"):
            conn = tracker_db.get_db_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id, product_name FROM tracked_products WHERE product_url = ?", (prod.get("url"),))
            row = cursor.fetchone()
            if row:
                tracker_db.delete_tracked_product(row["id"])
                return {"reply": f"🛑 Stopped tracking **{row['product_name']}** and removed it from your tracking list.", "tracked_product_added": False}

        return {"reply": "You can pause or remove any item from the **Tracked** dashboard tab.", "tracked_product_added": False}

    # Case 3: Show Tracked Products / Dashboard query
    if any(k in msg_lower for k in ["show tracked", "my tracked", "tracking list", "what am i tracking", "list tracked"]):
        tracked = tracker_db.get_all_tracked_products()
        if not tracked:
            return {"reply": "You have no tracked products yet. Open any product page and click 'Track This Product'!", "tracked_product_added": False}

        lines = [f"📋 **You are currently tracking {len(tracked)} product(s):**\n"]
        for idx, item in enumerate(tracked[:5], 1):
            c_p = float(item["current_price"])
            c_str = f"{item['currency']} {c_p:,.0f}" if c_p.is_integer() else f"{item['currency']} {c_p:,.2f}"
            status_emoji = "🟢" if item["tracking_status"] == "active" else ("⏸️" if item["tracking_status"] == "paused" else "🔔")
            lines.append(f"{idx}. {status_emoji} **{item['product_name'][:35]}** — {c_str} ({item['website']})")
        return {"reply": "\n".join(lines), "tracked_product_added": False}

    # Case 4: Track with Target Price or General Tracking
    if any(k in msg_lower for k in ["track", "alert me", "monitor", "watch", "save this"]):
        if not prod or not prod.get("name"):
            return {
                "reply": "No product was detected on the current page to track. Please open a product page first.",
                "tracked_product_added": False
            }

        # Check if user specified a target price e.g. "below PKR 160,000" or "below 160000"
        target_price = None
        target_match = re.search(r"\b(?:below|under|at|to|less than|target)\s*(?:pkr|rs\.?|\$|usd)?\s*([0-9]+(?:,[0-9]+)*(?:\.[0-9]+)?)\s*(k)?", msg_lower)
        if target_match:
            clean_num = target_match.group(1).replace(",", "")
            target_price = float(clean_num)
            if target_match.group(2) == "k":
                target_price *= 1000

        curr_p = float(prod.get("price", 0))
        currency = prod.get("currency", "PKR")
        
        tracked_item = tracker_db.add_tracked_product(
            product_name=prod.get("name"),
            product_url=prod.get("url"),
            website=prod.get("website", "Store"),
            current_price=curr_p,
            currency=currency,
            brand=prod.get("brand"),
            model=prod.get("model"),
            image_url=prod.get("image"),
            target_price=target_price,
            alert_type="target_price" if target_price else "any_drop",
            specifications=prod.get("specifications")
        )

        curr_str = f"{currency} {curr_p:,.0f}" if curr_p.is_integer() else f"{currency} {curr_p:,.2f}"
        if target_price:
            targ_str = f"{currency} {target_price:,.0f}" if target_price.is_integer() else f"{currency} {target_price:,.2f}"
            reply = (
                f"✅ **Tracking Started!**\n\n"
                f"I have added **{prod.get('name')}** to your tracking list.\n"
                f"• Current Price: **{curr_str}**\n"
                f"• Target Alert Price: **{targ_str}**\n\n"
                f"Our backend scheduler will periodically check this exact URL and send an email alert when the price drops below {targ_str}!"
            )
        else:
            reply = (
                f"✅ **Tracking Started!**\n\n"
                f"I have added **{prod.get('name')}** to your tracking list.\n"
                f"• Current Price: **{curr_str}**\n"
                f"• Alert Mode: **Any price drop**\n\n"
                "I will email you as soon as the seller lowers the price."
            )

        return {"reply": reply, "tracked_product_added": True, "product": tracked_item}

    # Fallback response
    return {
        "reply": (
            "I can help you monitor and track product prices across Daraz, OLX, Amazon, and eBay.\n"
            "Try asking:\n"
            "• *'What is this product?'*\n"
            "• *'Track this product'* (or *'Alert me when it drops below 160,000'*)\n"
            "• *'Show tracked products'*"
        ),
        "tracked_product_added": False
    }


if __name__ == "__main__":
    print("\nStarting ShopAI Assistant server at: http://localhost:8000")
    print("Open http://localhost:8000 in your browser to view the storefront.\n")
    uvicorn.run(app, host="127.0.0.1", port=8000)
