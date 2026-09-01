# AI & Agentic AI Engineer — Interview Prep

Complete learning path and interview Q&A for **AI Engineer**, **LLM Engineer**, and
**Agentic AI Engineer** roles (~2–5 YOE). Built on top of your existing `Artifacts/`,
`examples/`, and `Infosys_Interview_Prep/` — this folder fills the gaps (MCP, eval,
production, fine-tuning vs RAG) and ties everything into one study plan.

**Author:** Aalok Singh Mehra  
**Stack:** Python · FastAPI · LangChain · LangGraph · Pinecone · GCP · OpenAI

---

## Start here

| If you have… | Do this |
|---|---|
| **1 week before interview** | [00 Playbook](./00_Interview_Playbook.md) + [04 MCP & Agents](./04_MCP_Tools_Agentic_AI_QA.md) + Infosys [04](../Infosys_Interview_Prep/04_LangChain_LangGraph_Agents_QA.md) |
| **Learning from scratch** | Week 1 below → Artifacts lesson 1 + `examples/lesson_1_*` |
| **RAG-focused round** | Infosys [02](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) + [06](../Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md) + [System Design Module 14](../System_Design_Prep/14_AI_LLM_System_Design.md) |
| **Agentic / MCP round** | [04 MCP](./04_MCP_Tools_Agentic_AI_QA.md) + Artifact [lesson 7](../Artifacts/lesson_7_mcp_and_tool_calling.md) + `examples/lesson_7_mcp/` |
| **Gemini Live voice (VoXgent)** | [Gemini Live Voice Agent Guide](./GEMINI_LIVE_VOICE_AGENT_INTERVIEW_GUIDE.md) |

---

## Topic matrix — everything an AI engineer interview covers

### Tier A — Must know cold (almost every interview)

| Topic | Learn | Practice | Interview Q&A |
|-------|-------|----------|---------------|
| Tokens & context window | [Artifact L1](../Artifacts/lesson_1_llm_fundamentals.md) | `examples/lesson_1_*` | [01](./01_LLM_Fundamentals_QA.md) |
| Messages, roles, tool messages | L1 | `llm_fundamentals_manual.py` | 01 |
| Temperature, top-p, streaming | L1 | streaming in manual client | 01 |
| Function / tool calling | L1, L7 | `lesson_7_mcp/` | [04](./04_MCP_Tools_Agentic_AI_QA.md) |
| Embeddings & similarity | [L2](../Artifacts/lesson_2_embeddings.md) | `lesson_2_embeddings/` | Infosys [05](../Infosys_Interview_Prep/05_Embeddings_VectorDB_Retrieval_QA.md) |
| RAG pipeline end-to-end | [L5](../Artifacts/lesson_5_rag_production_pipeline.md) | Infosys [06](../Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md) | [02](./02_RAG_Pipeline_QA.md) + Infosys [02](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) |
| Chunking & retrieval | L5, SD [14](../System_Design_Prep/14_AI_LLM_System_Design.md) | — | Infosys 02, 05 |
| LangChain vs LangGraph | [L6](../Artifacts/lesson_6_langgraph_and_agents.md) | `langgraph_llm_client.py` | Infosys [04](../Infosys_Interview_Prep/04_LangChain_LangGraph_Agents_QA.md) + [03](./03_LangChain_LangGraph_QA.md) |
| Structured output / Pydantic | [L4](../Artifacts/lesson_4_advanced_grounding_and_apis.md) | L1 manual (Pydantic) | Infosys [03](../Infosys_Interview_Prep/03_Structured_Output_LLM_Integration_Grounding.md) + [05](./05_Structured_Output_Grounding_QA.md) |
| Hallucination & grounding | L4, L5 | — | Infosys 02, 03 |
| MCP & tool protocols | [L7](../Artifacts/lesson_7_mcp_and_tool_calling.md) | `lesson_7_mcp/` | [04](./04_MCP_Tools_Agentic_AI_QA.md) |

