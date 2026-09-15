# 03 — System Design & Ingestion Lifecycle Interview Q&A (50 Questions)

**Format:** **Say this** = speak in the interview (30–90 sec) · **Compare** = short X vs Y when useful · **Follow-up** = likely next question with a short **Say this** answer

**Audience:** Alok — VoXgent (LangGraph, Pinecone, GCP), 1M-document RAG architecture interviews

**Study with design docs first:** Read [01 — 1M Documents Architecture](./01_Design_1M_Documents_Architecture.md) for the bulk-ingest + query-at-scale diagram, then [02 — Cloud vs Local, Update & Delete](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md) for source-specific ingest and lifecycle events. Use this file to **drill speakable answers** aloud — numbers, trade-offs, and failure stories.

| Label | Meaning |
|-------|---------|
| **Say this** | Narrate like a senior engineer at a whiteboard — idea first, then one VoXgent/GCP example |
| **Compare** | Side-by-side when the panel asks "why A not B" |
| **Follow-up** | What they ask next — answer in one or two lines |

---

## A. Scale, Capacity & Throughput

### Q1. How do you size a pipeline for 1 million documents?

**Say this:**

> Start with assumptions, not boxes. Average doc size — say 20 pages PDF, ~8K tokens after parse. Chunk at 512 tokens with 15% overlap → roughly 18 chunks per doc → **18M vectors**. Embed batch size 64, embedding API ~200 ms per batch → ~3 batches/sec per worker if not rate-limited. One worker ≈ 200 docs/hour after parse overhead. For a **72-hour bulk backfill**, you need ~15–20 parallel embed workers plus separate parse workers because parsing is CPU-bound and embedding is API-bound. Postgres holds doc metadata; object storage holds raw files; Pinecone holds derived vectors. Always state **peak vs steady**: backfill is peak, daily delta is steady.

**Compare:**

> **Bottom-up** (tokens × docs) = defensible numbers. **Top-down** ("we did 10K in a day, scale linearly") = quick but breaks on parser bottlenecks.

**Follow-up:**

1. **What if docs vary wildly in size?**  
   **Say this:** > Use p95 doc size for capacity, not mean. Queue depth and worker count sized for p95; rate limiters prevent one 500-page PDF from starving the fleet.

2. **How many Pinecone pods?**  
   **Say this:** > 18M vectors at 1536 dims — check Pinecone's vectors-per-pod for your tier; plan headroom for updates and tombstones. Shard by tenant if any single tenant exceeds pod limits.

---

### Q2. What queue architecture do you use between ingest stages?

**Say this:**

> **Stage-per-queue** pattern: `raw_uploaded` → parse queue → `parsed` → chunk queue → `chunked` → embed queue → `indexed`. Each stage has its own consumer group so a slow embed API does not block parsers. On GCP I'd use **Pub/Sub** or **Cloud Tasks** for at-least-once delivery; critical state transitions commit in Postgres before ack. Message payload is `{doc_id, tenant_id, version, content_hash}` — not the full PDF. Dead-letter after N retries with alert. VoXgent-style: same split, smaller scale, but the decoupling is identical.

**Compare:**

> **One big queue** = simple, head-of-line blocking. **Stage queues** = more ops, independent scaling and backpressure per stage.

**Follow-up:**

1. **Kafka vs Pub/Sub for this?**  
   **Say this:** > Pub/Sub is enough for doc pipeline fan-out on GCP. Kafka if you need long retention replay for audit or multiple independent replay consumers at very high throughput.

---

### Q3. How many workers do you run for parse vs embed?

**Say this:**

> **Parse workers** — CPU-bound, scale on GKE HPA by queue lag and CPU; often 2–4× embed count because PDF/OCR is slow. **Embed workers** — IO-bound to OpenAI/Vertex; scale on embed queue depth; cap concurrency per API key quota. Rule of thumb: if embed queue grows while parse queue is empty, add embed workers; opposite means parser bottleneck. Never share one pool — they'll fight for resources.

**Follow-up:**

1. **Autoscaling signal?**  
   **Say this:** > Primary: oldest message age in queue. Secondary: consumer lag. Scale down slowly — embedding has cold-start and rate-limit warmup.

---

### Q4. What throughput can you realistically hit for 1M docs?

**Say this:**

> With 20 embed workers, batch-64, ~150–250 docs/hour each after parse → **3K–5K docs/hour** fleet throughput → **1M in 8–14 days** if nothing else breaks. Push to **10K+/hour** with more workers, regional embed endpoints, skip-unchanged hashing, and pre-filtering junk files. Interview honesty: quote a **range** and name the bottleneck — usually embed API quota or Pinecone upsert rate, not disk.

