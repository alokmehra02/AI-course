# Module 16 — Cheat Sheet, Numbers & Study Plan

> **What this module makes you able to do:** walk into an interview with the framework,
> numbers, phrases, and flashcards already in muscle memory — and follow a 12-week plan
> that maps directly to the module files in this folder.
>
> **Interview weight:** ★★★★★ (this is what you read the night before)
>
> **Prerequisites:** Modules 00–15. This module does not teach concepts; it compresses them.

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 16.1 | [One-page interview framework](#161-one-page-interview-framework) | ★★★★★ |
| 16.2 | [Numbers to memorize](#162-numbers-to-memorize) | ★★★★★ |
| 16.3 | [Estimation drill — 3 worked problems](#163-estimation-drill--3-worked-problems) | ★★★★★ |
| 16.4 | [Technology decision tables](#164-technology-decision-tables) | ★★★★★ |
| 16.5 | [Senior-sounding phrases](#165-senior-sounding-phrases) | ★★★★☆ |
| 16.6 | [Red flags checklist](#166-red-flags-checklist) | ★★★★★ |
| 16.7 | [Anti-patterns named](#167-anti-patterns-named) | ★★★★☆ |
| 16.8 | [Flashcards](#168-flashcards) | ★★★★★ |
| 16.9 | [12-week study plan](#169-12-week-study-plan) | ★★★★☆ |
| 16.10 | [Week-before and day-of checklist](#1610-week-before-and-day-of-checklist) | ★★★★☆ |
| 16.11 | [Questions to ask the interviewer](#1611-questions-to-ask-the-interviewer) | ★★★☆☆ |

---

## 16.1 One-page interview framework

Print this. Tape it above your monitor. The numbers are the budget from
[Module 00](./00_Interview_Playbook.md) §0.2.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  SYSTEM DESIGN — 45 MINUTES                                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  OPENING (30 s)                                                             │
│  "I'll spend ~5 min on requirements, ~5 on scale, ~5 on API + schema,     │
│   ~15 on architecture, ~10 on a deep dive you pick, ~5 to close.           │
│   Does that work, or should I go deep somewhere specific?"                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. REQUIREMENTS (0–5 min)                                                  │
│     □ 3–5 functional flows, numbered                                        │
│     □ Every NFR is a NUMBER (QPS, p99, availability, retention)             │
│     □ Explicit OUT OF SCOPE (3+ items)                                      │
│     □ Read:write ratio stated out loud                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│  2. ESTIMATION (5–10 min)                                                   │
│     □ DAU → actions/day → avg QPS → peak (×3–5)                            │
│     □ Storage: rows × row size × retention × replication                     │
│     □ Bandwidth if media-heavy                                              │
│     □ "This is a caching problem" OR "this needs sharding" — pick one       │
├─────────────────────────────────────────────────────────────────────────────┤
│  3. API (10–12 min)                                                         │
│     □ 3–5 endpoints; one shown in full (status codes, idempotency)          │
│     □ Separate hot path from admin path if SLOs differ                        │
├─────────────────────────────────────────────────────────────────────────────┤
│  4. DATA MODEL (12–15 min)                                                  │
│     □ Tables/collections with keys and indexes                                │
│     □ WHICH store and WHY (not "we'll use a database")                      │
│     □ Hot vs cold data split if volume > 1 TB                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  5. ARCHITECTURE (15–25 min)                                               │
│     □ One diagram: clients → LB → services → stores → async                 │
│     □ Walk WRITE path, then READ path, narrating every hop                  │
│     □ Name the async boundary ("ingest returns 202; workers do the rest")    │
├─────────────────────────────────────────────────────────────────────────────┤
│  6. DEEP DIVES (25–40 min) — interviewer picks 2–3                          │
│     □ The hard part of THIS problem (ordering, fan-out, idempotency…)       │
│     □ Failure mode + mitigation with a number                               │
│     □ Real company example if you have one                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  7. CLOSE (40–45 min)                                                       │
│     □ "I'd start with X because at Y QPS…"                                  │
│     □ "The decision I'd defend hardest is…"                                 │
│     □ "The thing I'd watch in production is…"                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  RECOVERY MOVES                                                             │
│  • Stuck → "Give me 10 seconds — deciding fan-out on write vs read."        │
│  • Lost → "Let me restate requirements to make sure I'm solving the right    │
│    problem."                                                                │
│  • Over time → "I'm going to skip detail on X and spend time on Y — the      │
│    riskier part."                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Scoring signals to hit every minute:** requirements discipline, quantitative
reasoning, justified choices, failure thinking, narration. See
[Module 00 §0.1](./00_Interview_Playbook.md#01-what-is-actually-being-scored).

---

## 16.2 Numbers to memorize

### Latency (same-region, well-tuned)

| Operation | Typical | Say in interview |
|-----------|---------|------------------|
| L1 cache / in-process lookup | ~50 ns | "nanoseconds — irrelevant at our scale" |
| Redis GET (same VPC) | 0.3–1 ms p99 | "sub-millisecond" |
| Postgres PK lookup (indexed, warm) | 1–5 ms | "single-digit ms" |
| Postgres simple JOIN (2 tables) | 5–20 ms | |
| Cross-AZ within region | +1–3 ms | |
| Cross-region (US ↔ EU) | 80–150 ms RTT | "I would not sync-write across this" |
| SSD sequential read | ~1 GB/s | |
| HDD seek | 5–10 ms | |
| TLS handshake (full) | 1–3 RTTs | "session resumption cuts this" |
| DNS lookup (cached) | ~1 ms | |
| DNS lookup (uncached) | 20–120 ms | |

**Rule of thumb:** users notice >100 ms; they abandon at >1 s for interactive UI.
Backend p99 targets: read APIs 50–200 ms; writes 100–500 ms; async jobs seconds–minutes.

### Availability nines

| Nines | Downtime/year | Downtime/month | When to claim it |
|-------|---------------|----------------|------------------|
| 99% (two nines) | 3.65 days | 7.2 h | Dev tools, internal dashboards |
| 99.9% | 8.76 h | 43.8 min | Most SaaS APIs |
| 99.95% | 4.38 h | 21.9 min | Payments-adjacent, notifications |
| 99.99% | 52.6 min | 4.38 min | Redirect/CDN hot paths |
| 99.999% | 5.26 min | 26 s | Only with redundancy + no human deploys |

**Memorize:** 99.9% ≈ 9 hours/year. 99.99% ≈ 53 minutes/year.

### Powers of 2 (for back-of-envelope)

| Power | Value | Mnemonic use |
|-------|-------|--------------|
| 2^10 | ~1 thousand (1 KB) | |
| 2^20 | ~1 million (1 MB) | |
| 2^30 | ~1 billion (1 GB) | |
| 2^40 | ~1 trillion (1 TB) | |
| 2^50 | ~1 quadrillion (1 PB) | |

**Seconds per day:** use **100,000** instead of 86,400 (within 16%, makes division trivial).

| Duration | Seconds |
|----------|---------|
| 1 day | 86,400 ≈ **100,000** |
| 1 month | ~2.6M ≈ **2.5M** |
| 1 year | ~31.5M ≈ **30M** |

### Throughput ceilings (planning figures, not benchmarks)

| System | Rough ceiling | Notes |
|--------|---------------|-------|
| Single Postgres primary | 5k–15k simple writes/s | depends on row size, indexes |
| Postgres PK reads | 50k–100k/s | with connection pool + replicas |
| Redis single shard | 100k–200k ops/s | small values, pipelining |
| Kafka partition | 5–50 MB/s ingest | size messages, not just count |
| Kafka consumer (one thread) | 1k–10k msgs/s | depends on processing |
| HTTP API (stateless, 1 vCPU) | 500–2k req/s | Node/FastAPI, JSON |
| CDN edge | millions/s | not your problem to size |
| S3/GCS PUT | 3,500/s per prefix | prefix = hot-spot risk |
| APNs/FCM (per connection) | ~2k req/s | pool connections |

**Little's Law:** `concurrency = throughput × latency`. At 1,000 QPS and 100 ms p99,
you need ~100 in-flight requests per instance.

### Storage sizing shortcuts

| Entity | Typical row size |
|--------|------------------|
| User profile | 500 B–2 KB |
| Message (chat) | 200–500 B + media ref |
| Event/log record | 200–500 B |
| URL shortener row | 250–500 B |
| Notification record | 300–500 B |
| Embedding vector (1536-dim float32) | ~6 KB |

**Replication multiplier:** ×3 for HA is the default planning factor.

---

## 16.3 Estimation drill — 3 worked problems

Do these on paper in 5 minutes each. Then check your arithmetic.

### Drill 1 — Photo-sharing app (Instagram-like)

**Given:** 100M DAU, each user posts 0.5 photos/day, views 50 photos/day.

```
Posts:   100M × 0.5  = 50M/day  → 500/s avg → 1,500/s peak
Views:   100M × 50   = 5B/day   → 50,000/s avg → 150,000/s peak
```

Photo size 2 MB average (after compression). **This is a read-heavy CDN problem.**

```
Upload storage:  50M × 2 MB = 100 TB/day  (needs object storage + lifecycle)
Read bandwidth:  150k/s × 200 KB thumbnail ≈ 30 GB/s at edge (CDN's job)
Metadata:        50M rows × 500 B = 25 GB/day → ~9 TB/year (Postgres or Cassandra)
```

**Conclusion out loud:** "150k reads/sec means every request must be served from CDN
or cache — the origin never sees viral traffic. Writes at 1,500/sec need async
processing for thumbnails and feed fan-out."

### Drill 2 — Real-time bidding / ad server

**Given:** 10M QPS bid requests, 1% win rate, 50 ms p99 latency budget.

```
Wins:     100k/sec
Storage:  100k × 500 B = 50 MB/s = 4.3 TB/day of bid logs (columnar, 30-day = 130 TB)
```

Latency budget breakdown:

```
  Network in          5 ms
  Feature lookup      5 ms  (Redis, precomputed)
  ML inference       20 ms  (GPU batch or compiled model)
  Auction + response 10 ms
  Buffer             10 ms
  ─────────────────────
  Total              50 ms p99
```

**Conclusion:** "At 10M QPS this is an in-memory problem with horizontal sharding by
`user_id` or `campaign_id`. Logging is async — the bid path never waits on disk."

### Drill 3 — SaaS document search (RAG)

**Given:** 10k tenants, 1k docs/tenant, 10 pages/doc, 500 tokens/page. 100 queries/tenant/day.

```
Corpus:     10k × 1k × 10 × 500 = 50B tokens total
Chunks:     ~500 tokens/chunk → 100M chunks
Embeddings: 100M × 6 KB       ≈ 600 GB vector index
Queries:    10k × 100 / 100k  = 10 QPS avg → 50 QPS peak (not a throughput problem)
```

Cost (order of magnitude):

```
Embedding ingest (one-time): 50B tokens × $0.02/1M ≈ $1,000
Query: 1M queries/day × ($0.001 embed + $0.01 LLM) ≈ $11k/day at scale
```

**Conclusion:** "10 QPS average is tiny — the design problem is tenant isolation, index
freshness, and cost per query, not raw QPS. I'd shard the vector index by `tenant_id`."

---

## 16.4 Technology decision tables

### Primary data store

| Need | Choose | Avoid | Why |
|------|--------|-------|-----|
| ACID multi-row transactions | PostgreSQL | DynamoDB alone | Orders, ledger, inventory |
| Massive KV, predictable access pattern | DynamoDB / Bigtable | Postgres at 100k+ writes/s | Single-digit-ms at scale |
| Time-series / append-only analytics | ClickHouse / BigQuery | Postgres | Compression + column scans |
| Full-text + filters | Postgres + GIN / OpenSearch | Vector DB alone | Hybrid search |
| Session/cache/ephemeral | Redis | Postgres | TTL, atomic ops, speed |
| Blob/media | GCS / S3 | Database BLOBs | Cost, CDN integration |
| Graph traversals (3+ hops) | Neo4j / graph layer | Recursive SQL | Path queries |
| High-write counter / feed | Cassandra / Scylla | Postgres primary | Wide-column, no hot row on PK |

### Messaging

| Pattern | Choose | When |
|---------|--------|------|
| Task queue (one consumer) | SQS / Pub/Sub pull | Job processing, retries |
| Event log (replay, ordering) | Kafka / Pub/Sub topics | Audit, fan-out, CDC |
| Fire-and-forget notify | Pub/Sub push | Webhooks, metrics |
| Delayed delivery | Tiered topics + scheduler | Retries, scheduled sends |
| Exactly-once illusion | Idempotent consumer + dedup store | Never claim true exactly-once |

### Caching

| Pattern | Use when | Cost |
|---------|----------|------|
| Cache-aside | Read-heavy, tolerates stale | Stampede risk — add single-flight |
| Write-through | Must not serve stale after write | Write latency +2× |
| Write-behind | Write-heavy, stale reads OK | Data loss window on crash |
| CDN | Static/media, geographic | Invalidation complexity |
| Negative cache | Scanner / enumeration attacks | Must TTL short |

### Consistency

| Requirement | Pattern |
|-------------|---------|
| Strong per entity | Single leader + sync replica OR row-level lock |
| Eventual OK (seconds) | Async replication + version vectors |
| Cross-service atomicity | Saga + compensating transactions |
| Read-your-writes | Route to leader or sticky session |
| Global low-latency reads | Multi-region replicas + accept staleness |

### API style

| Style | Use when |
|-------|----------|
| REST + JSON | Public API, CRUD, browser clients |
| gRPC | Internal service-to-service, streaming |
| GraphQL | Mobile clients, varied field needs |
| WebSocket / SSE | Server push, chat, live updates |
| Webhooks | Integrate with customer systems |

---

## 16.5 Senior-sounding phrases

Say these naturally — not as a checklist monologue.

1. "Let me pin down the read-write ratio first, because that tells me whether this is a caching problem or a sharding problem."
2. "I'll propose some numbers and you can correct me — that way we're designing against a shared spec."
3. "I'm explicitly scoping X out so we can go deep on Y."
4. "The hot path and the admin path have different SLOs, so I'd split them into separate services."
5. "Ingest returns 202; everything expensive happens asynchronously behind a log."
6. "At this QPS, one Postgres primary is fine — I'd shard when the working set stops fitting in RAM."
7. "I'd fail open here because a protective component that takes down the API is worse than the abuse."
8. "The exception is security controls — login and OTP must fail closed."
9. "I'm choosing at-least-once delivery and making the consumer idempotent — true exactly-once isn't worth the coordination cost."
10. "The dangerous window is between 'provider accepted' and 'we durably recorded it' — that's where duplicates come from."
11. "I'd use a deterministic idempotency key derived from the business event, not a random UUID per retry."
12. "Fan-out on write is simpler to read; fan-out on read is simpler to write — the celebrity problem decides."
13. "I'd smear the spike with jitter so we don't get a thundering herd at 9 AM in every timezone."
14. "Keyset pagination, not OFFSET — OFFSET on page 10,000 makes the database skip nine million rows."
15. "I'd partition by `user_id`, not `tenant_id`, because the largest tenant becomes a hot partition."
16. "Negative caching with a short TTL so a scanner can't turn cache misses into database load."
17. "Single-flight per key on cache miss — one in-flight fetch, everyone else awaits the same promise."
18. "I'd watch consumer lag, not CPU — lag is the metric that means users are waiting."
19. "Separate topics and worker pools per priority class — a marketing campaign must never delay an OTP."
20. "I'd ship the limiter in shadow mode first — the fastest incident is a correct system with a wrong number."
21. "Cross-region sync write adds 150 ms — I'd never put that on the user-facing path."
22. "I'd expire rows but never reclaim codes/IDs — reuse is a security incident, not a storage optimization."
23. "The ledger is append-only; balances are derived, never updated in place."
24. "I'd reserve an estimated cost at admission and settle the actual after — same pattern as LLM token metering."
25. "Tenant isolation is a hard boundary: separate index namespace, separate encryption key, separate rate limit."
26. "I'd rather over-provision the connection pool to the database's max than to the number of app instances."
27. "If I can't explain what breaks first and at what number, I don't understand the design yet."
28. "Let me walk the write path, then the read path — that's where the bottlenecks hide."

---

## 16.6 Red flags checklist

Before you finish, scan this list. If you said any of these, recover.

| # | Red flag | Say instead |
|---|----------|-------------|
| 1 | "We'll use microservices, Kafka, Redis, and Kubernetes." | Name one problem each solves; start monolith if QPS < 5k |
| 2 | "It needs to scale." | "At 3,500 peak QPS, one primary and two replicas handle this." |
| 3 | "We'll use NoSQL because SQL doesn't scale." | "I need transactions on orders — Postgres until proven otherwise." |
| 4 | Drawing boxes before requirements | "Before I design, let me confirm scope and numbers." |
| 5 | 90 seconds of silence | Narrate: "I'm deciding between fan-out on write vs read." |
| 6 | No failure modes | "If Redis dies, we absorb 60% in-process LRU; rest hits Postgres at X QPS." |
| 7 | "Exactly-once delivery" (unqualified) | "At-least-once with idempotent consumers." |
| 8 | `INCR` then `EXPIRE` as two commands | "One Lua script — atomic read-modify-write." |
| 9 | OFFSET pagination at scale | "Keyset: `WHERE id > $cursor LIMIT 100`." |
| 10 | Storing images in Postgres | "Object storage + CDN; DB holds metadata and signed URL." |
| 11 | Single global Redis for 1M writes/s | "Shard by hash tag; or local buckets with reconcile." |
| 12 | Sync call chain 6 services deep | "Async boundary after step 2; 202 + worker." |
| 13 | No idempotency on payments/writes | "`Idempotency-Key` header, 24h dedup store." |
| 14 | "We'll shard day one" at 100 writes/s | "Premature — fixed logical shards when index > 60% RAM." |
| 15 | Ignoring read:write ratio | State it: "100:1 reads — this is a cache design." |
| 16 | One size fits all availability | "99.99% on redirect; 99.9% on create — different paths." |
| 17 | `sleep()` in Kafka consumer | "Pause partition until `not_before`; never block poll loop." |
| 18 | No out-of-scope list | Name 3 things you are NOT building. |
| 19 | Custom crypto / auth from scratch | "OAuth2/OIDC provider; bcrypt/argon2 for passwords." |
| 20 | No closing trade-off summary | "I'd start with X; defend Y hardest; watch Z in prod." |

---

## 16.7 Anti-patterns named

One line each — recognize the name, explain the fix.

| Anti-pattern | One line |
|--------------|----------|
| **Thundering herd** | Cache expires → thousands of simultaneous backend fetches; fix: jittered TTL + single-flight. |
| **Cache stampede** | Same as thundering herd on a hot key. |
| **Hot partition / hot shard** | One Kafka partition or DB shard gets all traffic; fix: salt key or sub-shard counters. |
| **Hot key** | One Redis key at 100k ops/s; fix: split into N sub-keys, aggregate on read. |
| **N+1 queries** | Loop loads related rows one-by-one; fix: JOIN or `WHERE id IN (...)`. |
| **Dual write** | Write DB and queue separately without atomicity; fix: transactional outbox. |
| **Distributed monolith** | Microservices that must all be up for one request; fix: async boundaries + bulkheads. |
| **God service** | One service owns everything; fix: extract by change rate and SLO. |
| **Retry storm** | Clients retry instantly on 503; fix: `Retry-After` + exponential backoff with jitter. |
| **Cascading failure** | Slow dependency backs up thread pool; fix: timeouts, circuit breakers, bulkheads. |
| **Split brain** | Two leaders think they own the cluster; fix: quorum + fencing tokens. |
| **TOCTOU race** | Check-then-act without lock; fix: unique constraint or `SELECT FOR UPDATE`. |
| **Poison message** | One bad message blocks partition forever; fix: DLQ after N attempts + skip. |
| **Unbounded queue** | Queue grows until OOM; fix: backpressure, drop/shed, or scale consumers. |
| **Fan-out on write for celebrities** | Bieber posts → 100M inbox writes; fix: hybrid fan-out (write for normal, read for celebs). |
| **Chatty API** | 50 HTTP calls per page load; fix: batch endpoint or GraphQL field selection. |
| **Golden hammer** | Kafka for everything; fix: queue for tasks, log for events, DB for truth. |
| **Resume-driven architecture** | Tech chosen to sound impressive; fix: simplest store that meets NFRs. |
| **Leaky abstraction** | ORM hides N+1 until production; fix: explain query plan for hot paths. |
| **SPOF** | Single Redis/DB/LB with no failover story; fix: replica + health check + failover path. |

---

## 16.8 Flashcards

Cover the right column. Answer from the left. Aim for one sentence each.

| Concept | One-sentence answer |
|---------|---------------------|
| ACID | Atomicity, Consistency, Isolation, Durability — transactions all succeed or all roll back. |
| BASE | Basically Available, Soft state, Eventual consistency — trade consistency for availability under partition. |
| CAP theorem | Under partition, choose Consistency or Availability — not both. |
| PACELC | If Partition: A or C; Else: Latency or Consistency. |
| Strong consistency | Every read sees the latest write; usually one leader. |
| Eventual consistency | Replicas converge; reads may be stale for seconds. |
| Read-your-writes | User sees their own writes immediately; route to leader or sticky session. |
| Quorum read/write | R + W > N replicas ensures overlap; tunable consistency. |
| Leader election | One node is writer; others replicate; needs odd number for quorum. |
| Split brain | Two leaders after partition; prevented by quorum + fencing. |
| Replication lag | Time for replica to catch primary; causes stale reads. |
| Sharding | Horizontal partition by shard key; routing layer directs queries. |
| Resharding | Moving data between shards; use consistent hashing or fixed logical shards. |
| Consistent hashing | Keys map to ring; add/remove node moves only adjacent keys. |
| Hot shard | One shard gets disproportionate traffic; fix key design or salting. |
| Index (B-tree) | Speeds lookups; costs write amplification and storage. |
| Covering index | Index contains all queried columns; avoids table lookup. |
| Connection pool | Reuse DB connections; size to DB max, not instance count. |
| N+1 query | ORM loop issues one query per row; batch or JOIN instead. |
| Isolation: READ COMMITTED | See only committed rows; default in Postgres. |
| Isolation: REPEATABLE READ | Same transaction sees same snapshot; phantom reads possible. |
| Serializable | Strongest; prevents anomalies; may retry transactions. |
| Deadlock | Two transactions wait on each other's locks; DB picks victim to abort. |
| Optimistic locking | Version column; update fails if version changed since read. |
| Pessimistic locking | `SELECT FOR UPDATE` holds row lock until commit. |
| 2PC | Two-phase commit across DBs; blocking, fragile — avoid at scale. |
| Saga | Sequence of local transactions with compensating steps on failure. |
| Idempotency key | Same key + same body → same result; safe retries. |
| At-least-once | Message delivered ≥1 times; consumer must dedupe. |
| At-most-once | Message delivered ≤1 times; may lose on failure. |
| Exactly-once (claimed) | Usually at-least-once + idempotent consumer + dedup store. |
| Transactional outbox | Write business row + outbox row in one DB tx; relay publishes to queue. |
| CDC | Change Data Capture — stream DB changes to downstream systems. |
| CQRS | Separate read and write models; eventual consistency between them. |
| Event sourcing | Store events, not state; rebuild state by replay. |
| Cache-aside | App reads cache, on miss loads DB and populates cache. |
| Write-through | Write updates cache and DB synchronously. |
| Write-behind | Write to cache first; async flush to DB. |
| Cache invalidation | Hardest problem — TTL, version keys, or pub/sub invalidation. |
| TTL jitter | Randomize expiry so keys don't all expire together. |
| Single-flight | One in-flight load per key; others await same result. |
| CDN | Edge caches static content geographically; origin shield optional. |
| Signed URL | Time-limited auth for direct object storage access. |
| Token bucket | Refill tokens at rate R; burst up to capacity B. |
| Leaky bucket | Smooth output rate; shapes traffic. |
| Sliding window | Count requests in rolling window; more accurate than fixed window. |
| Fixed window | Counter per minute; 2× burst at boundary. |
| GCRA | Generic Cell Rate Algorithm; one scalar for rate limit state. |
| Fail open | On limiter failure, allow traffic — for protective limits. |
| Fail closed | On failure, deny — for security limits (login, OTP). |
| Circuit breaker | Stop calling failing dependency; probe after cooldown. |
| Bulkhead | Isolate thread pools per dependency so one slow call doesn't exhaust all. |
| Backpressure | Slow producer when consumer can't keep up. |
| Load shedding | Drop low-priority traffic under overload. |
| Timeout | Every outbound call gets one; default 1–5 s unless measured. |
| Retry with jitter | Exponential backoff + randomness; prevents synchronized retries. |
| DLQ | Dead letter queue — poison messages after max retries. |
| Poison message | Bad message that always fails processing; route to DLQ. |
| Consumer lag | Unprocessed messages behind head; primary Kafka health metric. |
| Partition (Kafka) | Ordered log segment; parallelism unit; choose key wisely. |
| Consumer group | Partitions divided among consumers; one consumer per partition max. |
| Pub/Sub vs queue | Pub/sub: many subscribers; queue: one consumer per message. |
| Webhook | HTTP callback on event; you retry with backoff on failure. |
| Long polling | Client holds request until data or timeout; simpler than WebSocket. |
| WebSocket | Full-duplex persistent connection; stateful, needs sticky LB or pub/sub fan-out. |
| SSE | Server pushes one-way events over HTTP; simpler than WebSocket for feeds. |
| gRPC | Binary, HTTP/2, streaming; internal service calls. |
| REST idempotency | PUT/DELETE idempotent; POST needs `Idempotency-Key`. |
| API versioning | URL path `/v1/` or header; never break without version bump. |
| Cursor pagination | `?cursor=xxx&limit=50` — stable under concurrent writes. |
| OAuth2 | Delegated authorization; access token + refresh token. |
| OIDC | OAuth2 + identity layer (ID token with claims). |
| JWT | Signed token; stateless but hard to revoke — use short TTL + refresh. |
| RBAC | Role-based access control — user has roles, roles have permissions. |
| ABAC | Attribute-based — policy on user/resource attributes. |
| mTLS | Mutual TLS — both client and server present certificates. |
| OWASP Top 10 | Injection, broken auth, XSS, etc. — know top 3 for interviews. |
| SSRF | Server fetches attacker-controlled URL; block private IPs on URL validators. |
| SLI | Service Level Indicator — measured metric (availability, latency). |
| SLO | Service Level Objective — target for SLI (99.9% uptime). |
| SLA | Contract with customer; includes penalties. |
| Error budget | 100% − SLO; spend on velocity or save for incidents. |
| RPO | Recovery Point Objective — max acceptable data loss duration. |
| RTO | Recovery Time Objective — max acceptable downtime duration. |
| Golden signals | Latency, traffic, errors, saturation (Google SRE). |
| RED method | Rate, Errors, Duration — for request-driven services. |
| USE method | Utilization, Saturation, Errors — for resources (CPU, disk). |
| Distributed trace | Span per hop; trace ID correlates across services. |
| Structured logging | JSON logs with trace_id, user_id — searchable in prod. |
| Health check | Liveness (restart if dead) vs readiness (stop sending traffic). |
| Feature flag | Runtime toggle; decouple deploy from release. |
| Strangler fig | Gradually replace monolith by routing slices to new services. |
| Service mesh | Sidecar proxies handle mTLS, retries, metrics per pod. |
| ULID | Lexicographically sortable ID; good for DB primary keys. |
| HyperLogLog | Probabilistic unique count; ~0.8% error, 12 KB per counter. |
| Bloom filter | Probabilistic set membership; false positives possible, no false negatives. |
| Vector embedding | Dense float array representing semantic meaning of text. |
| RAG | Retrieve relevant chunks, augment prompt, generate answer. |
| Chunking | Split documents for embedding; overlap 10–20% for context continuity. |
| Hybrid search | Combine keyword (BM25) + vector similarity; merge scores. |
| Reranker | Cross-encoder rescores top-k candidates; better precision, higher cost. |
| Semantic cache | Cache LLM responses by embedding similarity of query. |
| LLM gateway | Rate limit, route, log, fallback across model providers. |
| Prompt injection | User text manipulates system prompt; sanitize and separate roles. |
| Fan-out on write | Push post to all followers' feeds at write time — fast read, slow write. |
| Fan-out on read | Merge follows at read time — slow read, fast write. |
| Celebrity problem | User with millions of followers breaks write fan-out. |
| Message ordering | Per-partition ordering in Kafka; per-conversation in chat. |
| Lease | Time-bound lock; holder must renew or lock expires. |
| Fencing token | Monotonic token prevents stale leader from writing. |
| Double-entry ledger | Every debit has matching credit; balances derived not stored. |
| Payment idempotency | Same `Idempotency-Key` never double-charges. |
| Webhook signature | HMAC of payload; receiver verifies before processing. |
| Multi-tenancy | Shared infra, isolated data; tenant_id on every row + RLS. |
| Row-level security | Postgres policy filters rows by `tenant_id` automatically. |
| Object storage prefix | S3/GCS hot prefix limit ~3,500 PUT/s; salt prefix if needed. |
| Presigned POST | Browser uploads directly to object storage; API never touches bytes. |
| Back-of-envelope | Round aggressively; 100k seconds/day; state conclusion out loud. |
| Little's Law | L = λW — concurrency equals throughput times latency. |
| Zipf distribution | Traffic concentrates on few items; size cache for hot set. |

**Flashcard count: 120 rows.**

---

## 16.9 12-week study plan

Mapped to actual files in `System_Design_Prep/`. Each week: read modules,
say scripts aloud, one small build, one case study drill.

| Week | Focus | Read (in order) | Build / drill |
|------|-------|-----------------|---------------|
| **1** | Framework + requirements | [00](./00_Interview_Playbook.md), [01](./01_Requirements_And_NFRs.md) §1.1–1.6 | Write requirements for 3 prompts on paper (5 min each) |
| **2** | Networking + APIs | [02](./02_Networking.md), [03](./03_APIs.md) | Implement idempotent `POST` with Redis dedup |
| **3** | Scaling + databases | [04](./04_Scaling_And_LoadBalancing.md), [05](./05_Databases_Relational.md) | Explain a slow query plan; add a covering index |
| **4** | Distribution + caching | [06](./06_Data_Distribution.md), [07](./07_Caching_And_CDN.md) | Redis cache-aside + jittered TTL on one endpoint |
| **5** | Messaging + reliability | [08](./08_Messaging_And_Events.md), [09](./09_Reliability_Patterns.md) | Kafka/Pub/Sub consumer with DLQ after 3 retries |
| **6** | Security + observability | [10](./10_Security.md), [11](./11_Observability_And_SRE.md) | Add structured logs + one SLO dashboard |
| **7** | Architecture + performance | [12](./12_Architecture_Styles.md), [13](./13_Concurrency_And_Performance.md) | Size a connection pool; find one N+1 and fix it |
| **8** | AI / LLM systems | [14](./14_AI_LLM_System_Design.md) | Minimal RAG: chunk, embed, retrieve top-5, answer |
| **9** | Case studies 1–3 | [15](./15_Case_Studies.md) §15.1–15.3 | Drill URL shortener + rate limiter on paper (45 min each) |
| **10** | Case studies 4–7 | [15](./15_Case_Studies.md) §15.4–15.7 | Drill webhooks + chat + feed + payments |
| **11** | Case studies 8–10 | [15](./15_Case_Studies.md) §15.8–15.10 | Drill job scheduler + file pipeline + RAG platform |
| **12** | Review + weak spots | [16](./16_Cheatsheet_And_Drills.md) full pass | 2 mock interviews (record yourself); redo weakest case study |

**Weekly rhythm (≈6–8 hours):**

- **Mon–Wed:** Read assigned modules; say every "Say this" block aloud once.
- **Thu:** Build exercise (even 50 lines counts).
- **Sat:** One 45-minute case study on blank paper; diff against Module 15.
- **Sun:** Flashcards §16.8 + self-tests at end of modules read that week.

**If you have only 4 weeks:** Weeks 1, 5, 9, 12 — framework, messaging/reliability,
case studies, review.

---

## 16.10 Week-before and day-of checklist

### Week before

- [ ] Reread [Module 00](./00_Interview_Playbook.md) and §16.1 framework (30 min)
- [ ] Run through §16.8 flashcards once — mark any you miss
- [ ] Drill 2 case studies on paper (45 min each, no notes)
- [ ] Memorize §16.2: nines table, 100k sec/day, Redis/Postgres ceilings
- [ ] Prepare 3 questions for interviewer (§16.11)
- [ ] Sleep 7+ hours/night — fatigue kills narration

### Night before

- [ ] Skim §16.5 phrases and §16.6 red flags (15 min max — no cramming new topics)
- [ ] One case study outline from memory (requirements + estimate + one diagram)
- [ ] Lay out pen, paper, water; test video/audio if remote
- [ ] Stop studying 2 hours before sleep

### Day of (30 min before)

- [ ] Bathroom, water, quiet room
- [ ] Read §16.1 framework once — not modules
- [ ] Say opening script aloud: time budget + "Does that work?"
- [ ] Remind yourself: narrate, numbers early, name trade-offs, close with three sentences
- [ ] Deep breath — they want you to succeed; collaboration beats performance

### During interview

- [ ] Write requirements on board before boxes
- [ ] Propose numbers; get interviewer buy-in
- [ ] Announce transitions: "Now I'll estimate scale…"
- [ ] Ask which deep dive they prefer at minute 20
- [ ] Close with: start simple, defend one decision, watch one metric

---

## 16.11 Questions to ask the interviewer

Pick 2–3. Good questions reveal seniority without sounding rehearsed.

**About the role and team**

1. "What does the on-call rotation look like for this team — pager load or follow-the-sun?"
2. "Is this team mostly greenfield or evolving an existing system? I'd like to know how much design-from-scratch vs migration work to expect."
3. "How do you balance feature velocity against reliability — is there an error budget culture?"

**About their stack (shows curiosity, not interrogation)**

4. "What's the primary data store for transactional workloads — and what pushed that choice?"
5. "How do services communicate internally — REST, gRPC, or event-driven?"
6. "Where are you on the monolith-to-microservices spectrum today?"

**About growth**

7. "What would success look like for someone in this role in the first six months?"
8. "What's the hardest unresolved systems problem the team is working on right now?"

**Avoid:** questions answerable from the job posting; "What does your company do?";
anything about compensation in a pure system design round unless they invite it.

---

## Module 16 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Recite the 45-minute time budget from memory.
2. How much downtime per year is 99.99%?
3. DAU 10M, 10 actions/user/day — what is average QPS? Peak at 3×?
4. When do you fan-out on write vs read?
5. Name three differences between a rate limit and a monthly quota.
6. What is the transactional outbox pattern in one sentence?
7. Fail open vs fail closed — when is each correct?
8. What is the celebrity problem and the standard fix?
9. Say the closing trade-off template ("I'd start with… defend… watch…").
10. Name five flashcard concepts you missed on first pass.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Seconds per day (estimate shortcut) | ~100,000 |
| 99.9% downtime/year | ~8.76 hours |
| 99.99% downtime/year | ~52.6 minutes |
| Redis GET same VPC p99 | ~0.3–1 ms |
| Postgres PK lookup | ~1–5 ms |
| Cross-region RTT | ~80–150 ms |
| Single Postgres write ceiling (planning) | ~5k–15k/s |
| Redis shard ops ceiling | ~100k–200k/s |
| S3 prefix PUT ceiling | ~3,500/s |
| Flashcard rows in §16.8 | 120 |
| Senior phrases in §16.5 | 28 |
| Red flags in §16.6 | 20 |

---

**Back to:** [System Design Interview Prep — README](./README.md)
