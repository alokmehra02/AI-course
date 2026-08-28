# Infosys Interview Q&A — Python Developer (RAG / LangChain / LangGraph)

**Candidate:** Alok Mehra  
**Role:** Python Developer with RAG, LangChain, LangGraph  
**Experience:** ~2 years  
**Anchor projects:** VoXgent.AI (Tudip Technologies), Europa Locks  
**Company pattern:** Infosys Delivery interviews mix **project deep-dives**, **core GenAI/RAG**, **Python + backend**, **SDLC / production ownership**, and light **DSA / scenario** questions. Expect 2–3 rounds (technical → managerial / HR).

---

## How to use this doc

Every question uses the same layout:

| Label | What it means |
|-------|----------------|
| **Say this** | Exact words you can speak — 30–90 seconds, simple English |
| **Compare** | Short side-by-side when they ask *why* (LangChain vs LangGraph, RAG vs fine-tune, etc.) |
| **Follow-up** | What they often ask next + a short spoken answer |

**Speak in this structure for project answers:** Problem → Your design → Tech choices → Outcome → Trade-off / what you'd improve.

---

## How Infosys interviews for this role typically look

| Round | Focus | What they probe |
|-------|--------|-----------------|
| Technical 1 | Resume + GenAI stack | RAG end-to-end, LangChain vs LangGraph, Pinecone, prompts, tool calling |
| Technical 2 / Manager | Design + ownership | Production issues, APIs, DB, GCP, independent delivery |
| HR / Soft | Fit | Why Infosys, notice period, teamwork, learning |

**What wins at ~2 YOE:** clear ownership stories, production thinking (latency, cost, retries, grounding), and ability to explain *why* you chose a design—not just tool names.

---

# SECTION 1 — Introduction & Behavioral (almost always asked)

### Q1. Tell me about yourself.

**Say this:**

> I'm Alok Mehra, a Python backend and Generative AI developer with almost two years of experience. I'm currently at Tudip Technologies, where I'm a core contributor to VoXgent.AI — an enterprise conversational AI voice platform.
>
> On VoXgent, I built RAG pipelines using LangChain, LangGraph, and Pinecone so agents answer from client knowledge, not made-up LLM text. I also built tool-calling flows for CRM updates, scheduling, and human transfer, and I solely owned an outbound campaign scheduler on GCP with Pub/Sub and Cloud Tasks for 500-plus concurrent calls.
>
> Before that, on Europa Locks — an IoT smart-lock project — I built a Fastify API gateway over eight microservices and improved performance by about 40% using Redis caching.
>
> I'm strong in Python, FastAPI, REST APIs, PostgreSQL, MongoDB, Redis, and production GenAI. I'm looking for a role where I can grow RAG and agent systems at scale, which is why this Infosys Python plus RAG plus LangGraph role fits well.

**Follow-up:**

1. **Why are you leaving your current company?**
   **Say this:**
   > I've learned a lot shipping VoXgent in a small team. Now I want enterprise-scale delivery, bigger client systems, and deeper ownership in RAG and LangGraph — which Infosys offers on this role.

2. **What is your notice period?**
   **Say this:**
   > [Give your exact notice period.] I'm ready to wrap handover cleanly and can start as soon as policy allows.

---

### Q2. Walk me through your most recent / most relevant project (VoXgent.AI).

**Say this:**

> VoXgent.AI is an enterprise voice AI platform for healthcare, sales, and support. Clients need agents that answer from their own documents and can take actions — not just chat.
>
> I owned the RAG layer: documents go through chunking, embeddings, Pinecone indexing, retrieval, and then context goes into the LLM through LangChain and LangGraph. On top of that I built tool-calling so the agent can call Salesforce, Canvas EMR, Google Sheets, SMS, and WhatsApp APIs.
>
> For outbound campaigns I designed a GCP scheduler with Pub/Sub and Cloud Tasks to handle 500-plus concurrent calls with retry and reschedule logic. I also handled Twilio webhooks for call lifecycle, intent-based human transfer, and live call summaries.
>
> In a three-person backend team we defined PostgreSQL and MongoDB schemas and API contracts. The result is a production platform with grounded answers and end-to-end automation across six-plus enterprise integrations.

**Follow-up:**

1. **What was the hardest part?**
   **Say this:**
   > Keeping voice latency low while RAG retrieval and tool calls run in real time. I solved it with tight chunk sizes, metadata filters, small top-k, caching hot queries, and LangGraph routing so we only call tools when needed.

2. **What would you improve if you had more time?**
   **Say this:**
   > Formal RAG evaluation in production — retrieval hit rate, faithfulness scores, and weekly failure sampling — instead of mostly manual transcript review.

---

### Q3. What was your individual contribution vs the team?

**Say this:**

> The backend team had three engineers. I personally owned the RAG pipelines with LangChain, LangGraph, and Pinecone; tool-calling and prompt orchestration on top of RAG; the full outbound campaign scheduler on GCP — design and development; several enterprise API integrations; and Twilio call lifecycle handling.
>
> Schema design and API contracts were shared work — I was a key contributor, not someone who only implemented tickets handed to me.

**Follow-up:**

1. **Did anyone else work on RAG?**
   **Say this:**
   > I led the RAG design and most of the implementation. Teammates helped with API wiring and reviews, but retrieval quality, chunking strategy, and LangGraph flow were my ownership.

---

### Q4. Why Infosys? Why this role?

**Say this:**

> Infosys Delivery works on large enterprise digital projects — exactly where GenAI and RAG create real business value, not just demos. This job description matches what I've already shipped: Python, RAG, LangChain, and LangGraph.
>
> I want to take my production experience from VoXgent and apply it across bigger client systems, while growing in design ownership, knowledge sharing, and handling production incidents — things Infosys expects from delivery engineers.

**Follow-up:**

1. **Why not a product startup?**
   **Say this:**
   > I've done fast-paced product work. Now I want depth on enterprise scale, client delivery, and long-running production systems — that's Infosys's strength.