**Compare:**

> **Theoretical API max** vs **end-to-end pipeline max** — always quote end-to-end including parse failures and retries.

**Follow-up:**

1. **How do you hit a 48-hour SLA?**  
   **Say this:** > Raise embed quota with provider, horizontal shard ingest by tenant prefix, skip unchanged via content hash, and run parse fleet on preemptible VMs with checkpoint resume.

---

### Q5. How do you handle a bulk backfill without breaking online query?

**Say this:**

> **Separate offline ingest path** — bulk workers write to same Pinecone index but with lower upsert priority or off-peak scheduling. Online query never waits on ingest. Postgres marks docs `indexing` vs `ready`; retrieval filters `status=ready` so half-indexed docs never surface. Rate-limit bulk upserts so query p99 stays flat. VoXgent parallel: voice agent queries ran while batch policy uploads continued — tenant filter plus status gate prevented partial answers.

**Compare:**

> **Dedicated bulk index then alias swap** = zero query interference, more complex cutover. **Shared index with throttling** = simpler, needs rate control.

**Follow-up:**

1. **Would you pause bulk during business hours?**  
   **Say this:** > Optional cron throttle — not required if upsert rate cap and retrieval filters are correct; business-hours pause is a cost/latency politeness knob.

---

## B. Offline vs Online Pipelines

### Q6. Explain offline vs online paths in a 1M-doc RAG system.

**Say this:**

> **Offline (async):** ingest, parse, chunk, embed, upsert — minutes to hours, bursty, retriable. **Online (sync):** user question → embed query → Pinecone retrieve → optional rerank → LangGraph generate — target **under 2–3 s** for chat, tighter for voice. They share the index and Postgres catalog but never share thread pools. Offline failures go to DLQ; online failures return degraded "try again" with circuit breakers on embed and LLM.

**Compare:**

> **Offline** optimizes throughput and cost. **Online** optimizes p99 latency and correctness of *read* path.

**Follow-up:**

1. **Can online trigger re-embed?**  
   **Say this:** > Only enqueue — "refresh this doc" API writes a job, returns 202. Never block the chat request on full reindex.

---

### Q7. When would you add a near-real-time ingest path?

**Say this:**

> When **freshness SLA < 15 minutes** — e.g. regulatory bulletin must be searchable immediately. GCS object finalize → Pub/Sub → fast lane workers with higher priority queue. Still async, but dedicated small pool and pre-warmed embed clients. Bulk backfill uses the slow lane. Same Postgres schema, different `priority` on queue message.

**Follow-up:**

1. **Does near-real-time change chunk strategy?**  
   **Say this:** > No — same chunker; you might use smaller docs or incremental chunk append for append-only logs, but PDF replacement still full reindex.

---

### Q8. How does LangGraph fit in offline vs online?

**Say this:**

> **Offline:** LangGraph optional — usually plain DAG workers unless you need agentic parse (tool calls to tables API, human review branch). **Online:** LangGraph orchestrates retrieve → grade documents → rewrite query → rerank → generate → cite. The graph enforces retries and "I don't know" when retrieval score is below threshold. Ingest stays mostly acyclic; query benefits from cycles.

**Compare:**

> **Batch DAG** for ingest reliability. **Stateful graph** for query flexibility.

**Follow-up:**

1. **One monolithic service or two?**  
   **Say this:** > Split — `ingest-service` and `query-api` — shared libs for chunk/embed, separate deploy and scale curves.

---

## C. Postgres Source of Truth vs Vector Derived

### Q9. Why is Postgres the source of truth and Pinecone derived?

**Say this:**

> Postgres holds **canonical doc records**: `doc_id`, `tenant_id`, `uri`, `content_hash`, `version`, `status`, `deleted_at`, chunk rows with text and offsets. Pinecone is a **search index** — lossy, eventually consistent, optimized for ANN not transactions. If Pinecone drifts, rebuild from Postgres + object storage. If Postgres is wrong, you're legally wrong. VoXgent pattern: never delete a row in Pinecone without a tombstone in Postgres first.

**Compare:**

> **Postgres** = ACID, joins, audit. **Pinecone** = fast similarity — rebuildable.

**Follow-up:**

1. **Store chunk text in Postgres or only object storage?**  
   **Say this:** > Postgres for hot chunks and metadata; object storage for full parsed JSON if size hurts DB — but keep enough in Postgres to rebuild vectors without re-parsing when possible.

---

### Q10. How do you keep Postgres and Pinecone in sync?

**Say this:**

