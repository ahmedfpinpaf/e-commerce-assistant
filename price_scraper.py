import re
import json
import logging
from typing import Any, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup

logger = logging.getLogger("price_scraper")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ur;q=0.8",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache"
}

def parse_price_string(price_str: str) -> Optional[float]:
    if not price_str:
        return None
    clean = price_str.replace(",", "").replace("\xa0", " ").strip()
    match = re.search(r"([0-9]+(?:\.[0-9]+)?)", clean)
    if match:
        try:
            return float(match.group(1))
        except ValueError:
            return None
    return None

def detect_currency(text: str) -> str:
    text_lower = text.lower()
    if any(k in text_lower for k in ["pkr", "rs", "rupee", "₨"]):
        return "PKR"
    elif any(k in text_lower for k in ["$", "usd", "dollar"]):
        return "USD"
    elif any(k in text_lower for k in ["£", "gbp"]):
        return "GBP"
    elif any(k in text_lower for k in ["€", "eur"]):
        return "EUR"
    return "PKR"

class ProductPriceScraper:
    """Scrapes current prices and product info from e-commerce product pages."""
    
    # In-memory mock/simulation registry for testing price drops
    _simulated_overrides: Dict[str, Tuple[float, str]] = {}
    
    @classmethod
    def set_simulated_price(cls, url: str, price: float, currency: str = "PKR"):
        """Allows testing price drops reliably by mocking the price for a URL."""
        cls._simulated_overrides[url.strip().lower()] = (price, currency)
        
    @classmethod
    def clear_simulated_prices(cls):
        cls._simulated_overrides.clear()

    def scrape_product_info(self, url: str) -> Dict[str, Any]:
        """Fetches product URL and extracts name, brand, model, price, currency, image, specs."""
        url_clean = url.strip()
        
        # Check simulation registry first
        if url_clean.lower() in self._simulated_overrides:
            sim_price, sim_curr = self._simulated_overrides[url_clean.lower()]
            return {
                "name": "Simulated Tracked Product",
                "price": sim_price,
                "currency": sim_curr,
                "url": url_clean,
                "website": self.detect_website(url_clean),
                "image": "",
                "brand": "Simulated",
                "model": "Model-X",
                "specifications": {"Status": "Simulated Active Price"}
            }

        try:
            resp = requests.get(url_clean, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                logger.warning(f"Failed to fetch {url_clean}: status {resp.status_code}")
                return {"error": f"HTTP {resp.status_code}", "price": None, "currency": None}
            
            html = resp.text
            return self.extract_from_html(html, url_clean)
        except Exception as e:
            logger.error(f"Error scraping {url_clean}: {e}")
            return {"error": str(e), "price": None, "currency": None}

    def detect_website(self, url: str) -> str:
        url_lower = url.lower()
        if "daraz.pk" in url_lower:
            return "Daraz"
        elif "olx.com.pk" in url_lower:
            return "OLX"
        elif "amazon" in url_lower:
            return "Amazon"
        elif "ebay" in url_lower:
            return "eBay"
        return "Online Store"

    def extract_from_html(self, html: str, url: str) -> Dict[str, Any]:
        soup = BeautifulSoup(html, "html.parser")
        website = self.detect_website(url)
        
        name = None
        brand = None
        model = None
        price = None
        currency = "PKR"
        image = None
        specifications = {}

        # 1. Try structured data JSON-LD (universal on modern e-commerce)
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "{}")
                # Handle single or graph array
                candidates = data.get("@graph", [data]) if isinstance(data, dict) else (data if isinstance(data, list) else [data])
                for item in candidates:
                    if isinstance(item, dict) and item.get("@type") in ("Product", "IndividualProduct"):
                        if not name:
                            name = item.get("name")
                        if not image and item.get("image"):
                            img = item.get("image")
                            image = img[0] if isinstance(img, list) else (img.get("url") if isinstance(img, dict) else img)
                        if not brand and item.get("brand"):
                            b = item.get("brand")
                            brand = b.get("name") if isinstance(b, dict) else str(b)
                        if not model:
                            model = item.get("model") or item.get("sku") or item.get("mpn")
                        
                        offers = item.get("offers", {})
                        if isinstance(offers, list) and offers:
                            offers = offers[0]
                        if isinstance(offers, dict) and price is None:
                            p_val = offers.get("price") or offers.get("lowPrice")
                            if p_val:
                                price = parse_price_string(str(p_val))
                            if offers.get("priceCurrency"):
                                currency = offers.get("priceCurrency")
            except Exception:
                pass

        # 2. Site-specific DOM selectors
        if website == "Daraz":
            # Daraz price selectors
            if price is None:
                p_tag = soup.select_one(".pdp-price, .pdp-v-price, .notranslate.pdp-price_type_normal, [class*='pdp-price']")
                if p_tag:
                    price = parse_price_string(p_tag.get_text())
                    currency = detect_currency(p_tag.get_text())
            if not name:
                n_tag = soup.select_one(".pdp-mod-product-badge-title, h1.pdp-title, .pdp-product-title")
                if n_tag:
                    name = n_tag.get_text().strip()
            if not brand:
                b_tag = soup.select_one(".pdp-link_theme_blue, a.pdp-link")
                if b_tag:
                    brand = b_tag.get_text().strip()

        elif website == "OLX":
            if price is None:
                p_tag = soup.select_one('[data-aut-id="itemPrice"], span[class*="_10755a3b"], span[class*="price"]')
                if p_tag:
                    price = parse_price_string(p_tag.get_text())
                    currency = detect_currency(p_tag.get_text())
            if not name:
                n_tag = soup.select_one('[data-aut-id="itemTitle"], h1[class*="_10755a3b"], h1')
                if n_tag:
                    name = n_tag.get_text().strip()

        elif website == "Amazon":
            if price is None:
                p_tag = soup.select_one(".a-price .a-offscreen, #priceblock_ourprice, #priceblock_dealprice, #corePrice_desktop .a-offscreen")
                if p_tag:
                    price = parse_price_string(p_tag.get_text())
                    currency = detect_currency(p_tag.get_text())
            if not name:
                n_tag = soup.select_one("#productTitle, #title")
                if n_tag:
                    name = n_tag.get_text().strip()
            if not brand:
                b_tag = soup.select_one("#bylineInfo")
                if b_tag:
                    brand = b_tag.get_text().replace("Brand:", "").replace("Visit the", "").replace("Store", "").strip()

        elif website == "eBay":
            if price is None:
                p_tag = soup.select_one(".x-price-primary .ux-textspans, #prcIsum, [data-testid='x-price-primary']")
                if p_tag:
                    price = parse_price_string(p_tag.get_text())
                    currency = detect_currency(p_tag.get_text())
            if not name:
                n_tag = soup.select_one(".x-item-title__mainTitle .ux-textspans, h1.x-item-title")
                if n_tag:
                    name = n_tag.get_text().strip()

        # 3. Generic Meta Tags Fallback (OpenGraph / Microdata)
        if not name:
            og_title = soup.find("meta", property="og:title") or soup.find("meta", attrs={"name": "twitter:title"})
            if og_title and og_title.get("content"):
                name = og_title["content"].strip()
            elif soup.title:
                name = soup.title.get_text().split("|")[0].split("-")[0].strip()

        if price is None:
            og_price = (
                soup.find("meta", property="product:price:amount") or
                soup.find("meta", property="og:price:amount") or
                soup.find("meta", attrs={"itemprop": "price"})
            )
            if og_price and og_price.get("content"):
                price = parse_price_string(og_price["content"])

        if not image:
            og_img = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "twitter:image"})
            if og_img and og_img.get("content"):
                image = og_img["content"].strip()

        # Currency fallback from meta
        og_curr = soup.find("meta", property="product:price:currency") or soup.find("meta", property="og:price:currency")
        if og_curr and og_curr.get("content"):
            currency = og_curr["content"].strip().upper()

        return {
            "name": name or "Product",
            "brand": brand or "N/A",
            "model": model or "N/A",
            "price": price if price is not None else 0.0,
            "currency": currency or "PKR",
            "url": url,
            "image": image or "",
            "specifications": specifications,
            "website": website
        }

price_scraper = ProductPriceScraper()
