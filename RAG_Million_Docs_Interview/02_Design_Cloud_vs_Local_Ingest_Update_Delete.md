# 02 — Design: Cloud vs Local Ingest, Update & Delete

**Purpose:** Interview-ready system design for the two source cases interviewers always ask about — documents in **cloud storage** (S3/GCS) vs **local filesystem** — plus the lifecycle questions that separate mid-level from senior: **what happens when a PDF is updated or deleted**, how chunks stay consistent, and why naive RAG breaks after summarization.

**Audience:** Alok — VoXgent RAG (LangChain, LangGraph, Pinecone, GCP), FastAPI/Python

**Prerequisites:** Read [01 — 1M Documents Architecture](./01_Design_1M_Documents_Architecture.md) first for bulk ingest + query at scale.

**Also study:**
| Topic | Link |
|-------|------|
| Scale architecture (1M docs) | [01 — 1M Documents Architecture](./01_Design_1M_Documents_Architecture.md) |
| Lifecycle Q&A (50) | [03 — System Design & Lifecycle Q&A](./03_QA_System_Design_Ingestion_Lifecycle.md) |
| AI pipeline depth Q&A (50) | [04 — Chunk → Search → GraphRAG Q&A](./04_QA_AI_Pipeline_Chunk_Embed_Search_GraphRAG.md) |
| Full RAG step-by-step | [Infosys 06 — RAG Pipeline Step-by-Step](../Infosys_Interview_Prep/06_RAG_Pipeline_Step_by_Step.md) |
| LLM system design module | [SD 14 — AI & LLM System Design](../System_Design_Prep/14_AI_LLM_System_Design.md) |
| Production RAG Q&A supplement | [AI 02 — RAG Pipeline Q&A](../AI_Engineer_Prep/02_RAG_Pipeline_QA.md) |

---

## How to use this file

| Label | Meaning |
|-------|---------|
| **Say this** | Exact words to speak in the interview |
| **Compare** | Short "X vs Y" — use when they ask *why* |
| **Follow-up** | What they ask next |
| **Whiteboard** | Draw this while talking |

---

## Opening — Cloud vs Local (30 seconds)

### Say this

> "Whether documents live in **cloud object storage** or on a **local filesystem**, the RAG pipeline is the same shape: discover source → copy raw bytes to an immutable ingest bucket → hash for idempotency → parse → chunk → embed → upsert to vector + BM25 indexes, with **Postgres as source of truth** for document and chunk registries. The difference is **how we detect new and changed files**. Cloud: S3/GCS event notifications or scheduled listing with ETag/hash comparison — push-driven, scalable, no agent on customer network. Local: a **sync agent or watcher** on the customer side that uploads to our ingest API or staging bucket — pull/push hybrid, with strict security because we never mount arbitrary customer filesystems into our prod cluster without an isolated agent and signed uploads. **Updates and deletes are first-class events**: new `doc_version`, re-chunk, swap index pointers, tombstone old chunks — never overwrite vectors in place. **Deletes** go soft-tombstone first for instant query safety, then async vector/BM25 purge."

### Compare

| Dimension | Cloud (S3/GCS) | Local filesystem |
|-----------|----------------|------------------|
| Discovery | Event notifications, ListObjectsV2, GCS notifications | inotify/FSEvents watcher, scheduled sync agent |
| Change detection | ETag, `x-amz-meta-content-hash`, object versionId | mtime + size (fast), SHA-256 (authoritative) |
| Network | Same region as workers — low latency | Agent uploads over HTTPS to ingest API |
| Security | IAM roles, bucket policies, tenant prefixes | Never NFS-mount customer disk in prod; isolated agent |
| Scale | Millions of objects, parallel List + queue | Bounded by agent throughput; batch uploads |
| Delete signal | `ObjectRemoved`, lifecycle expiration | Agent reports deletion or missing from manifest |

### Follow-up they will ask

1. **"What if two sources feed the same chatbot?"** — Unified registry keyed by `(tenant_id, source_uri)`; cloud and local both land in the same raw bucket + same worker pipeline.
2. **"Do you re-embed on every cron run?"** — No. `content_hash` skip: if hash unchanged, mark `indexed_at` and exit.
3. **"What breaks if you skip versioning?"** — Stale chunks answer after PDF replace; summarization embeddings point at old text; Graph-RAG edges reference deleted entities.

---