> **Event-driven sync:** every state change in Postgres emits `DocIndexed`, `DocDeleted`, `DocUpdated`. Workers perform vector ops; reconciliation cron compares `postgres.indexed_version` vs `last_upserted_version`. Mismatch → re-enqueue. Retrieval always filters by Postgres `ready` flag cached in Redis with short TTL for hot path. Nightly job samples 1K random docs — vector count vs chunk count.

**Follow-up:**

1. **What if Pinecone upsert succeeds but Postgres update fails?**  
   **Say this:** > Outbox pattern — Postgres transaction includes outbox row; worker acks only after both Pinecone upsert and Postgres `indexed_at` update in one consumer idempotent flow. Reconciliation fixes orphans.

---

### Q11. Can you rebuild the entire vector index from Postgres?

**Say this:**

> Yes — that's the design test. Export all `ready` chunks with embedding model version, batch embed if vectors not stored, else replay stored vectors, upsert to new Pinecone index, alias swap. Store **`embedding_model_id`** and **`chunker_version`** on each chunk row so you know what to replay. Full rebuild of 18M vectors is hours — plan blue-green index migration.

**Compare:**

> **Store vectors in Postgres/blob** = faster rebuild, more storage. **Re-embed on rebuild** = simpler storage, higher rebuild cost.

**Follow-up:**

1. **How often would you full rebuild?**  
   **Say this:** > Rarely — model migration or catastrophic index corruption. Day-to-day is incremental upsert/delete.

---

## D. Sharding, Namespaces & Tenants

### Q12. How do you shard 1M documents across Pinecone?

**Say this:**

> Three layers: **(1)** Pinecone **namespace per tenant** for hard isolation and delete-by-namespace in offboarding. **(2)** Within mega-tenant, **metadata filter** on `collection_id` or date partition — not separate indexes unless quota forces it. **(3)** **Regional indexes** if data residency requires EU vs US. Vector ID = deterministic `{tenant_id}:{doc_id}:{chunk_index}` so upserts are idempotent.

**Compare:**

> **Namespace per tenant** = clean isolation, many namespaces. **Single index + tenant filter** = simpler ops, riskier if filter bug leaks data.

**Follow-up:**

1. **Pinecone namespace limits?**  
   **Say this:** > Know provider limits — if tenant count explodes, group small tenants into shared namespace with strict metadata filter, or shard tenants across multiple indexes.

---

### Q13. One big index with filters vs separate indexes per tenant?

**Say this:**

> **Separate index (or namespace) per tenant** when: compliance isolation, independent SLA, tenant offboarding = delete namespace, or embed model differs per tenant. **One index + `tenant_id` filter** when: thousands of small tenants, shared ops team, uniform embedding model — VoXgent-style healthcare clients each had namespace + mandatory filter from JWT. Rule: **filter is defense in depth**, not the only wall — auth must bind query to tenant.

**Compare:**

> **Separate indexes** = blast radius small, cost higher. **One index** = economical, one bug can cross tenants.

**Follow-up:**

1. **Hybrid search with filters?**  
   **Say this:** > BM25 index also partitioned by tenant — same isolation rule; never global BM25 without tenant prefix in doc ID.

---

### Q14. How do you handle a tenant with 500K docs vs one with 100?

**Say this:**

> **Fair scheduling** — weighted queue consumption so small tenants don't starve behind bulk upload. Per-tenant concurrency caps. Separate **bulk upload API** with declared doc count for capacity planning. Monitoring per-tenant lag metric: `time_since_upload_to_searchable`. Large tenant might get dedicated embed worker pool or namespace on dedicated Pinecone pod.

**Follow-up:**

1. **Noisy neighbor in shared index?**  
   **Say this:** > Rate limit upserts per tenant; query side unaffected if ANN is global — but upsert storm can hit shared pod limits → isolate big tenant.

---

## E. Cloud Storage Ingest (GCS / S3)

### Q15. Design GCS-triggered ingest for client uploads.

**Say this:**

> Client uploads to `gs://bucket/{tenant_id}/incoming/{uuid}.pdf`. **Object finalize** event → Pub/Sub → ingest API creates Postgres row `status=uploaded`, enqueues parse job with `{bucket, key, generation, tenant_id}`. Use **object generation** for idempotency — duplicate events ignored if generation matches. Virus scan / MIME validate optional Lambda/Cloud Function gate before parse. VoXgent on GCP: same pattern with signed upload URLs so files never hit app servers.

**Compare:**

> **Push (events)** vs **poll bucket** — events scale; poll only for legacy sources.

**Follow-up:**

1. **What if client overwrites same key?**  
   **Say this:** > New GCS generation → new version in Postgres, content hash compared — if changed, reindex pipeline; old chunks tombstoned.

