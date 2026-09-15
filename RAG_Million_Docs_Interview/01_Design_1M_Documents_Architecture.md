# Design — RAG Pipeline for 1 Million Documents

**Author:** Aalok Singh Mehra · VoXgent (LangChain, LangGraph, Pinecone, GCP)  
**Audience:** Alok — ~2 YOE backend/AI engineer  
**Interview prompt:** *"How will you process 1 million documents — give me the end-to-end architecture."*

**Related docs in this folder:**

| # | File | Topic |
|---|------|-------|
| 02 | [Cloud vs Local, Update & Delete](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md) | Source sync, versioning, delete/re-index |
| 03 | [Q&A — System Design & Lifecycle (50)](./03_QA_System_Design_Ingestion_Lifecycle.md) | Speakable architecture answers |
| 04 | [Q&A — AI Pipeline: Chunk → GraphRAG (50)](./04_QA_AI_Pipeline_Chunk_Embed_Search_GraphRAG.md) | Chunking, hybrid, rerank depth |

**Also study:**

- [System Design 14 — AI & LLM System Design](../System_Design_Prep/14_AI_LLM_System_Design.md) — LLM gateway, cost, guardrails
- [Infosys 06 — RAG Pipeline Step-by-Step](../Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md) — stage-by-stage walkthrough

---

## Say this in 60 seconds

> "For one million documents I split the system into **offline async ingest** and **online sync query**. Offline: discover sources, land raw files in object storage, parse by file type, chunk with idempotent workers, batch-embed, write **Postgres as source of truth** for docs and chunks, then upsert **derived indexes** — a vector store like Pinecone or pgvector plus BM25 in OpenSearch for hybrid search. Online: authenticate, filter by tenant, embed the query, run hybrid retrieval in parallel, rerank top candidates, assemble context with citations, generate via an LLM gateway — LangGraph if we need retries or tool use. Scale comes from **horizontal workers**, **checkpointed pipelines**, and **namespaces per tenant** — not from one giant batch job. Updates and deletes are first-class events so stale chunks never answer after a PDF changes — that's covered in doc 02."

---

## Table of contents

