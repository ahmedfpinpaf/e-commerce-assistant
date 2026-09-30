import json
import os
from typing import Any, Dict, List, Optional
import numpy as np

try:
    from sentence_transformers import SentenceTransformer, util
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


class ProductSearchEngine:
    """
    Semantic Product Search Engine using Sentence Transformers and vector caching.
    """

    def __init__(
        self,
        chunks_file: str = "catalog_chunks.json",
        embeddings_file: str = "catalog_embeddings.npy",
        model_name: str = "all-MiniLM-L6-v2"
    ):
        self.chunks_file = chunks_file
        self.embeddings_file = embeddings_file
        self.model_name = model_name
        self.model = None
        self.chunks: List[Dict[str, Any]] = []
        self.embeddings: Optional[np.ndarray] = None

    def _ensure_model(self):
        """Lazy load the sentence transformer model."""
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "The 'sentence-transformers' package is required for semantic search.\n"
                "Please install it using: pip install sentence-transformers"
            )
        if self.model is None:
            print(f"Loading embedding model '{self.model_name}'...")
            self.model = SentenceTransformer(self.model_name)
            print("Model loaded successfully.")

    def load_chunks(self) -> List[Dict[str, Any]]:
        """Load catalog chunks from disk."""
        if not os.path.exists(self.chunks_file):
            raise FileNotFoundError(
                f"Chunks file '{self.chunks_file}' not found. "
                "Please run engine.py first to generate product chunks."
            )
        with open(self.chunks_file, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)
        return self.chunks

    def build_or_load_index(self, force_rebuild: bool = False) -> np.ndarray:
        """
        Load precomputed embeddings from disk if available,
        otherwise encode chunks and cache the embeddings as a .npy file.
        """
        if not self.chunks:
            self.load_chunks()

        # Check if cached embeddings already exist and match chunk count
        if not force_rebuild and os.path.exists(self.embeddings_file):
            print(f"Loading cached embeddings from '{self.embeddings_file}'...")
            self.embeddings = np.load(self.embeddings_file)
            if len(self.embeddings) == len(self.chunks):
                print(f"Successfully loaded {len(self.embeddings)} cached product vectors.")
                return self.embeddings
            else:
                print(
                    f"Warning: Cached embeddings count ({len(self.embeddings)}) does not match "
                    f"chunks count ({len(self.chunks)}). Rebuilding index..."
                )

        # Build embeddings from chunk texts
        self._ensure_model()
        print(f"Generating embeddings for {len(self.chunks)} product chunks...")
        texts = [chunk["chunk_text"] for chunk in self.chunks]
        embeddings = self.model.encode(
            texts,
            batch_size=32,
            show_progress_bar=True,
            convert_to_numpy=True,
            normalize_embeddings=True
        )

        # Cache embeddings to disk
        self.embeddings = embeddings
        np.save(self.embeddings_file, self.embeddings)
        print(f"Saved {len(embeddings)} embeddings to '{self.embeddings_file}'.")
        return self.embeddings

    def search(
        self,
        query: str,
        top_k: int = 5,
        category: Optional[str] = None,
        max_price: Optional[float] = None,
        min_rating: Optional[float] = None,
        source: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Search for products semantically matching the query text.
        Supports optional metadata filtering by category, max_price, min_rating, and source.
        """
        if self.embeddings is None:
            self.build_or_load_index()

        self._ensure_model()

        # Encode search query with unit normalization
        query_vec = self.model.encode(query, convert_to_numpy=True, normalize_embeddings=True)

        # Cosine similarity is dot product when vectors are normalized
        scores = np.dot(self.embeddings, query_vec)

        # Filter candidate indices
        results = []
        ranked_indices = np.argsort(-scores)

        for idx in ranked_indices:
            score = float(scores[idx])
            chunk = self.chunks[idx]
            meta = chunk.get("metadata", {})

            # Metadata Filtering
            if category and meta.get("category", "").lower() != category.lower():
                continue
            if source and chunk.get("source", "").lower() != source.lower():
                continue
            if max_price is not None and meta.get("price") is not None:
                if meta["price"] > max_price:
                    continue
            if min_rating is not None and meta.get("rating") is not None:
                if meta["rating"] < min_rating:
                    continue

            results.append({
                "score": round(score, 4),
                "chunk_id": chunk.get("chunk_id"),
                "product_id": chunk.get("product_id"),
                "source": chunk.get("source"),
                "title": meta.get("title"),
                "category": meta.get("category"),
                "brand": meta.get("brand"),
                "price": meta.get("price"),
                "rating": meta.get("rating"),
                "stock": meta.get("stock"),
                "thumbnail": meta.get("thumbnail"),
                "chunk_excerpt": chunk.get("chunk_text", "")[:250] + "..."
            })

            if len(results) >= top_k:
                break

        return results


def format_search_results(results: List[Dict[str, Any]]) -> str:
    """Pretty prints search results for terminal / display."""
    if not results:
        return "No matching products found."

    output = []
    for rank, item in enumerate(results, start=1):
        price_str = f"${item['price']:.2f}" if item['price'] is not None else "N/A"
        rating_str = f"{item['rating']}/5" if item['rating'] is not None else "N/A"
        output.append(
            f"{rank}. [{item['category']}] {item['title']}\n"
            f"   Score: {item['score']} | Price: {price_str} | Rating: {rating_str} | Brand: {item['brand']}\n"
            f"   Source: {item['source']} | ID: {item['product_id']}\n"
            f"   Thumbnail: {item['thumbnail']}"
        )
    return "\n\n".join(output)


if __name__ == "__main__":
    engine = ProductSearchEngine()
    print("Initializing product search index...")
    try:
        engine.build_or_load_index()

        # Test queries
        sample_queries = [
            "dramatic mascara with good volume",
            "casual backpack for 15 inch laptop",
            "affordable skincare under $15"
        ]

        for q in sample_queries:
            print(f"\n================ Query: '{q}' ================")
            matches = engine.search(q, top_k=3)
            print(format_search_results(matches))

    except ImportError as e:
        print("\n" + str(e))

