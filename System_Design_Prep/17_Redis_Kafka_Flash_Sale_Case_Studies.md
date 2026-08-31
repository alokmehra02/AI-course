# Module 17 — Redis, Kafka & Flash-Sale Case Studies

> **What this module makes you able to do:** answer the four interview questions that
> show up constantly in Indian product-company rounds — "design with Redis," "design with
> Kafka," "BookMyShow seat booking," and "Flipkart flash sale on one SKU" — with the same
> rigour as Module 15: numbers first, then architecture, then the hot-path mechanics.
>
> **Interview weight:** ★★★★★ for backend roles at Flipkart, Amazon, BookMyShow, Swiggy,
> Paytm, and any e-commerce / ticketing company.
>
> **Prerequisites:** [Module 07 — Caching & Redis](./07_Caching_And_CDN.md),
> [Module 08 — Kafka & Events](./08_Messaging_And_Events.md),
> [Module 09 — Idempotency & Sagas](./09_Reliability_Patterns.md)

---

## Contents

| # | Case study | Weight | What it really tests |
|---|-----------|--------|----------------------|
| 17.1 | [Design a production Redis layer](#171-design-a-production-redis-layer) | ★★★★★ | Data structures, atomicity, cluster, hot keys, failure modes |
| 17.2 | [Design a Kafka event pipeline](#172-design-a-kafka-event-pipeline) | ★★★★★ | Partitions, consumer groups, outbox, ordering, lag |
| 17.3 | [BookMyShow — 10,000 users, one seat](#173-bookmyshow--10000-users-racing-for-the-same-seat) | ★★★★★ | Virtual queue, Redis SET NX, saga, DB fence |
| 17.4 | [Flipkart — 1M users, one product](#174-flipkart--1-million-users-ordering-the-same-product) | ★★★★★ | Inventory reservation, oversell prevention, backpressure |
| — | [How these connect](#how-these-connect) | — | When to use Redis vs Kafka in the same system |

---

## 17.1 Design a production Redis layer

**Asked at:** almost every backend interview where the JD mentions caching, sessions,
rate limiting, or real-time features  **Time budget:** 45 min (or 15 min as a component
deep dive inside a larger design)

**Tests you on:** picking the right Redis data structure, atomic operations, cluster vs
single node, hot-key mitigation, and what happens when Redis dies.

### Say this in the interview (opening 60 seconds)

> "Before I draw boxes, I want to separate what Redis is *for* in this system. Redis is
> not a database — it is an in-memory data structure server with optional durability. I
> use it for ephemeral hot state where sub-millisecond reads and atomic writes matter:
> session tokens, rate-limit counters, distributed locks with TTL, leaderboards, pub/sub
> fan-out, and cache-aside for read-heavy entities. The durable source of truth stays in
> Postgres; Redis is a performance and correctness accelerator on the hot path. Every key
> gets a namespace, a TTL where appropriate, and an explicit answer to 'what happens on
> cache miss and what happens on Redis failover.'"

### 1. Requirements (5 min)

Functional (typical shared Redis layer):

1. Session store — lookup user by session token, logout invalidates.
2. Distributed rate limiting — per user, per IP, per API key.
3. Cache-aside for hot entities (product, user profile).
4. Short-lived distributed locks (job claiming, seat holds).
5. Real-time pub/sub — push seat-map updates to connected clients.
6. Leaderboard / sorted rankings (optional).

Non-functional:

- 100,000 reads/sec, 20,000 writes/sec across all use cases combined.
- p99 GET latency < 1 ms in-VPC; p99 SET < 2 ms.
- 99.99% availability for the rate-limiter path (fail-open vs fail-closed per route).
- No cross-tenant data leakage — keys prefixed by `tenant_id`.
- Survive single-node loss without permanent data loss for sessions (replication).

Out of scope: Redis as primary database, full-text search (use Elasticsearch), vector
search (use pgvector / dedicated vector DB).

### 2. Estimation (5 min)

```
Reads   100,000/s peak
Writes   20,000/s peak

Memory (rough):
  Sessions:  5M active × 500 B        = 2.5 GB
  Rate keys: 1M users × 200 B          = 200 MB
  Cache:     hot set 2M keys × 2 KB    = 4 GB
  Locks:     50k concurrent × 100 B    = 5 MB
  Total working set                    ≈ 7 GB → provision 16 GB cluster (headroom + replicas)
```

Redis single thread handles ~100k–200k simple ops/sec per primary on modern hardware —
one primary may suffice for 120k ops/sec if commands are O(1). Above that: Redis Cluster
with hash slots, or split workloads (cache cluster vs locks cluster).

### 3. API (as internal service abstractions)

```http
GET    /internal/session/{token}           → user context
DELETE /internal/session/{token}           → logout

POST   /internal/ratelimit/check
       { "key": "user:123", "limit": 100, "window_sec": 60 }
       → { "allowed": true, "remaining": 87, "reset_at": "..." }

POST   /internal/cache/get|set|del         → cache-aside helpers

POST   /internal/lock/acquire
       { "key": "job:456", "owner": "uuid", "ttl_ms": 30000 }
       → { "acquired": true }

PUBLISH redis channel seat:{show_id}       → WebSocket gateways subscribe
```

### 4. Data model — Redis key design

| Use case | Key pattern | Type | TTL | Atomic op |
|----------|-------------|------|-----|-----------|
| Session | `sess:{token}` | HASH | 24 h | GETALL / DEL |
| Rate limit | `rl:{scope}:{id}:{window}` | STRING counter | window + 1 min | INCR + EXPIRE (Lua) |
| Cache | `cache:v3:{entity}:{id}` | STRING (JSON) | 5–60 min | GET / SET |
| Lock | `lock:{resource}` | STRING | 10 min | SET NX PX + Lua release |
| Leaderboard | `lb:{game_id}` | ZSET | none | ZADD / ZRANGE |
| Pub/sub | `seat:{show_id}` | channel | — | PUBLISH |

**Version prefix `cache:v3:`** — mass invalidation by bumping version, not scanning keys.

### 5. High-level architecture

```
                    ┌─────────────────────────────────────┐
                    │         Application tier            │
                    │  (FastAPI / Node — stateless)       │
                    └───────┬─────────────┬───────────────┘
                            │             │
              cache-aside   │             │  rate limit / locks
                            ▼             ▼
              ┌─────────────────────────────────────────┐
              │     Redis Cluster (3 primaries +        │
              │     replicas, hash-slot sharding)       │
              │  ┌─────────┐ ┌─────────┐ ┌─────────┐   │
              │  │Primary 1│ │Primary 2│ │Primary 3│   │
              │  │+ replica│ │+ replica│ │+ replica│   │
              │  └─────────┘ └─────────┘ └─────────┘   │
              └─────────────────────────────────────────┘
                            │
                   async persist (AOF everysec)
                            │
              ┌─────────────▼─────────────┐
              │   PostgreSQL (source of     │
              │   truth on cache miss)      │
              └───────────────────────────┘
```

**Read path (cache-aside):** GET `cache:v3:product:99` → hit return; miss → Postgres →
SET with TTL → return.

**Write path:** UPDATE Postgres → DELETE cache key (delete, don't update in place).

### 6. Deep dives

#### 6.1 Rate limiting — token bucket in Lua (atomic)

```lua
-- KEYS[1] = bucket key, ARGV[1]=rate, ARGV[2]=burst, ARGV[3]=now_ms, ARGV[4]=ttl
local tokens = tonumber(redis.call('GET', KEYS[1]) or ARGV[2])
local last = tonumber(redis.call('GET', KEYS[1]..':ts') or ARGV[3])
local rate = tonumber(ARGV[1])
local burst = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local delta = math.max(0, now - last)
tokens = math.min(burst, tokens + delta * rate / 1000)
if tokens < 1 then return {0, tokens} end
tokens = tokens - 1
redis.call('SET', KEYS[1], tokens, 'PX', tonumber(ARGV[4]))
redis.call('SET', KEYS[1]..':ts', now, 'PX', tonumber(ARGV[4]))
return {1, tokens}
```

Why Lua: `INCR` + `EXPIRE` as two commands races under load.

#### 6.2 Correct distributed lock (acquire + release)

```python
ACQUIRE = """
if redis.call('exists', KEYS[1]) == 0 then
  return redis.call('set', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2])
end
return nil
"""
RELEASE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""

async def acquire_lock(redis, key: str, owner: str, ttl_ms: int = 600_000) -> bool:
    return await redis.eval(ACQUIRE, 1, key, owner, ttl_ms) is not None
```

Never `DEL` without checking owner — you may delete another worker's lock after your
TTL expired and you ran long.

#### 6.3 Hot keys

If one product key gets 50k reads/sec, shard the cache key:

```
cache:product:FLASH99:0 .. cache:product:FLASH99:7
read from random replica key; write invalidates all 8
```

Or local in-process L1 (100 ms TTL) in front of Redis for truly hot keys.

#### 6.4 Redis failure

| Policy | When | Behaviour |
|--------|------|-----------|
| Fail-open | Rate limit on browse | Allow traffic; alert |
| Fail-closed | Login brute-force | Reject or degrade to CAPTCHA |
| Cache miss storm | Redis down | Request coalescing + circuit breaker to DB |

### 7. Failure modes

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Primary dies | Brief write unavailability | Replica promotion; Sentinel/Cluster auto-failover |
| Hot key | Single shard CPU 100% | Key splitting, local cache |
| Big KEY | `KEYS *` in prod | Never; use `SCAN`; monitor `slowlog` |
| Cache stampede | Miss storm on expiry | Jittered TTL, single-flight |
| Lock without TTL | Deadlock forever | Always `PX`; watchdog extends only if worker alive |

### 8. Trade-offs — closing summary

> I treat Redis as a specialised hot-state tier, not a database. Sessions and rate limits
> live here because they need atomic counters and TTL; product truth lives in Postgres
> with cache-aside on top. The decision I defend hardest is namespaced keys with explicit
> TTL on every ephemeral object, because Redis without TTL is a memory leak with a
> failover story attached. What I give up is strong durability — AOF everysec can lose
> one second of writes, which is why money and inventory confirmation still fence in SQL.

### If they push further

**Q: Redis Cluster vs separate Redis instances per use case?**
A: One cluster until noisy-neighbour or blast-radius forces split — e.g. seat-lock cluster
isolated from session cluster so a flash sale cannot evict session memory.

**Q: Redlock?**
A: Mention Martin Kleppmann's critique; for seat booking use Redis SET NX as efficiency
lock + Postgres unique constraint as correctness fence (see §17.3).

---

## 17.2 Design a Kafka event pipeline

**Asked at:** any system with async workflows, audit logs, or microservice decoupling
**Time budget:** 45 min

**Tests you on:** topic design, partition keys, consumer groups, delivery semantics,
transactional outbox, and consumer lag as the metric that matters.

### Say this in the interview (opening 60 seconds)

> "Kafka is a durable, partitioned append-only log — not a queue that deletes on read.
> I use it when multiple independent consumers need the same stream, when I need replay,
> or when the API must return before slow downstream work finishes. The design decisions
> that matter are: topic boundaries, partition key — because that fixes ordering and caps
> parallelism — retention, and whether producers use the transactional outbox so I never
> have 'row committed, event lost.' Consumers are always at-least-once with idempotent
> handlers unless I'm entirely inside Kafka Streams with EOS."

### 1. Requirements (5 min)

Design an **order events pipeline** for e-commerce (Flipkart-style):

1. `OrderPlaced`, `PaymentCaptured`, `OrderShipped`, `OrderCancelled` events.
2. Consumers: inventory, warehouse, notifications, analytics, search index.
3. Replay last 7 days for a new consumer or bug fix.
4. Ordering per `order_id` — all events for one order in sequence.
5. Peak 50,000 events/sec during sale; average 5,000/sec.

Non-functional:

- Event availability 99.95%.
- End-to-end lag p99 < 30 s for notifications; < 5 min for analytics.
- No lost events after DB commit (outbox).
- 7-day retention minimum; 30 days for compliance topics.

### 2. Estimation (5 min)

```
Peak     50,000 events/s
Average   5,000 events/s
Payload  ~500 B/event average
         50k × 500 B = 25 MB/s ingress
         × 7 days retention ≈ 15 TB raw (before replication RF=3)

Partitions: target ~10–50 MB/s per partition → 25/10 ≈ 3 partitions minimum;
            for consumer parallelism use 24–48 partitions (not 1 per order)
```

**Rule:** partition count = desired max consumer parallelism in the heaviest group.

### 3. API / event schema

```json
// Topic: order-events (key = order_id)
{
  "event_id": "01HQ...",
  "type": "OrderPlaced",
  "order_id": "ord_abc",
  "user_id": "usr_123",
  "items": [{"sku": "FLASH99", "qty": 1}],
  "amount_paise": 49900,
  "occurred_at": "2026-09-01T12:00:00Z",
  "schema_version": 2
}
```

Schema registry (Avro/Protobuf) with **backward** compatibility — new consumers read old
events.

### 4. Data model

**Outbox table (Postgres)** — same transaction as order insert:

```sql
CREATE TABLE outbox (
    id           BIGSERIAL PRIMARY KEY,
    aggregate_id TEXT NOT NULL,
    event_type   TEXT NOT NULL,
    payload      JSONB NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at TIMESTAMPTZ
);
CREATE INDEX idx_outbox_unpublished ON outbox (created_at) WHERE published_at IS NULL;
```

**Kafka:** topic `order-events`, 48 partitions, `key=order_id`, `acks=all`,
`min.insync.replicas=2`, retention 30 days.

### 5. High-level architecture

```
 Client
   │
   ▼
 Order API ──► Postgres (orders + outbox) ──► 201 Created
                    │
         Outbox Relay / Debezium CDC
                    │
                    ▼
              Kafka: order-events
                │    │    │    │
                ▼    ▼    ▼    ▼
            Inventory Notify WH   Analytics
            consumer  consumer  consumer
```

**Write path:** `BEGIN` → insert order → insert outbox row → `COMMIT` → relay polls or
CDC publishes to Kafka → mark `published_at`.

**Read path:** consumers commit offset **after** idempotent side effect.

### 6. Deep dives

#### 6.1 Partition key = `order_id`

All events for one order land in one partition → strict ordering for that order.
**Never** partition by `user_id` for order events if one user places 50 orders/sec —
hot partition. **Never** 1 partition per customer at 10M customers.

#### 6.2 Consumer groups

```
48 partitions, 12 inventory consumers → each handles ~4 partitions
48 partitions, 48 notification consumers → 1:1 (max parallelism)
```

If lag grows: add consumers up to partition count, then add partitions (rekey carefully).

#### 6.3 Idempotent consumer

```python
async def handle(msg):
    event_id = msg.value["event_id"]
    if await db.fetchval("SELECT 1 FROM processed_events WHERE id=$1", event_id):
        return  # already done
    await apply_business_logic(msg.value)
    await db.execute(
        "INSERT INTO processed_events (id) VALUES ($1) ON CONFLICT DO NOTHING",
        event_id,
    )
    await consumer.commit()
```

#### 6.4 DLQ and retries

```
order-events → consumer fails → retry-topic-30s → retry-topic-5m → DLQ
DLQ stores: original payload, stack trace, attempt count, first_seen_at
Alert on DLQ depth > 100
```

### 7. Failure modes

| Failure | Effect | Mitigation |
|---------|--------|------------|
| Broker loss | Partition unavailable briefly | RF=3, ISR, `acks=all` |
| Consumer slow | Lag grows | Scale consumers; backpressure at producer |
| Rebalance storm | Duplicate processing | Static membership, cooperative sticky assignor |
| Outbox relay stuck | Events not published | Alert unpublished rows > 1 min old |
| Poison message | Infinite retry | Max attempts → DLQ |

### 8. Trade-offs — closing summary

> Kafka buys durable fan-out and replay at the cost of operational surface and eventual
> consistency. I pair it with the transactional outbox so the API never lies about a
> committed order without a corresponding event. Partition by `order_id`, size partitions
> for consumer parallelism not cardinality, and treat consumer lag as the primary health
> signal — not CPU on the broker.

### If they push further

**Q: Kafka vs RabbitMQ for this?**
A: Multiple independent consumers need replay → Kafka. Single work queue with routing →
RabbitMQ. Order audit + analytics + search → Kafka.

**Q: Exactly-once?**
A: EOS inside Kafka Streams; for Postgres writes use outbox + idempotent consumer.

---

## 17.3 BookMyShow — 10,000 users racing for the same seat

**Asked at:** BookMyShow, Paytm Insider, Ticketmaster-style companies; classic concurrency
round  **Time budget:** 45 min

**Tests you on:** virtual waiting room, Redis atomic seat hold, hold ≠ booked, payment
saga, and DB unique constraint as the final fence.

### Say this in the interview (opening 60 seconds)

> "The hard part is not listing shows — it is making sure that when ten thousand people
> click seat A4 in the same second, exactly one of them gets a temporary hold and zero
> end up with a confirmed ticket for the same seat. I solve that with three layers: a
> virtual waiting room that converts a thundering herd into a bounded admission rate, an
> atomic seat hold in Redis with a TTL, and a payment saga where the database unique
> constraint on `(show_id, seat_id)` for confirmed bookings is the correctness backstop
> Redis alone cannot guarantee after failover."

### 1. Requirements (5 min)

Functional:

1. Browse shows, seat map (available / held / sold).
2. Select one or more seats → temporary hold (~10 min).
3. Pay within hold window → booking confirmed.
4. Hold expires → seat returns to available; optional waitlist.
5. Real-time seat map updates for users viewing the same show.

Non-functional — **the flash scenario:**

- One show, **one premium seat** (or row), **10,000 concurrent users** click within 1 s.
- Exactly **one** active hold at a time per seat; **zero** double bookings ever.
- Seat map read p99 < 200 ms; hold attempt p99 < 100 ms for admitted users.
- Payment p99 5–15 s; hold TTL 10 min (covers 3DS + hesitation).
- 99.95% availability on browse; booking path may queue users.

Out of scope: resale marketplace, dynamic pricing ML, venue seat geometry editor.

### 2. Estimation (5 min)

```
Flash moment:  10,000 users / 1 seat / 1 second
               = 10,000 hold attempts/s on ONE key (catastrophic hot key)

Without queue: 10,000 RPS → 1 Redis key + 1 DB row → meltdown

With virtual waiting room admitting 500 users/s:
               500 hold attempts/s (manageable)
               9,500 users wait 20 s average in queue (acceptable UX for flash sale)

Redis ops per admitted user:
  1 SET NX (hold) + 1 GET (seat map cache) ≈ 2 ops
  500 × 2 = 1,000 ops/s (trivial for Redis)

Postgres writes: only on confirm (~1/s for this seat) + async hold audit batch
```

### 3. API

```http
GET  /shows/{id}/seats                    → seat map (cached)
POST /shows/{id}/queue/join               → { queue_token, position, eta_sec }
GET  /shows/{id}/queue/status             → poll until admitted

POST /shows/{id}/holds
Authorization: Bearer {queue_admission_token}
{ "seat_ids": ["A4"] }
→ 201 { "hold_id": "...", "expires_at": "...", "seats": ["A4"] }
→ 409 { "code": "SEAT_UNAVAILABLE" }

POST /holds/{hold_id}/pay                 → payment session
POST /webhooks/payment                    → provider callback (idempotent)
```

### 4. Data model

**Redis (ephemeral truth for holds):**

```
seat:hold:{show_id}:{seat_id}  →  {owner_token}   TTL 600s   SET NX PX
seat:map:{show_id}             →  HASH seat_id → status (A/H/S)  refreshed from events
waitlist:{show_id}:{seat_id}   →  ZSET score=timestamp member=user_id
```

**Postgres (durable truth):**

```sql
CREATE TABLE bookings (
    id         BIGSERIAL PRIMARY KEY,
    show_id    BIGINT NOT NULL,
    seat_id    VARCHAR(8) NOT NULL,
    user_id    BIGINT NOT NULL,
    status     TEXT NOT NULL,  -- HELD, CONFIRMED, CANCELLED
    hold_token UUID NOT NULL,
    version    INT NOT NULL DEFAULT 1,
    UNIQUE (show_id, seat_id) WHERE status = 'CONFIRMED'  -- partial unique index
);
```

The **partial unique index** is the fence: even if Redis double-holds after failover, only
one CONFIRMED row can exist per seat.

### 5. High-level architecture

```
 10,000 users
      │
      ▼
┌─────────────┐     admit 500/s      ┌──────────────┐
│ Virtual     │ ───────────────────► │ Booking API  │
│ Waiting Room│     queue_token      │ (stateless)  │
│ (Redis ZSET)│                      └──────┬───────┘
└─────────────┘                             │
                                            │ SET NX seat:hold:...
                                            ▼
                                     ┌──────────────┐
                                     │ Redis Cluster │
                                     │ (seat locks)  │
                                     └──────┬───────┘
                                            │ seat.held event
                                            ▼
                                     ┌──────────────┐
                                     │ Kafka        │
                                     └──────┬───────┘
                    ┌───────────────────────┼───────────────────────┐
                    ▼                       ▼                       ▼
              Seat map cache          Saga / Temporal          Analytics
              (Redis pub/sub → WS)    payment workflow
                                            │
                                            ▼
                                     ┌──────────────┐
                                     │ Postgres     │
                                     │ bookings     │
                                     └──────────────┘
```

### 6. Deep dives — the 10,000-users-one-seat scenario

#### Step-by-step (say this out loud)

```
T+0ms    10,000 clicks arrive; CDN serves static seat map from cache
T+1ms    Only users with queue_admission_token reach hold API (500 admitted)
T+2ms    User U1: SET seat:hold:show1:A4 token_u1 NX PX 600000 → OK
         User U2..U500: same command → NIL (failed)
T+3ms    499 users get 409 SEAT_UNAVAILABLE instantly; UI grey seat
T+5ms    Kafka publishes seat.held; WebSocket pushes update to all viewers
T+30s    U1 completes payment
T+31s    Saga: INSERT booking CONFIRMED with unique (show_id, seat_id)
         DEL seat:hold key; publish seat.sold
T+10min  If U1 abandoned: TTL expires → seat available OR waitlist ZPOPMIN → next user
```

#### Hold acquisition — Lua (atomic)

```lua
-- KEYS[1]=hold key, ARGV[1]=owner_token, ARGV[2]=ttl_ms
if redis.call('exists', KEYS[1]) == 0 then
  redis.call('set', KEYS[1], ARGV[1], 'NX', 'PX', ARGV[2])
  return 1
end
return 0
```

#### Payment saga (choreography or Temporal)

```
1. Hold acquired (Redis)
2. Create booking row status=HELD in Postgres
3. Charge payment (idempotency key = hold_id)
4a. Success → UPDATE status=CONFIRMED (unique index enforces) → delete hold → notify
4b. Failure → UPDATE status=CANCELLED → delete hold → release seat
```

**Never** call payment gateway inside the Redis lock — hold TTL would expire during 3DS.

#### Virtual waiting room

```python
# Admit users fairly: ZADD queue:{show_id} timestamp user_id
# Worker admits oldest N per second with ADMIT token in Redis
# Token required on POST /holds — without it, 429
```

Reference pattern: high-demand onsales (e.g. major concert sales) use admission control
because unbounded traffic to inventory collapses queue ordering and downstream services.

### 7. Failure modes

| Failure | Risk | Mitigation |
|---------|------|------------|
| Redis primary failover | Brief double-hold window | DB unique constraint on CONFIRMED |
| Payment webhook retry | Double charge | Idempotency-Key on payment |
| Hold TTL too short | User loses seat mid-3DS | TTL = p99 payment × 3 |
| No waiting room | 10k RPS on one key | Queue is mandatory for this scenario |
| WebSocket fan-out | 100k connections | Redis pub/sub per show; horizontal WS gateways |

### 8. Trade-offs — closing summary

> I would not use `SELECT FOR UPDATE` on the seat row for ten thousand concurrent
> requests — that creates a convoy in Postgres. Redis SET NX is the right hot-path lock;
> Postgres is the correctness fence on confirm. The virtual waiting room is not optional
> for this scenario — it is how you turn ten thousand simultaneous clicks into five
> hundred per second the system can reason about. What I give up is instant gratification
> for users nine thousand five hundred deep in queue, which is better than an error page.

### If they push further

**Q: User holds 4 seats — all-or-nothing?**
A: Lua script reserves all four keys atomically; if any fails, rollback the holds set in
the same script.

**Q: Waitlist fairness?**
A: ZSET by timestamp; on TTL expiry, `ZPOPMIN` grants next hold — avoids thundering herd
on re-release.

**Q: Show-level sharding?**
A: Shard inventory by `show_id` so one mega-event does not contend with unrelated shows.

---

## 17.4 Flipkart — 1 million users ordering the same product

**Asked at:** Flipkart, Amazon India, Meesho flash sales  **Time budget:** 45 min

**Tests you on:** inventory reservation vs oversell, token/counter patterns, queue +
admission, async order acceptance, and idempotency at payment.

### Say this in the interview (opening 60 seconds)

> "One million users and one SKU is not a database problem — it is an admission and
> inventory accounting problem. I cannot run a million transactions against one row. I
> front-load with a virtual queue, pre-load stock into a Redis counter, decrement
> atomically on reservation, and accept orders asynchronously with a 202 response. The
> invariant is: confirmed orders never exceed available stock, even with retries and
> duplicate clicks. Postgres holds the authoritative ledger; Redis holds the hot counter
> during the sale window; Kafka carries order events to fulfillment."

### 1. Requirements (5 min)

Functional:

1. Product page for flash SKU `FLASH99` — price, countdown, stock indicator.
2. "Buy now" → user enters queue → on admission, attempt reservation.
3. If reserved, checkout and pay within 10 min.
4. If stock zero, user sees "sold out" — no false positives.
5. Order history and status tracking.

Non-functional — **the flash scenario:**

- **1,000,000 users** hit "Buy" within 60 s for **one SKU** with **10,000 units** stock.
- Max **10,000** successful reservations; **zero oversell** (legal and trust requirement).
- Admitted users see reservation result in < 500 ms p99.
- System stays up for browse traffic (may degrade purchase path).
- Orders may be **accepted async** — "we're processing your order" is OK for 30 s.

Out of scope: cart with 50 SKUs, recommendation feed, seller portal.

### 2. Estimation (5 min)

```
Traffic:   1,000,000 users / 60 s ≈ 17,000 requests/s (if all click once)
           Realistic with retries: 50,000 RPS at edge

Stock:     10,000 units — only 10,000 winners matter

Strategy:  Do NOT run 1M DB transactions on inventory row

Redis:     1 key inventory:FLASH99 = 10000
           DECR is O(1); Redis handles ~100k+ ops/s per node
           50k DECR attempts/s → ~40k get -1 (sold out) — fine

Admission: Allow 20,000 reservation attempts/s max
           1M users / 20k/s = 50 s to drain queue (acceptable for flash sale)

Postgres:  10,000 order INSERTs over ~2 min = 83/s (trivial)
           Async via Kafka buffer
```

### 3. API

```http
GET  /products/FLASH99                    → cached product page
POST /flash/FLASH99/queue                 → { queue_token, position }
GET  /flash/FLASH99/queue/status

POST /flash/FLASH99/reserve
Authorization: Bearer {queue_token}
Idempotency-Key: {client_uuid}
→ 202 { "reservation_id": "...", "status": "PROCESSING" }
→ 200 { "reservation_id": "...", "status": "RESERVED", "expires_at": "..." }
→ 409 { "status": "SOLD_OUT" }

GET  /reservations/{id}                   → poll status
POST /reservations/{id}/checkout          → payment
```

**202 Accepted** is key — the API does not block on Postgres during the spike.

### 4. Data model

**Redis:**

```
inventory:FLASH99              STRING "10000"     # preload before sale
reservation:{user_id}:FLASH99  STRING res_id      NX EX 600   # one res per user
reservation:{res_id}           HASH status, sku, user_id, ttl
```

**Atomic reserve — Lua:**

```lua
-- Decrement only if stock > 0 and user has no existing reservation
local stock = tonumber(redis.call('GET', KEYS[1]))
if stock <= 0 then return {0, 'SOLD_OUT'} end
if redis.call('exists', KEYS[2]) == 1 then return {2, 'ALREADY_RESERVED'} end
redis.call('DECR', KEYS[1])
redis.call('set', KEYS[2], ARGV[1], 'NX', 'EX', ARGV[2])
return {1, 'OK'}
```

**Postgres:**

```sql
CREATE TABLE inventory_ledger (
    sku        TEXT PRIMARY KEY,
    on_hand    INT NOT NULL CHECK (on_hand >= 0)
);

CREATE TABLE reservations (
    id         UUID PRIMARY KEY,
    sku        TEXT NOT NULL,
    user_id    BIGINT NOT NULL,
    status     TEXT NOT NULL,  -- RESERVED, CONFIRMED, EXPIRED
    UNIQUE (user_id, sku)     -- one active reservation per user per SKU
);

CREATE TABLE orders (
    id         UUID PRIMARY KEY,
    reservation_id UUID UNIQUE,
    idempotency_key TEXT UNIQUE
);
```

Reconcile job: `SUM(confirmed) <= inventory_ledger.on_hand` — alert on mismatch.

### 5. High-level architecture

```
 1M users
    │
    ▼
┌────────┐   static/assets    ┌─────────────┐
│  CDN   │ ◄────────────────  │ Product page│
└────────┘                    └─────────────┘
    │
    ▼
┌──────────────┐  admit 20k/s  ┌───────────────┐
│ Edge queue   │ ────────────► │ Reserve API   │
│ (token bucket│               │ (stateless)   │
│  + Redis)    │               └───────┬───────┘
└──────────────┘                       │
                                       │ Lua DECR + user lock
                                       ▼
                               ┌───────────────┐
                               │ Redis         │
                               │ inventory cnt │
                               └───────┬───────┘
                                       │ ReservationCreated
                                       ▼
                               ┌───────────────┐
                               │ Kafka         │
                               └───────┬───────┘
                                       ▼
                               ┌───────────────┐
                               │ Order workers │──► Postgres
                               └───────────────┘
```

### 6. Deep dives — 1M users, 10k stock

#### Why not row-lock in Postgres?

```sql
-- DISASTER at 1M concurrency:
BEGIN;
SELECT on_hand FROM inventory WHERE sku='FLASH99' FOR UPDATE;
-- 999,999 transactions queued on one row
```

#### Pre-load counter before sale

```bash
# T-5 minutes before sale
SET inventory:FLASH99 10000
```

During sale: only Redis DECR. Postgres updated asynchronously by workers consuming
`ReservationCreated` events.

#### Oversell prevention (belt and suspenders)

1. Redis Lua: decrement only if `stock > 0`
2. Worker INSERT with check: `UPDATE inventory_ledger SET on_hand = on_hand - 1 WHERE sku=$1 AND on_hand > 0`
3. Nightly reconciliation; kill switch if counts diverge

#### Idempotency

User double-clicks "Buy" → same `Idempotency-Key` → same reservation returned, not two
DECRs.

#### Sold-out path must be fast

When `inventory:FLASH99` hits 0, remaining 990k users should get instant 409 from Redis
— no DB touch. Optional: CDN edge flag `sold_out=true` after stock zero to shield origin.

#### Load shedding

| Tier | Traffic | Action |
|------|---------|--------|
| Browse | Everyone | CDN + cache |
| Queue join | 1M | Rate limit + captcha |
| Reserve | Admitted only | Redis Lua |
| Checkout | 10k reserved | Normal path |

### 7. Failure modes

| Failure | Risk | Mitigation |
|---------|------|------------|
| Redis lost counter | Oversell or undersell | Reconcile from Postgres; preload from ledger |
| Kafka lag | Slow order confirmation | Scale consumers; show "processing" UI |
| Worker crash after DECR | Lost reservation | Reconciliation: Redis res_id vs Postgres |
| Counter drift | Redis 100, sold 150 | Rebuild counter from ledger; halt sale |
| Bot traffic | Bots eat stock | Device fingerprint, queue captcha, per-user limit |

### 8. Trade-offs — closing summary

> For one million users on one SKU I refuse to serialize through a single database row.
> I preload ten thousand into Redis, admit a bounded RPS through a queue, and decrement
> atomically — that is how you sell ten thousand units in sixty seconds without lying to
> anyone about availability. Async order creation via Kafka trades instant confirmation
> for survival, which is the correct trade for a flash sale. The number I would monitor is
> the gap between Redis remaining stock and confirmed orders in Postgres — it should
> always be zero.

### If they push further

**Q: 10k stock but 50k in cart?**
A: Reservation model, not cart — DECR on reserve, not on add-to-cart. Carts cause false
scarcity and inventory lock-up.

**Q: Multi-city inventory?**
A: `inventory:FLASH99:BLR`, `inventory:FLASH99:DEL` — separate counters; route user to
nearest FC.

**Q: How did Flipkart Big Billion Day handle this publicly?**
A: Discuss pattern-level: queue, cache product pages, async order pipeline, pre-warm
caches — cite as industry pattern without inventing internal numbers.

---

## How these connect

Real flash-sale systems use **both** Redis and Kafka:

```
                    ┌─────────────────────────────────────┐
                    │  BookMyShow / Flipkart flash path   │
                    └─────────────────────────────────────┘

  Users ──► Queue (Redis ZSET / token) ──► Admission control
                    │
                    ▼
            Hot path locks / counters (Redis SET NX, DECR, Lua)
                    │
                    ▼
            Events (Kafka): seat.held, ReservationCreated, OrderPlaced
                    │
        ┌───────────┼───────────┐
        ▼           ▼           ▼
    Postgres    Notifications   Analytics
    (fence)     (email/SMS)     (dashboards)
```

| Question | Redis answers | Kafka answers |
|----------|---------------|---------------|
| Who holds seat A4 right now? | SET NX + TTL | — |
| How many FLASH99 left? | DECR counter | — |
| Notify warehouse of order | — | order-events topic |
| Replay analytics after bug | — | retained log |
| Prevent double booking | atomic hold + **SQL unique** | idempotent consumers |

**Study order:** read [Module 07](./07_Caching_And_CDN.md) and [Module 08](./08_Messaging_And_Events.md),
then drill §17.3 and §17.4 on paper. Build §17.1 rate limiter + §17.2 outbox consumer in
one weekend.

---

## Module 17 — self-test

1. Why is Redis not your source of truth for confirmed bookings?
2. Write the SET NX command for a 10-minute seat hold.
3. Why do you need a virtual waiting room before 10k users hit one seat?
4. Partition Kafka order events by what key, and why not by user?
5. How do you prevent oversell with 1M users and 10k stock?
6. Why return 202 on reserve during a flash sale?
7. What is the difference between a hold and a confirmed booking?
8. When does Redis fail-open vs fail-closed for rate limiting?
9. Name the three oversell prevention layers in §17.4.
10. What metric tells you Kafka consumers are falling behind?

---

## Key numbers from this module

| Scenario | Number to remember |
|----------|-------------------|
| Redis single-node throughput | ~100k–200k simple ops/s |
| Seat hold TTL | ~10 min (covers 3DS + hesitation) |
| BookMyShow flash | 10k users → 1 seat → queue mandatory |
| Flipkart flash | 1M users, 10k stock → Redis DECR not DB row lock |
| Kafka partitions | = max consumer parallelism per group |
| Hold vs confirm | Redis hold; Postgres UNIQUE on confirm |

---

**Back to:** [Module 15 — Worked Case Studies](./15_Case_Studies.md) ·
[Module 16 — Cheat Sheet](./16_Cheatsheet_And_Drills.md) ·
[README](./README.md)