## Core principle — Postgres is source of truth; indexes are derived

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         SOURCE OF TRUTH (Postgres)                           │
│  documents ──< chunks ──< chunk_embeddings (optional cache)                  │
│  status: pending | processing | active | tombstoned | purged                 │
└─────────────────────────────────────────────────────────────────────────────┘
         │                              │
         │ upsert / filter              │ delete by doc_id + version
         ▼                              ▼
┌─────────────────────┐        ┌─────────────────────┐
│  Vector index       │        │  BM25 / keyword     │
│  (Pinecone, pgvector)│        │  (OpenSearch, ES)   │
└─────────────────────┘        └─────────────────────┘
         │                              │
         └──────────┬───────────────────┘
                    ▼
            Query path filters:
            tenant_id + status=active + doc_version <= pinned
```

**Say this:** "Vectors and BM25 are **derived indexes**. If they drift from Postgres, a reconciliation job wins — Postgres decides what is active. Query path always filters on registry state, not 'trust the vector DB alone'."

---

## Unified document registry schema

Every ingest path — cloud or local — writes the same row shape.

### `documents` table

| Column | Type | Purpose |
|--------|------|---------|
| `doc_id` | UUID (PK) | Stable identity across versions; never reuse after hard purge |
| `tenant_id` | UUID / string | Multi-tenant isolation; every query filters on this |
| `source_uri` | text | Canonical locator: `s3://bucket/key`, `file:///path`, `gs://...` |
| `source_type` | enum | `s3`, `gcs`, `azure_blob`, `local_agent`, `upload` |
| `content_hash` | char(64) | SHA-256 of raw bytes; idempotency key per version |
| `version` | int | Monotonic per `doc_id`; increment on content change |
| `status` | enum | `pending`, `processing`, `active`, `tombstoned`, `purged`, `failed` |
| `filename` | text | Display + MIME hint |
| `mime_type` | text | Route parser (PDF, DOCX, …) |
| `byte_size` | bigint | Quota, progress |
| `raw_storage_uri` | text | Immutable copy in **your** raw bucket |
| `indexed_at` | timestamptz | Last successful index of this version |
| `created_at` | timestamptz | First seen |
| `updated_at` | timestamptz | Any registry mutation |
| `deleted_at` | timestamptz | Soft delete timestamp |
| `metadata` | jsonb | ACL, product line, tags, external_id |

**Unique constraint:** `(tenant_id, source_uri, version)` and `(tenant_id, source_uri, content_hash)`.

**Say this:** "`doc_id` is stable — when HR replaces `benefits-2024.pdf`, we increment `version`, not create a confusing second `doc_id` unless it's truly a different document. `source_uri` is how the customer thinks about the file; `raw_storage_uri` is our immutable ingest copy."

### `chunks` table

| Column | Type | Purpose |
|--------|------|---------|
| `chunk_id` | UUID (PK) | Globally unique chunk identity |
| `doc_id` | UUID (FK) | Parent document |
| `version` | int | Must match parent `documents.version` when active |
| `chunk_index` | int | Order within document (0-based) |
| `text` | text | Chunk body (or pointer to object storage if huge) |
| `token_count` | int | Context budget, billing |
| `metadata` | jsonb | `page`, `section_title`, `heading_path`, `parent_chunk_id` |
| `status` | enum | `active`, `tombstoned`, `purged` |
| `vector_id` | text | External ID in Pinecone/OpenSearch (`chunk_id` often reused) |
| `created_at` | timestamptz | |

**Index:** `(doc_id, version, chunk_index)` unique; `(tenant_id, doc_id, status)` for purge jobs.

**Say this:** "Each chunk row is version-scoped. When we re-index v3, we insert new chunk rows for v3; v2 chunks get `tombstoned`, not updated in place. Vector IDs can equal `chunk_id` so upsert is idempotent."

### Optional: `ingest_jobs` / `outbox`

| Column | Purpose |
|--------|---------|
| `job_id`, `doc_id`, `version`, `stage` | Track parse → chunk → embed → index |
| `attempts`, `last_error` | Retry + DLQ |
| `idempotency_key` | `(tenant_id, source_uri, content_hash)` |

---

## Case A — Cloud storage architecture (S3 / GCS)

### When interviewers say this

> "We have 500k PDFs in S3. Ingest them into an enterprise chatbot RAG. What happens when someone uploads a new file or replaces an old one?"

### High-level diagram