---

### Q16. How do S3 Event Notifications differ for the same design?

**Say this:**

> **S3:ObjectCreated:*** → SNS/SQS/EventBridge → same worker contract. S3 **version ID** maps to GCS generation. Watch ** eventual consistency** on LIST after PUT — event is source of truth, don't rely on immediate HEAD. Cross-cloud clients: normalize to internal `IngestEvent {source, uri, version, tenant_id}` so workers are cloud-agnostic.

**Follow-up:**

1. **Large multipart uploads?**  
   **Say this:** > Trigger only on `CompleteMultipartUpload` event, not per part — filter in event rule.

---

### Q17. How do you secure the cloud ingest path?

**Say this:**

> **Per-tenant prefix IAM** — client SA can write only `/{tenant_id}/*`. Ingest worker SA read-only on bucket, no public ACL. Signed URLs with short TTL for browser upload. Scan for PII/malware before parse. Audit log every object → doc_id mapping in Postgres. Never trust filename for tenant — tenant comes from auth when issuing signed URL.

**Follow-up:**

1. **Cross-tenant path traversal?**  
   **Say this:** > Reject keys not matching authenticated tenant prefix; normalize path, block `..`.

---

### Q18. What metadata do you capture from cloud object headers?

**Say this:**

> `content_type`, `size`, `etag`/MD5, `generation`, `custom_metadata` (original filename, uploaded_by). Store on Postgres doc row. **ETag + size** quick duplicate check before full download. Custom metadata `doc_type=policy` drives chunker selection in worker.

---

## F. Local Filesystem Ingest

### Q19. How do you ingest from a local filesystem or SFTP dump?

**Say this:**

> **Batch scanner** — cron or CLI `ingest scan /mount/customer/export` walks tree, computes SHA-256 per file, compares to Postgres hash → skip unchanged. New/changed → upload to GCS canonical bucket (even if source was local — **centralize blob store**), enqueue parse. Don't read local disk from online API — mirror to object storage first for durability. SFTP: pull to staging bucket, same pipeline from Q15.

**Compare:**

> **Watch folder (inotify)** = low latency, misses events if down. **Scheduled scan + hash** = reliable, minutes lag.

**Follow-up:**

1. **Millions of small files on NFS?**  
   **Say this:** > Parallel walker with checkpoint file list, rate-limit metadata ops, batch enqueue — don't hold 1M paths in memory.

---

### Q20. Cloud vs local ingest — same pipeline or fork?

**Say this:**

> **Same downstream** — parse → chunk → embed → upsert. **Different adapters** upstream: GCS event adapter vs directory scanner. Internal contract `IngestJob` identical. VoXgent narrative: some clients emailed ZIPs (local/ad-hoc), others S3 — both landed in GCS then one pipeline.

**Compare:**

> **Two pipelines** = duplicate bugs. **Adapter pattern** = one lifecycle, two sources.

**Follow-up:**

1. **Do you ever parse directly from laptop path in prod?**  
   **Say this:** > No — prod always copies to object storage with versioning; laptop path is dev/test only.

---

## G. Hash-Based Skip & Versioning

### Q21. Explain content-hash skip logic.

**Say this:**

> On ingest, compute **SHA-256 of normalized bytes** (or parsed text hash after strip whitespace). Compare to Postgres `content_hash` for active version. **Match → mark job done, no embed spend.** Mismatch → bump `version`, tombstone old chunk IDs, reindex. Use hash of file + **chunker_version** + **embed_model** — if only embed model changed, same text hash still triggers re-embed.

**Follow-up:**

1. **Hash collision risk?**  
   **Say this:** > SHA-256 — ignore for interview; optionally byte compare on collision.

---

### Q22. How do you version documents?

**Say this:**

> Postgres: `(doc_id, version)` monotonic integer; `content_hash` per version; `is_current` flag. Vectors carry metadata `doc_version`. Query filters **`is_current=true`** always. Update = insert version N+1, async index, swap pointer when index complete, then delete N vectors. Never mutate chunks in place — append-only versioning simplifies audit and rollback.

**Compare:**

> **In-place update** = simpler tables, stale vector risk. **Version append** = clean audit, brief dual-version window.

**Follow-up:**

1. **Can users query old version?**  
   **Say this:** > Only if product requires — pass `version` in API; default current only.

---

### Q23. What triggers reindex besides content change?

**Say this:**

> **Chunker config change**, **embedding model upgrade**, **metadata schema** needing re-embed, **legal hold release** requiring purge re-scan. Store **`pipeline_version`** on doc; batch job finds `pipeline_version < current` and re-enqueues. Same hash skip fails when pipeline_version mismatch even if bytes unchanged.

