# 02 — RAG Pipeline Interview Q&A

**Format:** **Say this** = speak in interview · **Compare** = why one vs other · **Follow-up** = next question they ask

**Note:** This file has **20 focused questions** on production RAG topics. The **full 60-question RAG set** lives in [Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) — study both.

**Audience:** Alok — ~2 years exp, VoXgent (RAG, LangGraph, Pinecone, voice agents, GCP), FastAPI/Python

---

## A. Chunking & indexing

### Q1. What chunking strategies do you use?

**Say this:**

> Depends on document type. **Fixed-size** — e.g. 512 tokens with overlap — good default for policies and FAQs. **Semantic chunking** splits on meaning boundaries — better for long prose. **Structure-aware** respects headings and sections in markdown or HTML. On VoXgent, healthcare policies used heading-based chunks so each section was one retrievable unit; sales scripts used smaller fixed chunks for tight matching.

**Compare:**

> **Small chunks** = precise retrieval, may lose context. **Large chunks** = more context, noisier search. **Overlap** = reduces boundary cuts — common 10–20% of chunk size.

**Follow-up:**

1. **How do you pick chunk size?**  
   **Say this:** Start 300–800 tokens, run eval recall@k on golden questions, adjust. Voice agents often prefer smaller top-k with tighter chunks.

---

### Q2. Why use chunk overlap?

**Say this:**

> Overlap repeats a few lines between consecutive chunks so a sentence split across a boundary still appears whole in at least one chunk. Without overlap, "coverage ends on December 31" might be cut in half and neither chunk ranks well. VoXgent used ~50–100 token overlap on dense policy PDFs.

**Follow-up:**

1. **Downside of overlap?**  
   **Say this:** More vectors to store and slightly redundant search results — dedupe at rerank or parent-child level.

---

### Q3. What metadata do you store with each chunk?

**Say this:**

> At minimum: `source`, `page`, `tenant_id`, `doc_version`, `chunk_index`. Optional: `section_title`, `last_updated`, `access_level`. Metadata powers filters — VoXgent never queried Pinecone without `tenant_id` from the auth token. Citations use `source` plus page for "according to your benefits guide page 4."

**Compare:**

> **Vector** = semantic match. **Metadata filter** = hard constraints — tenant, date, product line. Both together prevent cross-client leaks.

**Follow-up:**

1. **Can metadata hurt recall?**  
   **Say this:** Over-filtering can — if filter is wrong, you get zero results. Log empty retrieval and relax filters in a retry loop in LangGraph.

---

### Q4. What is parent-child chunking?

**Say this:**

> Index **small child chunks** for precise search, but each child points to a **parent chunk** with full section context. Retrieve on children, pass parent text to the LLM so the answer has surrounding context. VoXgent considered this for long policy sections — search hit the paragraph, prompt got the full section.

**Compare:**

> **Single chunk size** = simpler pipeline. **Parent-child** = better precision plus context — more ingest logic and storage.

**Follow-up:**

1. **How do you implement in Pinecone?**  
   **Say this:** Child vectors in index with metadata `parent_id`; fetch parent text from object storage or a second lookup by ID.

---

## B. Retrieval quality

### Q5. What is hybrid search and when do you need it?

**Say this:**

> Hybrid combines **dense** vector search with **sparse** keyword search — BM25 or Pinecone hybrid. Vectors catch paraphrases; keywords catch exact IDs, drug names, SKU codes. VoXgent used pure vector for most clients; hybrid when users queried exact policy numbers or product codes that embeddings missed.

**Compare:**

> **Vector only** = semantic, misses rare tokens. **Keyword only** = exact match, misses paraphrase. **Hybrid** = best recall, more infra — merge scores with weighted sum or RRF.

**Follow-up:**

1. **How do you merge scores?**  
   **Say this:** Reciprocal Rank Fusion is common — rank-based, no score normalization headache. Tune weights on eval set.

---

### Q6. What is reranking and where does it sit?

**Say this:**

> First stage retrieves top 20–50 fast; **reranker** — cross-encoder like Cohere rerank — scores query-chunk pairs and returns top 5. Much more accurate than vector alone, adds ~100–300ms. VoXgent enabled rerank on high-stakes healthcare flows where wrong chunk meant wrong coverage answer.

**Compare:**

> **Bi-encoder** (embed) = fast, approximate. **Cross-encoder** (rerank) = slow, accurate. Pipeline: bi-encoder recall, cross-encoder precision.

**Follow-up:**

1. **Skip rerank when?**  
   **Say this:** Latency budget under 500ms total, or small index where top-3 vector hits are already good on eval.