```
 Customer S3/GCS                    Your platform
 ┌──────────────┐                  ┌──────────────────────────────────────────┐
 │  s3://cust/  │                  │                                          │
 │  policies/   │───(A) event─────>│  Event receiver (SQS / Pub/Sub /       │
 │  *.pdf       │    notification  │  EventBridge / Cloud Function)           │
 └──────────────┘                  │         │                                │
        │                          │         ▼                                │
        │ (B) nightly ListObjects  │  Ingest orchestrator                     │
        └─────────────────────────>│  - resolve tenant from prefix/IAM        │
                                   │  - HEAD object → ETag / metadata hash    │
                                   │  - compare to documents.content_hash     │
                                   │         │                                │
                                   │         ▼                                │
                                   │  Copy to raw bucket (immutable)          │
                                   │  s3://your-raw/{tenant}/{doc_id}/v{n}/   │
                                   │         │                                │
                                   │         ▼                                │
                                   │  Enqueue: parse → chunk → embed        │
                                   │  (SQS / Cloud Tasks / Celery / Kafka)    │
                                   │         │                                │
                                   │         ▼                                │
                                   │  Workers → Postgres + Pinecone + BM25    │
                                   └──────────────────────────────────────────┘
```

### Step-by-step — cloud ingest (new document)

| Step | Action | Detail |
|------|--------|--------|
| 1 | **Event or list** | S3 `ObjectCreated` → SQS; or GCS `OBJECT_FINALIZE` → Pub/Sub. Backstop: nightly `ListObjectsV2` with prefix per tenant. |
| 2 | **Resolve tenant** | Bucket prefix `s3://cust-docs/{tenant_id}/...` or STS-assumed role tag. |
| 3 | **HEAD / get metadata** | Read ETag, size, `LastModified`. Optional customer-supplied `x-amz-meta-content-sha256`. |
| 4 | **Hash check** | Download stream (or S3 checksum) → SHA-256. Query: `SELECT ... WHERE tenant_id=? AND source_uri=? AND content_hash=? AND status='active'`. If hit → **skip** (idempotent). |
| 5 | **Assign version** | Existing `doc_id`? `version = max(version)+1`. New file? `doc_id = uuid4()`, `version = 1`. Insert `documents` row `status=pending`. |
| 6 | **Copy to raw bucket** | Server-side copy within cloud — durable, yours for re-parse. Path encodes version. |
| 7 | **Enqueue job** | Message: `{doc_id, version, raw_storage_uri, tenant_id, mime_type}`. Idempotency key on queue. |
| 8 | **Worker pipeline** | Parse → chunk → embed → upsert vectors with metadata `{doc_id, version, tenant_id, chunk_index, status}`. |
| 9 | **Activate** | Transaction: insert `chunks`, set parent `status=active`, `indexed_at=now()`. Tombstone prior version chunks (see Update flow). |
| 10 | **Ack** | Delete queue message; emit metric `ingest_success`. |

### Cloud-specific: delete detection

| Signal | Handling |
|--------|----------|
| S3 `ObjectRemoved` event | Trigger **Delete flow** (soft tombstone) — do not wait for reconciliation |
| Object replaced in place (same key) | Treated as **update** — new hash → new version |
| Versioning enabled (`versionId`) | Store `source_version_id` in metadata; map to `documents.version` |
| Lifecycle expiration | Same as delete event |

### Say this (cloud)

> "I'd never parse directly from the customer bucket on every query. Workers read from **our raw copy**, so re-indexing doesn't depend on customer IAM at query time. Events give near-real-time ingest; **listing is the backstop** because event delivery can be missed. Hash comparison prevents re-embedding unchanged files during nightly scans."

### Cloud security & ops

| Topic | Practice |
|-------|----------|
| IAM | Cross-account role or restricted prefix; least privilege `s3:GetObject`, `s3:ListBucket` |
| Encryption | SSE-KMS; tenant CMK optional |
| Cost | Transfer within region; batch small files; skip hash match before full download when ETag-strong |
| Poison PDF | Size cap, timeout, sandbox parser, DLQ after N attempts |

---

## Case B — Local filesystem architecture

### When interviewers say this

> "Documents live on a hospital's on-prem file share. Get them into our cloud RAG chatbot. How do you sync? What about security?"

### High-level diagram

```
 Customer network                         Your cloud (VPC)
 ┌─────────────────────────┐             ┌────────────────────────────────────┐
 │  /mnt/policies/*.pdf    │             │                                    │
 │                         │             │  Ingest API (HTTPS, mTLS optional) │
 │  ┌───────────────────┐  │  HTTPS      │  POST /v1/ingest/push              │
 │  │  Sync Agent       │──┼────────────>│  - presigned URL OR direct upload  │
 │  │  (Go/Rust/Python) │  │  + JWT      │  - manifest diff                   │
 │  │                   │  │             │         │                          │
 │  │  - walk / watch   │  │             │         ▼                          │
 │  │  - hash locally   │  │             │  Same pipeline as Case A           │
 │  │  - upload bytes   │  │             │  raw bucket → queue → workers      │
 │  └───────────────────┘  │             │                                    │
 │                         │             └────────────────────────────────────┘
 │  Optional: cron sync job│
 │  (no daemon)            │
 └─────────────────────────┘

  ⛔ NEVER in prod: mount customer NFS/SMB into your K8s pods "for convenience"
```

