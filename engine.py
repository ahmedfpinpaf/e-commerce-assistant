import json
import requests
from typing import Any, Dict, List, Optional
from search import ProductSearchEngine


def fetch_dummyjson_catalog() -> List[Dict[str, Any]]:
    """Fetch all products from DummyJSON API."""
    print("Fetching catalog from DummyJSON...")
    products = []
    skip = 0
    while True:
        resp = requests.get(f"https://dummyjson.com/products?limit=100&skip={skip}", timeout=15).json()
        for item in resp.get("products", []):
            item["source"] = "dummyjson"
            products.append(item)
        skip += 100
        if skip >= resp.get("total", 0):
            break
    print(f"Fetched {len(products)} products from DummyJSON.")
    return products


def fetch_fakestore_catalog() -> List[Dict[str, Any]]:
    """Fetch all products from Fake Store API."""
    print("Fetching catalog from Fake Store API...")
    resp = requests.get("https://fakestoreapi.com/products", timeout=15)
    resp.raise_for_status()
    products = resp.json()
    for item in products:
        item["source"] = "fakestore"
    print(f"Fetched {len(products)} products from Fake Store API.")
    return products


def fetch_all_catalogs(output_file: str = "catalog_raw.json") -> List[Dict[str, Any]]:
    """Fetch from both DummyJSON and Fake Store API, merge and save to catalog_raw.json."""
    dummy_products = fetch_dummyjson_catalog()
    fake_products = fetch_fakestore_catalog()
    catalog = dummy_products + fake_products

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"Saved total {len(catalog)} raw products to {output_file}")
    return catalog


def chunk_product(product: Dict[str, Any], index: Optional[int] = None) -> Dict[str, Any]:
    """
    Transforms a raw product dictionary into a semantically rich chunk and structured metadata
    optimized for RAG / vector retrieval.
    """
    source = product.get("source")
    if not source:
        source = "dummyjson" if ("sku" in product or "dimensions" in product) else "fakestore"

    pid = product.get("id")
    chunk_id = f"chunk_{source}_{pid}" if pid is not None else f"chunk_{index}"

    title = str(product.get("title", "Unknown Product")).strip()
    category = str(product.get("category", "General")).strip()
    brand = product.get("brand") or "N/A"
    price = product.get("price")
    discount = product.get("discountPercentage")
    stock = product.get("stock")
    availability = product.get("availabilityStatus") or ("In Stock" if stock is None or stock > 0 else "Out of Stock")
    sku = product.get("sku")
    tags = product.get("tags") or []
    description = str(product.get("description", "")).strip()

    # Format rating
    raw_rating = product.get("rating")
    if isinstance(raw_rating, dict):
        rating_val = raw_rating.get("rate")
        review_count = raw_rating.get("count")
        rating_str = f"{rating_val}/5 ({review_count} ratings)" if rating_val is not None else "N/A"
    elif isinstance(raw_rating, (int, float)):
        rating_val = float(raw_rating)
        rating_str = f"{rating_val}/5"
    else:
        rating_val = None
        rating_str = "N/A"

    # Specifications and policies
    specs = []
    weight = product.get("weight")
    if weight is not None:
        specs.append(f"- Weight: {weight}g")

    dimensions = product.get("dimensions")
    if isinstance(dimensions, dict):
        w = dimensions.get("width")
        h = dimensions.get("height")
        d = dimensions.get("depth")
        if w is not None and h is not None and d is not None:
            specs.append(f"- Dimensions (W x H x D): {w} x {h} x {d} cm")

    shipping = product.get("shippingInformation")
    if shipping:
        specs.append(f"- Shipping: {shipping}")

    warranty = product.get("warrantyInformation")
    if warranty:
        specs.append(f"- Warranty: {warranty}")

    return_policy = product.get("returnPolicy")
    if return_policy:
        specs.append(f"- Return Policy: {return_policy}")

    moq = product.get("minimumOrderQuantity")
    if moq is not None and moq > 1:
        specs.append(f"- Minimum Order Quantity: {moq}")

    # Customer reviews
    reviews_text = []
    raw_reviews = product.get("reviews")
    if isinstance(raw_reviews, list) and raw_reviews:
        for r in raw_reviews:
            r_rating = r.get("rating", "")
            r_comment = r.get("comment", "")
            r_name = r.get("reviewerName", "Anonymous")
            reviews_text.append(f"- [{r_rating}/5 stars] {r_name}: \"{r_comment}\"")

    # Build markdown chunk text
    text_parts = [
        f"# Product: {title}",
        f"- Source: {source}",
        f"- Category: {category}",
        f"- Brand: {brand}",
    ]

    if price is not None:
        price_str = f"- Price: ${price:.2f}"
        if discount is not None:
            price_str += f" (Discount: {discount}%)"
        text_parts.append(price_str)
    else:
        text_parts.append("- Price: N/A")

    text_parts.append(f"- Rating: {rating_str}")
    stock_info = f"- Availability: {availability}"
    if stock is not None:
        stock_info += f" ({stock} available)"
    text_parts.append(stock_info)

    if sku:
        text_parts.append(f"- SKU: {sku}")
    if tags:
        text_parts.append(f"- Tags: {', '.join(str(t) for t in tags)}")

    if description:
        text_parts.append(f"\n## Description\n{description}")

    if specs:
        text_parts.append("\n## Specifications & Policies\n" + "\n".join(specs))

    if reviews_text:
        text_parts.append("\n## Customer Reviews\n" + "\n".join(reviews_text))

    chunk_text = "\n".join(text_parts)

    # Best image or thumbnail
    thumbnail = product.get("thumbnail") or product.get("image")
    if not thumbnail and product.get("images") and isinstance(product["images"], list):
        thumbnail = product["images"][0]

    metadata = {
        "product_id": pid,
        "source": source,
        "title": title,
        "category": category,
        "brand": brand,
        "price": price,
        "rating": rating_val,
        "stock": stock,
        "tags": tags,
        "thumbnail": thumbnail,
    }

    return {
        "chunk_id": chunk_id,
        "product_id": pid,
        "source": source,
        "chunk_text": chunk_text,
        "metadata": metadata,
    }


def create_chunks_from_catalog(
    catalog: List[Dict[str, Any]],
    output_file: str = "catalog_chunks.json"
) -> List[Dict[str, Any]]:
    """Convert an entire catalog list into chunks and save to disk."""
    chunks = [chunk_product(prod, idx) for idx, prod in enumerate(catalog)]

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)

    print(f"Successfully generated {len(chunks)} chunks and saved to {output_file}")
    return chunks


def load_catalog(filepath: str = "catalog_raw.json") -> List[Dict[str, Any]]:
    """Load raw product catalog from JSON file."""
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # 1. Fetch and merge catalogs from DummyJSON + Fake Store API
    catalog = fetch_all_catalogs("catalog_raw.json")

    # 2. Generate chunks for all entries
    chunks = create_chunks_from_catalog(catalog, "catalog_chunks.json")

    # 3. Print sample chunk
    print("\n--- Sample Generated Chunk ---")
    print("Chunk ID:", chunks[0]["chunk_id"])
    print("Chunk Text:\n" + chunks[0]["chunk_text"])
    print("\nMetadata:", json.dumps(chunks[0]["metadata"], indent=2))