---

## H. Delete Lifecycle

### Q24. Walk through soft delete with tombstone.

**Say this:**

> User/API **DELETE /docs/{id}** → Postgres `deleted_at=now()`, `status=tombstoned` — **immediate** for auth and listing. Query path checks tombstone **before** retrieve — doc never returned even if vectors linger. Async worker deletes Pinecone IDs by prefix `{tenant}:{doc_id}:*`. BM25 index delete same IDs. When vector delete confirms, `status=purged_vectors`. Soft delete gives **instant UX** and **async eventually consistent** search index.

**Compare:**

> **Soft tombstone** = fast, recoverable. **Hard delete immediate** = slow, blocks on vector API.

**Follow-up:**

1. **Window where vector still searchable?**  
   **Say this:** > Seconds to minutes — mitigate with retrieval filter `deleted_at IS NULL` joined via cached denylist of doc_ids in Redis updated on tombstone.

---

### Q25. How do you async delete 50K vectors for one doc?

**Say this:**

> Batch delete by **metadata filter** `doc_id=X` if Pinecone supports delete-by-filter; else list chunk IDs from Postgres and delete in batches of 1K. Worker retries with exponential backoff. Track `vector_delete_job_id` in Postgres. Large doc delete is non-blocking HTTP 202. Idempotent — deleting already-gone IDs is OK.

**Follow-up:**

1. **Delete entire tenant?**  
   **Say this:** > Drop Pinecone namespace + Postgres tenant cascade + bucket prefix lifecycle rule — runbook with confirmation gate.

---

### Q26. GDPR erasure, legal retention, and hard purge?

**Say this:**

> **Soft delete** removes from search immediately (tombstone). **GDPR right-to-erasure** triggers **hard purge workflow**: delete Postgres rows, object storage objects, all Pinecone vectors, BM25 entries, and **document backup rotation** (crypto-shred or tenant-scoped backup expiry). **Legal retention** may block purge — hold flag keeps blob in cold storage but vectors tombstoned so chatbot cannot retrieve. Audit log every erasure with `request_id` and completion proof. Soft delete is reversible; hard purge is irreversible after confirmation gate.

**Compare:**

> **Soft** = reversible, vectors may lag. **Hard** = irreversible, must prove all copies gone.

**Follow-up:**

1. **Backups and replicas?**  
   **Say this:** > GDPR answer includes backup rotation — crypto-shred or re-key tenant data in backups; document RPO/RTO for erasure.

---

### Q27. How do you prevent deleted docs appearing in chatbot answers?

**Say this:**

> **Three gates:** (1) Postgres tombstone check on doc_ids in retrieval results. (2) Metadata filter exclude `deleted=true` in Pinecone. (3) LangGraph node validates citations against live catalog before generate. Defense in depth — one layer can lag. Log any hit on tombstoned doc_id — alert for reconciliation bug.

---

## I. Update, Reindex & Stale Chunks

### Q28. User replaces a PDF — what happens end to end?

**Say this:**

> New upload → new object generation → hash differs → create **version N+1** row, `status=indexing`. Parse/chunk/embed upsert new vectors with `doc_version=N+1`. On success, flip **`is_current=N+1`** in transaction, enqueue delete of N vectors. Queries filter current version only — users never see mixed chunks. VoXgent pain point: summarization broke when old chunks lingered — this swap prevents that.

**Compare:**

> **Delete-then-insert** = search gap during reindex. **Insert-then-swap** = brief double storage, zero gap.

**Follow-up:**

1. **Partial reindex failure?**  
   **Say this:** > Keep current pointer at N; N+1 stays `indexing_failed`; alert; old doc still serves until retry succeeds.

---

### Q29. How do you prevent stale chunks after update?

**Say this:**

> **Never upsert new chunks without version metadata.** Retrieval filter **`doc_version = current`**. After swap, async delete old version vectors. Reconciliation job finds vectors where metadata version < Postgres current → delete. Chunk ID includes version in vector ID so old and new coexist safely during cutover without overwrite collisions.

**Follow-up:**

1. **Same chunk index, different text?**  
   **Say this:** > Vector ID includes version — `{tenant}:{doc}:{version}:{chunk_idx}` — so no silent overwrite.

---

### Q30. Blue-green index swap for large reindex?

**Say this:**

> Build **index-green** while **index-blue** serves query. Bulk upsert all tenants or one tenant to green. Validation: recall@k sample, count match. Pinecone **collection alias** or app config flip `PINECONE_INDEX=green`. Keep blue 48h for rollback, then decommission. Use for embedding model migration affecting all 1M docs.

