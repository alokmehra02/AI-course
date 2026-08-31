# System Design Interview Prep

Complete study material for system design interviews, built for a backend + AI engineer
with ~2 years of experience working in **Node.js, Python/FastAPI, GCP, and LLM/RAG
applications**.

Every topic in this guide follows the same shape:

- **Say this in the interview** — a spoken script you can read aloud, in full sentences
- **Mental model** — why the thing exists, with an ASCII diagram of the data flow
- **Enterprise production example** — a real company, a real system, real numbers
- **Code** — runnable Python/FastAPI or Node.js, production-shaped
- **Trade-offs** — what the choice costs you
- **Follow-ups they will ask** — the hard questions, with answers
- **Red flags** — the naive answer, and what to say instead

---

## Start here

| If you have… | Read |
|---|---|
| **30 minutes before an interview** | [Module 00 — Playbook](./00_Interview_Playbook.md) + [Module 16 §16.1, §16.5](./16_Cheatsheet_And_Drills.md) |
| **One evening** | Module 00, then Module 16 flashcards, then one case study from Module 15 |
| **One week** | Modules 00, 01, 05, 06, 07, 08, 09 — these carry ~80% of interview questions |
| **12 weeks (proper prep)** | The full plan in [Module 16 §16.9](./16_Cheatsheet_And_Drills.md) |
| **An AI/LLM-focused role** | Module 00 → 14 → 15 case study 10. This is your differentiator. |
| **Flipkart / BookMyShow / flash-sale rounds** | Module 07 → 08 → **17** (§17.3 and §17.4). |

---

## Modules

| # | Module | Covers | Weight |
|---|--------|--------|:---:|
| 00 | [Interview Playbook](./00_Interview_Playbook.md) | The 6-step framework, time budgets, whiteboard layout, what's actually scored, recovery moves | ★★★★★ |
| 01 | [Requirements, NFRs & Estimation](./01_Requirements_And_NFRs.md) | Functional vs non-functional, availability nines, reliability, latency vs throughput, Little's Law, cost, back-of-the-envelope math | ★★★★★ |
| 02 | [Networking](./02_Networking.md) | DNS, TCP/UDP, TLS, HTTP/1.1–3, WebSockets, polling vs long polling vs SSE | ★★★★☆ |
| 03 | [API Design](./03_APIs.md) | REST, pagination, versioning, idempotency keys, errors, GraphQL, gRPC, webhooks, API Gateway | ★★★★★ |
| 04 | [Scaling & Load Balancing](./04_Scaling_And_LoadBalancing.md) | Vertical vs horizontal, stateless services, LB algorithms, health checks, consistent hashing, autoscaling, SPOF | ★★★★★ |
| 05 | [Databases: SQL, ACID & Indexes](./05_Databases_Relational.md) | Choosing a database, ACID, transactions, isolation levels, locking, indexes, query plans, connection pools, zero-downtime migrations | ★★★★★ |
| 06 | [Replication, Sharding & Consistency](./06_Data_Distribution.md) | Replication, read replicas, partitioning, shard keys, resharding, consistency models, CAP & PACELC, quorums, 2PC vs saga, multi-region | ★★★★★ |
| 07 | [Caching, CDN & Object Storage](./07_Caching_And_CDN.md) | Cache patterns, invalidation, eviction, stampede, hot keys, Redis in production, CDN, S3/GCS and signed URLs | ★★★★★ |
| 08 | [Messaging, Kafka & Events](./08_Messaging_And_Events.md) | Queue vs pub/sub vs log, Kafka internals, consumer groups, ordering, delivery semantics, DLQs, transactional outbox, EDA, CQRS | ★★★★★ |
| 09 | [Reliability Patterns](./09_Reliability_Patterns.md) | Timeouts, retries with jitter, **idempotency**, circuit breakers, bulkheads, backpressure, load shedding, cascading failures, distributed locks, sagas | ★★★★★ |
| 10 | [Security](./10_Security.md) | AuthN vs AuthZ, sessions vs JWT, OAuth2/OIDC, RBAC/ABAC, encryption in transit and at rest, secrets, rate limiting algorithms, OWASP | ★★★★☆ |
| 11 | [Observability & SRE](./11_Observability_And_SRE.md) | Logs, metrics, traces, golden signals, health checks, SLI/SLO/SLA, error budgets, incident response, DR, RPO/RTO, multi-region | ★★★★☆ |
| 12 | [Architecture Styles](./12_Architecture_Styles.md) | Monolith, modular monolith, microservices, strangler fig, service discovery, service mesh, deployment strategies | ★★★★☆ |
| 13 | [Concurrency, Performance & Cost](./13_Concurrency_And_Performance.md) | Node event loop, Python GIL and asyncio, race conditions, locking, pool sizing, finding bottlenecks, N+1, batching, cloud cost | ★★★★☆ |
| 14 | [AI & LLM System Design](./14_AI_LLM_System_Design.md) | Production RAG, ingestion pipelines, chunking, embeddings, vector indexes, hybrid search, reranking, LLM gateway, streaming, semantic caching, token cost, eval, guardrails, agents | ★★★★★ |
| 15 | [Worked Case Studies](./15_Case_Studies.md) | 10 complete 45-minute designs: URL shortener, rate limiter, notifications, webhooks, chat, feed, payments, job scheduler, file pipeline, multi-tenant RAG | ★★★★★ |
| 16 | [Cheat Sheet, Numbers & Study Plan](./16_Cheatsheet_And_Drills.md) | One-page framework, numbers to memorize, decision tables, senior-sounding phrases, anti-patterns, flashcards, 12-week plan | ★★★★★ |
| 17 | [Redis, Kafka & Flash-Sale Case Studies](./17_Redis_Kafka_Flash_Sale_Case_Studies.md) | Redis layer, Kafka pipeline, BookMyShow 10k/1 seat, Flipkart 1M/1 SKU | ★★★★★ |

