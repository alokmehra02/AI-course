# 05 — Structured Output & Grounding Q&A

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask  
**Focus:** Pydantic validation, JSON modes, grounding, citations, API choices.  
**Anchor project:** VoXgent.AI — call summaries, intent routing, Pinecone citations, CRM writes.

---

## A. Structured output fundamentals

### Q1. Why Pydantic validation at the API boundary?

**Say this:**

> The LLM returns text; your backend needs typed objects. **Pydantic** validates shape, types, enums, and max lengths before any side effect — CRM write, DB insert, Twilio transfer. On VoXgent, every call summary parsed into a `CallSummary` model. If validation fails, we retry once or set `needs_human: true`. Never trust the model output as correct just because it looks like JSON.

**Compare:**

> `json.loads` catches syntax errors only. Pydantic catches wrong enum, missing field, string where bool expected — the failures that break production routing.

**Follow-up:**

1. **FastAPI integration?**  
   **Say this:** Same Pydantic models for API responses and LLM parsing — one source of truth, OpenAPI docs for free.

---

### Q2. JSON mode vs function calling for structured output?

**Say this:**

> **JSON mode** forces valid JSON in the response — good for a single blob like `{ "intent": "...", "summary": "..." }`. **Function calling** defines a tool whose parameters *are* the schema — model "calls" `return_summary` with typed args. Both can work; OpenAI **structured outputs** with `response_format: json_schema` is the strictest JSON mode.

**Compare:**

> | | JSON mode | Function calling as output |
> |--|-----------|----------------------------|
> | Best for | Final API response | When you already use tools in the turn |
> | Strictness | Varies by provider | Schema on tool parameters |
> | Risk | Extra prose wrappers | Model may call wrong tool name |

**Follow-up:**

1. **VoXgent choice?**  
   **Say this:** Structured output / JSON schema for call summaries and intent. Separate tools for CRM actions — output shape vs side effects kept separate.

---

### Q3. Retry on schema validation failure?

**Say this:**

> Catch `ValidationError`, append to messages: "Your JSON failed validation: {error}. Return only valid JSON matching schema." **Retry once** — often fixes missing enum or wrong type. Second failure → safe default (`needs_human: true`) or 503 — never partial write to CRM.

**Compare:**

> Infinite retry burns money and loops. One retry fixes most transient format slips; two failures means model or schema mismatch — escalate.

**Follow-up:**

1. **Log retries?**  
   **Say this:** Yes — metric `llm_schema_retry_rate` alerts if schema or prompt regressed.

---

### Q4. OpenAI structured outputs — what changed?

**Say this:**

> OpenAI **structured outputs** with `strict: true` on JSON Schema constrain decoding so the model **must** match schema — fewer retries than old JSON mode. Fields, required keys, enums enforced by provider. I still run Pydantic afterward — belt and suspenders at the FastAPI boundary.

**Compare:**

> Old JSON mode = valid JSON, wrong shape possible. Strict structured outputs = provider guarantees schema compliance (within documented limits). Still validate enums and business rules in code.

**Follow-up:**

1. **Limitations?**  
   **Say this:** Schema size limits, not all JSON Schema features, some models only. Check docs for `anyOf` and recursion limits.

---

### Q5. Enums, Literal, and Field constraints in schemas?

**Say this:**

> Use `Literal["billing", "support"]` or enums for **routing fields** — intent, action_items. `Field(max_length=500)` on summaries. `confidence: float = Field(ge=0, le=1)`. Tight schemas reduce hallucinated category names that break switch statements downstream.

**Follow-up:**

1. **Too strict?**  
   **Say this:** Add `other` enum with `needs_human` rather than free string intent — predictable fallback path.

---

## B. Grounding & citations

### Q6. What is grounding?

**Say this:**

> **Grounding** means tying the model answer to **verifiable sources** — retrieved chunks, web results, or API data — not pure parametric memory. Reduces hallucination. On VoXgent, answers about policy came from Pinecone chunks; summary included `citations` with doc_id and chunk_id for audit.

**Compare:**

> Ungrounded = model guesses from training. RAG-grounded = private docs. Web-grounded = live public data. Best production answers often combine retrieved context + structured tool facts.

**Follow-up:**

1. **Grounding vs hallucination control?**  
   **Say this:** Grounding is the main fix for factual Q&A; structured output + HITL is the fix for actions.

---

### Q7. Gemini grounding metadata — how is it different?

**Say this:**

> Gemini can return **grounding metadata** — which web chunks supported each sentence, with URLs and confidence. Google handles retrieval + attribution in one API. Useful for consumer apps needing source links without building full RAG.

**Compare:**

> Gemini grounding = managed web grounding. Pinecone RAG = you own ingest, chunking, tenant filters. Enterprise private docs usually need your RAG; public fact checks may use Gemini or Bing grounding APIs.

**Follow-up:**

1. **Use on VoXgent?**  
   **Say this:** Private tenant docs in Pinecone, not Gemini web grounding — data residency and control. Same citation *idea* in our response schema.

---

### Q8. How do you show citations in the UI?

