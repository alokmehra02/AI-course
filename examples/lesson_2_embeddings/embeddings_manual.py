import json
import math
import logging
import asyncio
from typing import Dict, Any, List, Optional
import httpx
from pydantic import BaseModel, Field

# Configure logging for production observability
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("ManualEmbeddingsEngine")

# =====================================================================
# 1. Pydantic Schemas for Document and Search Results
# =====================================================================
class Document(BaseModel):
    """
    Represents a raw text document chunk to be embedded and searched.
    """
    id: str = Field(..., description="Unique identifier for the document chunk.")
    content: str = Field(..., description="The textual content of the chunk.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata associated with the chunk.")
    embedding: Optional[List[float]] = Field(default=None, description="The vector embedding representation.")

class SearchResult(BaseModel):
    """
    The output schema for a manual vector search operation.
    """
    document: Document = Field(..., description="The matched document chunk.")
    similarity: float = Field(..., description="The calculated similarity score (cosine similarity).")

# =====================================================================
# 2. Pure Python Math for Vector Operations (Zero-dependency)
# =====================================================================
def compute_cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Computes the cosine similarity between two high-dimensional vectors.
    Formula: (A . B) / (||A|| * ||B||)
    """
    if len(vec_a) != len(vec_b):
        raise ValueError(
            f"Dimension mismatch error. Vector A has dimension {len(vec_a)}, "
            f"but Vector B has dimension {len(vec_b)}."
        )
    
    # Calculate dot product
    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    
    # Calculate vector magnitudes (norms)
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    # Standard engineering safety check to prevent ZeroDivisionError
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    
    if norm_a == 0.0 or norm_b == 0.0:
        logger.warning("Zero magnitude vector encountered during similarity calculation.")
        return 0.0
        
    return dot_product / (norm_a * norm_b)

# =====================================================================
# 3. Manual Embeddings Engine Client
# =====================================================================
class ManualEmbeddingsEngine:
    """
    A production-grade, frameworkless client to generate text embeddings
    using raw HTTP/JSON APIs (OpenAI or compatible gateways like local Ollama/vllm).
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        if not api_key:
            raise ValueError("API Key is required to initialize ManualEmbeddingsEngine.")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        
        # Re-use connection pool for latency optimization
        self.client = httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            },
            timeout=httpx.Timeout(15.0)
        )

    async def close(self) -> None:
        """Gracefully release HTTP connection resources."""
        await self.client.aclose()

    async def get_embedding(self, text: str, model: str = "text-embedding-3-small") -> List[float]:
        """
        Sends a single string to the embeddings endpoint and returns the raw vector.
        """
        url = f"{self.base_url}/embeddings"
        payload = {
            "input": text,
            "model": model
        }
        
        try:
            logger.info(f"Generating embedding for text length: {len(text)} using model: {model}")
            response = await self.client.post(url, json=payload)
            
            if response.status_code != 200:
                raise RuntimeError(
                    f"Embeddings API Error (HTTP {response.status_code}): {response.text}"
                )
            
            data = response.json()
            # The API returns vectors under: data[0].embedding
            return data["data"][0]["embedding"]
            
        except httpx.RequestError as exc:
            logger.error(f"Network transport error during embedding generation: {exc}")
            raise RuntimeError(f"Failed to connect to embeddings gateway: {exc}")

    async def get_embeddings_batch(self, texts: List[str], model: str = "text-embedding-3-small") -> List[List[float]]:
        """
        Sends a batch of strings to the embeddings endpoint.
        Useful to minimize roundtrip times for document ingestion.
        """
        if not texts:
            return []
            
        url = f"{self.base_url}/embeddings"
        payload = {
            "input": texts,
            "model": model
        }
        
        try:
            logger.info(f"Generating batch embeddings for {len(texts)} texts using model: {model}")
            response = await self.client.post(url, json=payload)
            
            if response.status_code != 200:
                raise RuntimeError(
                    f"Embeddings API Batch Error (HTTP {response.status_code}): {response.text}"
                )
            
            data = response.json()
            # Map the API response order to the input order
            embeddings = [item["embedding"] for item in data["data"]]
            return embeddings
            
        except httpx.RequestError as exc:
            logger.error(f"Network transport error during batch embedding generation: {exc}")
            raise RuntimeError(f"Failed to connect to embeddings gateway: {exc}")

# =====================================================================
# 4. Manual Vector Database Retrieval Implementation
# =====================================================================
class ManualVectorStore:
    """
    A simple in-memory vector database simulating index retrieval.
    This demonstrates how documents are indexed and matched against a query vector.
    """
    
    def __init__(self, engine: ManualEmbeddingsEngine):
        self.engine = engine
        self.documents: List[Document] = []

    def add_document(self, doc: Document) -> None:
        """Adds a document chunk containing its precomputed embedding into the memory index."""
        if not doc.embedding:
            raise ValueError(f"Document ID {doc.id} must have a precomputed vector embedding to be indexed.")
        self.documents.append(doc)

    async def index_raw_documents(self, raw_docs: List[Document], model: str = "text-embedding-3-small") -> None:
        """
        In-memory document ingest pipeline.
        Generates embeddings in batch and inserts them into the collection.
        """
        texts = [doc.content for doc in raw_docs]
        embeddings = await self.engine.get_embeddings_batch(texts, model=model)
        
        for doc, emb in zip(raw_docs, embeddings):
            doc.embedding = emb
            self.add_document(doc)
        logger.info(f"Successfully indexed {len(raw_docs)} documents.")

    async def similarity_search(self, query: str, k: int = 2, model: str = "text-embedding-3-small") -> List[SearchResult]:
        """
        Retrieves top-K most similar documents using raw vector operations.
        """
        if not self.documents:
            logger.warning("Similarity search requested on an empty vector store.")
            return []
            
        # 1. Embed the user's incoming natural language query
        query_vector = await self.engine.get_embedding(query, model=model)
        
        # 2. Compute similarity for all documents in the collection
        results = []
        for doc in self.documents:
            # Type guard for safety
            assert doc.embedding is not None, "Indexed document is missing its embedding vector."
            
            similarity = compute_cosine_similarity(query_vector, doc.embedding)
            results.append(SearchResult(document=doc, similarity=similarity))
            
        # 3. Sort by similarity score descending and return top K
        results.sort(key=lambda x: x.similarity, reverse=True)
        return results[:k]