### Tier B — Should know (agentic / senior-leaning)

| Topic | Learn | Interview Q&A |
|-------|-------|---------------|
| Agent loops (ReAct, plan-act) | L6, L7 | 03, 04 |
| LangGraph state, nodes, edges, checkpointing | L6 | Infosys 04, 03 |
| Human-in-the-loop (HITL) | L6 | 03, 04 |
| Text-to-SQL safely | [L3](../Artifacts/lesson_3_text_to_sql.md) | `lesson_3_text_to_sql/` + [06](./06_Text_to_SQL_QA.md) |
| Evaluation (RAGAS, golden sets) | L5 | [07](./07_Evaluation_Guardrails_Production_QA.md) |
| Guardrails & prompt injection | L5, L7 | 07 |
| RAG vs fine-tuning vs prompt eng | L5 | [08](./08_FineTuning_Prompting_Model_Choice_QA.md) |
| Vector DB choice (Pinecone, pgvector) | L2, SD 14 | Infosys 05 |
| Hybrid search & reranking | L5 | Infosys 05 |
| Multi-tenancy in RAG | L5, SD 14 | Infosys 02 |
| Cost & token management | L1, SD 14 | 01, 07 |
| AI system design (production RAG) | SD [14](../System_Design_Prep/14_AI_LLM_System_Design.md) | SD [15.10](../System_Design_Prep/15_Case_Studies.md) |

### Tier C — Know what it is (staff / niche)

| Topic | One-liner |
|-------|-----------|
| Multi-agent orchestration | Multiple LLM agents with supervisor — high latency; use when domains are truly separate |
| RLHF / DPO | How models are aligned post-training — you consume, rarely train |
| LoRA / QLoRA fine-tuning | Parameter-efficient fine-tune — when RAG is not enough |
| vLLM / inference serving | Self-hosted model throughput — batching, KV cache |
| CRAG / Self-RAG | Retrieval quality loops — research patterns |
| OWASP LLM Top 10 | Security checklist for LLM apps |

---

## 12-week learning path

| Week | Focus | Read | Build | Drill |
|------|-------|------|-------|-------|
| **1** | LLM fundamentals | Artifact L1, AI [01](./01_LLM_Fundamentals_QA.md) | `lesson_1_llm_fundamentals/*` | 10 Qs from 01 out loud |
| **2** | Embeddings & vectors | Artifact L2, Infosys 05 | `lesson_2_embeddings/*` | Cosine similarity by hand |
| **3** | RAG concepts | Infosys 02 (first 30 Qs) | Pinecone or pgvector mini index | Draw pipeline on paper |
| **4** | RAG production | Artifact L5, Infosys 06 | Ingest 5 PDFs → answer API | "Explain your RAG pipeline" |
| **5** | LangChain | Infosys 04 §A–B | `langchain_llm_client.py` + retriever | LCEL chain explain |
| **6** | LangGraph & agents | Artifact L6, Infosys 04 §C | `lesson_6_langgraph_agents/` | LangChain vs LangGraph 30s |
| **7** | MCP & tools | Artifact L7, AI [04](./04_MCP_Tools_Agentic_AI_QA.md) | `lesson_7_mcp/` | MCP vs function calling |
| **8** | Structured output & grounding | Artifact L4, Infosys 03 | Pydantic validation loop | JSON failure retry |
| **9** | Text-to-SQL | Artifact L3, AI [06](./06_Text_to_SQL_QA.md) | `lesson_3_text_to_sql/` | AST guardrails explain |
| **10** | Eval & guardrails | AI [07](./07_Evaluation_Guardrails_Production_QA.md) | 20 golden Q&A pairs | "How do you know RAG got better?" |
| **11** | Model choice & production | AI [08](./08_FineTuning_Prompting_Model_Choice_QA.md), SD 14 | LLM gateway sketch | RAG vs fine-tune |
| **12** | Mock interviews | AI [00](./00_Interview_Playbook.md), Infosys 01 | Full VoXgent story | 3 × 45 min mocks |