### Local discovery modes

| Mode | Mechanism | Pros | Cons |
|------|-----------|------|------|
| **Watch** | inotify (Linux), FSEvents (macOS), ReadDirectoryChangesW | Low latency | Misses events if agent down; burst handling |
| **Scheduled sync** | Cron every N minutes: walk tree, compare manifest | Simple, reliable | Higher latency |
| **Hybrid** | Watch + full reconcile nightly | Best production pattern | Slightly more complex |

### Sync agent responsibilities

1. **Config allowlist** — roots, extensions, max depth; ignore `*.tmp`, `~$*`.
2. **Stable file read** — wait for write quiescence (size stable 2s) before hash.
3. **Compute SHA-256** locally.
4. **Manifest diff** — local state file or server-side `last_seen_hash` per `source_uri`.
5. **Upload** — presigned PUT to raw bucket, or multipart for large PDFs.
6. **Report** — `POST /ingest/register` with `{source_uri, content_hash, byte_size, op: upsert|delete}`.
7. **Deletion** — on file remove or manifest miss after grace period → `op: delete`.

### Say this (local + security)

> "We do **not** mount the hospital file share into our production Kubernetes cluster. That couples security boundaries, adds flaky NFS latency, and creates a direct attack path. Instead, a **small agent** the customer runs — or we ship as a container they operate — reads local files and **pushes** to our ingest API with tenant credentials. All parsing happens in **our** worker fleet off the raw bucket. For regulated environments: mTLS, IP allowlist, audit log of every uploaded path and hash."

### Security caveats (interview gold)

| Anti-pattern | Why it fails | Correct pattern |
|--------------|--------------|-----------------|
| NFS-mount customer share in prod | Lateral movement, no audit trail, brittle | Push agent + presigned URLs |
| Trust filename only | Replace content, same name | Content hash + version |
| Agent runs as root | Customer pushback | Least-privilege read-only service account |
| Full tree upload every hour | Bandwidth, cost | Manifest diff + hash skip |
| No delete propagation | Ghost answers from removed files | Agent sends delete events |

### Local delete / update detection

| Scenario | Detection |
|----------|-----------|
| File overwritten | mtime/size change → re-hash → hash differs → update flow |
| File renamed | Old path → delete (or orphan TTL); new path → new `source_uri` row (or alias table) |
| File deleted | inotify DELETE or missing from nightly walk → delete flow |
| Agent offline 3 days | On reconnect: full reconcile; server may have tombstoned stale docs |

---

## Idempotency and `content_hash` skip

### Idempotency keys

| Stage | Key | Behavior on duplicate |
|-------|-----|----------------------|
| Register document | `(tenant_id, source_uri, content_hash)` | Return existing `doc_id`, `version`; no new job |
| Queue message | Same + `job_id` | Consumer dedupes via Postgres unique constraint |
| Vector upsert | `vector_id = chunk_id` | Upsert overwrites same ID — safe retry |
| Activate version | `(doc_id, version)` status transition | Single-writer or advisory lock |

### content_hash skip (Say this)

> "Before any parse job, we SHA-256 the raw bytes. If the active row for that `source_uri` already has the same hash, we **skip** — no parse, no embed, no spend. Nightly S3 listing becomes cheap: HEAD + hash compare, not full re-index. This is critical at million-doc scale."

### When hash skip is wrong

| Case | Fix |
|------|-----|
| Embedding **model** changed | Bump `embedding_model_version` in registry; force re-embed all active docs |
| Chunking **policy** changed | Global `pipeline_version`; re-chunk jobs ignore hash skip |
| Parser bug fixed | Targeted re-ingest by `doc_id` list or date range |

---

## Update flow — step-by-step (replace / revise PDF)

### Trigger

- Cloud: new object at same key, or new `versionId`, hash differs.
- Local: agent reports new hash for same `source_uri`.
- Admin portal: user uploads replacement via UI → same pipeline.

### Sequence diagram

