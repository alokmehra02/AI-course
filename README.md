# AI Course — Generative AI, RAG & LangGraph

Personal learning repo for **Generative AI**, **RAG**, **LangChain**, and **LangGraph** — with hands-on Python examples, system design prep, and Infosys interview prep.

**Author:** Aalok Singh Mehra  
**Email:** alokmehra02@gmail.com

---

## Repository structure

```
AI-course/
├── README.md                          ← You are here
├── Artifacts/                         ← Course notes (markdown lessons)
├── examples/                          ← Runnable Python examples
│   ├── llm_clients/                   ← Basic LLM API clients
│   ├── lesson_1_llm_fundamentals/     ← Tokens, messages, completions
│   └── lesson_2_embeddings/           ← Embeddings (manual, LangChain, LangGraph)
├── Infosys_Interview_Prep/            ← Interview Q&A (speakable answers)
├── System_Design_Prep/                ← System design interview study material
└── .gitignore
```

---

## Course lessons (`Artifacts/`)

| Lesson | Topic | File |
|--------|--------|------|
| 1 | LLM fundamentals (tokens, messages, APIs) | [lesson_1_llm_fundamentals.md](./Artifacts/lesson_1_llm_fundamentals.md) |
| 2 | Embeddings & vector search | [lesson_2_embeddings.md](./Artifacts/lesson_2_embeddings.md) |
| 3 | Text-to-SQL | [lesson_3_text_to_sql.md](./Artifacts/lesson_3_text_to_sql.md) |
| 4 | Grounding, structured output, APIs | [lesson_4_advanced_grounding_and_apis.md](./Artifacts/lesson_4_advanced_grounding_and_apis.md) |

Each lesson has matching code under `examples/` where applicable.

---

## Code examples (`examples/`)

### LLM clients (`examples/llm_clients/`)

| File | Description |
|------|-------------|
| `manual_llm_client.py` | Raw HTTP / OpenAI SDK |
| `langchain_llm_client.py` | Same flow with LangChain |
| `langgraph_llm_client.py` | Same flow with LangGraph |

### Lesson 1 — LLM fundamentals (`examples/lesson_1_llm_fundamentals/`)

| File | Description |
|------|-------------|
| `llm_fundamentals_manual.py` | Manual implementation |
| `llm_fundamentals_langchain.py` | LangChain version |
| `llm_fundamentals_langgraph.py` | LangGraph version |
| `verify_lesson1.py` | Quick verification script |
| `verify_lesson1_fundamentals.py` | Fundamentals verification |

### Lesson 2 — Embeddings (`examples/lesson_2_embeddings/`)

| File | Description |
|------|-------------|
| `embeddings_manual.py` | Manual embedding + similarity |
| `embeddings_langchain.py` | LangChain retriever pattern |
| `embeddings_langgraph.py` | LangGraph embedding workflow |
| `verify_lesson2.py` | Verification script |

**Setup (typical):**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install openai langchain langchain-openai langgraph
export OPENAI_API_KEY="your-key"
```

---

## Infosys interview prep (`Infosys_Interview_Prep/`)

Structured Q&A for **Python Developer (RAG · LangChain · LangGraph)** — each question has:

- **Say this** — exact words to speak in the interview  
- **Compare** — LangChain vs LangGraph, RAG vs fine-tuning, etc.  
- **Follow-up** — likely next questions with short answers  

| # | File | Focus |
|---|------|--------|
| 01 | [General_Interview_QA.md](./Infosys_Interview_Prep/01_General_Interview_QA.md) | Intro, resume, Python, GCP, HR |
| 02 | [RAG_Deep_Dive_QA.md](./Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) | Full RAG stack (60 Qs) |
| 03 | [Structured_Output_LLM_Integration_Grounding.md](./Infosys_Interview_Prep/03_Structured_Output_LLM_Integration_Grounding.md) | JSON output, APIs, grounding |
| 04 | [LangChain_LangGraph_Agents_QA.md](./Infosys_Interview_Prep/04_LangChain_LangGraph_Agents_QA.md) | LangChain vs LangGraph, agents |
| 05 | [Embeddings_VectorDB_Retrieval_QA.md](./Infosys_Interview_Prep/05_Embeddings_VectorDB_Retrieval_QA.md) | Embeddings, Pinecone, hybrid search |
| 06 | [RAG_Pipeline_Step_by_Step.md](./Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md) | Ingestion → answer pipeline |

See [Infosys_Interview_Prep/README.md](./Infosys_Interview_Prep/README.md) for study order.

---

## System design prep (`System_Design_Prep/`)

Full system design interview study material — 17 modules covering everything from
requirements gathering to production RAG architecture. Every topic has a spoken
"say this in the interview" script, a real enterprise example with real numbers,
runnable code, trade-offs, and the follow-up questions interviewers actually ask.

| Track | Modules |
|-------|---------|
| **Framework** | [00 Interview Playbook](./System_Design_Prep/00_Interview_Playbook.md) · [01 Requirements & Estimation](./System_Design_Prep/01_Requirements_And_NFRs.md) |
| **Networking & APIs** | [02 Networking](./System_Design_Prep/02_Networking.md) · [03 API Design](./System_Design_Prep/03_APIs.md) · [04 Scaling & Load Balancing](./System_Design_Prep/04_Scaling_And_LoadBalancing.md) |
| **Data** | [05 SQL, ACID & Indexes](./System_Design_Prep/05_Databases_Relational.md) · [06 Replication & Sharding](./System_Design_Prep/06_Data_Distribution.md) · [07 Caching & CDN](./System_Design_Prep/07_Caching_And_CDN.md) |
| **Distributed systems** | [08 Messaging & Kafka](./System_Design_Prep/08_Messaging_And_Events.md) · [09 Reliability Patterns](./System_Design_Prep/09_Reliability_Patterns.md) |
| **Production** | [10 Security](./System_Design_Prep/10_Security.md) · [11 Observability & SRE](./System_Design_Prep/11_Observability_And_SRE.md) · [12 Architecture Styles](./System_Design_Prep/12_Architecture_Styles.md) · [13 Concurrency & Cost](./System_Design_Prep/13_Concurrency_And_Performance.md) |
| **AI system design** | [14 LLM & RAG System Design](./System_Design_Prep/14_AI_LLM_System_Design.md) |
| **Practice** | [15 Worked Case Studies](./System_Design_Prep/15_Case_Studies.md) · [16 Cheat Sheet & Study Plan](./System_Design_Prep/16_Cheatsheet_And_Drills.md) · [17 Redis, Kafka & Flash Sales](./System_Design_Prep/17_Redis_Kafka_Flash_Sale_Case_Studies.md) |

See [System_Design_Prep/README.md](./System_Design_Prep/README.md) for the study order.

---

## Quick links

- **Learn:** Start with `Artifacts/lesson_1_llm_fundamentals.md` + `examples/lesson_1_llm_fundamentals/`
- **Interview (AI):** Start with `Infosys_Interview_Prep/01` and `04` (LangChain vs LangGraph)
- **Interview (system design):** Start with `System_Design_Prep/00_Interview_Playbook.md`
- **Pipeline deep dive:** `Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md`

---

## License

Personal educational use.