---

### Q5. Strengths / Weaknesses.

**Say this:**

> **Strength:** End-to-end ownership. I can take a GenAI feature from design to production — RAG quality, APIs, cloud scheduling, and ops. Example: I owned both the RAG layer and the GCP campaign scheduler on VoXgent.
>
> **Weakness:** Early on I sometimes tuned prompts before checking if retrieval was good. Now I always check retrieval metrics first — hit rate and relevance — then tune prompts. I'm also building more formal evaluation, like RAGAS-style checks, for production monitoring.

**Follow-up:**

1. **Give an example of your strength in action.**
   **Say this:**
   > When outbound campaigns dropped retries under peak load, I traced Pub/Sub to Cloud Tasks, fixed idempotency and backoff, and stabilized 500-plus concurrent calls without double-dialing.

---

### Q6. A production issue you handled.

**Say this:**

> **Situation:** Outbound campaigns sometimes lost retries under peak load — some calls never got rescheduled.
>
> **Task:** Keep reliability for 500-plus concurrent calls without dialing the same person twice.
>
> **Action:** I traced the Pub/Sub to Cloud Tasks flow, fixed idempotency keys and retry backoff, added dead-letter-style handling, stored clearer task state in the database, and improved logging for Twilio webhook race conditions.
>
> **Result:** Stable concurrency with automated retry and reschedule, and fewer missed campaigns. I learned GenAI products fail as often on orchestration and state as on the LLM itself.

**Follow-up:**

1. **How did you debug it?**
   **Say this:**
   > Logs and task state in the DB first, then traced message flow Pub/Sub → worker → Cloud Tasks → Twilio callback. The bug was missing idempotency on retry enqueue, not the LLM.

---

### Q7. Conflict / disagreement / learning from another project.

**Say this:**

> On Europa Locks, the team debated whether to cache at the API gateway or inside each microservice. I pushed for Redis at the gateway for hot reads, with clear TTLs and cache-key design, while keeping write paths consistent so data stayed correct.
>
> Performance improved about 40%. I learned to back opinions with latency numbers and a rollback plan — useful when client stakeholders disagree on design at Infosys-scale projects.

**Follow-up:**

1. **What if your approach had failed?**
   **Say this:**
   > We had TTL-based expiry and could disable caching per route. I measured before and after so we could revert quickly if hit rate or stale data became a problem.

---

# SECTION 2 — RAG (highest weight for this JD)

### Q8. What is RAG? Why not just use a large context window or fine-tuning?

**Say this:**

> RAG means Retrieval-Augmented Generation. You search relevant documents, put them in the prompt as context, and the LLM answers from that context — so answers are grounded in real enterprise data.
>
> We used RAG on VoXgent because each client has different policies, products, and docs that change often. Fine-tuning is slow to update and doesn't reliably inject fresh facts. Stuffing everything into a huge context window is expensive, noisy, and still gets stale.

**Compare:**

| | **RAG** | **Fine-tuning** | **Huge context window** |
|---|---------|-----------------|-------------------------|
| Fresh data | Re-index docs | Retrain / fine-tune again | Must paste/update context each time |
| Cost at scale | Cheaper per query | Training cost + maintenance | High token cost |
| Best for | Changing enterprise knowledge | Style, tone, task behavior | Small, static doc sets |
| VoXgent fit | ✅ Client KBs across domains | ❌ Facts change too often | ❌ Too slow and expensive for voice |

**Follow-up:**

1. **When would you fine-tune instead?**
   **Say this:**
   > When you need consistent tone, format, or domain language — not when facts change weekly. On VoXgent we fine-tuned behavior through prompts and tools; knowledge came from RAG.

---

### Q9. Explain your RAG pipeline end-to-end.

**Say this:**

> First, **ingestion** — collect documents and knowledge-base content from client sources.
>
> Second, **preprocess** — clean text, normalize format, add metadata like domain, source, and date.
>
> Third, **chunking** — split into pieces sized for good retrieval, with overlap so sentences at boundaries aren't lost.
>
> Fourth, **embeddings** — convert chunks to vectors using the same model we'll use at query time.
>
> Fifth, **index** — store vectors in Pinecone with metadata filters for client, domain, and doc type.
>
> At **query time**, embed the user's question, run similarity search with filters, get top-k chunks, build a prompt with system instructions plus retrieved context plus user query plus chat history, then generate the answer. We log sources and latency, and fall back to human transfer if confidence is low.

**Follow-up:**

1. **Where do most failures happen?**
   **Say this:**
   > Usually retrieval — wrong chunk, wrong filter, or bad chunking — not the LLM. That's why I log query, retrieved chunks, and final answer together.

---

### Q10. How do you choose chunk size and overlap?

**Say this:**

> It's a trade-off. Chunks too small lose context. Chunks too large make embeddings vague and waste tokens.
>
> I start by domain: FAQs and policies often work at 300 to 800 tokens; longer narrative docs can be bigger. Overlap around 10 to 20 percent keeps sentences split across boundaries from getting lost.
>
> Then I **evaluate retrieval** — if answers miss info that spans two chunks, I increase size or overlap. If retrieval returns noisy irrelevant text, I shrink chunks or improve metadata filters. For voice agents I keep context tight for speed.

**Follow-up:**

1. **Fixed size or semantic chunking?**
   **Say this:**
   > I often start fixed with overlap for speed, then move to semantic or heading-based splits for messy docs. On VoXgent, tight chunks plus metadata worked for voice latency.

---

### Q11. What is an embedding? Cosine similarity?

**Say this:**

> An embedding is a list of numbers — a vector — that captures the meaning of text. Similar meanings sit close together in vector space.
>
> Cosine similarity measures the angle between two vectors — how similar their direction is. It works well for normalized embeddings in search. Pinecone runs approximate nearest-neighbor search on these vectors and returns the top-k closest chunks to the query embedding.