1. [Capacity estimation](#1-capacity-estimation)
2. [Offline vs online split](#2-offline-vs-online-split)
3. [End-to-end architecture diagram](#3-end-to-end-architecture-diagram)
4. [Components and responsibilities](#4-components-and-responsibilities)
5. [Text extraction by document type](#5-text-extraction-by-document-type)
6. [Chunking at scale](#6-chunking-at-scale)
7. [Embedding at scale](#7-embedding-at-scale)
8. [Indexing strategy](#8-indexing-strategy)
9. [Query path and latency budget](#9-query-path-and-latency-budget)
10. [Failure modes and DLQ](#10-failure-modes-and-dlq)
11. [Cost and observability](#11-cost-and-observability)
12. [Multi-tenancy](#12-multi-tenancy)
13. [Trade-offs table](#13-trade-offs-table)
14. [Whiteboard talk track](#14-whiteboard-talk-track)
15. [VoXgent anchor story](#15-voxgent-anchor-story)

---

## 1. Capacity estimation

**Say this:** *"Before I draw boxes, I sanity-check numbers — interviewers want to see you can back-of-envelope a million-doc corpus."*

### 1.1 Assumptions (enterprise mixed corpus)

| Parameter | Assumption | Notes |
|-----------|------------|-------|
| Total documents | **1,000,000** | Policies, contracts, KB articles, tickets, web pages |
| Avg raw text per doc | **~3,500 tokens** (~2,500 words, ~5 pages) | Mix of 1-page FAQs and 50-page manuals; use P50/P90 in prod |
| Avg chunks per doc | **~7** | 512-token chunks, 64-token overlap → ~6–8 chunks/doc |
| **Total chunks** | **~7,000,000** | Plan for **5M–10M** range in capacity planning |
| Embedding model | `text-embedding-3-small` (1536 dims) | VoXgent-style; swap to `-large` (3072) if recall eval demands |
| Vector dim storage | 1536 × 4 bytes ≈ **6 KB/vector** | Float32; quantized indexes can halve this |
| Metadata per vector | **~0.5–1 KB** | tenant_id, doc_id, chunk_index, page, section, version |
| **Vector index size** | **~45–55 GB** | 7M × ~7 KB; HNSW overhead adds ~20–30% |
| Raw object storage | **~2–4 TB** | PDFs average 200 KB–2 MB; OCR scans heavier |
| Postgres (docs + chunks) | **~100–200 GB** | chunk text, metadata, lineage, job state |

### 1.2 Ingest throughput (offline)

| Stage | Realistic throughput | Time to process 1M docs |
|-------|---------------------|------------------------|
| Discovery + landing | 500–2,000 docs/min | 8–33 hours (parallel crawlers) |
| Parse (text PDFs) | 200–800 docs/min/worker | 10 workers → ~2–8 hours |
| Parse (OCR scans) | 20–60 pages/min/worker | OCR is the bottleneck — isolate queue |
| Chunk | 5,000–20,000 chunks/min | CPU-bound; scales linearly with workers |
| Embed (API batch) | 50,000–150,000 chunks/hour | Depends on provider tier and batch size |
| Index upsert | 10,000–50,000 vectors/min | Pinecone bulk import faster than serial upsert |

**Say this:** *"Seven million chunks at ~100K embeddings per hour is roughly **70 hours** of embedding time on one stream — so I run **10–20 parallel embed workers** with rate-limit-aware batching and checkpointing, targeting **full initial ingest in 24–72 hours**, not a single monolithic job."*

### 1.3 Embedding QPS and rate limits

| Provider tier (illustrative) | RPM limit | Batch size | Effective chunk throughput |
|------------------------------|-----------|------------|----------------------------|
| Starter | 3,000 RPM | 100 texts/request | ~300K chunks/min theoretical; ~30–50K sustained with retries |
| Production | 10,000+ RPM | 2048 max batch | Scale with multiple API keys / regional endpoints |
| Self-hosted (e.g. TEI on GPU) | N/A | 256–512 | ~500–2,000 chunks/sec per A10 depending on model |

**Design rule:** Never call embed API one chunk at a time. Batch **64–256 chunks** per request; aggregate in a buffer with **max wait 2–5 seconds** to fill batches.

### 1.4 Query load (online)

| Metric | Conservative | High-traffic enterprise |
|--------|--------------|-------------------------|
| Average QPS | **10** | **50** |
| Peak QPS | **50** | **200** |
| Concurrent users | 500 | 5,000 |
| Retrieval p99 target | **< 150 ms** | Same — scale replicas |
| End-to-end p99 (with LLM) | **< 2.5 s** | Streaming TTFT < 800 ms |

**Per-query compute:**

- 1 query embedding (~20–50 ms)
- 2 parallel searches (vector + BM25): 30–80 ms each
- Rerank top 50 → top 5: 80–200 ms
- LLM generation: 500 ms–2 s (dominant)

**Say this:** *"Query path is cheap compared to ingest — 100 QPS peak is ~8.6M queries/day; the expensive part is the one-time 7M embedding calls and keeping indexes fresh on updates."*

---

## 2. Offline vs online split

| Dimension | OFFLINE (async ingest) | ONLINE (sync query) |
|-----------|------------------------|---------------------|
| **Trigger** | Schedule, webhook, upload event, CDC | User/API chat request |
| **Latency SLA** | Minutes to hours; progress bar OK | Sub-3-second p99 |
| **Consistency** | Eventual — doc searchable after pipeline completes | Read from current indexes + Postgres metadata |
| **Scaling** | Horizontal workers, queue depth | Stateless API replicas, index replicas |
| **Failure handling** | Retry, DLQ, checkpoint resume | Fast fallback (cache, keyword-only, apology) |
| **Cost profile** | Burst — embed once, store forever | Per-request — embed query + LLM tokens |
| **Source of truth** | **Postgres** (doc/chunk records) | Indexes are **derived** — rebuildable from Postgres + object store |

**Say this:** *"Ingest is a factory line — queues between stages, idempotent workers, checkpoint every N chunks. Query is a race track — parallel retrieval, tight latency budget, no heavy parsing on the request path."*

For update/delete lifecycle (PDF replaced, tenant offboarded), see [02 — Cloud vs Local, Update & Delete](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md).

---

## 3. End-to-end architecture diagram

```
╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                           OFFLINE — ASYNC INGEST / INDEXING                               ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │  Sources    │     │  Discovery  │     │  Ingest     │     │  Object     │
  │  S3 / GCS   │────▶│  Crawler /  │────▶│  Validator  │────▶│  Store      │
  │  Drive /    │     │  Scheduler  │     │  Dedupe     │     │  (raw blobs)│
  │  SharePoint │     │  Webhooks   │     │  Versioning │     │  s3://...   │
  └─────────────┘     └─────────────┘     └─────────────┘     └──────┬──────┘
                                                                      │
                    ┌─────────────────────────────────────────────────┘
                    │  message: { tenant_id, doc_id, uri, content_hash, mime }
                    ▼
  ┌─────────────────────────────────────────────────────────────────────────────┐
  │                        PARSE WORKER POOL (auto-scaled)                       │
  │  Route by mime ──▶ PDF parser │ DOCX │ HTML │ CSV │ OCR queue (slow path)   │
  └───────────────────────────────────┬─────────────────────────────────────────┘
                                      │  extracted text + structure (pages, headings)
                                      ▼
  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
  │  Preprocess │────▶│  Chunk      │────▶│  Embed      │────▶│  Index      │
  │  normalize  │     │  Workers    │     │  Batch      │     │  Writer     │
  │  lang/PII   │     │  idempotent │     │  + retry    │     │  dual-write │
  └─────────────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
                             │                   │                   │
                             ▼                   ▼                   ▼
                    ┌────────────────────────────────────────────────────────┐
                    │              POSTGRES — SOURCE OF TRUTH                 │
                    │  documents │ chunks │ ingest_jobs │ lineage │ versions  │
                    └────────────────────────────┬───────────────────────────┘
                                                 │
                         ┌───────────────────────┴───────────────────────┐
                         ▼                                               ▼
                ┌─────────────────┐                             ┌─────────────────┐
                │  VECTOR INDEX   │                             │  BM25 / LEXICAL │
                │  Pinecone or    │                             │  OpenSearch /   │
                │  pgvector HNSW  │                             │  Elasticsearch  │
                │  (derived)      │                             │  (derived)      │
                └─────────────────┘                             └─────────────────┘

  Queues between every stage:  SQS / Pub-Sub / Redis Streams
  DLQ on poison messages       Checkpoint: job_id + last_chunk_offset


╔══════════════════════════════════════════════════════════════════════════════════════════╗
║                           ONLINE — SYNC QUERY / ANSWER                                    ║
╚══════════════════════════════════════════════════════════════════════════════════════════╝

  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────────────────────────────┐
  │  Client  │───▶│  API /   │───▶│  Auth +  │───▶│  Query preprocessor              │
  │  Web /   │    │  Gateway │    │  Tenant  │    │  (optional rewrite, intent)      │
  │  Voice   │    │          │    │  context │    └───────────────┬──────────────────┘
  └──────────┘    └──────────┘    └──────────┘                    │
                                                                    ▼
                                                         ┌──────────────────┐
                                                         │  Query embedding │
                                                         └────────┬─────────┘
                                                                  │
                    ┌─────────────────────────────────────────────┼─────────────────────────┐
                    ▼                                             ▼                         │
           ┌─────────────────┐                           ┌─────────────────┐                │
           │  Vector search  │                           │  BM25 search    │                │
           │  top-K=50       │                           │  top-K=50       │                │
           │  + metadata     │                           │  + same filters │                │
           │    filter       │                           │                 │                │
           └────────┬────────┘                           └────────┬────────┘                │
                    │                                             │                         │
                    └──────────────────┬──────────────────────────┘                         │
                                       ▼                                                    │
                              ┌─────────────────┐                                           │
                              │  Hybrid fusion  │  RRF or weighted score                    │
                              │  dedupe by      │                                           │
                              │  chunk_id       │                                           │
                              └────────┬────────┘                                           │
                                       ▼                                                    │
                              ┌─────────────────┐                                           │
                              │  Reranker       │  cross-encoder top 50 → 5                 │
                              │  (optional)     │                                           │
                              └────────┬────────┘                                           │
                                       ▼                                                    │
                              ┌─────────────────┐                                           │
                              │  Context        │  token budget, citations,                 │
                              │  assembly       │  parent-child expansion                   │
                              └────────┬────────┘                                           │
                                       ▼                                                    │
                              ┌─────────────────┐     ┌──────────┐                          │
                              │  LLM Gateway    │────▶│  Stream  │──▶ user                │
                              │  (LangGraph)    │     │  response│                          │
                              │  grounded prompt│     └──────────┘                          │
                              └─────────────────┘                                           │
                                       │                                                    │
                                       ▼                                                    │
                              ┌─────────────────┐                                           │
                              │  Post-process   │  citation check, guardrails, log trace  │
                              └─────────────────┘                                           │
```

---

## 4. Components and responsibilities

| Component | Responsibility | Tech examples (VoXgent-aligned) |
|-----------|----------------|----------------------------------|
| **Discovery service** | Enumerate sources, emit ingest events, respect crawl politeness | Cloud Scheduler + custom crawler, Drive/SharePoint APIs |
| **Ingest API / validator** | Accept uploads, compute content hash, assign doc_id + version, reject unsupported mime | FastAPI, virus scan, size limits |
| **Object store** | Immutable raw bytes, lifecycle tiers (hot → cold) | GCS / S3, `/{tenant}/{doc_id}/{version}/raw` |
| **Message queue** | Decouple stages, backpressure, DLQ | GCP Pub/Sub, SQS, Redis Streams |
| **Parse workers** | MIME routing, text extraction, page/heading structure | Unstructured, PyMuPDF, python-docx, Tesseract / Document AI |
| **Preprocess** | Unicode normalize, language detect, optional PII redaction | langdetect, Presidio |
| **Chunk workers** | Split text, stable chunk_ids, write to Postgres | LangChain splitters, custom heading-aware |
| **Embed batcher** | Aggregate chunks, call embedding API, handle 429/5xx | OpenAI / Vertex embeddings, retry with jitter |
| **Index writer** | Upsert vectors + BM25 docs, delete stale IDs on re-index | Pinecone upsert, OpenSearch bulk API |
| **Postgres** | Source of truth: documents, chunks, jobs, tenant ACLs | RDS / Cloud SQL, partitioned by tenant |
| **Vector index** | Approximate nearest neighbor search | Pinecone serverless, pgvector + HNSW |
| **Lexical index** | Keyword/BM25 for exact terms, SKUs, IDs | OpenSearch |
| **Query API** | Auth, orchestrate retrieval + generation | FastAPI + LangGraph |
| **LLM gateway** | Model routing, token limits, fallback, logging | LiteLLM / custom gateway |
| **Reranker** | Precision layer on fused candidates | Cohere rerank, cross-encoder (ms-marco) |
| **Observability** | Traces per request, ingest dashboards, eval hooks | OpenTelemetry, LangSmith, Prometheus |

---

## 5. Text extraction by document type

**Say this:** *"Parsing is where million-doc pipelines win or die — I route by MIME type and never run OCR on a digital PDF."*

| Type | Detection | Extractor | Output | Pitfalls |
|------|-----------|-----------|--------|----------|
| **Digital PDF** | Text layer present (`pdfminer` probe) | PyMuPDF / pdfplumber | Page text + bbox for citations | Multi-column reading order; tables as garbage text |
| **Scanned PDF / image** | No text layer, image-only pages | **Separate OCR queue** — Google Document AI, AWS Textract, Tesseract | Page text + confidence scores | 10–50× slower; queue isolation mandatory |
| **DOCX** | `application/vnd...document` | python-docx / Unstructured | Paragraphs + heading styles | Embedded objects skipped unless needed |
| **HTML / web** | URL crawl or `.html` | Trafilatura, BeautifulSoup + boilerplate removal | Main content + title, URL metadata | Nav/footer noise — use readability extractors |
| **PPTX** | Office mime | python-pptx / Unstructured | Slide text + speaker notes | Diagrams need OCR or vision (expensive — defer) |
| **CSV / JSON** | Structured | Row-level or record-level chunks | One chunk per row or grouped records | Wide tables — chunk by column groups |
| **Email (.eml)** | MIME multipart | Parse headers + body; strip signatures | Thread_id metadata | PII-heavy — redact before embed |

### OCR slow-path architecture

```
parse_queue (fast) ──▶ digital PDF / DOCX / HTML  ──▶ chunk_queue
        │
        └── scan detected ──▶ ocr_queue (low concurrency, GPU/Document AI)
                                    │
                                    └──▶ chunk_queue (same downstream)
```

**Say this:** *"OCR workers are expensive — I cap concurrency at 5–20 and use page-level checkpointing so a 500-page scan doesn't restart from page 1 on failure."*

For step-by-step extraction narrative, see [Infosys 06 — RAG Pipeline](../Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md).

---

## 6. Chunking at scale

### 6.1 Strategy by document type

| Doc type | Strategy | Chunk size | Overlap |
|----------|----------|------------|---------|
| Policies / manuals | Structure-aware (headings) | 400–800 tokens | 64–128 tokens |
| FAQs | One Q+A pair per chunk | Variable | Minimal |
| Tickets / emails | Fixed recursive | 256–512 tokens | 50 tokens |
| Code / logs | Syntax-aware splitters | 512 tokens | 64 tokens |
| Tables | Row groups or markdown table units | Keep table intact in one chunk | N/A |

**VoXgent reference:** Healthcare policies used heading-based chunks — each section one retrievable unit; sales scripts used smaller fixed chunks.

### 6.2 Idempotency and stable IDs

**Say this:** *"Every chunk gets a deterministic ID: hash(tenant_id + doc_id + doc_version + chunk_index + chunking_algo_version). Re-running ingest after a crash produces the same IDs — upserts are safe, no duplicate vectors."*

```
chunk_id = sha256(f"{tenant_id}:{doc_id}:v{version}:{algo_v}:{index}")[:32]
```

**Postgres row** written **before** index upsert:

```sql
-- illustrative
INSERT INTO chunks (chunk_id, doc_id, tenant_id, chunk_index, text, token_count, status)
VALUES (...)
ON CONFLICT (chunk_id) DO UPDATE SET text = EXCLUDED.text, status = 'pending_index';
```

### 6.3 Batch processing at scale

| Pattern | Why |
|---------|-----|
| **Micro-batch 100–500 chunks** per worker tick | Amortize DB round-trips |
| **Partition ingest jobs by tenant + doc_id hash** | Avoid hot keys, fair scheduling |
| **Backpressure** — chunk queue depth triggers scale-up | Prevent embed API stampede |
| **Parent-child** (optional) | Index small children, expand parent at query time — see [04 Q&A](./04_QA_AI_Pipeline_Chunk_Embed_Search_GraphRAG.md) |

### 6.4 Checkpointing

Store in `ingest_jobs`:

- `job_id`, `doc_id`, `stage` (parse | chunk | embed | index)
- `last_completed_chunk_index`
- `content_hash` — skip entire doc if unchanged

**Say this:** *"If embed worker dies at chunk 4,000 of 7,000, I resume from 4,001 — I don't re-parse the PDF."*

---

## 7. Embedding at scale

### 7.1 Batching pipeline

```
chunk_queue ──▶ embed_batcher (buffer, max_wait=3s, batch_size=128)
                      │
                      ├──▶ embedding API (OpenAI / Vertex)
                      │
                      └──▶ on success: index_queue + UPDATE chunks SET status='embedded'
```

| Parameter | Recommended value |
|-----------|-------------------|
| Batch size | 64–256 texts (stay under provider token limit ~8191 tokens/input) |
| Max wait | 2–5 s to fill batch |
| Concurrency | 10–50 in-flight batches (tuned to rate limit) |
| Input truncation | 512–8192 tokens depending on model; log truncations |

### 7.2 Rate limits, retries, circuit breaker

**Say this:** *"Embedding at 7M chunks will hit 429s — that's expected, not a bug."*

| Error | Action |
|-------|--------|
| **429 Too Many Requests** | Exponential backoff + jitter; respect `Retry-After` header |
| **5xx** | Retry 3× with backoff; then DLQ |
| **400 (bad input)** | Quarantine chunk, log text hash, continue batch |
| **Sustained 429** | Circuit breaker — reduce worker concurrency globally |

```python
# pseudocode — speakable pattern
for attempt in range(5):
    try:
        return embed_api.batch(texts)
    except RateLimitError as e:
        sleep(exponential_backoff(attempt) + random_jitter())
```

### 7.3 Checkpointing embed progress

- After each successful batch: mark chunk_ids `embedded_at = now()` in Postgres
- Index writer reads only `status = 'embedded' AND status != 'indexed'`
- Enables **exactly-once semantics at the business level** (at-least-once delivery + idempotent upsert)

### 7.4 Self-hosted vs API (scale decision)

| Option | When | Throughput |
|--------|------|------------|
| **OpenAI / Vertex API** | Default; fastest to ship; 7M one-time ~$140–700 depending on model | Rate-limit bound |
| **Self-hosted TEI / vLLM embeddings** | >10M chunks/month ongoing or data residency | GPU-bound; fixed cost |

Cost math (7M chunks × 512 tokens avg × $0.02/1M tokens for `text-embedding-3-small`): **~$70 one-time embed cost** — cheap compared to engineering time; say this number in interviews.

---

## 8. Indexing strategy

### 8.1 Dual derived indexes

| Index | Purpose | Write pattern |
|-------|---------|---------------|
| **Vector (ANN)** | Semantic similarity | Upsert `{ id: chunk_id, values: embedding, metadata: {...} }` |
| **BM25 (lexical)** | Exact terms, SKUs, error codes, names | Index `{ chunk_id, text, tenant_id, ... }` |

**Postgres remains authoritative** — if Pinecone and OpenSearch disagree, rebuild index from Postgres.

### 8.2 Sharding and namespaces (multi-tenant)

**Say this:** *"I never put all tenants in one flat index without filters — I use Pinecone namespaces per tenant or per tenant-tier shard group, plus mandatory metadata filter on every query."*

| Scale | Strategy |
|-------|----------|
| < 100 tenants | Single index, `tenant_id` metadata filter (Pinecone) or RLS (pgvector) |
| 100–10K tenants | Namespace per tenant OR shard: `hash(tenant_id) % N` → index shard |
| Massive single tenant | Dedicated index replica for that tenant (noisy neighbor isolation) |

Example Pinecone layout:

```
index: prod-rag-v1
  namespace: tenant_abc123   →  ~50K vectors
  namespace: tenant_xyz789   →  ~2M vectors  (large client — own namespace)
```

### 8.3 HNSW notes (pgvector / Faiss / Pinecone internals)

| Parameter | Trade-off |
|-----------|-----------|
| **M** (connections) | Higher = better recall, more RAM |
| **efConstruction** | Higher = better index quality, slower build |
| **efSearch** | Higher at query time = better recall, slower query |

**Say this:** *"For 7M vectors I'd use managed Pinecone or pgvector with HNSW — build happens offline during ingest; at query time I tune ef_search for recall@10 ≥ 0.9 on our golden set. Initial bulk import: use provider's bulk load (S3 → Pinecone) instead of 7M serial upserts."*

### 8.4 Index versioning

- `index_version` in metadata — blue/green: build `prod-rag-v2` while `v1` serves traffic; flip router alias
- Re-embed all chunks when embedding **model** changes — not when doc text changes

---

## 9. Query path and latency budget

**Target p99: ≤ 2.5 s** (non-streaming); **TTFT ≤ 800 ms** (streaming)

| Step | Budget (ms) | Parallel? | Notes |
|------|-------------|-----------|-------|
| API gateway + auth | 15 | — | JWT validate, resolve tenant_id |
| Query preprocessing | 0–200 | — | Skip LLM rewrite on latency-sensitive path; use rules |
| Query embedding | 30–50 | — | Cache frequent queries in Redis |
| Vector search top-50 | 40–80 | **Yes** | Metadata filter applied in index |
| BM25 search top-50 | 40–80 | **Yes** | Same tenant filter |
| Hybrid fusion (RRF) | 5 | — | `score = Σ 1/(k + rank)` |
| Rerank 50 → 5 | 80–200 | — | Optional; skip for voice/low-latency |
| Context assembly | 10 | — | Token budget ~2–4K for retrieval context |
| LLM TTFT | 300–800 | — | GPT-4o-mini / Gemini Flash for speed |
| LLM full response | 500–2000 | — | Stream tokens to client |
| Post-process + log | 20 | — | Citation format, safety filter |

**Say this:** *"Retrieval is ~200 ms of the budget; the LLM is the rest — so I parallelize vector and BM25, cap rerank input at 50, and stream the answer so perceived latency drops even if total generation is 2 seconds."*

### Hybrid fusion (RRF)

```
final_score(chunk) = 1/(60 + rank_vector) + 1/(60 + rank_bm25)
```

Dedupe by `chunk_id` before rerank.

### LangGraph orchestration (optional)

```
START → embed_query → parallel_retrieve → fuse → rerank → assemble → generate
                          ↓ (empty results)
                      relax_filters → retry_retrieve → fallback_message
```

See [System Design 14 — LLM Gateway](../System_Design_Prep/14_AI_LLM_System_Design.md) for gateway patterns.

---

## 10. Failure modes and DLQ

| Failure | Stage | Detection | Recovery |
|---------|-------|-----------|----------|
| Corrupt PDF | Parse | Parser exception | DLQ + alert; mark doc `status=failed` |
| OCR timeout | Parse | Worker timeout (30 min/doc) | Page-level retry; DLQ after 3 attempts |
| Poison chunk (embed 400) | Embed | API rejects input | Quarantine table; skip chunk |
| Pinecone upsert partial failure | Index | Batch error response | Retry failed IDs; idempotent upsert |
| Stale index after update | Index | User report / eval drift | Versioned re-index from Postgres — [doc 02](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md) |
| Empty retrieval | Query | Zero results | Relax filters → BM25-only → "I don't know" |
| LLM timeout | Query | 30 s cutoff | Return retrieved snippets without generation |
| Tenant filter bug | Query | Cross-tenant result in eval | P0 — block deploy; metadata audit |

### DLQ architecture

```
main_queue ──▶ worker ──▶ success → next_queue
                │
                └── fail (max_retries=5) ──▶ DLQ
                                              │
                                              ├── manual replay tool
                                              └── dashboard: count by error_type
```

**Say this:** *"Every DLQ message retains the original payload plus error class and stack hash — ops replays after fixing the parser, not by re-crawling the whole million."*

### Saga / compensating actions

On doc delete:

1. Postgres soft-delete doc + chunks
2. Emit `delete_vectors` event with chunk_id list
3. Index writer removes from vector + BM25
4. Verify with sample query — tombstone until confirmed

---

## 11. Cost and observability

### 11.1 Monthly cost estimate (illustrative)

| Item | One-time (1M ingest) | Steady-state / month |
|------|----------------------|----------------------|
| Embedding API (7M chunks) | **~$70–350** | Re-embed deltas only |
| Pinecone (50 GB, serverless) | — | **~$200–800** |
| OpenSearch (3-node small) | — | **~$300–600** |
| GCS raw storage (3 TB) | — | **~$60** |
| Postgres Cloud SQL | — | **~$200–500** |
| LLM queries (10 QPS avg, 2K tokens/req) | — | **~$500–3,000** |
| Parse/OCR (Document AI) | **~$1,500–5,000** if 30% scanned | Ongoing for new scans |
| **Total ballpark** | **~$2K–6K ingest** | **~$1.5K–5K/month** |

**Say this:** *"Ingest is a one-time spike; steady cost is LLM tokens plus index hosting — I track cost per query and per tenant for chargeback."*

### 11.2 Observability

| Signal | What to track |
|--------|---------------|
| **Ingest** | docs/hour by stage, queue depth, DLQ rate, OCR vs digital ratio |
| **Quality** | recall@k on golden set, empty retrieval rate, thumbs down |
| **Query** | p50/p99 latency per stage, cache hit rate, token usage |
| **Cost** | $/query, $/tenant/month, embed tokens/day |
| **Safety** | cross-tenant leakage tests (automated), PII detection hits |

**Tracing:** One trace ID from query → retrieval chunk_ids → LLM prompt hash (not full prompt in logs if sensitive).

**Eval pipeline:** Nightly job runs 200 golden Q&A pairs; alert if recall@5 drops > 5%.

---

## 12. Multi-tenancy

**Say this:** *"Tenant isolation is non-negotiable — I enforce it at auth, Postgres RLS, object store prefix, index namespace, and every query filter."*

| Layer | Isolation mechanism |
|-------|---------------------|
| Auth | JWT `tenant_id` — never trust client body |
| Object store | `gs://bucket/{tenant_id}/...` — IAM scoped |
| Postgres | Row-level security on `tenant_id` |
| Vector index | Namespace per tenant OR mandatory metadata filter |
| BM25 | Index alias per tenant shard |
| Queues | `tenant_id` in message; fair-share scheduling |
| Rate limits | Per-tenant QPS and ingest quotas |
| Encryption | CMK per enterprise tier (optional) |

**Noisy neighbor:** Large tenant gets dedicated embed pool slice (K8s resource quota) so their bulk upload doesn't starve others.

For delete/offboard: [02 — Update & Delete](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md).

---

## 13. Trade-offs table

| Decision | Option A | Option B | When to pick A | When to pick B |
|----------|----------|----------|----------------|----------------|
| Vector store | **Pinecone** (managed) | **pgvector** (Postgres) | Fast ship, 10M+ vectors, ops-light | Already on Postgres, <5M vectors, strong consistency |
| Lexical | **OpenSearch** | Postgres FTS | Need BM25, faceting, highlight | Tiny corpus, simplify stack |
| Chunking | Fixed 512 | Structure-aware | Uniform docs, speed | Policies, manuals, HTML |
| Hybrid | Vector only | **Vector + BM25** | Pure semantic FAQ | SKUs, legal cites, mixed queries |
| Rerank | None | **Cross-encoder** | Voice / strict latency | Quality-critical enterprise search |
| Embed | API | Self-hosted GPU | <10M one-time, no residency rules | Data residency, high ongoing volume |
| Ingest | Real-time per upload | **Batch + queue** | Single-doc UX | Million-doc bulk — always batch |
| Consistency | Strong at query | **Eventual ingest** | Financial ledger RAG | Standard KB — eventual OK |
| OCR | Inline | **Separate slow queue** | Never at 1M scale | Always for scans |
| Updates | Full re-index | **Delta by content_hash** | Embedding model change | Doc edit — hash skip unchanged |

---

## 14. Whiteboard talk track

**Say this:** *"I'll draw left-to-right: sources, offline factory, two indexes, then online query path on the bottom — takes about 8 minutes with numbers."*

### Step 1 — Frame the problem (30 s)

- Write: **1M docs → ~7M chunks → offline ingest + online query**
- Ask clarifying: tenant count? scanned PDF %? latency SLA? — shows seniority

### Step 2 — Draw OFFLINE top half (3 min)

1. **Sources** box (S3, Drive, SharePoint)
2. Arrow to **Discovery / Scheduler**
3. **Object store** (raw files) — "immutable, versioned"
4. **Queue** — stress decoupling
5. **Parse workers** — split fast path vs **OCR queue**
6. **Chunk workers** → **Postgres** (circle it — "source of truth")
7. **Embed batcher** → fork to **Vector index** and **BM25 index**
   - Label indexes **"derived — rebuildable"**

### Step 3 — Numbers on the board (1 min)

- 7M chunks, ~100K embed/hour/worker stream, 10 workers → ~7 hours embed (parallel with parse)
- 50 GB vector index
- Checkpoint: `doc_id + chunk_index`

### Step 4 — Draw ONLINE bottom half (2 min)

1. **Client** → **API** → **Auth/tenant**
2. **Query embed** → split arrow to **Vector top-50** and **BM25 top-50** (parallel)
3. **RRF fuse** → **Rerank** → **Context** → **LLM** → **Stream**
4. Write latency: **200 ms retrieve + ~1 s LLM**

### Step 5 — Cross-cutting (1 min)

- **DLQ** off every queue
- **Multi-tenant**: namespace + filter on every query
- **Updates/deletes**: "events, not cron re-crawl" — pointer to doc 02

### Step 6 — Trade-off they'll probe (1 min)

- "Why Pinecone over pgvector?" → ops vs cost vs scale
- "Why hybrid?" → error codes, exact match
- "What breaks at 10M?" → shard indexes, embed cost, HNSW RAM

### Step 7 — Close with VoXgent (30 s)

> "This is the architecture I'd scale from what I built at VoXgent — same offline/online split, Postgres truth, Pinecone with tenant filters, LangGraph for retry on empty retrieval."

---

## 15. VoXgent anchor story

**Say this when they ask "have you done this?"**

> "At VoXgent I owned the RAG path for client knowledge bases — policies, scripts, FAQs. We weren't at a full million docs, but the **shape** was identical: ingest to object storage, structure-aware chunking on healthcare policies, embed with metadata including `tenant_id`, upsert to Pinecone, retrieve with mandatory tenant filter, optional rerank, generate in a LangGraph flow with retry when retrieval was empty. For interview scale I'd add **BM25 hybrid**, **checkpointed million-doc workers**, and **first-class delete/update events** — the failure mode I've seen in production is stale chunks after a PDF swap, not slow vector search."

---

## Quick reference card

| Question | One-line answer |
|----------|-----------------|
| How many chunks? | ~7M (7 per doc × 1M) |
| Source of truth? | Postgres + object store |
| Indexes? | Derived — vector + BM25 |
| Ingest time? | 24–72 h with parallel workers |
| Query p99? | < 2.5 s |
| Biggest bottleneck? | OCR + embedding rate limits |
| Tenant isolation? | Namespace + metadata filter + RLS |
| Idempotency key? | hash(tenant, doc, version, chunk_index) |

---

**Next:** [02 — Cloud vs Local, Update & Delete](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md) · **Drill:** [03 Q&A — Lifecycle](./03_QA_System_Design_Ingestion_Lifecycle.md) · [04 Q&A — AI Pipeline](./04_QA_AI_Pipeline_Chunk_Embed_Search_GraphRAG.md)