**Compare:**

> **In-place upsert** = simpler, query mixed old/new during migration. **Blue-green** = clean cutover, 2× index cost temporarily.

**Follow-up:**

1. **Dual-write during migration?**  
   **Say this:** > Prefer single write to green with alias flip; dual-write only if zero-downtime ingest must continue during days-long backfill.

---

### Q31. Incremental update for one changed section?

**Say this:**

> If parse yields stable **section IDs** (heading hash), re-chunk only changed section, upsert those chunk IDs, delete removed section chunks. Full PDF replacement usually full reindex — section incremental needs structured parse (HTML, markdown, not scanned PDF). Most enterprise PDFs → full doc version bump for simplicity.

---

## J. DLQ, Retries & Idempotency

### Q32. How do retries and DLQ work in ingest?

**Say this:**

> **Transient errors** (429 embed, 503 Pinecone) — exponential backoff, max 5 attempts, jitter. **Permanent errors** (corrupt PDF, password lock) — fail fast to **DLQ** with error class. DLQ dashboard + replay tool after fix. Alert on DLQ depth > threshold. Parse crash mid-doc → job status `failed`, doc retry from checkpoint if page-level parse supported else full reparse.

**Compare:**

> **Infinite retry** = poison pill blocks partition. **DLQ** = isolates bad docs, fleet keeps moving.

**Follow-up:**

1. **Who replays DLQ?**  
   **Say this:** > SRE or pipeline admin with `replay --doc_id` after parser upgrade; not automatic infinite loop.

---

### Q33. How do you make ingest idempotent?

**Say this:**

> **Deterministic vector IDs** from tenant+doc+version+chunk. Upsert = replace same ID. Queue messages carry **idempotency key** `{doc_id, version, stage}` — Postgres unique constraint on processed keys. GCS **object generation** dedupes events. Embed worker checks `chunk.status=embedded` before API call. At-least-once delivery safe.

**Follow-up:**

1. **Exactly-once possible?**  
   **Say this:** > End-to-end exactly-once is expensive — aim **at-least-once + idempotent writes**; reconciliation catches duplicates.

---

### Q34. Poison document handling?

**Say this:**

> Doc that crashes parser 3 times → DLQ, `status=quarantined`, notify tenant admin with file name. Fleet continues. Store **minimal error fingerprint** (stack hash, page number) for support. Option: skip OCR for that doc class after classify. Never block whole queue on one bad PDF.

---

## K. Latency Budgets, Backpressure & Rate Limits

### Q35. What latency budget for online RAG query?

**Say this:**

> **Chat target p99 ~2–3 s**, voice tighter ~1.5 s total. Budget: embed query 100–200 ms, Pinecone 50–150 ms, rerank 200–400 ms optional, LLM TTFT 300–800 ms, generation rest depends on length. Ingest is **not** in this budget. Instrument each span in LangGraph nodes. If over budget, drop rerank first, reduce top-k, cache frequent query embeddings.

**Compare:**

> **Voice** = strict cap, shorter answers. **Chat** = can tolerate 4–5 s with streaming UX.

**Follow-up:**

1. **Streaming help latency?**  
   **Say this:** > Improves perceived latency — time-to-first-token matters for UX even if total time similar.

---

### Q36. How do you apply backpressure on embed API limits?

**Say this:**

> **Token bucket** per API key in Redis — workers acquire tokens before batch embed. On 429, **global slowdown** — reduce consumer prefetch, exponential backoff. Separate **reservation** for online query embed vs offline bulk (online gets 20% guaranteed headroom). Queue age metric triggers scale-out before hitting 429 storm.

**Follow-up:**

1. **Multiple embed providers?**  
   **Say this:** > Fallback router — primary Vertex, secondary OpenAI — with same vector dimension requirement or separate index per model.

---

### Q37. How does backpressure propagate upstream?

**Say this:**

> If embed queue age > 10 min, **pause parse consumers** via feature flag or reduced prefetch — don't pile parsed chunks in memory. If Postgres write slow, block enqueue at API. **Pressure signals flow backward** stage by stage. Prevents OOM and wasted parse CPU on unembeddable backlog.

**Compare:**

> **Unbounded queues** = hidden failure, OOM. **Backpressure** = slower ingest, stable system.

---

## L. Cost at 1M Documents

### Q38. Rough cost to ingest 1M documents?

**Say this:**