**Follow-up:**

1. **Must index and query use the same embedding model?**
   **Say this:**
   > Yes. Different models live in different vector spaces. Mixing them breaks retrieval quality.

---

### Q12. Dense vs sparse retrieval? Hybrid search?

**Say this:**

> **Dense retrieval** uses embeddings — great when the user paraphrases, like "what's covered for dependents" vs "dependent benefits policy."
>
> **Sparse retrieval** uses keywords — great for exact IDs, codes, and rare terms like "policy 12.3" or a product SKU.
>
> **Hybrid search** combines both, often with reciprocal rank fusion. In enterprise healthcare and sales, hybrid helps because users mix natural language and exact references.

**Compare:**

| | **Dense** | **Sparse (BM25)** | **Hybrid** |
|---|-----------|-------------------|------------|
| Strength | Paraphrases, semantics | Exact terms, IDs | Both |
| Weakness | Misses rare exact tokens | Misses paraphrases | More moving parts |
| When | Default for RAG | Codes, SKUs, policy numbers | Production enterprise KBs |

**Follow-up:**

1. **Did VoXgent use hybrid?**
   **Say this:**
   > Mostly dense with strong metadata filters on Pinecone. For docs heavy on codes and IDs, I'd add BM25 or hybrid — that's a natural next step.

---

### Q13. How do you reduce hallucinations in RAG?

**Say this:**

> First, tell the model clearly: answer only from the retrieved context; say "I don't know" if it's not there.
>
> Second, fix retrieval — better top-k, metadata filters, re-ranking, or hybrid search so the right chunks actually arrive.
>
> Third, cite sources or return chunk IDs so answers stay tied to documents.
>
> Fourth, add confidence checks and human transfer when grounding is weak — we did intent-based transfer on VoXgent.
>
> Fifth, use low temperature for factual tasks and evaluate faithfulness, not just fluent-sounding answers.

**Follow-up:**

1. **Can you ever eliminate hallucinations completely?**
   **Say this:**
   > No, but you can push them down with good retrieval, strict prompts, refusals, and escalation. Production goal is measurable groundedness, not zero risk.

---

### Q14. What if retrieval returns irrelevant chunks?

**Say this:**

> I debug in order: Is the query embedding correct? Are metadata filters too wide or too narrow? Is chunking breaking meaning? Is top-k too high?
>
> Fixes include query rewriting or HyDE, stricter pre-filters on client and domain, a cross-encoder re-ranker on top of vector search, and MMR for diversity so you don't get ten near-duplicate chunks.
>
> In production I log query → retrieved chunks → what the model used, and sample failures weekly.

**Follow-up:**

1. **What is re-ranking?**
   **Say this:**
   > Vector search gets a broad top-20 fast; a re-ranker scores query-chunk pairs more accurately and picks the best top-5 for the prompt. Better accuracy, small extra latency.

---

### Q15. Vector DB — why Pinecone? Alternatives?

**Say this:**

> We used Pinecone because it's managed, scales well, supports metadata filtering, and let us ship fast without running our own vector infra.
>
> Alternatives: FAISS for local or self-hosted; Chroma for dev; Qdrant, Weaviate, or Milvus if you want self-managed control; pgvector if you're already on Postgres. Choice depends on scale, SLA, filtering needs, and how much ops the team can handle.

**Compare:**

| | **Pinecone** | **FAISS** | **pgvector** |
|---|--------------|-----------|--------------|
| Ops | Managed | You host | Inside Postgres |
| Metadata filters | Strong | DIY | SQL + vectors |
| Best for | Fast production RAG | Research / on-prem | Already on Postgres |

**Follow-up:**

1. **Would you pick Pinecone again for Infosys client work?**
   **Say this:**
   > If the client allows managed SaaS and needs speed — yes. If data must stay in-client VPC or Postgres — pgvector or self-hosted Qdrant/Milvus.

---

### Q16. How do you update / delete knowledge in the index?

**Say this:**

> Every chunk stores metadata like doc_id and chunk_id. When a document updates, delete all old vectors for that doc_id, re-chunk, re-embed, and upsert the new vectors.
>
> For multi-tenant systems, always filter by tenant_id so one client never sees another's data. Version metadata helps rollback if a bad ingest goes out.

**Follow-up:**

1. **Full re-index vs incremental?**
   **Say this:**
   > Incremental for day-to-day doc changes. Full re-index when embedding model or chunk strategy changes — otherwise old and new vectors don't match.

---

### Q17. Latency budget for a real-time voice RAG agent?

**Say this:**

> Voice is unforgiving on delay. I budget roughly 50 to 200 milliseconds for retrieval, keep top-k small, use metadata filters to avoid scanning junk, cache frequent queries in Redis, and run safe tool calls in parallel when possible.
>
> Stream tokens where the stack allows. Prefer a tight, relevant context over dumping twenty chunks. On VoXgent, every extra second hurts the call experience.

**Follow-up:**

1. **What do you cut first under pressure?**
   **Say this:**
   > Lower top-k, skip re-ranker on hot paths, cache embeddings for repeat questions, and use a smaller/faster model for simple intents before full RAG.

---

# SECTION 3 — LangChain & LangGraph (explicit JD skills)

### Q18. What is LangChain? When do you use it?

**Say this:**

> LangChain is a Python framework for building LLM apps. It gives you building blocks — prompts, retrievers, chains, tools, memory, output parsers — so you don't rewrite glue code every time.
>
> I use it to standardize RAG plus tool wiring. It's great for linear pipelines like retrieve-then-generate. For complex multi-step agents with loops and branching, I prefer LangGraph.

**Compare:**

| | **LangChain** | **LangGraph** |
|---|---------------|---------------|
| Model | Chains, LCEL pipelines | Graph of nodes with shared state |
| Flow | Mostly linear / DAG | Loops, branches, cycles |
| Best for | RAG glue, tools, parsers | Stateful agents, routing, retries |
| VoXgent | Chains for simple RAG steps | Graph for call flows with tools + transfer |