---

### Q7. How do citations work in RAG?

**Say this:**

> Each chunk in the prompt is labeled — `[1]`, `[2]` — with source metadata. System prompt says: cite sources when stating facts. Post-process can verify claims map to chunks. VoXgent voice agents paraphrased but support UIs showed doc name and section for compliance.

**Follow-up:**

1. **Model cites wrong chunk?**  
   **Say this:** Happens — eval citation accuracy, tighten prompt, or require answer only from quoted spans. Human review for regulated domains.

---

### Q8. What is query rewriting?

**Say this:**

> User question may be vague or use different words than the docs. Rewrite step turns "what about my copay" into "outpatient specialist copay amount 2024 plan" using chat history. VoXgent LangGraph had a rewrite node before Pinecone — big lift on pronoun-heavy voice queries.

**Compare:**

> **Raw user query** = fast, weak on follow-ups. **HyDE** = LLM generates hypothetical answer then embeds — good for hard queries, extra cost. **History-aware rewrite** = best for multi-turn voice.

**Follow-up:**

1. **Rewrite made query worse?**  
   **Say this:** Loop with max one rewrite; if retrieval score still low, escalate to human — do not keep rewriting forever.

---

## C. Ingestion & lifecycle

### Q9. How do you run ingestion asynchronously?

**Say this:**

> Upload hits FastAPI → validate file → publish to **GCP Pub/Sub** or Cloud Tasks → worker parses, chunks, embeds, upserts Pinecone. API returns job ID; client polls status. VoXgent could not block HTTP on 200-page PDF embed — async ingest kept the admin UI responsive.

**Compare:**

> **Sync ingest** = fine for one small file. **Async queue** = required for batch uploads, re-index jobs, and tenant onboarding.

**Follow-up:**

1. **Failure in worker?**  
   **Say this:** Dead-letter queue, retry three times, mark job failed with error in DB — ops can re-trigger without re-upload.

---

### Q10. What happens when you change the embedding model?

**Say this:**

> Vectors are not compatible across models — different dimensions and geometry. You must **re-embed all chunks** and rebuild or new index, then cut over. VoXgent planned blue-green indexes: `index-v2` built offline, switch query traffic, delete old after validation.

**Follow-up:**

1. **Can you mix old and new vectors?**  
   **Say this:** No in the same index — search quality breaks. Dual-write during migration if you need zero downtime.

---

### Q11. How do you handle stale documents?

**Say this:**

> Version metadata on every chunk — `doc_version`, `effective_date`. On re-upload, delete or soft-invalidate old vectors by `source_id`, ingest new. Scheduled job compares CMS or S3 to index and flags drift. VoXgent sales scripts refreshed weekly — stale script wrong answer is a revenue problem.

**Compare:**

> **Overwrite in place** = simple. **Versioned indices** = audit trail for healthcare — know which policy version backed each answer.

**Follow-up:**

1. **User asks about expired policy?**  
   **Say this:** Filter `effective_date <= today`; if only expired docs match, say policy may have changed and offer human agent.

---

### Q12. Multi-tenant RAG — how do you isolate data?

**Say this:**

> Every chunk has `tenant_id` in metadata. Every query applies filter `tenant_id == auth.tenant`. Separate namespaces per enterprise client if contract requires. Never rely on prompt alone — "only use Acme docs" fails under injection. VoXgent enforced filter in the retriever wrapper, not optional.

**Follow-up:**

1. **Shared vs dedicated index?**  
   **Say this:** Shared index plus metadata filter scales; dedicated index for largest clients or compliance isolation — cost trade-off.

---

## D. Evaluation & failure modes

### Q13. How do you measure recall@k?

**Say this:**

> Build golden set: question plus list of doc IDs that *should* be retrieved. Run retrieval, check if correct doc appears in top-k. **Recall@5** = percent of questions where gold doc is in top 5. Fix retrieval before tuning prompts — VoXgent debugged many "hallucination" bugs that were actually recall@3 failures.

**Compare:**

> **Recall@k** = did we fetch the right stuff. **Answer correctness** = did the LLM answer well — separate metrics; bad recall cannot be fixed by better prompt.

**Follow-up:**

1. **What k for voice?**  
   **Say this:** Often k=3–5 in prompt after rerank — more chunks add latency and noise.

---

### Q14. Top RAG failure modes in production?

**Say this:**