---

## How to actually use this

Reading is not preparation. The loop that works:

1. **Read** the module. Once, properly.
2. **Say it out loud.** Every topic has a "Say this in the interview" block written to be
   spoken. Read it aloud until it sounds like you rather than like a document. This feels
   silly and it is the highest-return thing in the whole guide.
3. **Build the small version.** One Redis rate limiter. One idempotent endpoint. One Kafka
   consumer with a DLQ. You cannot fake having operated something, and you do not need
   scale to have operated it.
4. **Break it.** Kill the cache. Kill the consumer mid-batch. Send the same request twice.
   The failure modes are what interviews are about.
5. **Drill a case study on paper**, 45 minutes, no notes, then diff against
   [Module 15](./15_Case_Studies.md).

Then take the self-test at the end of each module. If you cannot answer a question out
loud in under a minute, you have read that section but you do not know it.

---

## Coverage against the original roadmap

Every concept from `system_design_roadmap_for_2_year_backend_ai_engineer.md` is covered,
plus the gaps that roadmap left. Additions beyond the original list:

- Back-of-the-envelope estimation as a trained procedure (Module 01)
- Little's Law, tail latency amplification, percentile arithmetic (Modules 01, 13)
- Cursor pagination, API versioning, webhook design, schema evolution (Module 03)
- Power-of-two-choices load balancing, deep vs shallow health checks (Module 04)
- Write skew, `SELECT FOR UPDATE SKIP LOCKED`, `EXPLAIN ANALYZE`, expand/contract
  migrations, connection-pool sizing (Module 05)
- PACELC, quorum math, shard-key selection, resharding playbook (Module 06)
- Cache stampede mitigations in full, negative caching, Redis operational limits (Module 07)
- The dual-write problem and the transactional outbox (Module 08)
- Deadline propagation, retry budgets, metastable cascading failure (Module 09)
- Envelope encryption, ReBAC, SSRF, prompt injection (Modules 10, 14)
- Error budgets and multi-burn-rate alerting (Module 11)
- Node event loop and Python GIL/asyncio failure modes (Module 13)
- The entire modern AI stack: HNSW tuning, hybrid search with RRF, reranking, LLM
  gateways, semantic cache correctness, token economics, evaluation (Module 14)

---

## Conventions

- ★ ratings are **interview weight**, not difficulty. Triage by them when short on time.
- ❌ / ✅ pairs mark the naive answer and its replacement.
- Cross-references are relative links, e.g. [Module 09 §9.4](./09_Reliability_Patterns.md).
- Code targets Python 3.11+/FastAPI and Node.js 20+, with PostgreSQL, Redis, and
  Kafka/Pub/Sub — the stack you actually work in.

`_AUTHORING_TEMPLATE.md` is the internal style spec used to write these modules. You can
ignore it, or use it if you want to add a topic in the same voice.

---

**Start:** [Module 00 — The Interview Playbook](./00_Interview_Playbook.md)