**Say this:**

> Return structured `sources: [{ doc_id, title, snippet, page, score }]` alongside answer. UI renders footnotes or sidebar links — click opens original PDF chunk. For voice, cite briefly ("according to your fee schedule…"); full links in SMS follow-up or portal.

**Compare:**

> Inline `[1]` markers in prose = fragile parsing. Structured citations array = UI flexibly renders chips, tooltips, compliance audit.

**Follow-up:**

1. **What if chunk wrong but cited?**  
   **Say this:** Eval retrieval quality — citation of bad chunk is honest but wrong answer. Fix retrieval/rerank, not just UI.

---

### Q9. Hallucinated citations — problem and fix?

**Say this:**

> Models invent doc IDs or URLs that look real. Fix: **only cite IDs from retrieved_docs in state** — post-process answer to attach citations from retrieval results, or force model to pick from allowed list in schema enum. Reject citations not in context. Never trust free-form "Source: policy.pdf page 99" without lookup.

**Compare:**

> Prompt "only cite provided docs" helps; **code enforcement** — filter `citations` against `state.retrieved_docs` — is what production needs.

**Follow-up:**

1. **VoXgent pattern?**  
   **Say this:** Retrieved chunks passed with stable chunk_id; summary schema citations must reference those IDs; validator drops unknown ids.

---

### Q10. Grounding vs RAG for private docs?

**Say this:**

> **RAG** is the pattern for private docs — embed, retrieve, inject context, generate. **Grounding** is the outcome — answers anchored to that context. "Grounding" sometimes means provider-native features (Gemini, Google Search tool); **RAG is how you ground on enterprise data** Pinecone cannot leak across tenants.

**Compare:**

> Public web → search/grounding API may suffice. Private HIPAA/SOC2 docs → full RAG pipeline with tenant filters and audit.

**Follow-up:**

1. **Can you skip RAG?**  
   **Say this:** Only if docs fit in context once and rarely change — otherwise retrieval is required for scale and freshness.

---

## C. APIs & web search

### Q11. Responses API vs Chat Completions?

**Say this:**

> **Chat Completions** = messages in, assistant message out — what most LangChain/LangGraph apps use. **Responses API** = newer OpenAI surface with built-in tool types (web search, file search, computer use), reasoning models, and unified item stream. Pick Responses when you want hosted tools; Completions when you orchestrate everything in LangGraph.

**Compare:**

> Completions + your RAG = full control, portable. Responses + hosted web search = faster to ship public research bot, less control over retrieval logic.

**Follow-up:**

1. **VoXgent stack?**  
   **Say this:** Chat Completions / standard chat models inside LangGraph nodes — we own Pinecone retrieval and Twilio flow.

---

### Q12. When use web search tool vs RAG?

**Say this:**

> **Web search** for time-sensitive public info — news, stock prices, competitor launches. **RAG** for proprietary policies, contracts, product docs. Classify query first or offer both tools; merge results with clear source labels. Never web-search for data that should stay in tenant vector DB.

**Compare:**

> Web = freshness, less control. RAG = privacy, tenant isolation, you own eval.

**Follow-up:**

1. **Risk of web search tool?**  
   **Say this:** Untrusted page content → prompt injection. Sanitize snippets, do not execute instructions from web pages.

---

### Q13. Streaming vs structured output?

**Say this:**

> Streaming improves UX for long prose. **Structured JSON** usually needs full completion before parse — though some APIs stream JSON tokens. Voice on VoXgent streamed **spoken** text; structured summary generated at end of call in one non-streamed call or final node.

**Compare:**

> Do not stream partial JSON to parser — wait for complete object or use provider strict mode with buffer.

**Follow-up:**

1. **Partial JSON handling?**  
   **Say this:** Use JSON schema mode; avoid parsing incomplete stream unless using specialized partial JSON libraries.

---

### Q14. Validation at API boundary — double validation pattern?

**Say this:**

> Provider strict schema **plus** Pydantic in FastAPI **plus** business rules (refund amount ≤ order total). Each layer catches different failures. CRM write only after all three pass.

**Follow-up:**

1. **Redundant?**  
   **Say this:** Provider can change; Pydantic is your contract. Business rules are not in JSON Schema.

---

### Q15. Master compare — grounding strategies (30 seconds)

**Say this:**

> "For VoXgent private policy Q&A I ground with Pinecone RAG and structured citations in the response. For live CRM facts I ground with tool calls, not the model memory. For public research I would add an allowlisted web search tool or Responses API search — never mix tenant docs with web without labeling sources. Structured Pydantic output at the boundary makes every grounded answer machine-actionable."

---

**Related:** Infosys [03 Structured Output](../Infosys_Interview_Prep/03_Structured_Output_LLM_Integration_Grounding.md) · [Artifact lesson 4](../Artifacts/lesson_4_advanced_grounding_and_apis.md) · [04 MCP & Agents](./04_MCP_Tools_Agentic_AI_QA.md) · [02 RAG Pipeline](./02_RAG_Pipeline_QA.md) · Infosys [02 RAG Deep Dive](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md)
