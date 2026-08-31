# 07 — Evaluation, Guardrails & Production Q&A

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask  
**Focus:** RAGAS, golden sets, CI regression, security, tenancy, on-call, cost.  
**Anchor project:** VoXgent.AI — Pinecone RAG eval, LangGraph tracing, GCP scale, tenant isolation.

---

## A. Evaluation fundamentals

### Q1. What is RAGAS and which metrics matter?

**Say this:**

> **RAGAS** is a framework for RAG evaluation — automated scores without human label for every query. Key metrics: **faithfulness** (answer supported by context?), **answer relevancy** (does it address the question?), **context precision** (retrieved chunks useful?), **context recall** (did we retrieve what we needed?). I use these to compare chunking or reranker changes before shipping.

**Compare:**

> Single accuracy number hides failures — high relevancy with low faithfulness = fluent hallucination. Track all four on golden set.

**Follow-up:**

1. **Production threshold?**  
   **Say this:** Set team bar e.g. faithfulness > 0.85 on golden set; block deploy if drops > 2 points vs baseline.

---

### Q2. Golden datasets — how build?

**Say this:**

> Curate **50–200 real user questions** with expected answer points or ideal citations — from support tickets, call logs (redacted), SME-written. Include **hard negatives** — ambiguous, multi-hop, wrong tenant traps. Version in git as JSON; update when product docs change.

**Compare:**

> Synthetic only = easy scores, false confidence. Real user questions = messy but representative.

**Follow-up:**

1. **VoXgent example?**  
   **Say this:** Billing dispute questions with expected policy chunk_ids and `needs_human` flag for edge cases.

---

### Q3. LLM-as-judge — bias and limits?

**Say this:**

> Use strong model to score weaker pipeline output — "rate faithfulness 1–5." Fast but **biased** — same family model favors itself, lenient on verbosity. Mitigate: diverse judge model, rubric with examples, calibrate against human labels on subset, never judge solely for compliance-critical metrics.

**Compare:**

> Human eval = gold standard, expensive. LLM judge = scale. RAGAS metrics = middle ground with fixed formulas.

**Follow-up:**

1. **When human required?**  
   **Say this:** Regulated content, new product launch, after incident — sample 100 calls human-reviewed.

---

### Q4. Regression testing in CI?

**Say this:**

> On PR: run golden set against staging index and model — compare RAGAS scores and exact routing fields (`intent`, `needs_human`) to baseline. Fail build if faithfulness drops or CRM tool called on wrong fixtures. Mock external APIs; use fixed Pinecone namespace or local pgvector for reproducibility.

**Compare:**

> Manual "try 5 questions" before release vs automated — only CI catches prompt drift at 2 AM merge.

**Follow-up:**

1. **Flaky LLM scores?**  
   **Say this:** Run twice take median; use temperature 0 for eval; accept small variance with threshold bands.

---

### Q5. Offline vs online evaluation?

**Say this:**

> **Offline** = golden set before deploy. **Online** = production thumbs down, implicit signals (human transfer rate, repeat question), A/B metrics. Offline catches regressions; online catches distribution shift users actually ask.

**Follow-up:**

1. **Metric for VoXgent voice?**  
   **Say this:** `% calls needing unplanned human transfer`, `RAG confidence below threshold`, average tool errors per call.

---

### Q6. Faithfulness vs answer relevancy?

**Say this:**

> **Faithfulness** = claims match retrieved context (no extra facts). **Relevancy** = on-topic response. Model can be faithful but useless ("I don't know" is faithful) or relevant but unfaithful (plausible wrong answer). Production needs both high.

---

## B. Observability & tracing

### Q7. LangSmith / tracing — what to trace?

**Say this:**

> Trace full chain: input question → retrieval chunks (ids, scores) → prompt → LLM output → tool calls → final response. LangSmith or OpenTelemetry spans per LangGraph node. Link `call_id` / `trace_id` from Twilio through entire graph. Debug "why wrong answer call 4821" in minutes not hours.