```
Source          Orchestrator       Postgres        Workers         Vector/BM25
  │                  │                 │               │                │
  │  new bytes       │                 │               │                │
  ├─────────────────>│                 │               │                │
  │                  │  INSERT doc v+1 │               │                │
  │                  │  status=pending │               │                │
  │                  ├────────────────>│               │                │
  │                  │  copy raw       │               │                │
  │                  │  enqueue job    │               │                │
  │                  ├────────────────────────────────>│                │
  │                  │                 │  parse/chunk  │                │
  │                  │                 │<──────────────│                │
  │                  │                 │  INSERT chunks│                │
  │                  │                 │  (new version)│                │
  │                  │                 │               │  upsert new   │
  │                  │                 │               ├───────────────>│
  │                  │                 │  TX: activate │                │
  │                  │                 │  v+1 active   │                │
  │                  │                 │  v tombstone │                │
  │                  │                 │<──────────────│                │
  │                  │                 │               │  async delete  │
  │                  │                 │               │  old vectors   │
  │                  │                 │               ├───────────────>│
```

### Steps (numbered for whiteboard)

1. **Detect change** — hash(new bytes) ≠ `content_hash` of active version.
2. **Create new version row** — same `doc_id`, `version = N+1`, `status = processing`. Prior version stays `active` until cutover (or use blue/green flag).
3. **Copy raw** — `raw_storage_uri` points to immutable v{N+1} object.
4. **Re-chunk** — parse PDF fresh; chunk boundaries may shift — **never reuse old chunk text**.
5. **Re-embed** — all chunks for v{N+1}; metadata includes `doc_version: N+1`.
6. **Upsert vectors** — new `chunk_id`s; old vectors still exist briefly.
7. **Atomic swap (Postgres TX)** —
   - Set v{N+1} `status = active`, `indexed_at = now()`.
   - Set all chunks where `doc_id` AND `version = N` → `status = tombstoned`.
   - Set document v{N} → `status = tombstoned` (or `superseded`).
8. **Async index cleanup** — batch delete vectors where `doc_id=X AND version=N` from Pinecone; delete BM25 docs.
9. **Invalidate caches** — query cache, optional summary rows, Graph-RAG edges (below).
10. **Emit event** — `document.updated {doc_id, old_version, new_version}` for downstream.

### Say this (update)

> "We **never update vectors in place** for a content change. New version gets new chunk rows and new embeddings. Cutover is a **registry flip** in Postgres so queries never see half-old/half-new. Old vectors are deleted asynchronously — but they're already excluded by `status=tombstoned` and version filter, so users can't retrieve stale text."

### Partial failure during update

| Failure point | State | Recovery |
|---------------|-------|----------|
| Parse fails on v+1 | v active, v+1 `failed` | Retry job; v still serves |
| Embed partial | v+1 chunks incomplete | Do not activate; retry missing |
| Activate OK, vector delete lag | Tombstoned in PG, stale in Pinecone | Query filter saves you; reconciliation deletes |
| Activate before embed done | **Bug** — prevent with state machine: only `active` after all chunks indexed |

---

## Delete flow — step-by-step

### Trigger

- Cloud `ObjectRemoved`, lifecycle expiration.
- Local agent `op: delete`.
- Admin "remove from knowledge base".
- GDPR / retention job.

### Sequence

```
User/Agent       API              Postgres           Async cleaner      Vector/BM25
   │              │                  │                     │                │
   │  delete      │                  │                     │                │
   ├─────────────>│  TX: tombstone   │                     │                │
   │              ├─────────────────>│                     │                │
   │              │  doc status=     │                     │                │
   │              │  tombstoned      │                     │                │
   │              │  all chunks      │                     │                │
   │              │  tombstoned      │                     │                │
   │              │  deleted_at=now  │                     │                │
   │<─────────────┤  200 OK          │                     │                │
   │  instant     │                  │  enqueue purge      │                │
   │              ├────────────────────────────────────────>│                │
   │              │                  │                     │  delete vectors│
   │              │                  │                     ├───────────────>│
   │              │                  │  hard purge rows    │                │
   │              │                  │<────────────────────│                │
```

### Steps

1. **Soft tombstone (sync, <100ms)** — `documents.status = tombstoned`, all related `chunks.status = tombstoned`, set `deleted_at`. **Queries stop immediately** via filter `status = active`.
2. **Enqueue purge job** — `{doc_id, all versions or single version}`.
3. **Async vector delete** — Pinecone delete by metadata filter `doc_id == X` or explicit ID list from `chunks.vector_id`.
4. **BM25 delete** — OpenSearch delete-by-query on `doc_id`.
5. **Raw object lifecycle** — optional delay (30d legal hold) then delete raw bucket objects.
6. **Hard purge Postgres** — after retention window: delete chunk rows, mark `purged` or remove document row; keep audit log entry.
7. **Graph invalidation** — remove entity nodes/edges sourced from this `doc_id` (see below).