**Follow-up:**

1. **What is LCEL?**
   **Say this:**
   > LangChain Expression Language — a way to pipe steps like prompt, model, parser with the pipe operator. Readable for simple flows; not enough alone for complex agent control.

---

### Q19. What is LangGraph? How is it different from LangChain chains?

**Say this:**

> LangGraph models your agent as a graph — nodes do work, edges move state forward, and you can loop back.
>
> It keeps explicit **state** — messages, retrieved docs, tool results, intent flags — shared across steps.
>
> LangChain chains are mostly one-way: prompt, retrieve, generate. LangGraph handles "retrieve, maybe call a tool, maybe retrieve again, summarize, or transfer to human" — that's what VoXgent needed in production.

**Compare:**

| | **LangChain chain** | **LangGraph** |
|---|---------------------|---------------|
| Control flow | Sequential | Conditional edges, cycles |
| State | Passed step to step | Typed shared state object |
| Human-in-the-loop | Harder | Built-in patterns |
| Example | FAQ bot | Voice agent with tools + escalation |

**Follow-up:**

1. **When would you NOT use LangGraph?**
   **Say this:**
   > Simple one-shot RAG Q&A with no tools and no branching — a plain chain is less overhead.

---

### Q20. Explain State, Nodes, Edges, conditional routing in LangGraph.

**Say this:**

> **State** is a shared typed dictionary — things like messages, retrieved documents, intent, and tool results. Every node reads and updates it.
>
> **Nodes** are functions — retrieve node, generate node, tool node, human-transfer node.
>
> **Edges** connect nodes. **Conditional edges** pick the next node based on rules — for example, if confidence is low or `needs_human` is true, route to transfer instead of generate.
>
> Loops let the agent re-retrieve or ask a clarifying question until an exit condition is met.

**Follow-up:**

1. **How do you avoid infinite loops?**
   **Say this:**
   > Max iteration count, clear exit flags in state, and conditional edges that force END or human handoff after N tries.

---

### Q21. Multi-agent vs single-agent — when?

**Say this:**

> **Single-agent** — one LLM with tools. Simpler, lower latency, easier to debug. Enough for most voice bots and client assistants.
>
> **Multi-agent** — separate roles like planner, retriever, compliance checker. Better when domains conflict or you need isolation, but more tokens, latency, and orchestration pain.
>
> My Multi-Agent Chatbot side project used specialized agents. VoXgent production leaned on one strong agent plus RAG plus tools for reliability.

**Compare:**

| | **Single-agent** | **Multi-agent** |
|---|------------------|-----------------|
| Complexity | Low | High |
| Latency | Lower | Higher |
| Debug | Easier | Harder |
| VoXgent | ✅ Production choice | Side project experiment |

**Follow-up:**

1. **When would you split into multi-agent?**
   **Say this:**
   > When compliance, billing, and support need hard separation, or when one prompt can't cover conflicting policies without role split.

---

### Q22. Tool / function calling — how does it work?

**Say this:**

> You give the LLM a list of tools with name, description, and JSON parameter schema. The model returns a structured tool call — which tool and with what arguments — instead of only plain text.
>
> Your app runs the tool — for example, update Salesforce — puts the result back into the conversation, and the model continues to a final answer.
>
> On VoXgent, RAG handled knowledge and tools handled actions. Critical rules: validate arguments, set timeouts, make writes idempotent, and never let the model run unrestricted side effects.

**Follow-up:**

1. **What if the model calls the wrong tool?**
   **Say this:**
   > Tighter tool descriptions, fewer tools exposed at once, validation layer before execution, and human confirmation for high-risk writes like CRM updates.

---

### Q23. Prompt engineering patterns you used.

**Say this:**

> Clear role and hard rules — "use only retrieved context."
>
> Few-shot examples for tone and tool-call format.
>
> Structured JSON output for summaries, intents, and CRM fields.
>
> Separate system, user, and tool messages so the model doesn't confuse instructions with data.
>
> Domain-specific prompts — healthcare tone vs sales tone.
>
> Iteration on real call transcripts, not toy examples.

**Follow-up:**

1. **How do you test prompt changes?**
   **Say this:**
   > Golden set of real queries, compare retrieval plus answer quality before/after, and roll out behind a flag if possible.

---

### Q24. Memory in conversational agents.

**Say this:**

> **Short-term memory** — last N turns in graph state or Redis during the call.
>
> **Long-term memory** — summarize older turns; store user preferences in DB.
>
> For fact memory, embed important past facts and retrieve them like RAG when relevant.
>
> In voice, keep memory lean for latency. After the call ends, persist a summary to the database for the next interaction.

**Follow-up:**

1. **Full history vs summary?**
   **Say this:**
   > Full history blows token budget fast. Summarize older turns, keep recent turns verbatim, retrieve long-term facts only when needed.

---

# SECTION 4 — Python & Backend (always expected)

### Q25. Why Python for GenAI backends?

**Say this:**

> Python has the best ecosystem for GenAI — LangChain, LangGraph, OpenAI SDKs, embedding libraries. You can iterate fast.
>
> Async with FastAPI and asyncio fits I/O-heavy work — LLM calls, DB, HTTP — which is most of a RAG service. Pydantic helps validate tool arguments and API contracts so bad LLM output doesn't crash production.

**Follow-up:**

1. **Any downside of Python here?**
   **Say this:**
   > CPU-bound work and the GIL — so heavy parsing or embedding batches go to workers or queues, not the async event loop.

---

### Q26. FastAPI vs Flask / Django for this work?

**Say this:**

> **FastAPI** — async-native, automatic OpenAPI docs, Pydantic validation. Perfect for LLM microservices and webhook-heavy systems like Twilio.
>
> **Flask** — lighter but you wire validation and async yourself.
>
> **Django** — great for full web apps with admin and ORM; heavier than needed for a focused RAG API.
>
> We used FastAPI on VoXgent.

