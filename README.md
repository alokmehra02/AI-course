# AI Course — Generative AI, RAG & LangGraph

Personal learning repo for **Generative AI**, **RAG**, **LangChain**, and **LangGraph** — with hands-on Python examples and Infosys interview prep.

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

## Quick links

- **Learn:** Start with `Artifacts/lesson_1_llm_fundamentals.md` + `examples/lesson_1_llm_fundamentals/`
- **Interview:** Start with `Infosys_Interview_Prep/01` and `04` (LangChain vs LangGraph)
- **Pipeline deep dive:** `Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md`

---

## License

Personal educational use.