> **Embeddings dominate.** 1M docs × 18 chunks × ~400 tokens/chunk ≈ 7.2B tokens — at ~$0.02/1M tokens (order-of-magnitude) → **~$140 embed** (model-dependent). Parse/OCR higher if scanned — add **$0.50–2/doc** for heavy OCR worst case. Pinecone: 18M vectors — pod cost depends on tier (**$ hundreds–low thousands/month**). GCS storage 1M × 2 MB avg ≈ 2 TB → **~$40/mo**. **Total first-time ingest: low thousands USD** for digital PDFs; **much higher** if OCR-heavy — state assumption aloud.

**Follow-up:**

1. **How to cut cost?**  
   **Say this:** > Hash skip unchanged, smaller chunks where quality allows, batch embed, cheaper embed model with eval gate, dedupe near-duplicate docs.

---

### Q39. Ongoing cost and hot/cold storage tiers?

**Say this:**

> **Steady-state spend:** Pinecone monthly, GCS storage, delta embed for churn (~1–5% docs/month), plus query embed + LLM — LLM often exceeds storage at scale. **Hot tier:** Standard storage for active docs, full vectors in Pinecone, Postgres chunk rows. **Cold tier:** Nearline/Archive for compliance retention with rare access — either keep vectors (costly, instant search) or **drop vectors and retain blob only**, re-embed on rehydrate (cheaper, spiky latency). Lifecycle rules move by `last_accessed`. Monitor **cost per query** and per-tenant chargeback.

**Compare:**

> **Cold vectors retained** = higher Pinecone bill, no re-embed wait. **Cold blobs only** = lower index cost, reindex on access.

**Follow-up:**

1. **Legal hold on cold doc?**  
   **Say this:** > Block lifecycle delete; tombstone search only if regulations require hiding from users while retaining bytes.

---

### Q40. Embedding model migration — how do you re-embed 1M docs?

**Say this:**

> Treat as **new derived index**: bump `embedding_model_id` in config, blue-green Pinecone index, batch re-embed from cached chunk text in Postgres (skip re-parse). Workers tag vectors with new model version. Validate recall@k on golden set before alias flip. **Cost ≈ initial embed** minus parse. Schedule off-peak with rate limits. Rollback = flip alias back to old index. Only worth it when eval shows **>10–15% retrieval lift** or provider deprecates old model.

---

## M. Observability & Reconciliation

### Q41. What metrics do you dashboard for ingest?

**Say this:**

> **Queue:** depth, oldest message age per stage. **Throughput:** docs/hour indexed, chunks/hour embedded. **Quality:** parse failure rate, DLQ rate, empty retrieval rate online. **Lag:** p95 upload→searchable time. **Cost:** embed tokens/day. **Sync:** postgres_ready_count vs pinecone_vector_count drift. Alert on lag SLO breach and DLQ spike.

**Follow-up:**

1. **SLO for upload to searchable?**  
   **Say this:** > Bulk: 24h acceptable; near-real-time lane: 15 min p95; state both.

---

### Q42. Design a reconciliation job.

**Say this:**

> Nightly cron: for each tenant sample or full diff if affordable — Postgres chunk count vs Pinecone count by `doc_id`. Find **orphan vectors** (no Postgres row), **missing vectors** (Postgres ready but no Pinecone ID), **version mismatch**. Auto-fix: re-enqueue missing, delete orphans. Report CSV to S3 for audit. Weekly full tenant reconcile for premium SLAs.

**Compare:**

> **Continuous outbox** = prevents drift. **Reconciliation** = safety net — both required at 1M scale.

**Follow-up:**

1. **Full diff 18M vectors expensive?**  
   **Say this:** > Paginate by tenant, use Postgres as driver list, batch fetch Pinecone metadata — don't load all vectors.

---

### Q43. Distributed tracing across ingest?

**Say this:**

> **`trace_id` from upload API** propagated through Pub/Sub attributes and worker logs. Span per stage: download, parse, chunk, embed batch, upsert. Link to `doc_id` in LangGraph for online side. Grafana/Datadog: filter one doc's journey for support tickets "why isn't my PDF searchable yet?"

---

## N. Multi-Tenant Isolation

### Q44. How do you enforce tenant isolation end to end?

**Say this:**

> **Auth:** JWT `tenant_id` never from client body alone. **Ingest:** signed URL scoped to tenant prefix. **Postgres:** row-level security or tenant_id on every row. **Pinecone:** namespace + mandatory filter from token. **LangGraph:** retrieve node injects filter from state, not user prompt. **Logs:** redact cross-tenant. Pen-test: attempt retrieve with forged tenant in metadata — must fail.

**Follow-up:**

1. **Shared embed worker pool cross-tenant risk?**  
   **Say this:** > Workers are stateless — no isolation issue if jobs carry tenant and write only their namespace; bug is wrong metadata write — test with chaos injection.