**Compare:**

| | **FastAPI** | **Flask** | **Django** |
|---|-------------|-----------|------------|
| Async | Native | Needs extra setup | Mostly sync |
| Validation | Pydantic built-in | Manual | DRF / forms |
| OpenAPI | Auto | Plugins | DRF schema |
| Fit for RAG API | ✅ Best match | OK for small services | Overkill for microservice |

**Follow-up:**

1. **Why not Node like Europa?**
   **Say this:**
   > GenAI libraries and team speed pointed to Python for VoXgent. Same design ideas — gateway, cache, async I/O — different stack for AI tooling.

---

### Q27. Explain async/await — why it matters for LLM apps.

**Say this:**

> LLM and HTTP calls spend most time waiting on the network, not using CPU. Async lets one worker handle many concurrent waits — campaigns, webhooks, parallel tool calls — without blocking a thread per request.
>
> Use async HTTP clients like httpx. Don't run heavy CPU work on the event loop — offload to a worker process instead.

**Follow-up:**

1. **Async vs threading for LLM apps?**
   **Say this:**
   > Async wins for many concurrent I/O-bound requests with less memory than thousands of threads. Thread pools help for blocking libraries you can't avoid.

---

### Q28. REST API design principles you follow.

**Say this:**

> Resource-based URLs, correct HTTP status codes, idempotent PUT and DELETE where it matters, pagination for lists, authentication with JWT or API keys, versioning, and a consistent error format.
>
> Add rate limiting and observability. On Europa I built a gateway over eight-plus services with auth, rate limits, and logging — same principles apply to VoXgent APIs.

**Follow-up:**

1. **How do you version APIs?**
   **Say this:**
   > URL prefix like /v1/ or header-based version. Breaking changes get a new version; old version deprecated with a timeline.

---

### Q29. SQL vs NoSQL — how you used both.

**Say this:**

> **PostgreSQL** for relational data — users, campaigns, call state, anything needing joins and strong consistency.
>
> **MongoDB** for flexible documents — configs, semi-structured payloads, agent metadata that changes shape often.
>
> **Redis** for cache, short-lived session state, and speed between services.
>
> Pick based on query patterns and consistency needs, not hype.

**Compare:**

| | **PostgreSQL** | **MongoDB** | **Redis** |
|---|----------------|-------------|-----------|
| Data shape | Structured, relational | Flexible documents | Key-value / cache |
| VoXgent use | Campaigns, call state | Agent configs | Hot query cache |
| Consistency | Strong transactions | Document-level | Ephemeral / TTL |

**Follow-up:**

1. **When would you pick only Mongo?**
   **Say this:**
   > Rapidly evolving document schemas with few cross-document transactions. VoXgent still needed Postgres where campaign state and billing-like data needed ACID.

---

### Q30. Transactions, indexes, N+1 — quick hits.

**Say this:**

> Index columns in WHERE and JOIN — but don't over-index writes.
>
> Use transactions when multiple rows must stay consistent — e.g., update campaign state and enqueue a task together.
>
> Avoid N+1 queries with joins or eager loading.
>
> For RAG, index tenant and domain fields in both SQL metadata tables and vector DB filters.

**Follow-up:**

1. **Example of N+1?**
   **Say this:**
   > Loading 100 campaigns then one query per campaign for calls — fix with a join or `WHERE campaign_id IN (...)`.

---

### Q31. Docker / Kubernetes awareness.

**Say this:**

> I containerize services with Docker for consistent deploys — did this on my multi-agent project too.
>
> Kubernetes runs replicas, health checks, and rolling updates — relevant when Infosys clients run multi-service GenAI backends.
>
> I understand pods, services, and deployments conceptually and have hands-on Docker plus cloud deploy experience on GCP.

**Follow-up:**

1. **What goes in the Dockerfile for a FastAPI RAG service?**
   **Say this:**
   > Slim Python base, install deps from lockfile, copy app code, non-root user, expose port, health check endpoint, run uvicorn with workers sized to CPU.

---

# SECTION 5 — Cloud, Scale & System Design (matches your resume + Infosys delivery)

### Q32. Explain your GCP Pub/Sub + Cloud Tasks campaign scheduler.

**Say this:**

> Pub/Sub decouples producers — when someone creates a campaign — from consumers that process dial jobs.
>
> Cloud Tasks schedules and executes work with retries and rate control so we don't overwhelm Twilio or our workers.
>
> Design goals: 500-plus concurrent calls, automated retry and reschedule, no duplicate dials using idempotency keys. State lives in the database; workers are idempotent; failures follow retry policy then alerting.
>
> This is classic async enterprise design — not just "call an LLM."

**Follow-up:**

1. **Why not cron for this?**
   **Say this:**
   > Cron doesn't handle per-call retries, backoff, and dynamic load at 500-plus concurrency. Queue plus task system gives control and durability.

---

### Q33. How would you design a production RAG service for an Infosys client?

**Say this:**

> **Ingestion service** — batch and incremental doc updates.
>
> **Embedding workers** — queue-based so ingest doesn't block queries.
>
> **Vector index** — separate namespace per tenant.
>
> **Query API** — auth, rate limit, retrieve then generate, optional re-ranker.
>
> **Observability** — latency, token cost, retrieval hit rate, groundedness.
>
> **Safety** — PII redaction, prompt-injection defenses, audit logs.
>
> **Fallbacks** — search-only answer, canned response, human handoff.
>
> Deploy as FastAPI microservices on cloud with Redis cache for hot queries.

**Follow-up:**

1. **How do you handle a doc upload spike?**
   **Say this:**
   > Queue embedding jobs, scale workers horizontally, throttle per tenant, and serve queries from the existing index while new chunks stream in.

---

### Q34. How do you secure a RAG system?

**Say this:**