**Compare:**

> Print logging = unusable at 500 concurrent calls. Structured traces with searchable metadata = production requirement.

**Follow-up:**

1. **PII in traces?**  
   **Say this:** Redact or hash phone numbers; store chunk ids not full PHI in third-party SaaS unless BAA signed.

---

### Q8. What do you log vs not log in prod?

**Say this:**

> **Log:** latency, tokens, model version, retrieval scores, tool names, error types, tenant_id, trace_id. **Do not log:** full prompts with PHI, API keys, raw credit card audio transcripts in clear text unless encrypted and compliant.

---

## C. Security & guardrails

### Q9. Prompt injection defenses?

**Say this:**

> Layered: **structural** — tools and writes not controlled by retrieved text; **instruction hierarchy** — system prompt separated, delimiters on untrusted content; **input filters** — block known jailbreak patterns (weak alone); **output validation** — Pydantic routing; **HITL** for risky actions; **monitoring** — spike in tool calls after doc ingest.

**Compare:**

> "Ignore previous instructions" in user message vs hidden in PDF — both need same structural defenses for RAG.

**Follow-up:**

1. **VoXgent?**  
   **Say this:** Tenant RAG, no auto-refund from chunk text, human transfer on sensitive intents.

---

### Q10. OWASP LLM Top 10 — which apply to you?

**Say this:**

> Know the list for interviews: **LLM01 Prompt Injection**, **LLM02 Insecure Output Handling**, **LLM06 Sensitive Info Disclosure**, **LLM08 Excessive Agency** (too many tools), **LLM09 Overreliance**. Map each to your controls — Pydantic, read-only tools, tenant filter, HITL, eval.

**Follow-up:**

1. **Excessive agency example?**  
   **Say this:** Agent with delete-user tool on customer chatbot — remove or gate with approval.

---

### Q11. PII redaction — where?

**Say this:**

> Redact at **ingest** (mask in chunks), **log** (strip before Cloud Logging), **LLM send** (optional tokenize SSN/phone), **export** to analytics. Re-identification only in secure CRM with auth — not in vector metadata.

**Compare:**

> Redact before embed vs after — before embed prevents PII in vector DB which is harder to purge.

---

### Q12. Output filtering?

**Say this:**

> Block profanity, competitor mentions, medical advice disclaimers if required. Regex + small classifier on final string before TTS on voice. Fail closed to safe phrase if filter trips.

---

### Q13. Input sanitization?

**Say this:**

> Max length on user input, strip control chars, rate limit per user/tenant. Do not pass raw HTML from web scrape into prompt without cleaning.

---

## D. Production operations

### Q14. Rate limits — where apply?

**Say this:**

> Per user, per tenant, per IP on FastAPI; provider rate limits on OpenAI; Pinecone QPS; CRM API quotas. Queue excess with 429 and retry-after. Prevents abuse and runaway agent loops burning budget.

**Follow-up:**

1. **VoXgent outbound campaigns?**  
   **Say this:** Pub/Sub + Cloud Tasks throttle concurrent calls — same discipline for LLM API concurrency per campaign.

---

### Q15. Semantic cache pitfalls?

**Say this:**

> Cache embed(question) → answer for similar queries saves cost. **Pitfalls:** stale policy after doc update (TTL + invalidate on ingest), **cross-tenant leak** if cache key lacks tenant_id, wrong answer cached for paraphrase that changed intent, embedding model change invalidates keys.

**Compare:**

> Exact match cache = safe but low hit rate. Semantic cache = higher hit, needs tenant + version in key.

**Follow-up:**

1. **Cache key design?**  
   **Say this:** `hash(tenant_id + normalized_q + index_version + model_id)`.

---

### Q16. Tenant isolation audit?

**Say this:**