### Say this (delete)

> "Delete is **two-phase**. Phase one: tombstone in Postgres — the chatbot stops retrieving that doc on the very next query because we filter on active status. Phase two: async workers rip vectors out of Pinecone and BM25. If phase two lags, users still don't see deleted content — that's why Postgres must lead the vector index."

### Soft vs hard delete

| Type | Query visible? | Storage | Use case |
|------|----------------|---------|----------|
| Soft tombstone | No | Rows remain | Instant UX, undo window |
| Hard purge | No | Rows gone | GDPR, cost |
| Legal hold | No | Raw kept, index gone | Litigation |

---

## Partial failure and reconciliation job

### How drift happens

- Worker crashes after Pinecone upsert but before Postgres commit.
- Vector delete API times out; Postgres says tombstoned.
- Retry duplicates partial chunk set.
- Manual ops mistake in index.

### Reconciliation job (nightly + on-demand)

```
┌─────────────────────────────────────────────────────────────────┐
│  Reconciliation worker (cron)                                    │
├─────────────────────────────────────────────────────────────────┤
│  1. PG → Vector: for each chunk where status=active             │
│     assert vector_id exists in Pinecone with matching version    │
│     missing → re-embed upsert                                      │
│                                                                  │
│  2. Vector → PG: sample or scan metadata doc_id                   │
│     if doc tombstoned/purged in PG → delete orphan vector        │
│                                                                  │
│  3. Count check: |active chunks| vs vector count per doc_id       │
│     mismatch → alert + repair job                                  │
│                                                                  │
│  4. BM25 parity: same doc_id/version rules                         │
│                                                                  │
│  5. Report: drift_metrics, repair_actions                          │
└─────────────────────────────────────────────────────────────────┘
```

### Say this

> "Postgres wins every argument. Reconciliation treats vector and BM25 as **eventually consistent caches**. I'd rather delete an orphan vector than serve a tombstoned document."

---

## Graph-RAG / entity graph invalidation on doc update

If you maintain an **entity graph** (entities extracted from chunks, edges = co-occurrence or relations):

| Event | Graph action |
|-------|--------------|
| Doc update vN → vN+1 | Re-extract entities from new chunks; mark edges with `source_doc_version < N+1` stale |
| Doc delete | Remove nodes/edges where sole provenance is this `doc_id`; or decay weight |
| Partial re-chunk | Entity IDs tied to `chunk_id` — old chunk_ids invalidated |

**Say this:** "Graph-RAG adds a **third derived index**. On document update, entity edges don't automatically refresh — you must re-run extraction on new chunks and invalidate edges pointing at old chunk IDs. Otherwise the graph answers with relationships from the old policy PDF."

---

## Why naive RAG fails after PDF update (especially with summarization)

### The failure modes interviewers want to hear

| Failure | What goes wrong |
|---------|-----------------|
| **No versioning** | Query retrieves mix of v1 and v2 chunks; contradictory context |
| **In-place vector overwrite** | Same vector ID, new text — cached embeddings wrong; hybrid index inconsistent |
| **Summary layer stale** | Doc-level summary embedding still describes old PDF; parent summary retrieved instead of fresh chunks |
| **No version pin in metadata filter** | Retriever returns `max(version)` inconsistently across shards |
| **Chunk boundary shift** | Old chunk 7 text ≠ new chunk 7; citations point to wrong pages |
| **Delete not propagated** | Removed doc still ranks in top-k |
| **Graph entities stale** | "Who approves PTO?" returns old manager from deleted doc |

### Summarization-specific path (common anti-pattern)

```
Naive pipeline (breaks):
  PDF → chunks → embed chunks
              → ALSO embed ONE doc-summary vector per file

User replaces PDF → only re-embeds chunks, forgets summary row
                 → OR summary updated but chunk IDs reused incorrectly

Query: "What's the vacation policy?"
  → retrieves doc-summary vector (old policy text in metadata)
  → LLM answers with 2023 numbers
```

### Correct approach (Say this)

> "If I use document-level summaries — for hierarchical RAG or Graph-RAG — summaries are **version-scoped** rows keyed by `(doc_id, version)`. On update, regenerate summary from new chunks, embed new summary vector, tombstone old summary ID. Retrieval filter always includes `status=active` and optionally `doc_version = latest` or pin version at query time for audit mode."