> Authentication and authorization per tenant. Mandatory metadata filters on every retrieval query.
>
> Encrypt data at rest and in transit. Never put secrets in prompts.
>
> Sanitize retrieved text against prompt injection — like "ignore previous instructions" hidden in a document.
>
> Limit tool permissions — read-only vs write. Log access to sensitive docs. RBAC for admin ingestion endpoints.

**Follow-up:**

1. **What is prompt injection in RAG?**
   **Say this:**
   > Malicious text in a uploaded doc that tries to override system instructions. Mitigate with input sanitization, strict system prompts, and never executing instructions from retrieved content as code.

---

### Q35. Cost optimization for LLM apps.

**Say this:**

> Cache embeddings and frequent Q&A pairs. Use smaller models for routing and classification; bigger models only when needed.
>
> Compress context — smaller top-k, summarize long chunks. Batch embedding jobs offline.
>
> Monitor tokens per request and set budgets per tenant. Cheaper models for summarization; stronger models for complex reasoning only.

**Follow-up:**

1. **Biggest cost driver on VoXgent?**
   **Say this:**
   > LLM tokens on long contexts plus voice stack. Tight retrieval and caching repeat questions helped most.

---

# SECTION 6 — DSA / Coding (Infosys often includes light coding)

Practice aloud; keep solutions clean.

### Q36. Reverse a string / check palindrome / two sum / frequency count.

**Say this:**

> For **two sum**, I use a hash map. One pass through the array — for each number, check if `target minus number` is already in the map. If yes, return both indices. If no, store the current number and its index. Time O(n), space O(n). Same pattern works for frequency count with a dict.

Be ready in Python with clear complexity:

```python
# Two Sum - O(n) time, O(n) space
def two_sum(nums, target):
    seen = {}
    for i, x in enumerate(nums):
        if target - x in seen:
            return [seen[target - x], i]
        seen[x] = i
    return []
```

**Follow-up:**

1. **Palindrome check approach?**
   **Say this:**
   > Two pointers from start and end, compare characters, skip non-alphanumeric if needed. O(n) time, O(1) extra space.

---

### Q37. Deduplicate chunks / merge intervals style (RAG-flavored).

**Say this:**

> **Merge intervals** — sort by start time, walk through, merge if current start is before or equal to last end, else start a new interval. Useful when merging overlapping text spans or time windows from retrieved chunks. Time O(n log n) for sort, O(n) merge.

```python
def merge_intervals(intervals):
    intervals.sort()
    out = []
    for s, e in intervals:
        if not out or s > out[-1][1]:
            out.append([s, e])
        else:
            out[-1][1] = max(out[-1][1], e)
    return out
```

**Follow-up:**

1. **RAG use case for merge intervals?**
   **Say this:**
   > Overlapping chunks from the same doc section — merge spans before sending to the LLM to cut duplicate tokens.

---

### Q38. Rate limiter / sliding window (API gateway relevance).

**Say this:**

> **Token bucket** — tokens refill at a fixed rate; each request costs one token; burst allowed up to bucket size.
>
> **Fixed window** — count requests per minute per client; simple but can spike at window boundaries.
>
> **Sliding window** — smoother limit over rolling time — often implemented with Redis sorted sets or counters.
>
> On Europa we used Redis for distributed rate limiting at the gateway so all service instances shared the same counts.

**Follow-up:**

1. **Redis key design?**
   **Say this:**
   > Key like `ratelimit:{client_id}:{window}` with TTL matching window length; INCR or sorted-set timestamps for sliding window.

---

### Q39. OOP basics they may ask.

**Say this:**

> **Encapsulation** — hide internal state, expose methods. **Inheritance** — child class extends parent. **Polymorphism** — same interface, different behavior. **Abstraction** — hide implementation details behind an interface.
>
> Example: a `Retriever` interface with `PineconeRetriever` and `FAISSRetriever` implementations — swap vector backend without changing the RAG chain.

**Follow-up:**

1. **Composition vs inheritance?**
   **Say this:**
   > Prefer composition — wrap a retriever inside a service — over deep inheritance trees. Easier to test and swap parts.

---

# SECTION 7 — OS / DB / SDLC (from Infosys "Additional Responsibilities")

### Q40. Process vs thread; concurrency.

**Say this:**

> A **process** has its own memory space. A **thread** shares memory inside a process.
>
> Python's GIL limits CPU-bound threads — they don't run Python bytecode in parallel on multiple cores. For CPU work, use multiprocessing. For I/O-bound LLM and HTTP work, asyncio plus async workers is the right fit.

**Follow-up:**

1. **Why is VoXgent mostly I/O-bound?**
   **Say this:**
   > Waiting on LLM APIs, Pinecone, Postgres, Twilio, and external CRM APIs — async keeps throughput high without hundreds of threads.

---

### Q41. What is SDLC? Where have you practiced it?

**Say this:**

> SDLC is Software Development Life Cycle — requirements, design, implement, test, deploy, maintain.
>
> On VoXgent I wrote design specs for APIs and RAG flows, implemented features, tested integrations, deployed to GCP, handled production issues, and documented knowledge for the team. Infosys delivery expects exactly that loop.

**Follow-up:**

1. **Which phase do you spend most time in?**
   **Say this:**
   > Implement and maintain — but good design upfront on RAG and scheduler saved us from costly rework in production.

---

### Q42. How do you test a RAG / agent system?

**Say this:**

> **Unit tests** for chunking logic and tool wrappers.
>
> **Contract tests** for external APIs.
>
> **Golden Q&A set** — known questions with expected grounded answers.
>
> **Retrieval metrics** — recall at k and answer faithfulness.
>
> **Load tests** for webhooks and scheduler under peak concurrency.
>
> **Staging** with production-like anonymized data. Manual transcript review for voice quality.

**Follow-up:**

1. **How is testing RAG different from normal APIs?**
   **Say this:**
   > Output is non-deterministic — you test retrieval quality and groundedness ranges, not one exact string every time.

---

### Q43. How do you handle production incidents?

