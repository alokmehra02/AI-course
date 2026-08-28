# Infosys Interview Prep — Alok Mehra

Python Developer · **RAG · LangChain · LangGraph** · 2–5 YOE band

---

## How to use these docs

Every question in **01–06** uses the same layout:

| Label | What it means |
|-------|----------------|
| **Say this** | Exact words you can speak in the interview — read aloud until it feels natural |
| **Compare** | Short LangChain vs LangGraph (or RAG vs fine-tune, PDF parser vs one-size-fits-all, etc.) — use when they ask *why* |
| **Follow-up** | What they often ask next + a short **Say this** answer |

**Tips**
- Keep answers 30–90 seconds unless they ask for depth
- Always tie back to **VoXgent** or **Europa** when you can
- Use **Compare** lines — interviewers like "LangChain does X, but in production LangGraph because Y"
- Avoid fancy words — speak like you explain to a teammate

---

## Files in this folder

| File | Topics | Priority |
|------|--------|----------|
| [01_General_Interview_QA.md](./01_General_Interview_QA.md) | Intro, resume, Python, GCP, HR, scenarios | Round 1 + HR |
| [02_RAG_Deep_Dive_QA.md](./02_RAG_Deep_Dive_QA.md) | Full RAG stack (60 Qs) | **Highest** |
| [03_Structured_Output_LLM_Integration_Grounding.md](./03_Structured_Output_LLM_Integration_Grounding.md) | JSON output, APIs, grounding | Technical round |
| [04_LangChain_LangGraph_Agents_QA.md](./04_LangChain_LangGraph_Agents_QA.md) | LangChain vs LangGraph, agents | **JD keywords** |
| [05_Embeddings_VectorDB_Retrieval_QA.md](./05_Embeddings_VectorDB_Retrieval_QA.md) | Embeddings, Pinecone, hybrid search | Deep follow-ups |
| [06_RAG_Pipeline_Step_by_Step.md](./06_RAG_Pipeline_Step_by_Step.md) | Pipeline walkthrough + speakable Q&A per step | *"Explain your pipeline"* |

---

## Anchor story (memorize this)

**VoXgent.AI:** RAG with LangChain + LangGraph + Pinecone → grounded voice agents → tool calling to Salesforce / EMR / Sheets → GCP Pub/Sub + Cloud Tasks for 500+ concurrent outbound calls → human transfer + call summaries.

**Compare line for LangGraph:** *"LangChain chains are fine for retrieve-then-answer. VoXgent needed loops — retry retrieval, call a tool, then answer or transfer to human. That control flow is why we used LangGraph in production."*

---

## Last-hour drill (say aloud)

1. Tell me about yourself  
2. What is RAG + your pipeline  
3. LangChain vs LangGraph  
4. How do you stop hallucinations  
5. Structured output + grounding  
6. Production issue (campaign scheduler)  
7. Why Infosys  