---

## Chatbot online path — version-aware retrieval

### Request flow

```
User query
    │
    ▼
┌─────────────────┐
│ Auth → tenant_id│
└────────┬────────┘
         ▼
┌─────────────────┐     optional: query rewrite, intent
│ Retrieval plan  │     filter: product_line, date, ACL
└────────┬────────┘
         ▼
┌─────────────────────────────────────────────────────────┐
│ Hybrid retrieve (vector + BM25)                          │
│  HARD FILTER: tenant_id = ?                              │
│               status = 'active'   (chunks + parent doc)  │
│               doc_version = latest OR explicit pin       │
│  TOP-K per shard → merge RRF                             │
└────────┬────────────────────────────────────────────────┘
         ▼
┌─────────────────┐
│ Reranker        │  cross-encoder; drop low scores
└────────┬────────┘
         ▼
┌─────────────────┐
│ Context pack    │  citations: filename, page, doc_version
└────────┬────────┘
         ▼
┌─────────────────┐
│ LLM generate    │  LangGraph: grounded answer + cite
└─────────────────┘
```

### Metadata on every vector (required)

```json
{
  "tenant_id": "t_abc",
  "doc_id": "d_uuid",
  "doc_version": 3,
  "chunk_id": "c_uuid",
  "chunk_index": 12,
  "status": "active",
  "source_uri": "s3://cust/policies/benefits.pdf",
  "page": 4,
  "indexed_at": "2026-09-01T12:00:00Z"
}
```

### Say this (online)

> "Every query carries `tenant_id` from JWT — no filter, no search. We filter `status=active` on both document and chunk metadata so tombstoned content never appears even if vector delete is slow. For compliance, we can pin `doc_version` in the citation so users know which revision answered them."

### Caching caveat

| Cache | Invalidation on update/delete |
|-------|----------------------------------|
| Query-result cache | Key includes `(tenant_id, query_hash, corpus_generation)` |
| Embedding cache | Key includes `content_hash` |
| LLM response cache | Short TTL or invalidate on `doc_updated` event |

---

## Comparison table — cloud vs local (interview crib sheet)

| Topic | Cloud (S3/GCS) | Local filesystem |
|-------|----------------|------------------|
| **Discovery** | Event notification + periodic list | Sync agent watch + nightly reconcile |
| **Change detect** | ETag, checksum, versionId | SHA-256 after stable read |
| **Ingress** | Same-region copy to raw bucket | HTTPS upload / presigned PUT |
| **Latency to index** | Seconds–minutes (event driven) | Minutes (sync interval) |
| **Delete signal** | ObjectRemoved event | Agent delete op / manifest diff |
| **Security** | IAM, bucket policy, prefix per tenant | Isolated agent; no prod mount |
| **Scale ceiling** | Very high (parallel list + queue) | Agent bandwidth + file count |
| **Ops burden** | Bucket policy, event wiring | Agent deployment, updates, monitoring |
| **Offline customer** | N/A — cloud is source | Agent queues uploads when back online |
| **Pipeline after raw bucket** | **Identical** | **Identical** |

---

## Interview whiteboard scripts

### Script 1 — "User deletes a PDF from the knowledge base" (3–4 min)

**Whiteboard:** Draw Postgres in center, chatbot on left, vector index on right.

**Say this while drawing:**

1. "User hits delete in admin UI — or S3 sends `ObjectRemoved` — or local agent sends delete."
2. "API transaction: find `doc_id` by `(tenant_id, source_uri)`, set `documents.status = tombstoned`, all `chunks.status = tombstoned`, `deleted_at = now()`."
3. "Return 200. **Chatbot path already safe** — next query filters `status=active`; deleted doc excluded."
4. "Enqueue purge worker: delete vectors by `doc_id` metadata filter from Pinecone; delete-by-query in OpenSearch."
5. "Optional 30-day retention on raw bucket for legal hold, then lifecycle delete."
6. "Hard purge Postgres rows after retention; audit log keeps `{doc_id, deleted_at, actor}`."
7. "If Graph-RAG: drop entity edges provenanced to this doc."

**Follow-up:** "What if purge fails?" — "Postgres tombstone still protects queries; reconciliation retries delete."

---

### Script 2 — "HR replaces the benefits PDF with a new version" (4–5 min)

**Whiteboard:** Timeline with v1 and v2 rows in `documents` table.

**Say this while drawing:**