**Say this:**

> Triage severity first — customer impact and data risk.
>
> Mitigate fast — rollback, feature flag, or disable a tool.
>
> Root cause from logs and traces.
>
> Fix, deploy, write a short postmortem, and add a knowledge article so the team doesn't repeat the mistake.
>
> Tell stakeholders early with an ETA — Infosys client delivery expects clear communication.

**Follow-up:**

1. **Severity 1 example from your work?**
   **Say this:**
   > Campaign retries failing at peak — calls not rescheduled. Mitigated with idempotency fix and backoff tuning; communicated impact window to the team.

---

# SECTION 8 — Resume deep-dive "trap" questions (prepare tightly)

### Q44. Explain the ~40% performance improvement on Europa.

**Say this:**

> Redis caching for hot read paths and inter-service calls, plus API pagination to avoid heavy full-table scans.
>
> I measured latency and throughput before and after — not a guess. MQTT over TLS and Agora integration also improved realtime reliability by about 35%.
>
> Be ready to explain cache invalidation — TTLs and write-path consistency — and how we avoided cache stampedes on popular keys.

**Follow-up:**

1. **How did you invalidate cache on writes?**
   **Say this:**
   > TTL for most reads plus explicit delete or version bump on write for keys we knew had to be fresh immediately.

---

### Q45. Salesforce / Canvas EMR / Google Sheets integrations — challenges?

**Say this:**

> **Auth** — OAuth and API keys with token refresh.
>
> **Rate limits** — backoff and queue writes.
>
> **Schema mismatch** — CRM fields are strict; LLM output is messy. You need a validation layer mapping tool args to exact field types.
>
> **Retries and idempotency** — partial failures and duplicate tool calls must not double-write.
>
> Never let the LLM write directly without validation.

**Follow-up:**

1. **Example validation rule?**
   **Say this:**
   > Phone number must match E.164; required fields checked before Salesforce create; reject and ask user again if the model omits a mandatory field.

---

### Q46. Twilio webhook lifecycle — what events?

**Say this:**

> Events like call initiated, ringing, answered, completed, and failures. Status callbacks drive our state machine in the database.
>
> Must validate Twilio signature, return 200 fast, process heavy work async, and reconcile if webhooks arrive out of order.

**Follow-up:**

1. **Why return 200 quickly?**
   **Say this:**
   > Twilio retries on timeout. Slow handlers cause duplicate events and race conditions in call state.

---

### Q47. ElevenLabs Conversational AI — your role?

**Say this:**

> ElevenLabs was the conversational voice layer in the stack. My work was grounding via RAG, tool-calling orchestration with LangGraph, and backend event and API integration so voice agents stayed context-aware and could take real actions — not just talk.

**Follow-up:**

1. **Who owned the voice model vs backend?**
   **Say this:**
   > Voice synthesis and conversational layer from ElevenLabs; I owned backend RAG, tools, scheduler, and Twilio integration around it.

---

### Q48. Databricks GenAI Engineer Associate / GCP PCA — what did you learn that's relevant?

**Say this:**

> **Databricks cert** — GenAI lifecycle, RAG patterns, evaluation, responsible AI — vocabulary and structure for client conversations.
>
> **GCP Professional Cloud Architect** — designing scalable, secure, reliable cloud systems — directly applied in Pub/Sub, Cloud Tasks scheduler, and multi-service backends on VoXgent.

**Follow-up:**

1. **One PCA concept you used on VoXgent?**
   **Say this:**
   > Decouple with Pub/Sub, make workers stateless, push state to DB, design for retry and idempotency — standard reliable async pattern on GCP.

---

### Q49. Multi-Agent Chatbot project — difference from VoXgent?

**Say this:**

> **Multi-Agent Chatbot** — side project: FastAPI, MySQL, SQLAlchemy, modular agents, conversation memory, Docker. Shows initiative and agent design practice.
>
> **VoXgent** — production voice platform: Pinecone RAG, LangGraph, enterprise integrations, GCP scale, Twilio, 500-plus concurrent campaigns. Project proves learning; VoXgent proves delivery ownership.

**Follow-up:**

1. **Which one do you lead with in interviews?**
   **Say this:**
   > VoXgent always — it's production. I mention the side project as extra proof I explore agents beyond day job.

---

# SECTION 9 — Scenario / Case questions (Infosys loves these)

### Q50. Client PDF knowledge base is messy (tables, scans). How do you RAG it?

**Say this:**

> Don't just run naive text split on raw PDF bytes.
>
> Pipeline: detect if page is scan vs text → OCR for scans → extract tables to markdown or structured text → optionally describe figures with a vision model → chunk with layout-aware splitters → store metadata like page and section → evaluate on questions where the answer lives in a table or scan.
>
> Messy enterprise docs are a **parsing problem first**, chunking second.

**Follow-up:**

1. **What if OCR quality is poor?**
   **Say this:**
   > Human review queue for low-confidence pages, flag those docs in metadata, and fall back to human agent when retrieval confidence is low.

---

### Q51. Agent gives wrong CRM update. What do you do?

**Say this:**

> **Immediate:** disable the write tool or require human confirmation; pull audit logs; rollback or compensate data if possible.
>
> **Then:** tighten tool schema, add field validation, human-in-the-loop for high-risk writes, improve prompts, add regression tests from the failing call transcript.
>
> Treat it like a production incident with postmortem — not just a prompt tweak.

**Follow-up:**

1. **How prevent recurrence?**
   **Say this:**
   > Allow-list fields, dry-run mode in staging, confirmation step for deletes and large updates, and monitor tool error rate.

---

### Q52. Retrieval is slow under load.

**Say this:**

> Cache frequent query embeddings and answers in Redis. Reduce top-k. Scale Pinecone replicas or upgrade plan. Run retrieval async with tight timeout.
>
> Don't re-embed identical queries. Move heavy ingestion off the query path into background workers. If still slow, degrade gracefully — smaller context or cached FAQ path.

