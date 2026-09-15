# RAG at Scale — Million Documents Interview Prep

Your **strongest interview track**: you built an end-to-end RAG pipeline. Interviewers
probe two things hard:

1. **Scale** — “Process 1 million documents — draw the architecture.”
2. **Lifecycle** — cloud vs local sources, ingest into a chatbot, **update / delete** chunks correctly.

Plus AI depth: extraction, chunking, recursive splitters, embeddings, cosine similarity,
thresholds, hybrid search, cross-encoders, Graph-RAG, and **why RAG fails on summarization
when a PDF changes**.

**Author:** Aalok Singh Mehra · VoXgent (LangChain, LangGraph, Pinecone, GCP)

---

## Files in this folder

| # | File | What it is |
|---|------|------------|
| 01 | [Design — 1M Documents Architecture](./01_Design_1M_Documents_Architecture.md) | End-to-end system design for bulk ingest + query at scale |
| 02 | [Design — Cloud vs Local, Update & Delete](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md) | Two source cases + versioning, delete, re-index |
| 03 | [Q&A — System Design & Lifecycle (50)](./03_QA_System_Design_Ingestion_Lifecycle.md) | Speakable answers for architecture rounds |
| 04 | [Q&A — AI Pipeline: Chunk → Search → GraphRAG (50)](./04_QA_AI_Pipeline_Chunk_Embed_Search_GraphRAG.md) | Speakable answers for ML/AI depth rounds |

**Format (Q&A):** **Say this** · **Compare** · **Follow-up** — same as Infosys / AI_Engineer_Prep.

---

## How to study (1 week crash plan)

| Day | Focus | Read | Drill |
|-----|-------|------|-------|
| 1 | Draw 1M pipeline offline + online | 01 | Whiteboard: boxes only, no code |
| 2 | Cloud vs local + delete/update | 02 | Narrate delete of one PDF aloud |
| 3 | Chunking, embeddings, cosine | 04 Q1–Q25 | Threshold + hybrid in 60s |
| 4 | Rerank, hybrid, Graph-RAG failures | 04 Q26–Q50 | “Why summarization broke after PDF update” |
| 5 | Scale Q&A | 03 Q1–Q25 | Numbers: workers, shards, cost |
| 6 | Lifecycle Q&A | 03 Q26–Q50 | Soft delete vs hard delete |
| 7 | Mock | 01 + 02 diagrams | 45-min mock: “design RAG for 1M docs” |

---

## Anchor story (30 seconds)

> “On VoXgent I owned the RAG path: ingest client policies, chunk with structure awareness,
> embed, upsert to Pinecone with `tenant_id` metadata, retrieve with filters, optionally
> rerank, then generate in a LangGraph flow. At interview scale I’d keep the same **offline
> async ingest** and **online sync query** split — Postgres as source of truth for docs/chunks,
> vector + BM25 as derived indexes, and **delete/update as first-class events** so stale
> chunks never answer after a PDF is replaced.”

---

## Also study (existing repo)

| Topic | Where |
|-------|-------|
| Full RAG 60 Qs | [Infosys 02](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) |
| Pipeline walkthrough | [Infosys 06](../Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md) |
| Production RAG lesson | [Artifact L5](../Artifacts/lesson_5_rag_production_pipeline.md) |
| LLM system design | [SD 14](../System_Design_Prep/14_AI_LLM_System_Design.md) |
| AI engineer supplement | [AI 02](../AI_Engineer_Prep/02_RAG_Pipeline_QA.md) |

---

**Start:** [01 — 1M Documents Architecture](./01_Design_1M_Documents_Architecture.md)