> **Bad retrieval** — wrong or empty chunks. **Chunking** — answer split across chunks. **Stale index** — old policy. **Prompt overflow** — truncated context. **Injection via docs** — malicious upload. **Over-trust** — model answers without sufficient context. VoXgent mitigated with eval, tenant filters, confidence thresholds, and human transfer.

**Follow-up:**

1. **First thing you debug?**  
   **Say this:** Log retrieved chunks and scores for the failing query — usually retrieval, not the LLM.

---

### Q15. When does RAG fail — and what do you do instead?

**Say this:**

> RAG fails when knowledge is not in the index, when reasoning needs live data — stock price now — or when format is too complex for chunks — huge tables, heavy math. Fallbacks: tool APIs, text-to-SQL, human handoff, or "I don't know." VoXgent routed low retrieval score to transfer rather than guess.

**Compare:**

> **RAG** = static knowledge, updates on ingest. **Tools** = live systems. **Fine-tune** = style and format, not replacing weekly policy updates.

**Follow-up:**

1. **Fine-tune instead of RAG?**  
   **Say this:** Rare for changing docs — RAG plus eval beats fine-tune for factual enterprise knowledge.

---

## E. Performance & caching

### Q16. What cache layers help RAG?

**Say this:**

> **Embedding cache** — same query text, same vector. **Retrieval cache** — query hash to top-k chunk IDs with short TTL. **Answer cache** — exact FAQ match, careful with personalization. Redis in front of Pinecone cut repeat queries on VoXgent support lines. Invalidate on doc update for that tenant.

**Compare:**

> **Cache hit** = sub-100ms path. **Miss** = full embed plus search — log hit rate to justify Redis cost.

**Follow-up:**

1. **Cache wrong answer risk?**  
   **Say this:** Key cache by tenant plus query plus index version — bump version on re-ingest.

---

### Q17. PDF table extraction — why is it hard?

**Say this:**

> PDFs are layout, not structure — tables become scrambled text when naively parsed. Bad table chunk means RAG returns garbage rows. Use specialized parsers — Unstructured, pdfplumber, or vendor OCR — extract tables as markdown or CSV, chunk per table with caption metadata. VoXgent learned this on benefits comparison PDFs; plain `pypdf` text was not enough.

**Follow-up:**

1. **Interview one-liner?**  
   **Say this:** "Garbage parse in, garbage retrieve out — invest in ingestion quality before buying a bigger LLM."

---

## F. Architecture recap

### Q18. Draw the VoXgent RAG path in 45 seconds.

**Say this:**

> Offline: client uploads docs → parse → chunk with metadata → embed → Pinecone upsert per tenant. Online: voice STT → text → optional query rewrite → embed query → hybrid search with tenant filter → rerank → top chunks into prompt → LLM stream → TTS. LangGraph loops if confidence low. Log chunks, scores, and latency every call.

**Follow-up:**

1. **Bottleneck?**  
   **Say this:** Usually LLM generation and rerank — parallelize embed plus retrieve, cap prompt size.

---

### Q19. How does RAG fit with LangGraph on VoXgent?

**Say this:**

> RAG is one node — not the whole app. Graph flow: rewrite → retrieve → check scores → if low retry rewrite → if still low human node → else generate or tool call with context. State holds `retrieved_docs`, `retrieval_score`, `messages`. That separation made RAG testable on its own.

**Follow-up:**

1. **Tool plus RAG same turn?**  
   **Say this:** Yes — retrieve policy first, then tool to check patient eligibility, then answer combining both in final prompt.

---

### Q20. Master compare — naive vs production RAG.

**Say this:**

> Naive: chunk, embed, top-3, prompt, done. Production VoXgent: structure-aware chunking, tenant metadata, async ingest, query rewrite, optional hybrid plus rerank, citations, eval recall@k, cache, stale doc versioning, confidence routing, and human fallback. Interview tip: always say what you would add when scale or compliance increases.

**Follow-up:**

1. **What would you add next?**  
   **Say this:** Online eval dashboard, automated golden set from support tickets, and chunk quality scoring at ingest.

---

**Related:** [Infosys 02 — RAG Deep Dive (60 Qs)](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) · [Infosys 05 — Embeddings & Vector DB](../Infosys_Interview_Prep/05_Embeddings_VectorDB_Retrieval_QA.md) · [Infosys 06 — RAG Step by Step](../Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md) · [01_LLM_Fundamentals_QA.md](./01_LLM_Fundamentals_QA.md) · [03_LangChain_LangGraph_QA.md](./03_LangChain_LangGraph_QA.md) · [Artifact lesson 5](../Artifacts/lesson_5_rag_production_pipeline.md)