---

## Interview Q&A modules (this folder)

| # | File | Questions | Focus |
|---|------|-----------|-------|
| 00 | [Interview Playbook](./00_Interview_Playbook.md) | Framework | How to structure AI technical rounds |
| 01 | [LLM Fundamentals](./01_LLM_Fundamentals_QA.md) | 25 | Tokens, APIs, streaming, tool calling |
| 02 | [RAG Pipeline](./02_RAG_Pipeline_QA.md) | 20 | Unique Qs; **full set** in Infosys 02 |
| 03 | [LangChain & LangGraph](./03_LangChain_LangGraph_QA.md) | 15 | Extra agentic Qs; **full set** in Infosys 04 |
| 04 | [MCP & Agentic AI](./04_MCP_Tools_Agentic_AI_QA.md) | 30 | MCP, ReAct, multi-step agents, HITL |
| 05 | [Structured Output & Grounding](./05_Structured_Output_Grounding_QA.md) | 15 | JSON, citations, web grounding |
| 06 | [Text-to-SQL](./06_Text_to_SQL_QA.md) | 20 | Schema pruning, AST, self-correction |
| 07 | [Eval, Guardrails, Production](./07_Evaluation_Guardrails_Production_QA.md) | 25 | RAGAS, injection, observability, cost |
| 08 | [Fine-tuning vs RAG](./08_FineTuning_Prompting_Model_Choice_QA.md) | 15 | When to fine-tune, model routing |

**Also use:** [Infosys_Interview_Prep/](../Infosys_Interview_Prep/) (60+ RAG Qs, behavioral, resume)

---

## Artifacts (concept lessons)

| Lesson | Topic | Status |
|--------|-------|--------|
| [1](../Artifacts/lesson_1_llm_fundamentals.md) | Tokens, messages, streaming, tools | ✅ |
| [2](../Artifacts/lesson_2_embeddings.md) | Embeddings, vector search | ✅ |
| [3](../Artifacts/lesson_3_text_to_sql.md) | Text-to-SQL, guardrails | ✅ |
| [4](../Artifacts/lesson_4_advanced_grounding_and_apis.md) | Grounding, Responses API | ✅ |
| [5](../Artifacts/lesson_5_rag_production_pipeline.md) | Production RAG pipeline | ✅ NEW |
| [6](../Artifacts/lesson_6_langgraph_and_agents.md) | LangGraph, agent patterns | ✅ NEW |
| [7](../Artifacts/lesson_7_mcp_and_tool_calling.md) | MCP, tool calling | ✅ NEW |

---

## Code examples (`examples/`)

| Folder | Topic |
|--------|-------|
| `llm_clients/` | Manual, LangChain, LangGraph LLM clients |
| `lesson_1_llm_fundamentals/` | Tokens, tools, structured output |
| `lesson_2_embeddings/` | Manual + LangChain + LangGraph embeddings |
| `lesson_3_text_to_sql/` | Text-to-SQL with guardrails | ✅ NEW |
| `lesson_6_langgraph_agents/` | Refund agent graph | ✅ NEW |
| `lesson_7_mcp/` | MCP client + tool loop | ✅ NEW |

---

## Anchor story (memorize)

> **VoXgent.AI:** Production voice agents with RAG (LangChain retriever + Pinecone),
> orchestration in **LangGraph** (retrieve → classify → tool → respond or human transfer),
> tool calling to Salesforce / EMR / Google Sheets, **GCP Pub/Sub + Cloud Tasks** for
> 500+ concurrent outbound calls, structured outputs for CRM writes, tenant isolation on
> every retrieval.

**30-second LangGraph line:** *"LangChain wired RAG and tools. VoXgent needed loops —
retry retrieval, call CRM, transfer to human. That control flow is LangGraph."*

---

**Start:** [00 — Interview Playbook](./00_Interview_Playbook.md)