> Quarterly test: tenant A token, ask for tenant B doc name, assert retrieval empty and answer refuses. Audit Pinecone metadata filters in code path — every query, no bypass route. Log violations if any chunk wrong tenant. Same for SQL text-to-SQL and CRM tools.

**Follow-up:**

1. **How bug happens?**  
   **Say this:** Debug endpoint without filter, or filter taken from user message instead of JWT.

---

### Q17. On-call for LLM provider outages?

**Say this:**

> Runbook: detect elevated 5xx/latency from OpenAI → flip **fallback model** (GPT-4o → mini or Azure secondary) via feature flag → degrade non-critical features → status page message. VoXgent: prioritize live calls — shorter answers, RAG-only, defer summaries to queue.

**Compare:**

> Multi-provider gateway costs engineering; single provider with fallback model is common first step.

**Follow-up:**

1. **What to monitor?**  
   **Say this:** Error rate, p95 latency, token usage anomaly, zero retrieval results spike.

---

### Q18. Cost dashboard — what track?

**Say this:**

> Per tenant, per feature, per model: tokens in/out, embedding cost, Pinecone read units, tool calls. Daily budget alerts. Cost per successful call vs per human transfer — justify RAG investment to client.

**Follow-up:**

1. **Top cost driver on VoXgent?**  
   **Say this:** Often outbound campaign volume × (STT + LLM + TTS) — optimize model routing and cache FAQ answers.

---

### Q19. A/B testing models?

**Say this:**

> Split traffic 90/10 on mini vs full model for classification node only — compare human transfer rate and faithfulness on sampled calls. Never A/B voice quality without consent on enterprise clients — contract may forbid.

**Compare:**

> Offline golden set first; online A/B for subtle UX metrics offline misses.

---

### Q20. Fallback models strategy?

**Say this:**

> Tier: primary → secondary provider or smaller model → rule-based ("please hold for agent"). Configure in LLM gateway env vars; no redeploy. Smaller model for intent, larger for final answer if budget tight.

---

### Q21. SLA for AI features?

**Say this:**

> Define realistic SLAs — p95 latency 3s for voice turn, 99.5% availability excluding provider outages. Document **graceful degradation** as part of SLA — not guaranteed perfect answer every time, guaranteed safe behavior.

---

### Q22. Guardrails libraries (Guardrails AI, NeMo)?

**Say this:**

> Know they exist — schema validation, toxic language checks, rail definitions. Many teams use **Pydantic + custom filters** first; add library when rails proliferate. Interview: name one, explain you'd wrap final output.

---

### Q23. Context precision vs recall in prod?

**Say this:**

> Low **precision** = noisy context, confused model. Low **recall** = right doc not retrieved, hallucination or "I don't know." Tune top_k, hybrid search, reranker; measure separately on golden set with labeled relevant chunk_ids.

---

### Q24. How prove RAG got better after change?

**Say this:**

> "We changed chunk size 512→768, reran golden set: faithfulness +4 pts, recall +6, latency +80ms acceptable, deployed behind flag, monitored transfer rate 48h — flat." Numbers beat "it feels better."

---

### Q25. Master compare — production AI checklist (30 seconds)

**Say this:**

> "Ship with golden-set RAGAS regression in CI, tenant filter on every retrieval, Pydantic on every LLM output, tool allowlists and HITL for writes, traces with call_id, rate limits and cost caps, on-call runbook for provider failover, and quarterly tenant isolation audit. VoXgent voice added latency caps and human transfer as the ultimate guardrail."

---

**Related:** [Artifact lesson 5](../Artifacts/lesson_5_rag_production_pipeline.md) · [04 MCP & Agents](./04_MCP_Tools_Agentic_AI_QA.md) · [05 Structured Output](./05_Structured_Output_Grounding_QA.md) · Infosys [02 RAG](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) · [System Design Module 14](../System_Design_Prep/14_AI_LLM_System_Design.md)
