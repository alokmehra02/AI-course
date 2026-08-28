import logging
from typing import TypedDict, List, Dict, Any, Optional, Literal
from langgraph.graph import StateGraph, START, END
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from embeddings_langchain import LangChainEmbeddingsEngine, LangChainVectorStore, Document

logger = logging.getLogger("LangGraphEmbeddingsEngine")

# =====================================================================
# 1. State Definition
# =====================================================================
class IngestionRetrievalState(TypedDict):
    """
    State representing the context passed through our graph pipeline.
    """
    query: str
    retrieved_documents: List[Dict[str, Any]]
    best_similarity_score: float
    response: str
    api_key: str
    base_url: str
    model: str
    similarity_threshold: float

# =====================================================================
# 2. Graph Nodes
# =====================================================================
async def retrieve_documents_node(state: IngestionRetrievalState) -> dict:
    """
    Graph node that performs the vector database retrieval using embeddings.
    """
    logger.info(f"Retrieving documents for query: {state['query']}")
    
    # Initialize the LangChain embeddings client and vector store wrapper
    engine = LangChainEmbeddingsEngine(api_key=state["api_key"], base_url=state["base_url"])
    vector_store = LangChainVectorStore(engine)
    
    # Seed some mock documents to represent an existing corpus
    mock_corpus = [
        Document(
            id="doc_1", 
            content="Siemens is a global powerhouse focusing on the areas of electrification, automation and digitalization.",
            metadata={"source": "siemens_overview"}
        ),
        Document(
            id="doc_2", 
            content="FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.8+.",
            metadata={"source": "fastapi_docs"}
        ),
        Document(
            id="doc_3", 
            content="LangGraph is a library for building stateful, multi-actor applications with LLMs, used to create agent workflows.",
            metadata={"source": "langgraph_docs"}
        )
    ]
    
    # Index the mock corpus in-memory
    await vector_store.index_raw_documents(mock_corpus)
    
    # Retrieve top K match
    results = await vector_store.similarity_search(query=state["query"], k=1)
    
    if results:
        best_match = results[0]
        logger.info(f"Best match found: {best_match.document.id} with score {best_match.similarity}")
        return {
            "retrieved_documents": [{"id": best_match.document.id, "content": best_match.document.content}],
            "best_similarity_score": best_match.similarity
        }
    
    return {
        "retrieved_documents": [],
        "best_similarity_score": 0.0
    }

async def generate_answer_node(state: IngestionRetrievalState) -> dict:
    """
    Graph node that executes when similarity threshold is met.
    Formulates a response using the retrieved document context.
    """
    logger.info("Retrieved document is relevant. Generating answer using LLM.")
    
    llm = ChatOpenAI(
        model=state["model"],
        openai_api_key=state["api_key"],
        openai_api_base=state["base_url"],
        temperature=0.3
    )
    
    context = "\n".join([doc["content"] for doc in state["retrieved_documents"]])
    prompt = (
        f"You are a helpful assistant. Use the context below to answer the user query.\n\n"
        f"Context:\n{context}\n\n"
        f"Query: {state['query']}\n\n"
        f"Answer:"
    )
    
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return {"response": response.content}

async def fallback_handling_node(state: IngestionRetrievalState) -> dict:
    """
    Graph node that executes when similarity threshold is not met.
    Provides a safe, non-hallucinated response.
    """
    logger.warning("No highly relevant context was found in the vector database.")
    fallback_response = (
        f"I'm sorry, but I couldn't find any relevant technical information in our vector database "
        f"to answer the question: '{state['query']}'. Similarity score was only {state['best_similarity_score']:.2f}."
    )
    return {"response": fallback_response}

# =====================================================================
# 3. Conditional Edge Routing Logic
# =====================================================================
def route_retrieval_decision(state: IngestionRetrievalState) -> Literal["generate_answer", "fallback_handling"]:
    """
    Decides routing based on the best similarity score.
    """
    threshold = state.get("similarity_threshold", 0.7)
    score = state.get("best_similarity_score", 0.0)
    
    if score >= threshold:
        logger.info(f"Similarity score {score:.4f} >= threshold {threshold}. Routing to response generation.")
        return "generate_answer"
    
    logger.info(f"Similarity score {score:.4f} < threshold {threshold}. Routing to fallback handler.")
    return "fallback_handling"

# =====================================================================
# 4. LangGraph Engine Orchestrator
# =====================================================================
class LangGraphEmbeddingsEngine:
    """
    Builds and executes a stateful graph to process user requests via embeddings similarity.
    """
    
    def __init__(self, api_key: str, base_url: str = "https://api.openai.com/v1"):
        self.api_key = api_key
        self.base_url = base_url
        
        # Initialize StateGraph
        builder = StateGraph(IngestionRetrievalState)
        
        # Add processing nodes
        builder.add_node("retrieve_documents", retrieve_documents_node)
        builder.add_node("generate_answer", generate_answer_node)
        builder.add_node("fallback_handling", fallback_handling_node)
        
        # Define workflow paths
        builder.add_edge(START, "retrieve_documents")
        
        # Add conditional router based on cosine similarity score
        builder.add_conditional_edges(
            "retrieve_documents",
            route_retrieval_decision,
            {
                "generate_answer": "generate_answer",
                "fallback_handling": "fallback_handling"
            }
        )
        
        # Set endpoints
        builder.add_edge("generate_answer", END)
        builder.add_edge("fallback_handling", END)
        
        # Compile graph
        self.app = builder.compile()

    async def execute_rag_pipeline(
        self, 
        query: str, 
        model: str = "gpt-4o", 
        threshold: float = 0.7
    ) -> str:
        """
        Executes the compiled LangGraph workflow.
        """
        initial_state = {
            "query": query,
            "retrieved_documents": [],
            "best_similarity_score": 0.0,
            "response": "",
            "api_key": self.api_key,
            "base_url": self.base_url,
            "model": model,
            "similarity_threshold": threshold
        }
        
        final_state = await self.app.ainvoke(initial_state)
        return final_state["response"]
