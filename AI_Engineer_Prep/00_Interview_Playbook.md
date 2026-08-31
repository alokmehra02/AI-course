# AI Engineer Interview — Playbook

> **What this makes you able to do:** structure any AI/LLM technical round — from "explain
> RAG" to "design an agent with tools" — without rambling or skipping production concerns.

---

## The 5 buckets every AI interview tests

| Bucket | What they probe | Your proof |
|--------|-----------------|------------|
| **Fundamentals** | Tokens, context, APIs, streaming | You count tokens; you know tool message rules |
| **RAG & retrieval** | Pipeline, chunking, eval, hallucination | You draw ingest → retrieve → generate |
| **Agents & tools** | LangGraph, MCP, loops, HITL | You explain VoXgent graph nodes |
| **Production** | Cost, latency, tenancy, guardrails | You mention tenant filter, Pydantic, timeouts |
| **Judgment** | RAG vs fine-tune, LangChain vs Graph | You give trade-offs, not buzzwords |

---

## Round types and how to open

### "Explain RAG / your pipeline" (10–15 min)

```
1. Problem     — "LLM alone hallucinates on private docs"
2. Pipeline    — ingest → chunk → embed → store → retrieve → prompt → generate
3. Your stack  — Pinecone, LangChain retriever, LangGraph orchestration
4. Quality     — hybrid search, rerank, eval set, citations
5. Production  — tenant filter, async ingest, cost per query
```

### "LangChain vs LangGraph" (5 min)

Use the **master compare** from Infosys 04 — 30 seconds, then one VoXgent example.

### "Design an agent with tools" (20–30 min)

```
1. Clarify     — sync or async? human approval? which tools?
2. Graph       — nodes: understand → retrieve → tool → respond / HITL / end
3. State       — what fields in state? (messages, retrieved_docs, tool_results)
4. Tools       — schema, auth, idempotency on writes
5. Failures    — tool timeout, bad JSON, max steps, injection
6. Eval        — golden paths + regression
```

### "MCP vs function calling" (5 min)

See [04_MCP_Tools_Agentic_AI_QA.md](./04_MCP_Tools_Agentic_AI_QA.md) Q1.

### System design AI round

Use [System Design Module 14](../System_Design_Prep/14_AI_LLM_System_Design.md) framework.

---

## Answer template (every technical question)

1. **One-sentence definition** — what it is
2. **Why it exists** — problem it solves
3. **How you used it** — VoXgent / Europa / side project
4. **Production caveat** — cost, security, eval, or failure mode
5. **Trade-off** — when you would *not* use it

Keep answers **30–90 seconds** unless they ask to go deeper.

---

## Questions you should ask them

- What does your RAG stack look like today — vector DB, orchestration?
- Is the role more **retrieval quality** or **agent orchestration**?
- How do you evaluate LLM features before release?
- On-call for model provider outages — fallback models?
- Data residency / tenant isolation requirements?

---

## Night-before checklist

- [ ] VoXgent story (2 min)
- [ ] RAG pipeline diagram on paper
- [ ] LangChain vs LangGraph (30 s)
- [ ] MCP one-liner
- [ ] 3 ways you reduce hallucination
- [ ] Text-to-SQL guardrails (read-only + AST)
- [ ] Infosys 04 master compare
- [ ] Infosys 02 Q1–Q10 skim

---

**Next:** [01 — LLM Fundamentals Q&A](./01_LLM_Fundamentals_QA.md)
