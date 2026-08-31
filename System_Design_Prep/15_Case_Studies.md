# Module 15 — Worked Case Studies

> **What this module makes you able to do:** walk into a 45-minute system design
> round on any of ten common problems and produce a complete, numbered, defensible
> design — requirements, arithmetic, API, schema, architecture, deep dives, failure
> modes, trade-offs — without improvising the structure while the clock runs.
>
> **Interview weight:** ★★★★★ (this *is* the interview)
>
> **Prerequisites:** Modules 01-14. Every case study assumes you already know the
> concepts; this module is only about assembling them under time pressure.

The concept modules taught you the parts. This module is ten fully assembled machines.
Each one is written the way you would actually deliver it out loud, with the arithmetic
shown so you can check your own working when you drill it on paper.

---

## Contents

| # | Case study | Weight | What it really tests |
|---|-----------|--------|----------------------|
| 15.1 | [Design a URL shortener](#151-design-a-url-shortener) | ★★★★★ | ID generation, read-heavy caching, cache/DB layering |
| 15.2 | [Design a distributed rate limiter](#152-design-a-distributed-rate-limiter) | ★★★★★ | Algorithm choice, Redis atomicity, fail-open reasoning |
| 15.3 | [Design a notification system for 50M users](#153-design-a-notification-system-for-50m-users) | ★★★★★ | Fan-out, provider abstraction, retries/DLQ, idempotency |
| 15.4 | [Design a webhook delivery system](#154-design-a-webhook-delivery-system) | ★★★★☆ | At-least-once, backoff over days, per-tenant isolation |
| 15.5 | [Design a chat / messaging system](#155-design-a-chat--messaging-system) | ★★★★★ | Stateful connections, ordering, offline delivery |
| 15.6 | [Design a news feed / timeline](#156-design-a-news-feed--timeline) | ★★★★★ | Fan-out on write vs read, the celebrity problem, pagination |
| 15.7 | [Design a payment processing service](#157-design-a-payment-processing-service) | ★★★★★ | Idempotency, double-entry ledger, sagas, reconciliation |
| 15.8 | [Design a distributed job scheduler](#158-design-a-distributed-job-scheduler--task-queue) | ★★★★★ | Queue semantics, leases, leader election, fairness |
| 15.9 | [Design a file upload & processing pipeline](#159-design-a-file-upload--processing-pipeline) | ★★★★☆ | Signed URLs, async pipelines, quotas, lifecycle |
| 15.10 | [Design a multi-tenant RAG platform](#1510-design-a-multi-tenant-rag--ai-document-qa-platform) | ★★★★★ | Tenant isolation, vector scale, LLM gateway, eval, cost |
| — | [How to practise these](#how-to-practise-these) | — | The drill method |

### The 45 minutes, allocated

Every case study below is written against this budget. Memorize the budget, not the
answers.

```
 0-5 min   Requirements     scope down, 3-5 functional, every NFR a number
 5-10 min  Estimation       DAU -> QPS -> peak -> storage -> bandwidth -> cache
10-15 min  API              3-5 endpoints, one shown in full
15-20 min  Data model       tables, keys, indexes, and WHICH store and why
20-30 min  Architecture     one diagram, then walk write path and read path
30-40 min  Deep dives       the 2-3 things they push on
40-45 min  Failures + close what breaks first, at what number, 3 closing sentences
```

If you are still drawing boxes at minute 35 you have failed on time management, not on
knowledge. The fix is to say the numbers out loud early and let them drive the design.

---

## 15.1 Design a URL shortener

**Asked at:** almost everywhere as a warm-up; standard at SDE-1 → SDE-2  **Time budget:** 45 min
**Tests you on:** unique ID generation, read-heavy cache layering, the 301-vs-302
trade-off, and whether you can keep analytics off the hot path.

### 1. Requirements (5 min)

Functional:

1. Create a short link from a long URL, optionally with a custom alias and an expiry.
2. Redirect a short code to its long URL.
3. Per-link click analytics: total clicks, clicks by day, referrer, country.
4. Disable or delete a link (it must stop redirecting).
5. List the links owned by an account.

Non-functional, each one a number:

- 10M new links/day, 1B redirects/day — a 100:1 read:write ratio.
- Redirect p99 under 50 ms measured at the client, under 20 ms server-side.
- 99.99% availability on the redirect path (52.6 min/year), 99.9% on the create path.
  The redirect path and the create path get different SLOs on purpose.
- Links live 5 years by default.
- Analytics may lag up to 5 minutes. Stating this explicitly buys you the entire
  asynchronous pipeline later.
- Short codes of 7 characters or fewer.

Explicitly out of scope: authentication and billing UI, link preview/unfurling, QR
code generation, A/B destination rotation, and branded custom domains. I will mention
where each would attach.

### 2. Estimation (5 min)

I use 100,000 seconds per day instead of 86,400 — it is within 16% and makes the
division trivial.

```
Writes   10M/day  / 100,000 s = 100 writes/sec average
         peak 3x                = 300 writes/sec
Reads    1B/day   / 100,000 s = 10,000 reads/sec average
         peak 3x                = 30,000 reads/sec
```

Row size: code 7 B + long URL 200 B average + owner_id 8 B + two timestamps 16 B +
flags. Call it 250 B of data, 500 B with index and page overhead.

```
Storage  10M x 500 B      = 5 GB/day
         x 365            = 1.8 TB/year
         x 5 years        = 9 TB   (x3 replication = 27 TB provisioned)
```

Keyspace: base62 with 7 characters is 62^7 = 3.52 x 10^12 codes. At 3.65B links/year
that is roughly 960 years of headroom. Six characters gives 5.68 x 10^10, which is
about 15 years — enough, but 7 gives me room for random generation without frequent
collisions, so I take 7.

```
Bandwidth  30,000 redirects/s x ~500 B of response headers
           = 15 MB/s = 120 Mbps egress   (trivial; this is not a bandwidth problem)
```

Cache sizing: click distribution is Zipfian — a small fraction of links takes most of
the traffic. If the hot working set is 20M codes at 250 B each, that is 5 GB. I would
provision a 3-node Redis cluster at ~16 GB usable so I have headroom and HA, not
because I need 16 GB.

Analytics: 1B click events/day at 200 B each is 200 GB/day of raw events. I do not
store those in Postgres. Counters go to Redis and flush to a columnar store; raw
events land in BigQuery/ClickHouse with a 30-day retention, which is ~6 TB.

### 3. API (5 min)

```
POST   /v1/links                      create (Idempotency-Key header)
GET    /{code}                         redirect  (the hot path, own service)
GET    /v1/links/{code}                metadata
DELETE /v1/links/{code}                disable
GET    /v1/links/{code}/stats?from=&to=&granularity=day
```

The interesting one:

```http
POST /v1/links
Idempotency-Key: 8f1c...  (client-generated UUID)
Content-Type: application/json

{ "long_url": "https://example.com/a/very/long/path?x=1",
  "custom_alias": null,
  "expires_at": "2031-01-01T00:00:00Z" }

201 Created
{ "code": "aZ3kR9x",
  "short_url": "https://sho.rt/aZ3kR9x",
  "long_url": "https://example.com/a/very/long/path?x=1",
  "created_at": "2026-09-01T04:00:00Z" }

409 Conflict   -> custom alias already taken
422            -> same Idempotency-Key, different body
```

The redirect is deliberately not under `/v1/` and is served by a separate deployment,
because it has a different SLO, a different scaling profile, and must survive the
create path being down.

### 4. Data model (5 min)

PostgreSQL for the link table:

```sql
CREATE TABLE links (
  code        text        PRIMARY KEY,           -- base62, <= 7 chars
  long_url    text        NOT NULL,
  owner_id    bigint      NOT NULL,
  created_at  timestamptz NOT NULL DEFAULT now(),
  expires_at  timestamptz,
  disabled    boolean     NOT NULL DEFAULT false
);
CREATE INDEX links_owner ON links (owner_id, created_at DESC);
CREATE UNIQUE INDEX links_idem ON links (owner_id, idem_key);
```

Why Postgres: the hot path is a single primary-key point lookup, custom-alias
uniqueness wants a real unique constraint rather than application-level checking, and
9 TB is comfortably shardable later by `hash(code) % 16` fixed logical shards. The
honest alternative is a wide-column store — **Bitly** publicly described moving its
link data from MySQL to Google Cloud Bigtable, walking 80 billion MySQL rows into just
over 40 billion Bigtable records for a 26 TB starting dataset, because they wanted
built-in replication and single-digit-millisecond reads. If the interviewer says
"assume 100B links", Bigtable/DynamoDB is the right answer and I would say so.

Redis: `l:{code} -> long_url` with a 24-hour jittered TTL, plus negative caching
(`l:{code} -> ""`, 60 s TTL) so a scanner probing random codes cannot turn into 30,000
Postgres misses per second.

Click events: Kafka/Pub/Sub topic → ClickHouse or BigQuery, partitioned by day.
Per-day counters in Redis (`c:{code}:{yyyymmdd}`), flushed once a minute.

### 5. High-level architecture (10 min)

```
        create path                          redirect path
  client                                 client
    | POST /v1/links                       | GET /aZ3kR9x
    v                                      v
 +--------+                            +--------+   L1 in-process LRU
 |  API   |--(1) alloc code range----->|  CDN   |   (60 s, 50k entries)
 | (Node) |    from code allocator     +---+----+
 +---+----+                                | miss
     | (2) INSERT                          v
     v                                +----------+  (1) L1 LRU hit -> 302
 +----------+   invalidate/warm       | Redirect |  (2) Redis GET   -> 302
 | Postgres |<---------------------+  | service  |  (3) Postgres    -> 302
 +----+-----+                      |  +----+-----+      + warm Redis
      | logical repl               |       | fire-and-forget click
      v                            +-------+
 +----------+                      | Redis |------+
 | replicas |                      +-------+      v
 +----------+                                +---------+   +------------+
                                             | Pub/Sub |-->| ClickHouse |
                                             +---------+   +------------+
```

**Write path.** The API validates the URL (scheme allowlist, reject private IP
literals to avoid becoming an SSRF/redirect laundering service), takes a code from a
pre-allocated range held in memory, inserts the row, writes the code into Redis
proactively so the first click is a hit, and returns 201. One database round trip, one
Redis round trip, no coordination.

**Read path.** CDN edge answers the viral codes. On miss the redirect service checks
its in-process LRU, then Redis, then Postgres, warming each layer on the way back. It
appends the click event to a local ring buffer and returns the 302 immediately — the
analytics publish happens on a background flush, so a Kafka hiccup can never add
latency to a redirect. Layered hit rates I would expect: CDN 20-30%, in-process LRU
brings the cumulative rate to ~60%, Redis to ~96%, leaving 3-5% of requests hitting
Postgres. At 30,000 peak reads/sec that is ~1,200 QPS of primary-key lookups on
Postgres, which one primary and two replicas handle without effort.

### 6. Deep dives (10 min)

**Deep dive 1 — code generation.** Three real options:

*Random base62 + unique insert.* Generate 7 random characters, insert, retry on unique
violation. After a year at 3.65B links the keyspace is 0.1% occupied, so roughly 1 in
960 inserts collides and retries. Simple, unguessable, but every write needs the
database to adjudicate.

*Counter + base62.* A monotonic counter (Postgres sequence, Redis `INCRBY`, or a
ticket service) encoded to base62. No collisions ever, dense codes, and no read before
write. The problem is that sequential codes are enumerable — anyone can walk the
keyspace and scrape every link, which is a real privacy incident because people shorten
private documents. The fix is to keep the counter but pass it through a bijective
scramble before encoding: multiply by a large secret odd number modulo 62^7. The
mapping stays one-to-one (so still zero collisions) while the output looks random.

*Snowflake IDs.* A 64-bit Snowflake encodes to 11 base62 characters, which breaks the
7-character requirement, and truncating it reintroduces collisions. Snowflake is the
right tool when you need time-sortable IDs across shards; a short code does not need
time ordering. Saying *why you are not using* a well-known technique is a stronger
signal than using it.

I take the batched counter with a scramble. Each API instance reserves 10,000 codes at
a time with one `UPDATE ... RETURNING` on a counter row, so at 300 writes/sec across
say 6 instances each instance refills once every ~200 seconds. Codes lost when an
instance dies are irrelevant — the keyspace is 3.5 trillion.

Custom aliases live in the same table and namespace, enforced by the primary key, with
a reserved-word blocklist (`api`, `login`, `admin`, `static`). Never
`SELECT ... then INSERT` — that is a TOCTOU race; let the unique constraint fail and
translate the error to a 409.

**Deep dive 2 — redirect latency and the 301/302 decision.** A 301 is cacheable by
browsers and intermediaries, so returning users never touch your servers again: cheap
and fast, but your click analytics decay and revoking a link can take weeks to
propagate. A 302 forces every click through you: accurate analytics and instant
revocation, at the cost of serving every click forever. The middle ground is a 301
with a short private max-age — public HTTP probes of `bit.ly` show exactly that shape,
a permanent redirect with a small `Cache-Control: private, max-age`. My default:

```
HTTP/1.1 301 Moved Permanently
Location: https://example.com/...
Cache-Control: private, max-age=90
```

That keeps the first click of every session on my server (so analytics stay useful and
revocation propagates within 90 seconds) while sparing me the repeat clicks.

Cache stampede protection matters here because virality is the normal case: when a
code goes from 0 to 5,000 requests/sec, a cache miss must not become 5,000 concurrent
Postgres queries. Single-flight per key in the redirect service (one in-flight fetch
per code, other requests await the same promise) plus a jittered TTL solves it. See
[Module 07](./07_Caching_And_CDN.md) §7.6.

**Deep dive 3 — analytics without touching the hot path.** The redirect handler does
three things: resolve, append the click to an in-process buffer, return. A background
task flushes the buffer to Pub/Sub every 200 ms or 1,000 events, whichever comes first.
If the publish fails, I drop the batch and increment a counter — losing 0.01% of
analytics events is acceptable, adding 5 ms to a redirect is not. **Bitly** made
exactly this split publicly: shortening is fully synchronous because it must be fast
and consistent, while analytics is fully asynchronous, at a reported 6 billion clicks
per month.

Counters use Redis `INCR` on `c:{code}:{date}`, flushed to the warehouse every minute.
Unique visitors use HyperLogLog (`PFADD`/`PFCOUNT`): 12 KB per counter and 0.81%
standard error, versus storing a set of visitor IDs which would be gigabytes per
popular link.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| A viral link makes one Redis key hot | ~10,000 req/s on one key lands on one shard | The read is fine (replicas), the *counter* is the problem: split `c:{code}:{day}` into 16 sub-keys and sum on read |
| Redis cluster unavailable | immediately | In-process LRU absorbs ~60%; remainder goes to Postgres at ~12k QPS of PK lookups; 20 ms Redis timeout + circuit breaker so a slow Redis does not become slow redirects |
| Postgres working set exceeds RAM | ~1-2B rows, when the `code` index no longer fits | Move to 16 fixed logical shards on `hash(code)`, or migrate the link table to Bigtable/DynamoDB. Trigger metric: index-to-RAM ratio above ~60% |
| Analytics pipeline backs up | consumer lag > 5 min | Shed: drop to counters-only, stop writing raw events. The redirect path is unaffected by design |
| Enumeration / scraping | any | Scrambled codes, negative caching, per-IP rate limit on 404s |
| Malicious destinations | any | Asynchronous safe-browsing check after creation; a flagged link returns an interstitial, not a 302 |

### 8. Trade-offs — the closing summary

> I would start with a single Postgres primary plus Redis and a CDN, because at 30,000
> peak redirects per second and 9 TB over five years, the read path is a caching
> problem and the write path is 300 inserts per second — neither justifies sharding on
> day one. The two decisions I would defend hardest are the batched counter with a
> bijective scramble, which gives me zero collisions *and* unguessable codes without a
> read-before-write, and pushing analytics fully off the redirect path so a Kafka
> incident can never slow down a redirect. The thing I would watch is the index-to-RAM
> ratio on Postgres: when it passes 60% I would move to fixed logical shards on
> `hash(code)` rather than trying to scale the single node further.

### If they push further

**Q: How would this change at 100 billion links?**
The link table stops being a Postgres problem. I would move it to Bigtable or DynamoDB
keyed on the code, which gives single-digit-millisecond point reads and horizontal
growth without me operating shards — the same move Bitly made to Bigtable. I would
keep Postgres for accounts, ownership and billing, because those are relational and
small. The redirect service does not change at all, which is the point of having kept
it as one point lookup.

**Q: How do you expire links and reclaim codes?**
I expire but never reclaim. Set `expires_at`, have the redirect return 410 Gone when
`now() > expires_at`, and let a monthly partition drop remove the rows. Reclaiming
codes means a URL that used to point at document A now points at document B, which is
a security problem, not a storage optimization. With 3.5 trillion codes I never need
to reclaim.

**Q: Multi-region — how do you serve redirects from three continents?**
The redirect path is read-only and eventually consistent, so it replicates beautifully:
one Redis cluster and one read replica per region, with a global anycast load balancer
routing to the nearest. Writes stay in one region (300/sec does not need multi-master)
and replicate out. The visible consequence is that a link created in us-central1 may
404 in asia-south1 for a second or two, so the create response writes the code into
the creating region's cache and I accept that a link shared within milliseconds of
creation can miss once. If that is unacceptable, the redirect service falls back to a
cross-region read on miss before returning 404 — one extra 150 ms round trip on the
rarest path.

**Q: A customer wants 100 million links created in an hour (bulk import).**
That is 28,000 writes/sec against a system sized for 300, so it does not go through the
normal API. Bulk import becomes an async job: upload a CSV to object storage, a worker
allocates a large code range up front (one round trip for 10 million codes), and writes
with `COPY` in batches of 10,000 rather than single-row inserts. Postgres will do
50,000+ rows/sec with `COPY` where it does a few thousand with individual inserts. The
customer gets a job ID and a completion webhook.

---

## 15.2 Design a distributed rate limiter

**Asked at:** infrastructure and platform teams, and as a follow-up to almost any API
design question  **Time budget:** 45 min
**Tests you on:** algorithm selection with real arithmetic, atomicity in Redis, the
latency/accuracy trade-off of local counters, and whether you understand that a
protective component must not become the outage.

### 1. Requirements (5 min)

This is a *shared service*, not a decorator in one app. Functional:

1. Given a key and a cost, return an allow/deny decision with the remaining budget.
2. Rules configurable per (tenant, route, identity dimension) without a deploy.
3. Multiple dimensions evaluated per request — per-IP, per-API-key, per-tenant,
   per-route — with the most restrictive result winning.
4. Standard response contract: 429 with `Retry-After` and `X-RateLimit-*` headers.
5. Rule changes take effect everywhere within 30 seconds.

Non-functional:

- 1M decisions/sec globally at peak.
- Added latency: p99 ≤ 2 ms (budget: ~1 ms Redis round trip, ~1 ms our overhead).
- Accuracy within 5% of the configured rate. I am stating a tolerance because exact
  global counting at 1M/sec is not worth what it costs.
- The limiter must fail **open** for protective limits and **closed** for security
  limits. This is the single most important design decision in the problem.
- 99.99% availability, and a hard requirement that a limiter outage does not become an
  API outage.

Out of scope: bot detection and WAF rules, L3/L4 DDoS scrubbing (that is the CDN's
job), and billing quotas — I will explain why a monthly quota is a different problem
from a per-second rate.

### 2. Estimation (5 min)

```
Decisions      1M/sec peak
Redis capacity ~100k ops/sec per node for a small Lua script
               1M / 100k = 10 nodes at 100% -> 16 shards at ~60% utilization
```

State per bucket is small: token count (8 B) + last-refill timestamp (8 B) = 16 bytes
of logical state. Real Redis overhead for a hash with a ~40-byte key is closer to
100 B, so:

```
Active keys    50M (distinct API keys x routes x windows)
Memory         50M x 100 B = 5 GB      -> 16 GB cluster with headroom
```

Now the important arithmetic — the two-tier design:

```
Without local buckets:  1M decisions/sec -> 1M Redis ops/sec  -> 16 shards
With local buckets:     ~90% decided locally
                        -> 100k Redis ops/sec -> 2-4 shards
                        -> p99 drops from ~1.5 ms to ~0.05 ms for 90% of requests
```

Published two-tier designs report roughly an order of magnitude less central traffic
while staying within single-digit percent of the true rate. I would take that trade
and state the error budget explicitly.

Config: a few thousand rules at ~500 B each — kilobytes. It fits in memory on every
gateway, which is why 30-second propagation is easy.

### 3. API (5 min)

```
POST /v1/check                    single decision (HTTP for simplicity)
POST /v1/check:batch              N keys in one round trip
GET  /v1/rules?tenant=            read rules
PUT  /v1/rules/{id}               upsert a rule
```

The interesting one:

```http
POST /v1/check
{ "dimensions": [
    { "scope": "api_key", "id": "ak_9f2", "route": "POST /charges" },
    { "scope": "tenant",   "id": "t_42" },
    { "scope": "ip",       "id": "203.0.113.7" } ],
  "cost": 1 }

200 OK
{ "allowed": false,
  "limiting_dimension": "api_key",
  "limit": 100, "remaining": 0,
  "reset_after_ms": 420,
  "retry_after_s": 1 }
```

Two notes I would say out loud. First, `cost` exists because not all requests are
equal — a bulk endpoint that fans out to 50 internal calls should consume 50 tokens,
which is how you stop one expensive endpoint from evading a limit designed for cheap
ones. Second, in production the gateway would call this over gRPC (Envoy's
`ShouldRateLimit` shape) or, better, decide locally and only reconcile with the
service — an HTTP round trip per request is exactly the latency I am trying to avoid.

### 4. Data model (5 min)

Redis, one hash per bucket:

```
Key:    rl:{v1}:{scope}:{id}:{route_hash}
Fields: tokens (float), ts (ms epoch of last refill)
TTL:    2 x (capacity / refill_rate) seconds, refreshed on write
```

The TTL is what keeps memory bounded: an API key that goes quiet has its bucket
evicted automatically, and a bucket that is absent is simply a full bucket. The `{v1}`
prefix lets me invalidate every bucket during a migration by bumping the version.

Rules live in Postgres (`rules` table: id, tenant_id, scope, route_pattern, capacity,
refill_per_sec, burst, action, enabled) and are pushed to gateways over a config
stream, with a 30-second poll as the fallback so a broken stream degrades to slightly
stale rules rather than no rules.

Counters and decisions go to a metrics pipeline asynchronously. Never write metrics on
the decision path.

### 5. High-level architecture (10 min)

```
   client
     |
     v
 +-----------------------------+   local token bucket per (key, rule),
 |  API gateway / sidecar      |   in-process, absorbs ~90% of decisions
 |  [ local bucket + rules ]   |
 +------+----------------+-----+
        | sync (async, batched every 100 ms or N requests)
        v                |
 +---------------+       |  on local-bucket miss / drift check
 | Rate limit    |<------+
 | service       |
 +------+--------+                +--------------+
        | EVALSHA (Lua, atomic)   | Rules svc    |
        v                         | + Postgres   |
 +---------------------------+    +------+-------+
 | Redis cluster, 16 shards  |           | config stream (<= 30 s)
 | hash-tagged by key        |-----------+--> gateways
 +---------------------------+
        | async
        v
 +---------------+
 | metrics/logs  |  (decisions, rejections, drift)
 +---------------+
```

**Decision path.** The gateway evaluates local buckets for every dimension. If all
have tokens, it consumes locally and forwards the request — no network hop at all. It
increments a pending-consumption counter; every 100 ms or every 20 consumed tokens it
sends the batch to the service, which applies it atomically in Redis and returns the
authoritative remaining count, which the gateway uses to correct its local view. If a
local bucket is empty, the gateway asks Redis synchronously before rejecting — I would
rather spend 1 ms than wrongly 429 a paying customer.

**Failure path.** If Redis or the service is unreachable, the gateway keeps using local
buckets with the limit divided by the number of gateway nodes (a conservative local
share), and emits a "degraded" metric. For dimensions marked `security: true` (login,
OTP, signup) it fails closed instead.

### 6. Deep dives (10 min)

**Deep dive 1 — algorithm choice, with the arithmetic.**

*Fixed window counter.* `INCR rl:{key}:{minute}`. Trivial, and wrong at the boundary:
with a limit of 100/min, a client sends 100 requests at 11:59:59.9 and 100 more at
12:00:00.1, so 200 requests land in 200 ms — 2x the intended rate. Fine for coarse
protection, never for a contractual limit.

*Sliding window log.* Store a sorted set of request timestamps, `ZREMRANGEBYSCORE` the
expired ones, count what remains. Exact, and the memory is O(requests) per key: at
100 req/min × 8 B × 50M keys = 40 GB just for timestamps, plus sorted-set overhead.
Correct, unaffordable.

*Sliding window counter.* Weight the previous window by how far into the current one
you are: `count = prev * (1 - elapsed/window) + curr`. Two integers per key, error
bounded by the assumption that the previous window's traffic was uniform. This is what
I would pick if bursts must be smooth.

*Token bucket.* Two numbers per key, lazily refilled at read time. Burst capacity is a
first-class parameter, which matters because real clients *are* bursty — a checkout
flow fires four API calls in 500 ms and should not be throttled for it. **Stripe**
describes using token buckets in Redis for their per-user request rate limiter, with
one bucket per user, which is the single limiter they recommend building first.

*Leaky bucket / GCRA.* One scalar (the theoretical arrival time) and a few arithmetic
operations. The most memory-efficient option and a good fit for a memory-constrained
edge node; it is what the Rust `governor` crate implements. The cost is that it shapes
traffic to a smooth rate, which is worse UX for legitimately bursty clients.

I choose token bucket, and I say why I rejected the other four in one sentence each.
That comparison is what the question is actually testing.

**Deep dive 2 — atomicity, and why `INCR` + `EXPIRE` is a bug.** Two commands are two
opportunities to fail between them. If the process dies after `INCR` and before
`EXPIRE`, the key has no TTL and the client is rate-limited forever. Redis is
single-threaded per shard, so a Lua script gives me a real atomic read-modify-write:

```lua
-- KEYS[1] = bucket   ARGV = capacity, refill_per_sec, cost, now_ms, ttl_s
local cap   = tonumber(ARGV[1])
local rate  = tonumber(ARGV[2])
local cost  = tonumber(ARGV[3])
local now   = tonumber(ARGV[4])

local b     = redis.call('HMGET', KEYS[1], 'tokens', 'ts')
local tokens = tonumber(b[1]) or cap
local ts     = tonumber(b[2]) or now

tokens = math.min(cap, tokens + (now - ts) / 1000 * rate)   -- lazy refill

local allowed = 0
if tokens >= cost then
  tokens  = tokens - cost
  allowed = 1
end

redis.call('HSET', KEYS[1], 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', KEYS[1], tonumber(ARGV[5]))
-- retry_after_ms until `cost` tokens are available again
local wait = 0
if allowed == 0 then wait = math.ceil((cost - tokens) / rate * 1000) end
return { allowed, math.floor(tokens), wait }
```

Three details worth pointing at. The refill is lazy — no background job ever touches
these keys, which is why 50M buckets cost nothing when idle. `now_ms` is passed in by
the caller from a single source (the service, not each gateway) because gateway clocks
drift and a fast clock hands out free tokens; using `redis.call('TIME')` is the
alternative and is safer for replication determinism in older Redis versions. And the
script must be loaded with `SCRIPT LOAD` and called with `EVALSHA`, so I ship ~40 bytes
per call instead of the whole script.

Multi-dimension checks need to be one round trip. With Redis Cluster that means the
keys must land on the same shard, so I hash-tag by the coarsest dimension:
`rl:{t_42}:api_key:ak_9f2` and `rl:{t_42}:tenant:t_42` share the tag `{t_42}` and
therefore the slot. That is a real constraint people miss: without hash tags, a
multi-key Lua script on Redis Cluster simply errors.

**Deep dive 3 — local vs global, and the accuracy you are buying.** With N gateways
and a global limit L, three strategies:

| Strategy | Redis ops | Accuracy | When |
|---|---|---|---|
| Every request hits Redis | 1M/sec | Exact within one round trip | Small volume, contractual limits |
| Static split: each gateway gets L/N | 0 | Badly wrong under uneven LB | Never, unless Redis is down |
| Two-tier: local bucket + periodic reconcile | ~100k/sec | Overshoot bounded by (N × local batch size) | The production answer |

The overshoot is calculable, which is what makes it defensible: if each gateway holds
at most 20 unreconciled tokens and there are 30 gateways, the worst case is 600 extra
requests above the limit in one reconcile interval. Against a limit of 10,000/min that
is 6%. If the interviewer needs 1%, I shrink the local batch to 3 tokens and pay more
Redis traffic — the dial is explicit.

**Deep dive 4 — fail open or fail closed.** This is the question that separates levels.
A rate limiter exists to protect the system; if the limiter is down and I fail closed,
I have converted a limiter outage into a total API outage, which is strictly worse than
the abuse I was preventing. **Stripe** states this plainly for their request rate
limiter: if the rate-limiting code has a bug or Redis goes down, requests are not
affected. So: fail open by default.

The exception is when the limit *is* the security control. Login attempts, OTP
verification, password reset and account creation must fail closed, because failing
open there means unlimited credential stuffing. So the rule schema carries a
`fail_mode: open | closed` field, defaulted to open, and the handful of security rules
set it to closed. Saying "fail open" without naming the exception is a half answer.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| One tenant's key becomes a hot shard | ~100k decisions/sec on one key | Split the bucket into 8 sub-buckets with the limit divided by 8, choose one at random per request; or pin that tenant to a dedicated shard |
| Redis failover | 5-30 s of lost global state | Local buckets carry the load; degraded metric fires; security rules fail closed |
| Clock skew across gateways | tens of ms is enough to matter | Timestamps come from one authority (the service or `redis.call('TIME')`), never from the calling gateway |
| Rule misconfiguration takes down a customer | one bad PUT | Rules are versioned, changes are dry-run against a traffic sample first, and every rule has a `shadow: true` mode that logs what it *would* have rejected — this is how you roll out a limiter safely on live traffic |
| Memory growth | 50M keys → 5 GB, unbounded if TTLs are wrong | TTL on every write; `maxmemory-policy allkeys-lru` so the worst case is lost state (fail open), not an OOM |
| The 429 storm | clients that retry instantly | `Retry-After` plus documented jittered backoff; and reject with a cheap response — a 429 must cost you far less than a 200 |

Quota vs rate, since it always comes up: a rate limit is a per-second protection
mechanism whose state can be lost safely (a bucket that vanishes is a full bucket). A
monthly quota is a *billing* fact — it must be durable, exactly counted, and
reconciled, so it lives in Postgres with an event log, not in a Redis key with a TTL.
Conflating them is how people end up with unbillable usage.

### 8. Trade-offs — the closing summary

> I would build this as a token bucket in Redis driven by one atomic Lua script, with a
> local in-process bucket in front of it that absorbs about 90% of decisions — that
> takes the central load from 1M to roughly 100k operations per second and keeps p99
> added latency under a millisecond, at the cost of a bounded overshoot I can calculate
> at about 6% and tune by shrinking the local batch. The decision I would defend
> hardest is failing open by default: a rate limiter that takes down the API it was
> protecting is a worse outcome than the abuse, so only the security-critical rules —
> login, OTP, signup — fail closed. The thing I would not compromise on is
> observability: every rule ships in shadow mode first, because the fastest way to
> cause an incident with this system is to deploy a correct limiter with a wrong number
> in it.

### If they push further

**Q: How do you support a limit like "1,000 requests per day per user" as well?**
Long windows break the token bucket's memory story — a per-day bucket is fine (one key
per user per day, 24 h TTL), but the interesting problem is that daily limits are
usually *quotas* with billing consequences. I would keep sub-hour windows in Redis and
move day/month windows to a durable counter: increment in Redis for the fast path,
persist deltas to Postgres every 10 seconds, and reconcile on read. Then a Redis flush
costs me at most 10 seconds of counting rather than a customer's whole month.

**Q: The rate limit service adds a network hop. How do you eliminate it entirely?**
Ship the limiter as a library or a sidecar so the decision is in-process, and make the
Redis reconciliation asynchronous. That is the two-tier design taken to its conclusion:
the request path has zero network calls in the common case. The cost is deployment
coupling — every service now embeds a version of your limiter, and upgrading it means
redeploying the fleet. A sidecar (Envoy with a local rate limit filter) is the
compromise: process-local latency, independent lifecycle.

**Q: How would you rate limit by something expensive to compute, like "tokens of LLM
output"?**
You cannot know the cost before the call, so you do a two-phase charge: reserve an
estimate (say `max_tokens`) at admission, then settle the actual usage when the
response completes, returning the unused reservation to the bucket. This is exactly how
I would meter an LLM gateway, and it is why the `cost` parameter exists in the API. See
[Module 14](./14_AI_LLM_System_Design.md) §14.14.

**Q: How do you rate limit fairly when one tenant has 1,000 API keys?**
Hierarchical buckets: check the key bucket *and* the tenant bucket, and reject if
either is empty. The subtlety is charge ordering — if you consume from the key bucket
and then discover the tenant bucket is empty, you have silently burned a token. Do the
check for all dimensions and the consume for all dimensions inside one Lua script, so
it is all-or-nothing.

---

## 15.3 Design a notification system for 50M users

**Asked at:** product companies at SDE-2; extremely common because it touches queues,
fan-out, third-party providers and idempotency all at once  **Time budget:** 45 min
**Tests you on:** fan-out patterns, provider abstraction and failure isolation,
at-least-once with deduplication, and whether you remember that users have preferences
and timezones.

### 1. Requirements (5 min)

Functional:

1. Send a notification to a user through the best available channel — push, email, SMS
   — chosen by user preference and category.
2. Bulk/campaign send to an audience segment (millions of recipients from one request).
3. Schedule for a future time, expressed in the *user's* timezone.
4. Respect preferences: per-category opt-in, quiet hours, and a frequency cap.
5. Track delivery status per notification, including provider webhooks (delivered,
   bounced, opened, failed).
6. Templates with versioning and localization.

Non-functional:

- 50M users, ~5 notifications/user/day = 250M notifications/day.
- Transactional notifications (password reset, OTP, payment receipt): p95 under 30
  seconds from API call to provider acceptance.
- A 10M-recipient campaign drains in under 15 minutes.
- At-least-once delivery with deduplication: no duplicate for the same idempotency key
  within 24 hours.
- 99.95% availability on the ingest API. Ingest must never block on a provider.
- Delivery status retained 90 days.
- Quiet hours honoured to the minute.

Out of scope: the in-app notification inbox UI, marketing consent/GDPR consent
capture, the template WYSIWYG editor, and email deliverability strategy (IP warm-up,
DKIM/SPF/DMARC) — I would name that as a real workstream owned by a deliverability
engineer, not something I hand-wave in an architecture.

### 2. Estimation (5 min)

```
Volume    250M/day / 100,000 s   = 2,500 notifications/sec average
          morning digest + campaigns push peak to 5x = 12,500/sec
          a 10M campaign in 15 min = 10M / 900 s = 11,000/sec on top
          => design the pipeline for 25,000/sec sustained
```

Channel mix — 60% push, 30% email, 10% SMS:

```
Push   150M/day = 1,500/sec avg   Email 75M/day = 750/sec   SMS 25M/day = 290/sec
```

Fan-out ratio: a campaign is one API request that becomes 10M messages. So the ingest
tier's only job is to accept and enqueue; the expansion happens in a worker that can
checkpoint. Never expand a segment inside a request handler.

Storage:

```
Message record ~400 B (ids, user, channel, template+version, status, timestamps,
                       provider message id, attempt count)
250M x 400 B = 100 GB/day
90-day retention = 9 TB
```

9 TB in one Postgres is possible but unpleasant. I keep 7 days hot in Postgres with
daily partitions (700 GB) and stream older rows to BigQuery/Bigtable for the 90-day
status lookup, which is a read-only, low-QPS access pattern.

Dedup store: 250M keys/day × ~64 B = 16 GB in Redis with a 24 h TTL. That is a real
cost, so I would say out loud that the alternative — a unique index on
`(tenant_id, idem_key)` in a daily-partitioned Postgres table — is cheaper and durable,
and I would use Redis only as a fast negative check in front of it.

Provider capacity, and this is where designs fail:

```
Push peak 10,000/sec. APNs is HTTP/2 with no published rate limit but aggressive
throttling; the common planning figure is ~2,000 requests/sec per connection, so
5-10 pooled connections per worker and ~10 workers. FCM's v1 API takes batches.
(Verify both against current provider docs before committing to numbers.)

SMS at 290/sec average is above most default provider accounts, which start in the
single or low double digits per second. That requires provisioned throughput and a
token bucket per provider so we shape our own traffic rather than collecting 429s.
```

Cost, which nobody estimates and everybody should: at roughly $0.005-$0.01 per SMS,
25M SMS/day is $125,000-$250,000 per day. That single number justifies a rule engine
that downgrades SMS to push whenever the device has a live token.

### 3. API (5 min)

```
POST /v1/notifications          single, transactional (Idempotency-Key required)
POST /v1/campaigns              bulk, by segment query or recipient list
GET  /v1/notifications/{id}     status timeline
PUT  /v1/users/{id}/preferences channels, categories, quiet hours, timezone
POST /v1/hooks/{provider}       inbound delivery receipts from SendGrid/Twilio/FCM
```

The interesting one:

```http
POST /v1/notifications
Idempotency-Key: order-8842-shipped-v1

{ "user_id": "u_9931",
  "category": "order_updates",
  "template": { "id": "order_shipped", "version": 7 },
  "data": { "order_id": "8842", "eta": "2026-09-03" },
  "channels": ["push", "email"],          // preference order, not a broadcast
  "priority": "transactional",            // transactional | digest | marketing
  "send_at": null,
  "ttl_seconds": 86400 }

202 Accepted
{ "notification_id": "n_01J8...", "status": "queued" }
```

Four things I would call out. `Idempotency-Key` is the caller's business key
(`order-8842-shipped-v1`), not a random UUID — that way a retry from *their* retry loop
dedups correctly. `channels` is a preference ordering: try push, fall back to email if
there is no live device token, which is different from sending both. `priority` drives
whether quiet hours and frequency caps apply at all (an OTP ignores quiet hours; a
digest does not). And `ttl_seconds` means "if you cannot deliver this within a day,
drop it" — a stale "your order shipped" notification is worse than none.

### 4. Data model (5 min)

```sql
-- Postgres: control plane and hot status
CREATE TABLE user_preferences (
  user_id     bigint PRIMARY KEY,
  timezone    text   NOT NULL DEFAULT 'UTC',
  quiet_start time,  quiet_end time,
  channels    jsonb  NOT NULL,   -- {"push":true,"email":true,"sms":false}
  categories  jsonb  NOT NULL,   -- {"order_updates":true,"marketing":false}
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE templates (
  id text, version int, channel text, locale text,
  subject text, body text, PRIMARY KEY (id, version, channel, locale)
);

CREATE TABLE notifications (              -- PARTITION BY RANGE (created_at), daily
  id             bytea       NOT NULL,    -- ULID: sortable, no hot index tail
  tenant_id      bigint      NOT NULL,
  user_id        bigint      NOT NULL,
  channel        text        NOT NULL,
  status         text        NOT NULL,    -- queued|sent|delivered|bounced|failed|dropped
  attempt        smallint    NOT NULL DEFAULT 0,
  provider       text,  provider_msg_id text,
  idem_key       text,
  created_at     timestamptz NOT NULL,
  PRIMARY KEY (id, created_at)
) PARTITION BY RANGE (created_at);
CREATE INDEX ON notifications (user_id, created_at DESC);
CREATE UNIQUE INDEX ON notifications (tenant_id, idem_key, created_at);
CREATE INDEX ON notifications (provider, provider_msg_id);  -- webhook lookup
```

Kafka/Pub/Sub topics:

```
notif.requests            partitioned by user_id  (per-user ordering, free)
notif.push / .email / .sms
notif.retry.30s / .5m / .1h                (tiered delay topics)
notif.dlq
notif.status                              (provider receipts -> status updater)
```

Redis: dedup keys (24 h TTL), per-provider token buckets, per-user frequency counters,
and a cached copy of `user_preferences` with a 5-minute TTL.

Why this split: preferences and templates are small, relational and read constantly →
Postgres plus cache. The message pipeline is high-volume, ordered-per-key and needs
replay → a log. Status history is write-once, read-rarely, huge → columnar.

### 5. High-level architecture (10 min)

```
 callers                                          providers
   |                                          +--> APNs / FCM
   v                                          |
+--------+   +----------------+   +--------+  |  +--> SendGrid/SES
| Ingest |-->| notif.requests |-->| Policy |--+->| Channel workers |
|  API   |   |    (Kafka)     |   | worker |     | (adapter+breaker)|
+--------+   +----------------+   +---+----+     +--------+--------+
   ^ 202                              |                   |    +--> Twilio
   |                                  | drop / defer      |
+--------------+                      v                   v
| Campaign     |               +-------------+     +-------------+
| fan-out      |               | scheduler   |     | retry topics|
| worker       |               | (minute     |     | 30s/5m/1h   |
| (checkpoints)|               |  buckets)   |     +------+------+
+------+-------+               +-------------+            | exhausted
       |                                                  v
       v                        +-------------+       +-------+
  segment store                 | Status      |<------| DLQ   |
  (BigQuery/PG replica)         | updater     |       +-------+
                                +------+------+
                                       ^ provider webhooks
```

**Write path (transactional).** Ingest validates, checks the dedup key, writes a
`queued` row and produces to `notif.requests` in one logical step (transactional
outbox — see [Module 08](./08_Messaging_And_Events.md) §8.11), and returns 202 in under
50 ms. The policy worker resolves preferences, applies the rule chain, picks the
channel, renders the template, and produces to the channel topic. The channel worker
calls the provider through an adapter, records `sent` with the provider message ID, and
the status updater later reconciles the provider's webhook into `delivered` or
`bounced`.

**Write path (campaign).** Ingest writes a campaign row and returns 202. The fan-out
worker pages the segment with keyset pagination in batches of 1,000, produces one
message per recipient, and checkpoints the cursor after each batch. A crash resumes at
the cursor rather than restarting, and the unique `(campaign_id, user_id)` key makes
the overlap harmless.

**Read path.** Status lookups hit the hot Postgres partitions for recent notifications
and BigQuery for anything older than 7 days. There is no read path on the hot pipeline
at all, which is why the whole thing scales on write throughput alone.

### 6. Deep dives (10 min)

**Deep dive 1 — fan-out and scheduling.** The two hard parts of fan-out are resumability
and not melting the segment store. Keyset pagination
(`WHERE user_id > $cursor ORDER BY user_id LIMIT 1000`) is mandatory: `OFFSET 9000000`
on a 10M-row segment makes the database skip nine million rows per page. Ten million
recipients at 1,000 per batch is 10,000 batches; at 20 batches/sec per worker and 5
workers that is 100 seconds of expansion — well inside the 15-minute SLO, and the
bottleneck moves to the providers, which is where it should be.

Scheduling: a `scheduled` table partitioned by minute bucket, and a ticker that every
second claims rows whose `fire_at` has passed using `SELECT ... FOR UPDATE SKIP LOCKED`
(see [15.8](#158-design-a-distributed-job-scheduler--task-queue)). Two rules that are
easy to get wrong. First, quiet hours are evaluated at *dispatch* time in the user's
current timezone, not at request time, because a user can move and because a
notification scheduled 30 days ago should respect today's preferences. Second, a
notification that lands inside quiet hours is *re-scheduled* to the next allowed
minute, not dropped — unless its TTL expires first, in which case dropping it is the
correct behaviour and I record `dropped` with a reason so support can explain it.

The 9 AM problem: if every user gets a digest at 09:00 local time, you get 24 spikes a
day of roughly 50M/24 ≈ 2M notifications each. Smear each user's send over a jittered
15-minute window derived from `hash(user_id) % 900` seconds. That converts a 2M-in-a-
minute spike into a steady 2,300/sec.

**Deep dive 2 — provider abstraction, retries, DLQ.** One interface, several adapters:

```python
class SendResult(NamedTuple):
    outcome: Literal["accepted", "retryable", "permanent", "invalid_token"]
    provider_msg_id: str | None
    retry_after_s: float | None
    detail: str | None

class PushAdapter(Protocol):
    async def send(self, msg: Message) -> SendResult: ...
```

The value is entirely in the error classification, so I would put the table on the
board:

| Provider signal | Outcome | Action |
|---|---|---|
| 2xx | accepted | record `sent` + provider id |
| 429 / 503 with `Retry-After` | retryable | honour the header, then tiered retry |
| 5xx, timeout, connection reset | retryable | tiered retry with full jitter |
| APNs 410 Gone, FCM `UNREGISTERED` | invalid_token | **delete the device token**, do not retry, try the next channel |
| 400 malformed payload | permanent | DLQ + alert; this is our bug, not theirs |
| 402/403 account/billing | permanent | page someone; retrying will never help |

Kafka has no per-message delay, so retries use tiered topics: `retry.30s`, `retry.5m`,
`retry.1h`, then DLQ. The consumer of a delay topic checks `not_before` and, if the
message is not due, *pauses the partition* and resumes later — it must not `sleep()` in
the poll loop, or the consumer group will rebalance and you will have created a much
more interesting problem than a delayed notification.

Per-provider circuit breakers, one per (provider, channel). Trip on error rate *and*
slow-call rate: a provider that answers in 30 seconds is worse than one that returns
503 immediately, because it consumes your concurrency. When open, messages stay in the
channel topic (backpressure by design) and, for channels with a secondary provider,
route there — which only works because the adapter interface is identical, so failover
is a config change and not a code change.

**Deep dive 3 — idempotency and deduplication at three layers.** Duplicate
notifications are the most visible bug this system can have, so I defend at three
levels:

1. **API level.** `Idempotency-Key` per (tenant, key), stored with the response, 24 h
   retention. A retry returns the original 202 and the original notification ID.
2. **Message level.** A unique index on `(campaign_id, user_id)` or
   `(tenant_id, idem_key)` means the fan-out worker replaying a batch inserts zero new
   rows.
3. **Send level.** The dangerous window is between "provider accepted" and "our commit
   succeeded" — a crash there means the message went out but we think it did not, and a
   retry double-sends. Two mitigations: pass a deterministic
   `collapse_id`/`apns-collapse-id` or provider-side dedup key so the provider itself
   collapses the duplicate, and record the `sent` state *before* the provider call as
   `sending` with the attempt number, so recovery can query the provider by our
   deterministic key rather than guessing.

The underlying pattern is the dual-write problem, and the honest answer is
at-least-once delivery plus an idempotent receiver, with the provider's own dedup as
the last line. See [Module 09](./09_Reliability_Patterns.md) §9.4.

**Deep dive 4 — the preference and policy chain.** Evaluated in this order, and the
order matters:

```
global kill switch (per category, per channel)   -> drop, reason=killed
user channel opt-in                               -> try next channel
category opt-in                                   -> drop, reason=unsubscribed
priority == transactional ? skip the next two checks
quiet hours in the user's tz                      -> defer to next allowed minute
frequency cap (max 5 pushes/hour, 1 digest/day)   -> collapse into digest
device token exists and is fresh                  -> else fall to email
render template (id, version, channel, locale)    -> on failure: DLQ, alert
```

Preference lookups are 25,000/sec at peak, which is 25,000 QPS against one Postgres
table if you are naive. Cache in Redis with a 5-minute TTL and invalidate on write via
CDC, or replicate preferences into a per-worker local store. I would say the number out
loud, because "cache the preferences" without "because it is 25,000 QPS" is a guess.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| Preference lookups | 25,000 QPS on one table | Redis cache (5 min TTL) + CDC invalidation; degraded mode uses last-known preferences rather than sending blind |
| One provider is down | any | Per-provider circuit breaker; secondary provider for email/SMS; push has no substitute, so messages queue and TTL out |
| Consumer lag on a channel topic | > 5 min for transactional | Page. Autoscale consumers on lag (KEDA), and shed marketing traffic first — the priority field exists for this moment |
| Campaign starves transactional traffic | one 10M campaign | Separate topics and separate worker pools per priority class. A marketing campaign must never delay an OTP. This is the bulkhead, and it is the most important isolation in the system |
| Poison template | one bad template version | Render inside a try/except, route failures to DLQ, keep consuming. Never let one message stop a partition |
| DLQ nobody reads | after the first quiet week | Alert on DLQ depth > 0 sustained 15 min, plus a weekly digest of DLQ reasons. An unwatched DLQ is data loss with extra steps |
| SMS cost | $125k-250k/day at 25M/day | Channel downgrade rules, per-tenant spend caps, and a daily cost report. Cost is a non-functional requirement |
| Timezone/DST bugs | twice a year | Store the tz name (`Asia/Kolkata`), never a UTC offset; compute at dispatch; unique key on `(schedule_id, fire_at_utc)` so a DST repeat cannot double-fire |

### 8. Trade-offs — the closing summary

> The core of this design is that ingest never talks to a provider: the API accepts and
> returns 202 in under 50 milliseconds, and everything expensive — segment expansion,
> preference evaluation, template rendering, provider calls — happens in workers behind
> a log, which is what lets a 10-million-recipient campaign coexist with a 30-second
> SLO on password resets. The isolation I would defend hardest is separating priority
> classes into their own topics and worker pools, because the failure I actually expect
> is a marketing campaign delaying an OTP, not a provider outage. The number I would
> watch is consumer lag per channel: it is the single metric that tells me whether
> notifications are late, and I would alert on it long before I alert on CPU.

### If they push further

**Q: How do you guarantee we never send the same push twice, truly?**
I cannot, and I would say so. Between "provider accepted the request" and "we durably
recorded that fact" there is a window where a crash forces a choice between possibly
duplicating and possibly dropping. I choose duplicating for most categories and dropping
for none. What I *can* do is make duplicates rare and harmless: a deterministic
collapse key so the provider itself collapses them on the device, and idempotent
receivers. The honest formulation is at-least-once delivery with effectively-once
observable behaviour.

**Q: A user complains they got 47 notifications in one minute. What went wrong and how
does the design prevent it?**
Most likely a retry loop with a non-deterministic idempotency key, or a fan-out worker
that restarted without a checkpoint. The frequency cap is the backstop: max N per
category per hour, enforced with a Redis counter keyed
`freq:{user}:{category}:{hour}` checked in the policy worker. I would also add a global
per-user circuit breaker — more than 20 notifications in 5 minutes to one user stops
the pipeline for that user and raises an alert, because at that point the system is
almost certainly malfunctioning.

**Q: How would you add an in-app inbox?**
It becomes a fourth channel with a different storage model: instead of calling an
external provider, the "delivery" is an insert into an inbox table keyed
`(user_id, created_at DESC)` with a read cursor, plus a real-time nudge over
WebSocket/SSE if the user is connected. The interesting difference is retention and
read state — an inbox is a feed, so it inherits the pagination problems from
[15.6](#156-design-a-news-feed--timeline).

**Q: 50M users is 250M/day. What changes at 5 billion/day?**
2,500/sec becomes 50,000/sec, which changes three things. The status table stops being a
Postgres problem: move message state to Bigtable/Cassandra keyed
`(user_id, notification_id)` and keep only aggregates relational. Kafka partition count
has to be planned rather than guessed — at 50,000/sec with per-partition throughput in
the low tens of MB/s I would size partitions for consumer parallelism, and I would
*not* partition by tenant, because that creates a hot partition for the largest tenant.
And provider throughput becomes the binding constraint, so the design shifts from "send
fast" to "shape traffic to what the providers will accept", which means a token bucket
per provider account and negotiated throughput.

## 15.4 Design a webhook delivery system

**Asked at:** B2B SaaS, payments, and platform teams  **Time budget:** 45 min
**Tests you on:** at-least-once delivery over unreliable HTTP, exponential backoff over
days, per-tenant isolation, signature verification, and whether you treat webhooks as a
first-class product surface.

### 1. Requirements (5 min)

Functional:

1. Register webhook endpoints per tenant: URL, secret, event types, optional filters.
2. Deliver events to subscriber URLs with JSON payload and cryptographic signature.
3. Automatic retries with exponential backoff until success or max attempts (e.g. 3 days).
4. Delivery log: attempt history, response codes, latency, next retry time.
5. Pause/resume/disable endpoints; manual replay of a single event.
6. Dead-letter after exhaustion with alert to tenant.

Non-functional:

- 50k tenants, 500 events/sec average, 5k events/sec peak (Black Friday billing).
- Delivery attempt p99 under 5 s for first try (subscriber's problem after that).
- At-least-once delivery; subscribers must tolerate duplicates via idempotency.
- Per-tenant fair scheduling — one broken endpoint must not starve others.
- Endpoint secrets rotatable without downtime.
- 30-day delivery log retention.

Out of scope: inbound webhooks from third parties (that's your integration layer),
webhook payload transformation UI, and SDK generation — I would mention where they attach.

### 2. Estimation (5 min)

```
Events     500/s avg → 5,000/s peak
Attempts   assume 1.5 attempts/event avg → 7,500 delivery HTTP calls/s peak
           (broken endpoints retry; healthy ones = 1 attempt)
```

Storage:

```
Event record:  id 16 B + tenant 8 B + type 32 B + payload 2 KB avg + status 32 B ≈ 2.1 KB
500/s × 2.1 KB = 1 MB/s = 86 GB/day
30-day retention ≈ 2.6 TB (columnar or partitioned Postgres, not one table)
Attempt log:  7,500/s × 300 B = 2.25 MB/s — same store, partitioned by day
```

Outbound HTTP is the bottleneck, not storage. At 7,500 concurrent outbound connections
with 5 s timeout, I need a worker pool sized for concurrency, not QPS:

```
Little's Law: concurrency = 7,500/s × 0.2 s avg response = 1,500 in-flight
              provision 3,000 workers with headroom
```

Per-tenant limit: default 100 concurrent deliveries per tenant so one customer pointing
at `http://localhost` cannot exhaust the fleet.

### 3. API (5 min)

```
POST   /v1/webhook-endpoints              register URL + secret + event filters
GET    /v1/webhook-endpoints/{id}
PATCH  /v1/webhook-endpoints/{id}         pause, rotate secret, update URL
DELETE /v1/webhook-endpoints/{id}
GET    /v1/events/{event_id}/deliveries   attempt timeline
POST   /v1/events/{event_id}/replay       manual retry (admin)
POST   /internal/events                   ingest from product services (mTLS)
```

The interesting one — event ingest (internal):

```http
POST /internal/events
X-Idempotency-Key: evt_order_paid_8842

{ "tenant_id": "t_42",
  "type": "order.paid",
  "occurred_at": "2026-09-01T10:00:00Z",
  "data": { "order_id": "8842", "amount_cents": 4999 } }

202 Accepted
{ "event_id": "evt_01J8...", "status": "pending" }
```

Subscriber receives:

```http
POST https://customer.com/hooks/acme
X-Webhook-Id: evt_01J8...
X-Webhook-Timestamp: 1693564800
X-Webhook-Signature: sha256=abc123...
Content-Type: application/json

{ "id": "evt_01J8...", "type": "order.paid", "data": { ... } }
```

Signature: `HMAC-SHA256(secret, timestamp + "." + body)` — subscriber verifies timestamp
is within 5 minutes to block replay attacks. **Stripe** documents this exact shape.

### 4. Data model (5 min)

```sql
CREATE TABLE webhook_endpoints (
  id           uuid PRIMARY KEY,
  tenant_id    bigint NOT NULL,
  url          text NOT NULL,
  secret_hash  bytea NOT NULL,        -- never store plaintext; rotate with grace period
  event_types  text[] NOT NULL,
  status       text NOT NULL,         -- active|paused|disabled
  created_at   timestamptz NOT NULL
);
CREATE INDEX ON webhook_endpoints (tenant_id);

CREATE TABLE events (
  id           bytea PRIMARY KEY,     -- ULID
  tenant_id    bigint NOT NULL,
  type         text NOT NULL,
  payload      jsonb NOT NULL,
  idem_key     text,
  created_at   timestamptz NOT NULL
) PARTITION BY RANGE (created_at);

CREATE TABLE deliveries (
  event_id     bytea NOT NULL,
  endpoint_id  uuid NOT NULL,
  attempt      smallint NOT NULL,
  status       text NOT NULL,         -- pending|success|failed|dlq
  http_status  smallint,
  response_ms  int,
  next_retry   timestamptz,
  PRIMARY KEY (event_id, endpoint_id, attempt)
) PARTITION BY RANGE (created_at);
CREATE INDEX ON deliveries (status, next_retry) WHERE status = 'pending';
```

Kafka/Pub/Sub:

```
webhook.events.ingest     → fan-out worker (matches endpoints, creates deliveries)
webhook.deliver           → delivery workers (HTTP outbound)
webhook.retry.1m / .5m / .1h / .6h / .24h   (tiered delay)
webhook.dlq
```

Redis: per-endpoint circuit breaker state, per-tenant concurrency semaphores.

### 5. High-level architecture (10 min)

```
 product services                    subscriber endpoints
       |                                      ^
       v                                      |
 +-----------+   webhook.events    +------------------+
 | Internal  |-------------------->| Fan-out worker   |
 | ingest    |                     | (match endpoints)|
 +-----------+                     +--------+---------+
       | 202                                  |
       v                                      v
  events table                         deliveries table
                                              |
                                     +--------v---------+
                                     | Delivery workers |
                                     | (HTTP + sig)     |
                                     +--------+---------+
                                              |
                              +---------------+---------------+
                              v               v               v
                         retry topics      DLQ          metrics/alerts
```

**Write path.** Ingest validates, dedups on `(tenant_id, idem_key)`, inserts event,
publishes to `webhook.events.ingest`, returns 202. Fan-out worker loads active
endpoints for `(tenant_id, event.type)`, inserts one `deliveries` row per endpoint with
`status=pending`, publishes to `webhook.deliver`. Delivery worker acquires per-tenant
semaphore slot, signs payload, POSTs with 10 s timeout. On 2xx → `success`. On
429/5xx/timeout → schedule retry with full jitter backoff. On 410/404 → disable
endpoint and alert tenant.

**Read path.** Tenant dashboard queries `deliveries` joined to `events` by `event_id`,
paginated with keyset on `(created_at, event_id)`.

### 6. Deep dives (10 min)

**Deep dive 1 — retry schedule over days.** Backoff must be exponential with full jitter
so 10,000 failing endpoints don't retry in sync:

```
attempt 1: immediate
attempt 2: 1 min  ± 50%
attempt 3: 5 min
attempt 4: 30 min
attempt 5: 2 h
attempt 6: 6 h
attempt 7–12: 24 h apart → ~3 days total
```

Retries use tiered delay topics (same pattern as [15.3](#153-design-a-notification-system-for-50m-users)):
consumer checks `next_retry`, pauses partition if not due. Never `sleep()` in the poll loop.

**Deep dive 2 — per-tenant isolation.** Three layers:

1. **Concurrency cap** — Redis `INCR` semaphore per tenant, max 100; release on completion.
2. **Fair queue** — partition `webhook.deliver` by `hash(tenant_id) % 64`, not by endpoint,
   so one tenant cannot fill every partition.
3. **Circuit breaker per endpoint** — 10 consecutive failures → open for 30 min; events
   queue in DB with `next_retry` pushed out, not hammering a dead URL.

**Deep dive 3 — idempotency contract with subscribers.** We guarantee at-least-once.
Document that subscribers must:

- Verify signature before processing.
- Dedup on `X-Webhook-Id` for 24+ hours.
- Return 2xx only after durable processing.

If they return 2xx before committing, we stop retrying and the event is lost on their
side — that is their bug. **GitHub** webhooks document the same contract explicitly.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| One tenant's endpoint is slow (30 s) | holds semaphore slots | Per-endpoint timeout 10 s; per-tenant cap; slow endpoints don't block fast ones in other tenants |
| Retry storm after regional outage | all endpoints fail at once | Jitter + max publish rate to delivery topic; circuit breakers |
| Fan-out for broadcast event | 1 event × 50 endpoints/tenant | Async fan-out; never expand in ingest handler |
| Secret rotation | mid-flight deliveries | Store `secret_version` on endpoint; sign with current; accept verification with current or previous for 24 h |
| DLQ growth | tenant never fixes URL | Alert at attempt 3; auto-pause at DLQ; dashboard shows failing endpoint prominently |
| Ingest spike | 5k events/s | Kafka absorbs; scale fan-out and delivery workers on lag (KEDA) |

### 8. Trade-offs — the closing summary

> I would treat webhooks as an async pipeline: ingest returns 202 in under 50 ms, and
> HTTP delivery happens in workers with tiered retries over three days. The decisions I
> would defend hardest are at-least-once with signed payloads and documented subscriber
> idempotency, and per-tenant concurrency caps so one broken `localhost` URL cannot starve
> the fleet. The metric I would watch is delivery success rate per endpoint over a
> rolling hour — it predicts support tickets before the DLQ fills.

### If they push further

**Q: How do you deliver within 1 second for "real-time" webhooks?**
Separate priority class: `webhook.deliver.realtime` topic with dedicated workers, max 3
retries in 60 seconds, then fall back to the standard schedule. Charge more or cap rate.

**Q: Multi-region — where do deliveries originate?**
Deliver from the region closest to the subscriber URL's DNS resolution, or default
egress region per tenant. Cross-region ingest is fine (event log replicates); outbound
HTTP should minimize RTT.

**Q: How does replay work without duplicating side effects?**
Replay creates a new `delivery` row with a new attempt number but the same `event_id`.
Subscriber dedups on `X-Webhook-Id`. We document that replays are intentional duplicates.

---

## 15.5 Design a chat / messaging system (WhatsApp-like)

**Asked at:** Meta, Slack, Discord, any social/product company  **Time budget:** 45 min
**Tests you on:** WebSocket connection management, message ordering per conversation,
offline delivery, read receipts, and media handling.

### 1. Requirements (5 min)

Functional:

1. 1:1 and group chats (up to 256 members).
2. Send/receive text messages in real time; offline users get messages on reconnect.
3. Message history: scroll back, paginated.
4. Delivery and read receipts (single/double/blue ticks).
5. Media messages (image/video) — upload and inline preview.
6. Online/presence indicators (optional but expected in discussion).

Non-functional:

- 500M DAU, 50B messages/day.
- Send-to-deliver p99 under 500 ms for online recipients.
- Messages never lost for online or offline users (durability).
- Per-conversation ordering guaranteed.
- 99.95% availability on messaging path.
- Message retention 5 years (compliance); media in object storage.

Out of scope: end-to-end encryption implementation details (mention Signal protocol as
follow-up), voice/video calls, message search at scale, moderation ML pipeline.

### 2. Estimation (5 min)

```
Messages   50B/day / 100,000 s = 500,000 writes/sec average
           peak 3x = 1.5M writes/sec
```

Assume 80% text (200 B), 20% media metadata (500 B + media in GCS):

```
Text storage:  40B × 200 B = 8 TB/day metadata
5-year metadata ≈ 15 PB before compression (→ sharded Cassandra/Scylla, not Postgres)
Media:         10B files × 500 KB avg = 5 PB/day — object storage + CDN
```

Connections: 100M concurrent WebSockets (20% of DAU online) — this drives the architecture.
Cannot pin 100M connections on one load balancer; need connection layer sharded by `user_id`.

```
Per connection server: ~50k–100k WebSockets (uWebSockets/Go)
100M / 75k ≈ 1,400 connection servers
```

### 3. API (5 min)

```
WS     /v1/ws?token=...                    real-time channel
POST   /v1/conversations                   create 1:1 or group
GET    /v1/conversations                   inbox list
GET    /v1/conversations/{id}/messages?cursor=&limit=50
POST   /v1/conversations/{id}/messages     send (also over WS)
POST   /v1/media/upload-url                signed URL for attachment
POST   /v1/messages/{id}/read              read receipt
```

WebSocket frame (send message):

```json
{ "type": "message.send",
  "client_msg_id": "cm_9f2a...",          // client idempotency
  "conversation_id": "conv_42",
  "body": { "text": "hello" },
  "sent_at": "2026-09-01T10:00:00Z" }

{ "type": "message.ack",
  "client_msg_id": "cm_9f2a...",
  "server_msg_id": "msg_01J8...",
  "status": "delivered" }
```

`client_msg_id` dedups client retries — same ID returns same `server_msg_id`.

### 4. Data model (5 min)

**Cassandra/Scylla** for messages (write-heavy, time-range queries):

```sql
CREATE TABLE messages_by_conversation (
  conversation_id uuid,
  msg_id          timeuuid,           -- time-ordered
  sender_id       bigint,
  body            text,
  media_ref       text,
  client_msg_id   text,
  PRIMARY KEY ((conversation_id), msg_id)
) WITH CLUSTERING ORDER BY (msg_id DESC);
```

**Postgres** for conversation metadata and membership:

```sql
CREATE TABLE conversations (
  id         uuid PRIMARY KEY,
  type       text,                    -- direct|group
  created_at timestamptz
);
CREATE TABLE members (
  conversation_id uuid,
  user_id         bigint,
  joined_at       timestamptz,
  last_read_msg   timeuuid,
  PRIMARY KEY (conversation_id, user_id)
);
CREATE UNIQUE INDEX ON members (user_id, conversation_id);
```

Redis:

- `online:{user_id}` → connection server ID (TTL 60 s, heartbeat renews).
- `inbox:{user_id}` → sorted set of conversation_id by last_message_at (cache).
- Pub/Sub or dedicated fan-out service for cross-server delivery.

### 5. High-level architecture (10 min)

```
  client A                    client B
     | WS                           | WS
     v                              v
 +----------+                   +----------+
 | Conn Srv |<---- Redis ----->| Conn Srv |   (user_id -> server mapping)
 | (shard)  |     pub/sub      | (shard)  |
 +----+-----+                   +----+-----+
      |                              ^
      | persist                      | push if online
      v                              |
 +----------+    +--------+    +-------------+
 | Message  |--->| Kafka  |--->| Delivery    |
 | API      |    | (by    |    | router      |
 +----------+    | conv_id)|    +-------------+
                 +--------+           |
      |                              offline?
      v                              v
 +----------+                   +----------+
 | Cassandra|                   | Push     |
 | (msgs)   |                   | (APNs/FCM)|
 +----------+                   +----------+
```

**Write path.** Client sends over WS or HTTP. API validates membership, dedups on
`(sender_id, client_msg_id)`, writes to Cassandra with `msg_id = now()` as timeuuid,
updates `inbox` cache, publishes to Kafka partitioned by `conversation_id` (ordering).
Delivery router checks `online:{user_id}`:

- Online → publish to connection server's Redis channel → WS push.
- Offline → enqueue push notification (collapse key = `conversation_id`).

**Read path.** History: `SELECT * FROM messages_by_conversation WHERE conversation_id = ?
AND msg_id < ? LIMIT 50` — keyset on timeuuid. Inbox: Postgres join or cached Redis ZSET.

### 6. Deep dives (10 min)

**Deep dive 1 — ordering.** Kafka partition per `conversation_id` guarantees order within
a chat. Across conversations order does not matter. Group message fan-out: one write to
Cassandra, N delivery events (one per member except sender). For 256-member groups at
1.5M msg/s global, group messages are ~5% of traffic — fan-out in delivery router, not
256 Cassandra writes.

**Deep dive 2 — connection routing.** User connects to any edge; handshake returns
`user_id` from JWT. Server registers `online:{user_id} = server_instance_id` in Redis
with 60 s TTL; heartbeat every 30 s. To deliver: lookup Redis → publish to
`channel:server:{id}` → that server pushes to socket. Sticky sessions at LB optional if
registration is authoritative.

**Deep dive 3 — read receipts.** `last_read_msg` on `members` row; on read, update and
broadcast `message.read` event to other participants. High frequency in active chats —
debounce updates to 1 per 2 seconds per user per conversation to avoid write amplification.

**Deep dive 4 — media.** Never bytes through API servers. `POST /media/upload-url` returns
presigned GCS URL; client uploads direct; message body references `media_ref`. Thumbnail
generation async via Pub/Sub worker. **WhatsApp** famously uses Erlang + custom protocol;
the lesson for interviews is separation of connection layer, message store, and media blob store.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| Hot conversation (viral group) | 256 members × high rate | Partition still one — ordering non-negotiable; scale consumers for delivery events |
| Connection server dies | 75k users disconnect | Clients reconnect with exponential backoff; messages safe in Cassandra; push for offline |
| Redis pub/sub gap | message lost between persist and push | Delivery router retries from Kafka; at-least-once to WS — client dedups on `server_msg_id` |
| Cassandra write spike | 1.5M/s | Shard cluster; batch writes; CL=QUORUM |
| Inbox query slow | power users in 10k groups | Cap groups; paginate inbox; cache top 50 conversations |

### 8. Trade-offs — the closing summary

> At 500k messages per second this is a write-optimized message store (Cassandra) plus
> a sharded WebSocket connection layer, with Kafka providing per-conversation ordering.
> I would defend partitioning Kafka by `conversation_id` and client-side idempotency via
> `client_msg_id`. The thing I would watch is connection server memory and file
> descriptors — that is what caps concurrent users before message throughput does.

### If they push further

**Q: End-to-end encryption?**
Signal protocol: keys exchanged out of band; server stores ciphertext only; read receipts
and search become harder. Mention trade-off; scope encryption to 1:1 first.

**Q: How do you implement "typing..." indicators?**
Ephemeral WS events, no persistence, drop if recipient offline. Rate limit to 1 per 3 s
per user to prevent flood.

**Q: Message sync across multiple devices?**
Each device has `last_synced_msg_id` per conversation; on connect, fetch `msg_id > cursor`.
Writes go to all devices via user_id fan-out (not conversation partition).

---

## 15.6 Design a news feed / timeline

**Asked at:** Meta, Twitter/X, LinkedIn  **Time budget:** 45 min
**Tests you on:** fan-out on write vs read, celebrity problem, pagination, ranking.

### 1. Requirements (5 min)

Functional:

1. Users post short updates (text, image, link).
2. Home feed: chronological or ranked posts from people they follow.
3. Follow/unfollow users.
4. Like and comment on posts.
5. User profile shows their posts.

Non-functional:

- 300M DAU, 100M posts/day, 500 feed reads/user/day.
- Feed load p99 under 200 ms.
- New post visible to followers within 5 seconds (eventual).
- 99.9% availability on read path.

Out of scope: full-text search, ads insertion ML, video transcoding, DMs.

### 2. Estimation (5 min)

```
Posts      100M/day / 100,000 = 1,000 writes/sec avg → 3,000 peak
Feed reads 300M × 500 / 100,000 = 1.5M reads/sec avg → 5M peak
```

Read:write ≈ **1,500:1** — optimize the read path aggressively.

```
Fan-out on write: avg user follows 200 people
  each post → 200 inbox writes → 3,000 × 200 = 600k writes/sec peak (borderline)
Celebrity: 1 user with 50M followers → 50M writes per post (impossible on write path)
```

Conclusion out loud: hybrid fan-out — write for normal users, read for celebrities.

Storage:

```
Post row ~500 B; 100M/day × 500 B = 50 GB/day posts
Feed cache per user: 500 post IDs × 8 B × 300M users = 1.2 TB if materialized for everyone
  (only active users' feeds hot — ~30M DAU × 4 KB = 120 GB Redis)
```

### 3. API (5 min)

```
POST   /v1/posts                         create (Idempotency-Key)
GET    /v1/feed?cursor=&limit=20         home feed
GET    /v1/users/{id}/posts?cursor=      profile
POST   /v1/users/{id}/follow
DELETE /v1/users/{id}/follow
POST   /v1/posts/{id}/like
GET    /v1/posts/{id}/comments?cursor=
```

Feed response:

```json
{ "items": [
    { "post_id": "p_01J8...", "author_id": "u_42", "text": "...",
      "created_at": "...", "like_count": 12, "liked_by_me": false }
  ],
  "next_cursor": "eyJ..." }
```

Cursor is base64-encoded `(created_at, post_id)` for keyset pagination.

### 4. Data model (5 min)

```sql
CREATE TABLE posts (
  id         bytea PRIMARY KEY,
  author_id  bigint NOT NULL,
  body       text,
  media_ref  text,
  created_at timestamptz NOT NULL
);
CREATE INDEX posts_author ON posts (author_id, created_at DESC);

CREATE TABLE follows (
  follower_id  bigint,
  followee_id  bigint,
  created_at   timestamptz,
  PRIMARY KEY (follower_id, followee_id)
);
CREATE INDEX follows_followee ON follows (followee_id);
```

**Feed cache (Redis/Cassandra):**

```
feed:{user_id} → sorted set of post_id by timestamp (precomputed fan-out)
```

Post content in Postgres or Cassandra; feed stores only IDs. Hydrate posts in batch:
`GET posts WHERE id IN (...)` — one query, not N+1.

Celebrity flag: `users.is_celebrity` if followers > 100k — skip write fan-out.

### 5. High-level architecture (10 min)

```
 post create                         feed read
     |                                    |
     v                                    v
 +--------+    posts table          +----------+
 | Post   |------------------------>| Feed     |
 | API    |                         | API      |
 +---+----+                         +----+-----+
     |                                   |
     v                                   | cache miss / celebrity merge
 +--------+    fan-out worker        +----v-----+
 | Kafka  |------------------------>| Redis    |
 | posts  |   (normal users only)    | feed:*   |
 +--------+                         +----------+
     |
     v
 fan-out: for each follower, ZADD feed:{follower_id} post_id
```

**Write path.** Insert post, publish to Kafka. Fan-out worker loads followers (paginated
keyset), for each follower with `< 100k` followers on their account... actually: if
*author* is not celebrity, `ZADD feed:{follower_id}`. Trim feed ZSET to 1000 entries.
If author `is_celebrity`, skip fan-out — followers merge at read time.

**Read path.**

1. `ZRANGE feed:{user_id} 0 19` → 20 post IDs.
2. If feed short or user follows celebrities, merge posts from celebrity followees
   (max 10 celebs × fetch recent 10 each = 100 extra IDs).
3. Batch load post bodies; apply ranking if not purely chronological.
4. Return with cursor.

**Twitter** historically used hybrid fan-out; **Meta** has published similar split between
normal and high-degree nodes.

### 6. Deep dives (10 min)

**Deep dive 1 — celebrity problem.** Threshold at 100k followers. Write fan-out for
50M followers = 50M Redis ops per post — minutes of work and hot keys. Read-time merge:
when user opens feed, fetch precomputed feed + `SELECT posts FROM celebrity_followees
WHERE created_at > ? LIMIT 50` — 10 queries for 10 celeb follows, acceptable at read time
because reads are cached and celeb follows are few per user.

**Deep dive 2 — ranking vs chronological.** Chronological = pure ZSET by timestamp.
Ranked = fetch candidate pool (200 posts), score by `w1*recency + w2*engagement + w3*affinity`,
return top 20. Ranking on read adds 20–50 ms — precompute scores in fan-out worker for
premium tier, or rank async and cache result for 60 s.

**Deep dive 3 — hot post.** Viral post liked 1M times — do not `UPDATE posts SET like_count`.
Counter in Redis `INCR likes:{post_id}`, flush to Postgres every 10 s. Feed hydration
reads counter from Redis.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| Fan-out worker lag | > 5 s to populate feeds | Scale consumers; shed: stop fan-out for inactive users (no login 30 days) |
| Redis memory | 300M feed keys | Only materialize feeds for MAU; cold users rebuild on read from follows |
| Thundering herd on celebrity post | millions read same post | CDN for media; post body cache with single-flight |
| Fan-out DB load | loading 10k followers per post | Cache follower lists; incremental fan-out checkpoints |

### 8. Trade-offs — the closing summary

> With a 1,500:1 read:write ratio I would precompute feeds for normal users (fan-out on
> write) and merge celebrity posts at read time. I would defend storing only post IDs in
> the feed cache and hydrating in one batch query. The metric I would watch is fan-out
> consumer lag — it is the user's "why don't I see my friend's post yet?" alarm.

### If they push further

**Q: Global feed vs following-only?**
Following-only for this design. Global/trending is a separate ranked stream (Redis ZSET
of trending post IDs, updated by engagement velocity).

**Q: Consistency when unfollowing?**
Remove followee's future posts from fan-out; lazy delete old post IDs from ZSET on read
filter, or async cleanup job.

---

## 15.7 Design a payment processing service

**Asked at:** Stripe, Square, fintech, e-commerce  **Time budget:** 45 min
**Tests you on:** idempotency, double-entry ledger, sagas, PCI boundaries, reconciliation.

### 1. Requirements (5 min)

Functional:

1. Charge a customer's payment method (card, wallet).
2. Refund full or partial.
3. Query payment status.
4. Webhooks to merchant on `payment.succeeded` / `payment.failed`.
5. Support multiple payment providers (Stripe, Adyen) with routing rules.

Non-functional:

- 10k merchants, 100k payments/day → ~1.2 payments/sec avg, 50/sec peak.
- Charge API p99 under 500 ms (provider-bound).
- **Exactly-once money movement** — no double charges (stronger than at-least-once).
- 99.99% availability on status reads; 99.95% on writes.
- PCI DSS: card data never touches our disks (tokenization).
- 7-year audit trail.

Out of scope: subscription billing engine, fraud ML, merchant onboarding KYC UI.

### 2. Estimation (5 min)

```
Payments   100k/day / 100,000 = 1/s avg → 50/s peak
```

Low QPS — **correctness over throughput**. Postgres handles this easily; the design is
about invariants, not sharding.

```
Ledger entries: 2 per payment (debit/credit) + refunds → 300k rows/day
Row ~200 B → 60 MB/day → 150 GB over 7 years (partitioned Postgres)
```

Provider API: 50 concurrent charges at 300 ms each = 150 in-flight — small connection pool.

### 3. API (5 min)

```
POST   /v1/payments                      charge (Idempotency-Key required)
GET    /v1/payments/{id}
POST   /v1/payments/{id}/refund
GET    /v1/payments/{id}/refunds
POST   /v1/webhooks/stripe               provider callbacks (internal)
```

```http
POST /v1/payments
Idempotency-Key: order-8842-charge-v1
Authorization: Bearer sk_live_...

{ "amount_cents": 4999,
  "currency": "usd",
  "payment_method": "pm_token_abc",    // tokenized — never PAN
  "merchant_id": "m_42",
  "metadata": { "order_id": "8842" } }

201 Created
{ "id": "pay_01J8...", "status": "processing" }

200 OK (retry same key)
{ "id": "pay_01J8...", "status": "succeeded" }   // same body, same response
```

States: `processing` → `succeeded` | `failed` | `requires_action` (3DS).

### 4. Data model (5 min)

```sql
CREATE TABLE payments (
  id              bytea PRIMARY KEY,
  merchant_id     bigint NOT NULL,
  idem_key        text NOT NULL,
  amount_cents    bigint NOT NULL,
  currency        char(3) NOT NULL,
  status          text NOT NULL,
  provider        text,
  provider_ref    text,
  created_at      timestamptz NOT NULL,
  UNIQUE (merchant_id, idem_key)
);

-- Append-only ledger — balances NEVER updated in place
CREATE TABLE ledger_entries (
  id            bigserial PRIMARY KEY,
  account       text NOT NULL,       -- merchant:42:available, platform:fees
  payment_id    bytea NOT NULL,
  amount_cents  bigint NOT NULL,     -- negative = debit
  currency      char(3) NOT NULL,
  entry_type    text NOT NULL,       -- charge|refund|fee
  created_at    timestamptz NOT NULL
);
CREATE INDEX ON ledger_entries (account, created_at);
```

Balance = `SUM(amount_cents) WHERE account = ?` — materialized view refreshed or cached
with ledger as source of truth.

Idempotency store: `(merchant_id, idem_key) → response_body` for 24 h minimum.

### 5. High-level architecture (10 min)

```
 merchant                payment service              providers
    |                          |                         |
    | POST /payments           |                         |
    v                          v                         |
 +--------+   idempotent    +--------+   token charge   +--------+
 | Merchant|--------------->| Payment |---------------->| Stripe |
 | app     |                | API     |<----------------| Adyen  |
 +--------+                 +----+----+   webhook         +--------+
                                 |
                    +------------+------------+
                    v            v            v
               Postgres      outbox       ledger
               (payments)   (webhooks)   (append)
```

**Write path (charge).**

1. Begin transaction.
2. Insert `payments` with `status=processing` OR return existing if idem hit.
3. Insert ledger entries (merchant pending + platform clearing) — still in same tx.
4. Commit.
5. Call provider API with `idempotency_key = payment.id` (provider-side dedup).
6. On success: update status, finalize ledger, write outbox row for merchant webhook.
7. On failure: compensating ledger entries, status `failed`.

Never call provider inside the DB transaction — hold locks too long. Order: persist
intent → call provider → persist outcome.

**Read path.** `GET /payments/{id}` from primary or replica; `processing` older than 5 min
→ reconciliation job queries provider by `provider_ref`.

### 6. Deep dives (10 min)

**Deep dive 1 — idempotency at three layers.**

1. API: `(merchant_id, Idempotency-Key)` unique — retries return same JSON.
2. Provider: pass same key to Stripe — they dedup for 24 h.
3. Webhook: provider events have unique `event_id` — insert before processing.

**Deep dive 2 — double-entry ledger.** Charge $49.99:

```
DEBIT  customer:pm_token     -4999  (conceptual — money leaves customer)
CREDIT merchant:42:pending   +4799  (after 4% fee)
CREDIT platform:fees         +200
```

Refund reverses with new entries, never DELETE. **Stripe** and every real processor
uses immutable ledger semantics internally.

**Deep dive 3 — sagas for partial failure.** Provider succeeds, our DB update crashes:

- Reconciliation worker polls provider by idempotency key every minute.
- Finds succeeded charge without local `succeeded` → complete ledger + webhook.
- Opposite: local `succeeded` but provider unknown → query provider before refunding.

**Deep dive 4 — PCI boundary.** Card numbers enter browser → Stripe.js Elements → token
`pm_xxx`. Our servers only see tokens. SAQ A scope. Never log request bodies containing
payment fields.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| Duplicate charge on retry | same idem key | Unique constraint + return cached response |
| Provider timeout | unknown state | Stay `processing`; reconcile; never auto-retry charge without idem key |
| Webhook before API response | race | Webhook handler idempotent on `payment_id`; order doesn't matter |
| Ledger imbalance | bug | Nightly `SUM(entries)` must net to zero per payment; alert on mismatch |
| 50 charges/s | peak | Still one Postgres primary; connection pool 50; provider rate limit is binding |

### 8. Trade-offs — the closing summary

> At 50 payments per second peak this is a correctness problem, not a scale problem: I
> would use Postgres with an append-only ledger and idempotency at the API and provider
> layers. I would defend never calling the provider inside a database transaction and
> running continuous reconciliation for indeterminate states. The metric I would watch is
> ledger imbalance alerts — money bugs are the ones that end careers.

### If they push further

**Q: How do you handle 3D Secure / SCA?**
Return `requires_action` with client secret; merchant frontend completes challenge;
webhook or poll completes payment. State machine must not skip steps.

**Q: Multi-currency?**
Store `amount_cents` + `currency` on every row; never convert in application floats;
ledger per currency account.

**Q: Scale to 10k payments/sec?**
Shard by `merchant_id`, outbox per shard, still append-only ledger per shard;
cross-shard reconciliation becomes batch ETL.

---

## 15.8 Design a distributed job scheduler / task queue

**Asked at:** infra, platform, backend-heavy companies  **Time budget:** 45 min
**Tests you on:** queue semantics, leases, at-least-once execution, fairness, cron vs delay.

### 1. Requirements (5 min)

Functional:

1. Submit one-off jobs (run now or at scheduled time).
2. Recurring/cron jobs.
3. Job payload + retry policy + timeout.
4. At-least-once execution; workers idempotent.
5. Cancel job before run; query status.
6. Priority queues (high/normal/low).

Non-functional:

- 10M jobs/day, 500 concurrent executions peak.
- Schedule accuracy ±1 second for cron.
- 99.9% scheduler availability.
- No duplicate execution for non-idempotent jobs (best-effort via leasing).
- Multi-tenant fair scheduling.

Out of scope: full workflow DAG engine (Airflow), GPU workload placement, job UI.

### 2. Estimation (5 min)

```
Jobs       10M/day / 100,000 = 100 enqueues/sec avg → 500 peak
Workers    500 concurrent × 30 s avg job = need 500 worker slots
           (CPU-bound vs IO-bound changes worker count, not scheduler design)
```

Scheduler metadata:

```
Job row ~1 KB; 10M/day × 1 KB = 10 GB/day
30-day retention = 300 GB Postgres with daily partitions
```

Heartbeat every 10 s on running jobs — 500 × 0.1 = 50 updates/sec, trivial.

### 3. API (5 min)

```
POST   /v1/jobs                    enqueue
GET    /v1/jobs/{id}               status
DELETE /v1/jobs/{id}               cancel if pending
POST   /v1/cron-jobs               register schedule
GET    /v1/cron-jobs/{id}
```

```http
POST /v1/jobs
{ "type": "send_report",
  "payload": { "user_id": 42 },
  "run_at": "2026-09-01T10:00:00Z",    // or null = now
  "priority": "high",
  "retry": { "max_attempts": 5, "backoff": "exponential" },
  "timeout_seconds": 300 }

202 Accepted
{ "job_id": "job_01J8...", "status": "pending" }
```

### 4. Data model (5 min)

```sql
CREATE TABLE jobs (
  id            bytea PRIMARY KEY,
  tenant_id     bigint NOT NULL,
  type          text NOT NULL,
  payload       jsonb NOT NULL,
  status        text NOT NULL,       -- pending|leased|running|succeeded|failed|cancelled
  priority      smallint NOT NULL,
  run_at        timestamptz NOT NULL,
  lease_owner   text,
  lease_until   timestamptz,
  attempt       smallint DEFAULT 0,
  created_at    timestamptz NOT NULL
);
CREATE INDEX jobs_ready ON jobs (priority DESC, run_at)
  WHERE status = 'pending' AND run_at <= now();

CREATE TABLE cron_jobs (
  id            uuid PRIMARY KEY,
  tenant_id     bigint,
  cron_expr     text NOT NULL,
  next_run_at   timestamptz NOT NULL,
  job_template  jsonb NOT NULL
);
```

Alternative at scale: Redis ZSET `schedule` score = `run_at` unix ms, member = job_id;
Postgres as source of truth, Redis as hot queue.

### 5. High-level architecture (10 min)

```
 clients                    scheduler tier              workers
    |                            |                         |
    v                            v                         v
 +--------+    jobs table   +----------+   lease      +----------+
 | API    |---------------->| Scheduler|-------------->| Worker   |
 +--------+                 | (leader + |   poll/claim | pool     |
                            |  tickers)|<--------------+----------+
                            +----------+   heartbeat
                                 |
                            +----+----+
                            | Kafka/  |
                            | SQS     |
                            +---------+
```

**Enqueue path.** API inserts `pending` row with `run_at`, returns 202. If `run_at` is
near, also ZADD to Redis schedule queue.

**Scheduler (leader-elected).** Every second:

1. `SELECT id FROM jobs WHERE status='pending' AND run_at <= now()
   ORDER BY priority DESC, run_at LIMIT 1000
   FOR UPDATE SKIP LOCKED` — see [Module 09](./09_Reliability_Patterns.md).
2. Publish claimed job IDs to priority topic.
3. Cron ticker: `UPDATE cron_jobs SET next_run_at = ... WHERE next_run_at <= now()`,
   insert child job rows.

**Worker path.** Pull from queue, `UPDATE jobs SET status='leased', lease_owner=?, lease_until=now()+30s WHERE id=? AND status='pending'` — if 0 rows updated, another worker got it. Execute with timeout. Success → `succeeded`. Failure → increment attempt, requeue with backoff or DLQ.

**Heartbeat.** Running job renews `lease_until` every 10 s. Sweeper marks `lease_until < now()` as `pending` for retry (orphan recovery).

### 6. Deep dives (10 min)

**Deep dive 1 — at-least-once vs exactly-once execution.** True exactly-once requires
distributed transactions with the side effect. Production answer: at-least-once + idempotent
workers (`job_id` in side-effect dedup table). Lease prevents *concurrent* duplicate;
crash after side effect but before ack → retry may duplicate — worker must handle.

**Deep dive 2 — leader election.** One scheduler leader computes cron fires to avoid
duplicate cron children. Use Postgres advisory lock, Redis `SET NX`, or etcd lease.
Followers standby; on leader death, new leader in < 30 s. Missed tick: catch-up next
minute, don't stack duplicates — `next_run_at` advances regardless.

**Deep dive 3 — fairness.** Per-tenant cap: max 50 concurrent jobs per tenant. Scheduler
query adds `WHERE tenant_id NOT IN (tenants at cap)`. Starvation prevention: aging —
boost priority by 1 every minute waiting.

**Deep dive 4 — comparison to Celery/Sidekiq.** Same primitives: broker, worker, visibility
timeout (= lease). **AWS SQS** visibility timeout is the managed version of `lease_until`.
Say that connection — interviewers recognize you know the managed service mapping.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| Scheduler leader dies | any | Failover < 30 s; SKIP LOCKED prevents double-claim |
| Worker dies mid-job | lease expires 30 s | Sweeper requeues; idempotent worker required |
| DB poll bottleneck | 10k ready jobs/s | Move ready queue to Redis; Postgres for durability only |
| Cron thundering herd | 0 * * * * for 1M jobs | Smear: `run_at += hash(cron_id) % 60` seconds |
| Poison job | always throws | Max attempts → DLQ; alert on DLQ depth |

### 8. Trade-offs — the closing summary

> I would persist jobs in Postgres for durability and audit, use `FOR UPDATE SKIP LOCKED`
> for claiming, and leases with a heartbeat sweeper for orphan recovery. I would defend
> at-least-once execution with idempotent workers rather than chasing exactly-once. The
> metric I would watch is job age p99 — time from `run_at` to `running` — because that
> is what users feel as "my report is late."

### If they push further

**Q: DAG dependencies?**
Separate orchestrator layer: each node is a job; edges stored in `job_dependencies`;
scheduler enqueues when all parents `succeeded`. That's Airflow territory.

**Q: 1M jobs scheduled for the same second?**
Don't `SELECT` 1M rows in one tick — batch claim 1000/s, Redis schedule queue as buffer,
scale workers horizontally.

---

## 15.9 Design a file upload & processing pipeline

**Asked at:** Dropbox-like, media, ML data ingest, document platforms  **Time budget:** 45 min
**Tests you on:** signed URLs, direct-to-storage upload, async processing, multipart, quotas.

### 1. Requirements (5 min)

Functional:

1. Upload files up to 5 GB (images, PDFs, video).
2. Async processing: virus scan, thumbnail, metadata extraction, transcription.
3. Download via signed URL; access control per owner/tenant.
4. List/delete files; storage quota per user.
5. Processing status API.

Non-functional:

- 1M users, 10 uploads/user/day = 10M uploads/day.
- Upload initiation p99 under 200 ms (bytes do not pass API).
- Processing complete within 5 minutes for files under 100 MB.
- 99.9% durability (GCS/S3 standard).
- Per-user quota 50 GB default.

Out of scope: collaborative editing, version diff UI, client-side encryption.

### 2. Estimation (5 min)

```
Uploads    10M/day / 100,000 = 100/sec avg → 300/sec peak
Avg size   2 MB → 20 TB/day ingest bandwidth (to object storage, not API)
           10M × 2 MB = 20 TB/day storage growth
```

API servers see metadata only — **no bytes through the app tier**.

Processing workers:

```
100 MB file, virus scan + thumbnail = ~10 s CPU
300 uploads/s × 10 s / 60 workers per machine ≈ 50 machines at peak (autoscaled)
```

### 3. API (5 min)

```
POST   /v1/files/initiate              returns signed upload URL + file_id
POST   /v1/files/{id}/complete         client signals upload done
GET    /v1/files/{id}                  metadata + processing status
GET    /v1/files/{id}/download-url     signed GET URL
GET    /v1/files?cursor=               list
DELETE /v1/files/{id}
```

```http
POST /v1/files/initiate
{ "filename": "report.pdf", "size_bytes": 2400000, "content_type": "application/pdf" }

200 OK
{ "file_id": "f_01J8...",
  "upload_url": "https://storage.googleapis.com/bucket/...?X-Goog-Signature=...",
  "upload_method": "PUT",
  "expires_in": 3600 }
```

Multipart for > 100 MB: initiate returns `upload_id` + part URLs; complete with ETags.

### 4. Data model (5 min)

```sql
CREATE TABLE files (
  id            bytea PRIMARY KEY,
  owner_id      bigint NOT NULL,
  tenant_id     bigint NOT NULL,
  filename      text NOT NULL,
  size_bytes    bigint NOT NULL,
  content_type  text,
  storage_key   text NOT NULL,         -- gcs path
  status        text NOT NULL,         -- uploading|processing|ready|failed|deleted
  quota_bytes   bigint,                -- snapshot at upload time
  created_at    timestamptz NOT NULL
);
CREATE INDEX files_owner ON files (owner_id, created_at DESC);

CREATE TABLE processing_jobs (
  file_id     bytea PRIMARY KEY,
  steps       jsonb,                   -- [{name, status, error}]
  updated_at  timestamptz
);
```

Object storage: `gs://bucket/{tenant_id}/{file_id}/{filename}` — salt prefix if > 3k PUT/s
per prefix (see [Module 07](./07_Caching_And_CDN.md)).

Redis: `quota:{user_id}` → bytes used (updated on complete, reconciled nightly).

### 5. High-level architecture (10 min)

```
 client                         object storage
   |  initiate (metadata)              ^
   v                                 | PUT bytes (signed URL)
 +--------+                           |
 | API    |---------------------------+
 +---+----+
     | insert status=uploading
     v
 GCS event (OBJECT_FINALIZE)  or  client POST /complete
     |
     v
 +----------+    +------------------+
 | Pub/Sub  |--->| Processing       |
 |          |    | workers          |
 +----------+    | (scan, thumb,    |
                 |  extract)        |
                 +--------+---------+
                          v
                    update status=ready
```

**Write path.** API checks quota (`quota_used + size <= limit`), inserts row
`uploading`, returns presigned PUT URL (1 h TTL). Client uploads direct to GCS. GCS
notification → Pub/Sub → processing pipeline. On success, `status=ready`, decrement
pending quota reservation. On virus hit, delete object, `status=failed`, alert user.

**Read path.** `GET /download-url` verifies ACL, returns signed GET URL (15 min TTL).
Optional CDN in front for public assets.

### 6. Deep dives (10 min)

**Deep dive 1 — upload reliability.** Client retries PUT on 5xx. Idempotent: same
`file_id` + same storage key. Multipart: client tracks completed parts; `complete`
assembles — GCS/S3 native API. Stale `uploading` > 24 h → lifecycle rule deletes orphan
objects + row marked `abandoned`.

**Deep dive 2 — processing pipeline.** Chain as separate Pub/Sub topics or one worker
with step state machine:

```
virus_scan → (fail: stop) → thumbnail → metadata → transcribe (if video)
```

Each step updates `processing_jobs.steps`. Partial failure: retry step 3×, then `failed`
with reason. **Dropbox**-class systems use similar async pipelines; API never blocks on scan.

**Deep dive 3 — quota enforcement.** Soft check at initiate (cached `quota_used`); hard
check at complete after size verified from object metadata. Race: two initiates could
overshoot — reserve quota at initiate with TTL, confirm at complete, release on abandon.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| Hot prefix on GCS | > 3,500 PUT/s | Hash prefix: `{hash(file_id)[0:2]}/{file_id}` |
| Giant file blocks worker | 5 GB video | Dedicated long-running worker pool; step timeout per stage |
| Malware in object | any | Scan before `ready`; block download URLs until scan passes |
| Quota drift | cache vs truth | Nightly reconciliation `SUM(size) FROM files` per user |
| Orphan objects | client never completes | Lifecycle delete after 24 h; metric on abandon rate |

### 8. Trade-offs — the closing summary

> I would never route file bytes through the API — presigned URLs to object storage with
> GCS notifications driving an async processing pipeline. I would defend quota reservation
> at initiate and virus scan before marking `ready`. The metric I would watch is
> processing lag p95 — time from `OBJECT_FINALIZE` to `ready` — because that is the
> user's "why is my file still processing?" experience.

### If they push further

**Q: Resumable uploads?**
Multipart with client-held state; server tracks completed part ETags; resume from last
part. tus.io protocol if they want standard.

**Q: Cross-region users?**
Upload to nearest region bucket; metadata in global Postgres or region-local with
replication; processing in same region as object to avoid egress.

---

## 15.10 Design a multi-tenant RAG / AI document Q&A platform

**Asked at:** AI-native startups, enterprise SaaS adding copilots  **Time budget:** 45 min
**Tests you on:** tenant isolation, ingestion pipeline, vector scale, LLM gateway, cost,
eval. This is your differentiator — go deep.

### 1. Requirements (5 min)

Functional:

1. Tenants upload documents (PDF, DOCX, HTML); system indexes for Q&A.
2. Chat interface: natural language question → grounded answer with citations.
3. Document management: list, delete, re-index on update.
4. Per-tenant API keys and usage limits.
5. Admin: view query logs, feedback thumbs up/down.

Non-functional:

- 5,000 tenants, 10k documents/tenant avg, 50 pages/doc.
- 100 queries/tenant/day = 500k queries/day ≈ 6 QPS avg, 30 QPS peak.
- Query p95 under 8 s (retrieval + LLM).
- **Hard tenant isolation** — no cross-tenant data leakage.
- 99.9% availability on query API.
- Cost target: under $0.05 per query at scale.

Out of scope: fine-tuning custom models, autonomous agents with tool use, on-prem GPU
deployment — mention as enterprise tier.

### 2. Estimation (5 min)

```
Corpus per tenant: 10k docs × 50 pages × 500 tokens = 250M tokens
Total (5k tenants): 1.25T tokens — but tenants are isolated; index per tenant

Chunks: 500 tokens/chunk, 20% overlap → ~1.2 chunks/page × 50 × 10k = 600k chunks/tenant
5k tenants × 600k = 3B chunks total (upper bound; many tenants smaller)

Embedding: 3B × 1536 dims × 4 B = ~18 TB vector data (the binding storage cost)
Queries: 500k/day — throughput is NOT the problem; latency and cost are.
```

Cost per query (order of magnitude):

```
Embed query:     500 tokens × $0.02/1M ≈ $0.00001
Retrieve:        vector DB negligible at this QPS
LLM generation:  2k input + 500 output × GPT-4o-mini-class ≈ $0.002–0.01
Total target:    $0.01 with caching; semantic cache hits save 30–50%
```

### 3. API (5 min)

```
POST   /v1/documents/upload-url          presigned upload (same as 15.9)
POST   /v1/documents/{id}/ingest         trigger re-index
GET    /v1/documents?cursor=
DELETE /v1/documents/{id}
POST   /v1/chat/completions              RAG query (OpenAI-compatible shape)
GET    /v1/usage                         tokens/queries this month
```

```http
POST /v1/chat/completions
Authorization: Bearer tenant_sk_...
X-Request-Id: req_9f2a...

{ "messages": [{ "role": "user", "content": "What is our refund policy?" }],
  "stream": true,
  "filters": { "document_ids": ["doc_1", "doc_2"] } }

data: {"delta": "Our refund policy allows..."}
data: {"citations": [{"doc_id": "doc_1", "page": 4, "snippet": "..."}]}
data: [DONE]
```

### 4. Data model (5 min)

```sql
CREATE TABLE tenants (
  id              bigint PRIMARY KEY,
  api_key_hash    bytea NOT NULL,
  plan            text,
  monthly_quota   bigint
);

CREATE TABLE documents (
  id            bytea PRIMARY KEY,
  tenant_id     bigint NOT NULL,
  title         text,
  storage_key   text,
  status        text,              -- ingesting|ready|failed
  chunk_count   int,
  created_at    timestamptz
);
CREATE INDEX ON documents (tenant_id, created_at DESC);
-- RLS: SET app.tenant_id per request; policy tenant_id = current_setting(...)
```

Vector store (per-tenant namespace or metadata filter):

```
chunk_id, tenant_id, document_id, page, embedding[1536], text
```

**Every query includes `tenant_id` filter** — non-negotiable. Prefer separate index
collections per tenant for enterprise tier (physical isolation).

Postgres: `query_logs (tenant_id, request_id, question_hash, latency_ms, tokens, feedback)`.

Redis: semantic cache `sem:{tenant_id}:{hash(embed(query))}` → answer + citations, TTL 1 h.

### 5. High-level architecture (10 min)

```
 upload                         query path
    |                               |
    v                               v
 +--------+   GCS    +-----------+  +----------+   +-------------+
 | Upload |--------->| Ingest    |  | Query    |-->| LLM       |
 | API    |          | pipeline  |  | API      |   | Gateway   |
 +--------+          | chunk+emb |  +----+-----+   +------+------+
                     +-----+-----+       |               |
                           |             v               v
                     +-----v-----+  +----------+   +----------+
                     | Vector DB |  | Hybrid   |   | OpenAI / |
                     | (per      |  | retrieve |   | Vertex   |
                     |  tenant)  |  +----------+   +----------+
                     +-----------+
```

**Ingest path.** Upload → object storage → Pub/Sub → extract text (PyMuPDF/unstructured),
chunk with 500-token windows and 100-token overlap, embed via batch API (save cost),
upsert vectors with `tenant_id` + `document_id` metadata, mark `ready`.

**Query path.**

1. Auth: API key → `tenant_id`; rate limit per tenant.
2. Semantic cache lookup.
3. Embed question.
4. Hybrid retrieve: vector top-20 + BM25 top-20 → merge → rerank top-5.
5. Build prompt: system + context chunks + user question (cite sources).
6. Stream LLM response; log tokens; return citations.

See [Module 14](./14_AI_LLM_System_Design.md) for chunking, hybrid search, and gateway patterns.

### 6. Deep dives (10 min)

**Deep dive 1 — tenant isolation.** Three levels:

1. **Application:** `tenant_id` from auth context, never from client body.
2. **Database:** Postgres RLS; vector queries mandatory filter `tenant_id = ?`.
3. **Enterprise:** dedicated vector collection + encryption key per tenant (CMEK).

Run quarterly pen test: "retrieve with wrong tenant_id" must return zero results.

**Deep dive 2 — ingestion at scale.** Batch embeddings: 100 chunks/request to embedding
API. Backpressure: ingest queue depth per tenant; free tier max 100 docs/day. Delete path:
remove vectors by `document_id` filter, then object + row.

**Deep dive 3 — LLM gateway.** Central service: model routing, API keys, token counting,
fallback model on 429, prompt injection guard (input length cap, block "ignore previous
instructions" patterns — defense in depth, not foolproof). Reserve `max_tokens` at
admission; settle actual after stream completes (same as rate limiter two-phase charge).

**Deep dive 4 — eval and quality.** Offline: golden Q&A set per tenant template; recall@5
on retrieval weekly. Online: thumbs down → queue for review; track groundedness (answer
supported by citation chunk). **Glean** and **Notion Q&A**-class products invest heavily
in retrieval eval — mention that hiring managers care about eval, not just RAG wiring.

**Deep dive 5 — cost control.** Semantic cache, smaller model for simple queries
(classifier routes 70% to mini), summarize long contexts before LLM, per-tenant monthly
cap with 402 response.

### 7. Failure modes & scale

| What breaks | At what number | What I do |
|---|---|---|
| Cross-tenant leak | any bug | RLS + integration tests + mandatory tenant filter in vector SDK wrapper |
| Ingest backlog | large PDF | Per-tenant fair queue; 500-page doc split across workers |
| LLM 429 | provider rate limit | Exponential backoff, fallback model, queue with SLA message |
| Stale index | doc updated | Version `document_id`; delete old vectors before upsert new |
| Hallucination | user trust | Require citations; system prompt "answer only from context"; abstain if low score |
| Cost overrun | tenant abuse | Per-tenant token budget; alert at 80%; hard stop at 100% |

### 8. Trade-offs — the closing summary

> At 30 QPS peak this is a retrieval-quality and tenant-isolation problem, not a
> throughput problem. I would use presigned uploads, async ingest with batched embeddings,
> hybrid search with reranking, and an LLM gateway for routing and cost control. I would
> defend physical or logical per-tenant vector isolation and mandatory citation in
> responses. The metrics I would watch are retrieval recall@5 on golden sets and cost
> per query — quality and unit economics, not CPU.

### If they push further

**Q: On-prem / data residency?**
Deploy ingest + vector + LLM in customer VPC; sync only anonymized telemetry out. Use
local model (Llama) for generation; same architecture, different endpoint.

**Q: Real-time collaborative docs?**
CDC from editor → debounced re-chunk (30 s) → partial re-embed changed chunks only.

**Q: Agent with tools (search + calculator + API)?**
Orchestrator loop above RAG; each tool call audited; step budget max 5 to control cost.

---

## How to practise these

Reading Module 15 is not preparation. Use this drill loop for each case study:

### The 45-minute paper drill

1. **Blank paper.** Write the prompt at the top (e.g. "Design a webhook delivery system").
2. **Set a timer for 45 minutes.** No notes, no looking at the module.
3. **Follow the budget** from the top of this file: requirements → estimate → API →
   schema → diagram → two deep dives → failure table → closing three sentences.
4. **Stop at 45** even if unfinished — time management is part of the grade.
5. **Diff against the module.** Mark gaps in red. Reread only those sections.
6. **Redo the same problem in 3 days** — you should finish 5 minutes early with a
   cleaner diagram.

### The out-loud drill (20 minutes)

Pick one case study. Read only the **Requirements** section, then close the file and
deliver the rest spoken, recording yourself. Listen for: silence > 10 s, missing numbers,
unjustified technology choices, no failure modes.

### The build drill (one weekend each)

You cannot fake having operated something:

| Case study | Minimal build |
|------------|---------------|
| 15.1 URL shortener | Redis cache-aside + redirect in FastAPI |
| 15.2 Rate limiter | Token bucket Lua script in Redis |
| 15.3 Notifications | Kafka consumer + DLQ after 3 retries |
| 15.4 Webhooks | Outbound HTTP worker with HMAC signature |
| 15.5 Chat | WebSocket echo + Redis pub/sub between two tabs |
| 15.6 Feed | Fan-out on write into Redis ZSET |
| 15.7 Payments | Idempotent POST + append-only ledger table |
| 15.8 Scheduler | `SKIP LOCKED` job claim in Postgres |
| 15.9 File pipeline | Presigned GCS upload + Pub/Sub handler |
| 15.10 RAG | Chunk PDF, embed, retrieve top-5, stream answer |

Break one thing on purpose: kill Redis, send duplicate idempotency keys, fill the DLQ.
The failure story is what separates mid-level from senior in the interview room.

### Rotation schedule

| Week | Case studies | Module review |
|------|--------------|---------------|
| 1 | 15.1, 15.2 | 05, 07, 09 |
| 2 | 15.3, 15.4 | 03, 08, 09 |
| 3 | 15.5, 15.6 | 02, 04, 06 |
| 4 | 15.7, 15.8 | 05, 09, 11 |
| 5 | 15.9, 15.10 | 07, 14 |

Then cycle all ten again with stricter time limits (40 minutes, then 35).

---

## Module 15 — self-test

Answer out loud, without notes. If you stumble, reread that case study.

1. URL shortener: why batched counter with scramble instead of Snowflake?
2. Rate limiter: why fail open by default, and when fail closed?
3. Notifications: why separate topics per priority class?
4. Webhooks: what is the subscriber's responsibility for idempotency?
5. Chat: why partition Kafka by `conversation_id`?
6. Feed: how do you handle a user with 50M followers?
7. Payments: why never call the provider inside a DB transaction?
8. Scheduler: what does `FOR UPDATE SKIP LOCKED` buy you?
9. File upload: why do bytes never pass through the API tier?
10. RAG platform: name three layers of tenant isolation.

---

## Key numbers from this module

| Case study | Number to remember |
|------------|-------------------|
| 15.1 URL shortener | 30k peak redirects/s; 300 writes/s |
| 15.2 Rate limiter | 1M decisions/s; 90% local buckets |
| 15.3 Notifications | 25k peak pipeline/s; $125k+/day SMS risk |
| 15.4 Webhooks | 5k events/s peak; 3-day retry window |
| 15.5 Chat | 500k messages/s; 100M concurrent WS |
| 15.6 Feed | 5M feed reads/s; hybrid fan-out |
| 15.7 Payments | 50 charges/s peak; ledger is append-only |
| 15.8 Scheduler | 500 concurrent jobs; 1 s cron accuracy |
| 15.9 File pipeline | 300 uploads/s; 5 GB max file |
| 15.10 RAG | 30 QPS peak; $0.05/query cost target |

---

**Next:** [Module 16 — Cheat Sheet, Numbers & Study Plan](./16_Cheatsheet_And_Drills.md)