---

### Q45. Noisy tenant bulk upload — fair share?

**Say this:**

> **Token bucket per tenant** on enqueue rate and embed concurrency. **Weighted fair queue** — round-robin dequeue across tenants when backlog mixed. Enterprise tenant can buy dedicated queue shard. Monitor per-tenant **indexing lag** separately in status API.

---

## O. Chatbot Integration & API Shape

### Q46. API shape for chatbot querying the 1M-doc index?

**Say this:**

> **`POST /v1/chat`** `{message, conversation_id, filters?}` → returns `{answer, citations[{doc_id, chunk_id, snippet, page}], trace_id}`. **`GET /v1/docs/{id}/status`** for indexing state. **`POST /v1/docs/upload`** returns `{doc_id, upload_url}`. **`DELETE /v1/docs/{id}`** tombstone. Internal: LangGraph service calls retrieve with **`tenant_id` from auth context**, never from request body. Streaming via SSE for tokens.

**Compare:**

> **Sync upload** small files OK. **Signed URL** required for large PDFs — don't proxy bytes through API.

**Follow-up:**

1. **How does bot know doc still indexing?**  
   **Say this:** > Status API + prompt injection "these docs pending" — or retrieval excludes non-ready and bot says "your upload is still processing."

---

### Q47. How do citations map to lifecycle state?

**Say this:**

> Citation carries **`doc_version` and `indexed_at`**. If user asks about doc being replaced, bot cites **current version only** post-swap. If tombstoned doc somehow in context, validation node strips and regenerates. Citations enable "view source" deep link to signed URL from Postgres uri.

---

## P. Failure Modes

### Q48. Embed half-complete — crash after 10 of 20 chunks?

**Say this:**

> Postgres tracks **`chunks_embedded / chunks_total`**. Crash leaves doc `status=indexing_partial`. Retry job embeds **only missing chunks** by status flag — idempotent upsert. Query excludes partial docs unless **`allow_partial=false` default**. Reconciliation finds partials older than 1h and re-enqueues.

**Compare:**

> **All-or-nothing transaction** across 20 embed calls = impractical. **Per-chunk checkpoint** = resilient.

**Follow-up:**

1. **User sees half doc in search?**  
   **Say this:** > No — gate on `indexing_complete` before flipping to `ready`.

---

### Q49. Parser crash on page 847 of 900?

**Say this:**

> **Page-level checkpoint** if parser supports — store parsed pages 1–846, resume from 847. Scanned PDF OCR slower — same pattern. If atomic parse required, fail doc to DLQ with partial artifact for debugging. Don't mark ready. Metrics: **`parse_failure_by_mime`**. Fallback: textract alternate parser queue.

**Follow-up:**

1. **Retry same file infinitely?**  
   **Say this:** > Max attempts → DLQ → human triage; maybe deliver with "partial content" product flag for legal review only.

---

### Q50. Index lag — Postgres says ready but Pinecone 30 min behind?

**Say this:**

> **Root cause:** upsert backlog, wrong status flip order, or cache stale. **Fix order:** only flip Postgres `ready` **after** Pinecone upsert ack for all chunks; invalidate Redis catalog cache on flip. **Mitigation:** retrieval denylist until ack; reconciliation job every 5 min for `ready` docs with vector spot-check. **Communicate lag** in status API `searchable_at`. Never flip ready before vectors exist — that's the bug class.

**Compare:**

> **Postgres-first ready** = lying to users. **Vector-ack-first ready** = truthful, slight delay.

**Follow-up:**

1. **Cache showing deleted doc?**  
   **Say this:** > TTL 60s max on hot metadata; pub/sub cache invalidation on tombstone; LangGraph final cite check hits Postgres read-through.

---

## Related

| Doc | Why |
|-----|-----|
| [01 — 1M Documents Architecture](./01_Design_1M_Documents_Architecture.md) | Whiteboard diagram for bulk ingest + query |
| [02 — Cloud vs Local, Update & Delete](./02_Design_Cloud_vs_Local_Ingest_Update_Delete.md) | Source adapters + lifecycle events |
| [04 — AI Pipeline Q&A (50)](./04_QA_AI_Pipeline_Chunk_Embed_Search_GraphRAG.md) | Chunking, hybrid search, Graph-RAG depth |
| [Infosys 02 — RAG Deep Dive (60)](../Infosys_Interview_Prep/02_RAG_Deep_Dive_QA.md) | Full RAG fundamentals + production patterns |
| [SD 14 — AI & LLM System Design](../System_Design_Prep/14_AI_LLM_System_Design.md) | LLM gateway, eval, cost, multi-tenancy module |