**Follow-up:**

1. **What metric tells you retrieval is the bottleneck?**
   **Say this:**
   > P95 retrieval latency spiking while LLM TTFT stays flat — fix index, filters, or cache before blaming the model.

---

### Q53. Two clients on same platform — data leak risk?

**Say this:**

> Hard tenant isolation — separate Pinecone namespaces or indexes per client, **plus** mandatory tenant_id filter at retrieval and in application code.
>
> Never trust the model to "only use client A docs." Bind auth token to tenant. Audit retrieval logs. Test cross-tenant access in QA deliberately.

**Follow-up:**

1. **Defense in depth?**
   **Say this:**
   > Filter in app layer even if vector DB filters exist; encrypt per-tenant if policy requires; separate ingestion credentials per client.

---

# SECTION 10 — Managerial / HR

### Q54. Are you open to client location / shifts / learning new stack?

**Say this:**

> Yes. Enterprise delivery often means client tech constraints, onsite or hybrid, and sometimes shift overlap with client timezone.
>
> I learn fast — I moved from Node on Europa to Python GenAI on VoXgent — and I keep engineering standards while adapting to client stack.

**Follow-up:**

1. **Any stack you won't work with?**
   **Say this:**
   > I'm flexible on tools. I care more about clear requirements, reasonable delivery practices, and learning support than a specific framework name.

---

### Q55. Where do you see yourself in 3 years?

**Say this:**

> Senior GenAI or backend engineer who designs production RAG and agent systems, mentors juniors, and owns delivery quality end to end — aligned with Infosys key contributor path, not just coding tickets.

**Follow-up:**

1. **Technical or people leadership?**
   **Say this:**
   > Technical depth first — architecture and production quality — with mentoring and client communication growing alongside.

---

### Q56. Current CTC / expected / notice period.

**Say this:**

> [Prepare exact numbers before the interview.]
>
> State current CTC honestly. Expected CTC framed on market range plus your GenAI production experience — stay flexible within Infosys band. Give exact notice period and earliest join date.

**Follow-up:**

1. **If they say budget is lower?**
   **Say this:**
   > Ask about growth path, project exposure, and learning on LangGraph at scale; negotiate within reason if role and learning fit is strong.

---

### Q57. Questions *you* should ask them.

**Say this:**

> I'd like to ask a few things:
>
> 1. Is the project greenfield RAG or improving an existing LangChain or LangGraph system?
> 2. Which vector DB and cloud — Azure, GCP, or AWS — does the client use?
> 3. How is success measured — accuracy, latency, CSAT, or cost?
> 4. Team size and what ownership you expect from me in the first 90 days?
> 5. How do you handle production support rotations?

**Follow-up:**

1. **If they answer "existing LangGraph system"?**
   **Say this:**
   > Great — I'd ask how they handle eval, tenant isolation, and on-call today so I can ramp on real constraints fast.

---

# SECTION 11 — Quick revision cheat sheet

Use with the **Say this / Compare / Follow-up** format above. One line per topic — expand aloud into 30–90 sec.

| Topic | One-liner → speak aloud |
|-------|-------------------------|
| RAG | Retrieve docs → put in prompt → generate grounded answer |
| RAG vs fine-tune | RAG for fresh facts; fine-tune for style and behavior |
| Chunking | Balance context vs precision; measure retrieval, don't guess |
| Embeddings | Meaning as vectors; **same model** for index and query |
| Pinecone | Managed vector DB + metadata filters |
| LangChain | Building blocks for LLM apps — chains, tools, retrievers |
| LangGraph | Stateful graph — loops, branches, agents, control flow |
| LangChain vs LangGraph | Chain = linear pipeline; Graph = multi-step stateful agent |
| Tool calling | Model picks tool → app runs it → result back to model |
| Hallucination | Better retrieval + strict prompt + refuse + human escalate |
| FastAPI vs Flask | FastAPI = async + Pydantic + OpenAPI for LLM services |
| SQL vs Mongo | Postgres for relational state; Mongo for flexible configs |
| Pub/Sub + Tasks | Decouple producers/consumers + schedule + retry at scale |
| Tenant isolation | Namespace + filter every query + never trust the model |
| Infosys fit | Independent delivery, SDLC, prod issues, knowledge sharing |
| Your anchor | VoXgent RAG + LangGraph + GCP scheduler; Europa gateway + Redis |

---

# 60-minute last-day practice plan

Uses **Say this** blocks in this file — read aloud, don't silently skim.

1. **10 min — Intro & project (Q1–Q2)**  
   Say full **Say this** blocks aloud until smooth. Time yourself — aim 60–90 sec each.

2. **20 min — RAG + LangGraph (Q8–Q21)**  
   Whiteboard pipeline from Q9. For Q18–Q19, speak the **Compare** tables in your own words.

3. **15 min — Production stories (Q6, Q32, Q44)**  
   Campaign scheduler + Europa 40% — practice **Follow-up** answers too.

4. **10 min — One DSA problem (Q36 or Q37)**  
   Code on blank editor, then say the **Say this** complexity explanation aloud.

5. **5 min — HR close (Q4, Q57)**  
   Why Infosys + your five questions for them.

**Self-check after each answer:** Did I say Problem → design → tech → outcome? Did I mention VoXgent or Europa?

---

# Red flags to avoid in answers

- Saying "LangChain does RAG for me" without explaining retrieve → generate steps.  
- Claiming fine-tuning when you mean prompting or RAG.  
- Metrics you can't explain (40%, 35%, 500+) — know assumptions and how you measured.  
- Speaking only tool names — always add trade-offs and production concerns.  
- Badmouthing current employer.  
- Reading **Compare** tables word-for-word — paraphrase naturally in simple English.

---

**Good luck, Alok.** Your VoXgent story is a near-perfect match for this JD — lead with RAG plus LangGraph ownership, then prove backend and production maturity with the GCP scheduler and Europa scale.
