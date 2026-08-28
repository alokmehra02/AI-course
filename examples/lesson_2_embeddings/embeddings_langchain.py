import logging
from typing import List, Dict, Any
from pydantic import BaseModel, Field
from langchain_openai import OpenAIEmbeddings
from langchain_core.documents import Document as LCDocument
from langchain_core.vectorstores import InMemoryVectorStore

logger = logging.getLogger("LangChainEmbeddingsEngine")

# =====================================================================
# 1. Pydantic Schemas (Aligned with Manual Implementation)
# =====================================================================
class Document(BaseModel):
    id: str = Field(..., description="Unique identifier for the document chunk.")
    content: str = Field(..., description="The textual content of the chunk.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata associated with the chunk.")

class SearchResult(BaseModel):
    document: Document = Field(..., description="The matched document chunk.")
    similarity: float = Field(..., description="The calculated similarity score.")

# =====================================================================
# 2. LangChain Embeddings Engine
# =====================================================================
class LangChainEmbeddingsEngine:
    """
    An Embeddings Client Engine leveraging LangChain wrappers.
    This replaces raw HTTP requests, batch handling, rate-limit retries, 
    and manually parsing JSON headers.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        # LangChain's OpenAIEmbeddings wraps the client and manages details such as:
        # - Automatic retries on rate limits (429) or transient network drops.
        # - Payload serialization and content parsing.
        # - Dynamic pooling.
        self.embeddings = OpenAIEmbeddings(
            openai_api_key=api_key,
            openai_api_base=base_url,
            model="text-embedding-3-small"
        )

    async def get_embedding(self, text: str) -> List[float]:
        """
        Equivalent to manual call. Replaces raw POST with a single async call.
        """
        # aembed_query retrieves the vector representation for a query string
        return await self.embeddings.aembed_query(text)

    async def get_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Equivalent to manual batching. Replaces multi-element array encoding with a single method.
        """
        # aembed_documents retrieves the vectors for a list of document strings
        return await self.embeddings.aembed_documents(texts)

# =====================================================================
# 3. LangChain Vector Database Integration
# =====================================================================
class LangChainVectorStore:
    """
    A vector store using LangChain's native InMemoryVectorStore.
    Replaces custom index storage and manual cosine similarity math.
    """
    
    def __init__(self, engine: LangChainEmbeddingsEngine):
        # We pass LangChain's embedding wrapper to the vector store wrapper.
        # The vector store will automatically call the embeddings engine internally when indexing or searching.
        self.vector_store = InMemoryVectorStore(embeddings=engine.embeddings)

    async def index_raw_documents(self, raw_docs: List[Document]) -> None:
        """
        Indexes raw documents. This abstracts away batching and embedding mapping.
        """
        # Convert custom Document objects into LangChain Core Document objects
        lc_docs = [
            LCDocument(
                page_content=doc.content,
                metadata={"id": doc.id, **doc.metadata}
            )
            for doc in raw_docs
        ]
        
        # add_documents embeds and indexes all documents in one step
        await self.vector_store.aadd_documents(lc_docs)
        logger.info(f"LangChain: Indexed {len(raw_docs)} documents.")

    async def similarity_search(self, query: str, k: int = 2) -> List[SearchResult]:
        """
        Retrieves top-K matches using LangChain's native similarity search.
        This completely hides the cosine similarity math from our codebase.
        """
        # similarity_search_with_relevance_scores returns (LCDocument, score)
        results = await self.vector_store.asimilarity_search_with_relevance_scores(query, k=k)
        
        search_results = []
        for doc, score in results:
            doc_id = doc.metadata.get("id", "")
            # Reconstruct original metadata by removing internal tracking fields
            clean_metadata = {k: v for k, v in doc.metadata.items() if k != "id"}
            
            search_results.append(
                SearchResult(
                    document=Document(id=doc_id, content=doc.page_content, metadata=clean_metadata),
                    similarity=score
                )
            )
            
        return search_results