1. "Same `source_uri`, new bytes — cloud event or agent upload."
2. "Hash differs from active v1 — **not** a skip."
3. "Insert `documents` row: same `doc_id`, `version=2`, `status=processing`. v1 stays active until cutover."
4. "Copy to raw bucket path `.../v2/` — immutable."
5. "Worker: parse → chunk → embed → upsert all v2 vectors with `doc_version=2`."
6. "Postgres transaction: v2 `active`, v1 document + chunks `tombstoned`."
7. "Async: delete v1 vectors from Pinecone/BM25."
8. "If we store doc-level summary: regenerate for v2, tombstone v1 summary vector."
9. "User asking vacation policy gets v2 chunks only — citations show version 2."

**Follow-up:** "Can users still ask about old policy?" — "Only if we keep v1 `active` with ACL or explicit 'archived corpus' filter; default is latest active only."

---

### Script 3 — "Why did summarization RAG break after the PDF changed?" (2 min)

**Say this:**

> "They likely had a **document-level summary embedding** — one vector for the whole PDF — and on replace they re-chunked but **didn't re-embed or tombstone the summary**. Queries hit the summary vector first in hierarchical retrieval, so the model saw 2023 policy text. Fix: version-scoped summaries, tombstone on update, same Postgres-led lifecycle as chunks. Second common bug: **no version filter** so top-k mixed old and new chunks — the LLM blended contradictory numbers."

---

## End-to-end lifecycle ASCII (both sources converge)

```
                    CLOUD                          LOCAL
                      │                              │
              S3/GCS events/list              Sync agent watch/cron
                      │                              │
                      └──────────┬───────────────────┘
                                 ▼
                    ┌────────────────────────┐
                    │  Register + hash skip  │
                    │  Postgres documents    │
                    └───────────┬────────────┘
                                ▼
                    ┌────────────────────────┐
                    │  Raw bucket (immutable)│
                    └───────────┬────────────┘
                                ▼
                    ┌────────────────────────┐
                    │  Queue workers         │
                    │  parse→chunk→embed     │
                    └───────────┬────────────┘
                                ▼
              ┌─────────────────┴─────────────────┐
              ▼                                   ▼
     ┌─────────────────┐                 ┌─────────────────┐
     │ Vector index    │                 │ BM25 index      │
     │ + chunk registry│                 │ + same metadata │
     └────────┬────────┘                 └────────┬────────┘
              └─────────────────┬─────────────────┘
                                ▼
                    ┌────────────────────────┐
                    │  Chatbot query path    │
                    │  tenant + active +     │
                    │  version-aware top-k   │
                    └────────────────────────┘

        UPDATE: new version → activate → tombstone old → async index delete
        DELETE: tombstone PG first → async vector/BM25 purge → hard purge later
```

---

## Quick reference — status state machine

### Document

```
pending → processing → active
                    ↘ failed (retry)
active → tombstoned → purged
```

### Safe query rule

```sql
-- Conceptual filter applied on every retrieval
SELECT c.*
FROM chunks c
JOIN documents d ON d.doc_id = c.doc_id AND d.version = c.version
WHERE d.tenant_id = :tenant
  AND d.status = 'active'
  AND c.status = 'active'
  AND d.deleted_at IS NULL;
```

Vector metadata filter mirrors this — **never rely on vector alone**.

---

## VoXgent anchor (personalize)

> "On VoXgent we ingested client healthcare policies via uploads and cloud storage, chunked with structure awareness, embedded to Pinecone with `tenant_id` and source metadata, and served answers in LangGraph with mandatory tenant filter. For production at scale I'd add explicit **version and tombstone** semantics in Postgres — that's the piece interviewers probe when they ask 'what happens when the PDF changes?' — and a sync agent pattern for on-prem customers instead of mounting their filesystem."

---

## Checklist before the interview

- [ ] Draw cloud path: event → hash → raw bucket → queue → indexes
- [ ] Draw local path: agent → upload → **same** pipeline
- [ ] Recite delete: tombstone PG first, async vector purge
- [ ] Recite update: new version, swap, tombstone old, never in-place embed overwrite
- [ ] Explain summarization failure: stale doc-summary vector, no version pin
- [ ] Mention reconciliation: Postgres wins drift
- [ ] Mention Graph-RAG edge invalidation on update/delete

---

**Next:** [03 — System Design & Lifecycle Q&A (50 questions)](./03_QA_System_Design_Ingestion_Lifecycle.md) · [04 — AI Pipeline Q&A](./04_QA_AI_Pipeline_Chunk_Embed_Search_GraphRAG.md)
