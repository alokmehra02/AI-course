# Module 00 — The Interview Playbook

> **What this module makes you able to do:** Walk into any 45-minute system design
> interview, drive the conversation yourself, and cover the full territory without
> freezing or rambling.
>
> **Interview weight:** ★★★★★ — this is the only module that is useful in *every*
> interview regardless of the question.
>
> **Prerequisites:** None. Read this first, reread it the night before.

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 0.1 | What is actually being scored | ★★★★★ |
| 0.2 | The 6-step framework with time budgets | ★★★★★ |
| 0.3 | Step 1 — Clarify requirements | ★★★★★ |
| 0.4 | Step 2 — Estimate scale | ★★★★★ |
| 0.5 | Step 3 — Define the API | ★★★★☆ |
| 0.6 | Step 4 — Design the data model | ★★★★★ |
| 0.7 | Step 5 — High-level architecture | ★★★★★ |
| 0.8 | Step 6 — Deep dive and stress test | ★★★★★ |
| 0.9 | Closing: the trade-off summary | ★★★★☆ |
| 0.10 | Whiteboard layout | ★★★☆☆ |
| 0.11 | The bar at your level | ★★★★★ |
| 0.12 | Recovery moves when you are stuck | ★★★★☆ |

---

## 0.1 What is actually being scored

> **One-liner:** The interviewer is not checking whether you know Kafka; they are
> checking whether you can turn a vague sentence into a defensible system.

### Say this in the interview

You do not say this one out loud. It is the frame you hold in your head.

### Mental model

Almost every system design rubric reduces to five signals. Every minute you spend
should be producing evidence for one of them.

| Signal | What it looks like | What its absence looks like |
|---|---|---|
| **Requirements discipline** | You ask before you draw | You start with boxes |
| **Quantitative reasoning** | "That's 3,500 QPS at peak, so one Postgres primary is fine" | "It needs to be scalable" |
| **Justified choices** | "Postgres, because we need multi-row transactions on orders" | "I'll use Cassandra because it scales" |
| **Failure thinking** | "If the cache dies, we take 100% of reads to the DB — that's 40k QPS, so I need request coalescing" | Happy path only |
| **Communication** | Interviewer always knows where you are | They have to interrupt to follow |

The single biggest failure mode is well documented: roughly half of failed interviews
trace to **drawing the architecture before clarifying requirements**. It is not that the
architecture is wrong. It is that an unscoped design cannot be evaluated, so the
interviewer has nothing to grade.

The second biggest is **silence**. An unnarrated diagram is worth almost nothing. You
are being hired partly for how you reason in front of other engineers.

### Red flags — do not say this

- ❌ "Let's use microservices, Kafka, Redis and Kubernetes." → ✅ "Let me first understand the read/write ratio, because that determines whether this is a caching problem or a sharding problem."
- ❌ Silence for 90 seconds while you think. → ✅ "Give me ten seconds — I'm deciding whether to fan out on write or on read here."

---

## 0.2 The 6-step framework with time budgets

> **One-liner:** Six steps, strict clock, and you announce each transition out loud.

### Say this in the interview

> "Let me lay out how I'll use the time. I'll spend about five minutes on requirements
> and scope, five on rough numbers, five on the API and data model, fifteen on the
> high-level architecture, and I'd like to leave ten or so for a deep dive on whichever
> part you find most interesting. Does that work, or would you rather I go deep
> somewhere specific?"

That opening does three things: it shows structure, it hands the interviewer control
over the deep dive (they always have one in mind), and it buys you permission to move
on when you are running long.

### Mental model

```text
 0 ────5────10───15───20───25───30───35───40───45 min
 │     │              │         │         │      │
 │  1. CLARIFY        │         │         │      │
 │     │  2. ESTIMATE │         │         │      │
 │     │     │ 3. API + 4. DATA MODEL     │      │
 │     │     │        │  5. HIGH-LEVEL    │      │
 │     │     │        │         │ 6. DEEP DIVE   │
 │     │     │        │         │         │ WRAP │
 └─────┴─────┴────────┴─────────┴─────────┴──────┘
   5m     5m      5m       15m       10m      5m
```

The steps are not a script to recite; they are scaffolding so that under stress you
always know what the next sentence is. Each step feeds the next: requirements constrain
the estimate, the estimate sizes the architecture, the architecture reveals what is
worth a deep dive.

**Variant — Meta-style product questions** ("design Instagram"): move the data model
*ahead* of the architecture. Their rubric weights domain modelling heavily.

**Variant — infra/backend questions** ("design a rate limiter", "design a job
scheduler"): compress requirements to three minutes and spend the surplus on the deep
dive. These questions are mostly deep dive.

### Follow-ups they will ask

**Q: Should I really spend 10 minutes before drawing anything?**
A: Yes, and say why you are doing it. "I want to pin the scale down first, because a
design for 1,000 QPS and a design for 100,000 QPS are different systems and I don't
want to over-build." That sentence alone reads as senior.

---

## 0.3 Step 1 — Clarify requirements (5 min)

> **One-liner:** Turn a one-sentence prompt into a written, bounded, numeric spec.

### Say this in the interview

> "Before I design anything, I want to pin down scope. I'll separate this into what the
> system does and how well it has to do it, and I'll write both on the board so we're
> working from the same spec.
>
> On the functional side, I'm assuming the core flows are [X, Y, Z]. I'm going to
> explicitly leave [A and B] out of scope unless you want them — I'd rather design three
> things properly than eight things vaguely.
>
> On the non-functional side, the numbers I care about most are scale, the read/write
> ratio, the latency target, and how much staleness is acceptable. Do you have numbers
> in mind, or should I propose some and you correct me?"

That last sentence is the highest-leverage line in the whole interview. Interviewers
frequently do not have numbers prepared. Proposing your own and getting them ratified
means *you* set the constraints you then design against.

### Mental model

Ask in this order. Stop at five or six questions — this is a conversation, not an
intake form.

**Functional — what does it do?**
1. Who are the actors? (end users, internal services, admins, batch jobs)
2. What are the three core operations? Force a ranking.
3. What is explicitly out of scope?

**Non-functional — how well?**
4. Scale: how many users, and how many are active per day?
5. Read/write ratio? *(This one question decides more of your design than any other.
   100:1 read-heavy means caching and replicas. 1:1 means the write path is the problem.)*
6. Latency target, stated as a percentile: "p99 under 200 ms" not "fast".
7. Consistency: if a user writes and immediately reads, must they see their own write?
   Must other users?
8. Availability target, and what happens during a partial outage — degrade or reject?
9. Data retention and deletion requirements.

**The scoping move.** Whatever the prompt, cut it down:

> "Design Twitter" → "I'll design post creation, the home timeline, and follow, at
> 100 million DAU. I'll leave search, DMs, ads and trending out unless you'd rather I
> cover one of those."

### Enterprise production example

**Scenario (not a claim about a named company).** A recruitment-tech team is asked to
"add SMS reminders". The naive spec is "send an SMS before the interview". The real spec
that emerged after clarification: 40,000 reminders/day clustered into two 30-minute
spikes (9:00 and 14:00 local time), across 14 timezones, with a hard requirement that a
candidate never receives a duplicate, and a soft requirement that a reminder is useless
if delivered more than 10 minutes late.

Those four facts change everything: the spikes force a queue rather than a cron loop,
the timezones force a scheduling index rather than a single daily job, "never duplicate"
forces idempotency keys, and "useless after 10 minutes" means messages should be dropped
rather than retried forever. None of that is visible in the original one-line request.

### The output on the board

```text
FUNCTIONAL                          NON-FUNCTIONAL
1. POST /shorten  (create)          Scale:      100M URLs, 100M DAU
2. GET  /{code}   (redirect)        Read:Write  100 : 1
3. Analytics on click               Latency:    p99 < 100 ms (redirect)
                                    Avail:      99.99% read, 99.9% write
OUT OF SCOPE                        Consistency: eventual OK for analytics,
- custom domains                                 read-your-write for creates
- user accounts / auth              Retention:  5 years
```

Leave that on the board for the whole interview. You will refer back to it, and it
signals discipline every time the interviewer's eye passes over it.

### Follow-ups they will ask

**Q: The interviewer says "you decide" to every question. Now what?**
A: Decide, out loud, with a reason, and mark it as an assumption. "I'll assume 10 million
DAU — that's large enough to force real distributed design but small enough that I don't
need multi-region. I'll flag it if that assumption changes anything material." Then move.

**Q: How do I know when to stop asking?**
A: When further answers would not change a design decision. Say exactly that: "I think I
have enough to start — the remaining unknowns don't change the shape of the system."

### Red flags — do not say this

- ❌ "It should be highly available and scalable." → ✅ "99.9% availability on the write path, 99.99% on reads, and it has to hold 3,000 QPS at peak."
- ❌ Asking fifteen questions and burning twelve minutes. → ✅ Six questions, then design.

---

## 0.4 Step 2 — Estimate scale (5 min)

> **One-liner:** Convert users into QPS, bytes and machines, so that every later choice
> is arithmetic rather than opinion.

### Say this in the interview

> "Let me get rough numbers so we're not guessing later. I'm going to round aggressively
> — I want the order of magnitude, not accuracy.
>
> There are about 100,000 seconds in a day, which makes the QPS math easy. Ten million
> daily active users doing ten reads a day is 100 million reads, so roughly 1,000 reads
> per second on average. I'll assume peak is three times average, so 3,000 QPS. That
> matters, because 3,000 QPS of simple key lookups is comfortably one cached Postgres
> primary — I don't need to shard yet, and I'd be over-engineering if I did."

The point of the estimate is not the number. It is the *conclusion* you draw from it.
Always finish an estimate with "…so that means I do / don't need X."

### Mental model — the estimation pipeline

Run it in this fixed order every time:

```text
   DAU
    │  × actions per user per day
    ▼
 requests/day
    │  ÷ 100,000  (seconds in a day, rounded)
    ▼
 average QPS
    │  × 2 to 3   (peak factor; higher if there's a daily spike)
    ▼
 peak QPS ──────────────► how many app servers? which DB?
    │
    │  writes/day × bytes per record
    ▼
 storage/day ──► × 365 × years ──► total storage ──► shard or not?
    │
    │  QPS × payload size
    ▼
 bandwidth ────────────────────► CDN? egress cost?
    │
    │  20% of data serves 80% of traffic
    ▼
 cache size ───────────────────► how much Redis?
```

### The constants to memorize

| Thing | Value | Why it matters |
|---|---|---|
| Seconds in a day | ~100,000 (86,400) | Makes all QPS math mental arithmetic |
| Seconds in a month | ~2.5 million | Monthly totals |
| 2^10 / 2^20 / 2^30 / 2^40 | KB / MB / GB / TB | Storage conversions |
| UUID | 16 bytes raw, 36 chars as text | Key sizing |
| int64 / timestamp | 8 bytes | Row sizing |
| One char of ASCII | 1 byte | Text sizing |
| Typical DB row | 100 B – 1 KB | Storage per record |
| Tweet-sized text | ~200 bytes | Text records |
| Compressed web page | ~100 KB – 1 MB | Bandwidth |
| Mobile photo | ~1–5 MB | Media storage |
| Minute of 1080p video | ~50 MB | Media storage |
| One LLM token | ~4 chars ≈ 0.75 words | Token/cost math (Module 14) |

### Worked example — URL shortener

```text
ASSUMPTIONS (state these out loud)
  100 M new URLs per month
  read : write = 100 : 1
  retention 5 years
  each row ≈ 500 bytes (short code, long URL, user, timestamps)

WRITES
  100 M / month ÷ 2.5 M sec  ≈  40 writes/sec average
  peak ×3                    ≈  120 writes/sec        → trivially one primary

READS
  40 × 100                   ≈  4,000 reads/sec average
  peak ×3                    ≈  12,000 reads/sec      → needs a cache

STORAGE
  100 M × 500 B              =  50 GB/month
  × 12 × 5                   =  3 TB over 5 years     → one node, no sharding

CACHE (80/20)
  daily reads   4,000 × 100,000     ≈ 400 M/day
  20% of keys serve 80% of reads
  hot set ≈ 20% × (daily unique URLs)  ≈ a few GB     → one Redis instance

CONCLUSION
  "3 TB and 12k peak QPS. This is a read-heavy caching problem, not a sharding
   problem. Single Postgres primary with read replicas, Redis in front, and I'd
   revisit sharding past ~10 TB or if writes go 10x."
```

That final paragraph is what earns the marks. Deep-dive coverage of the arithmetic and
more worked examples are in [Module 01 §1.9](./01_Requirements_And_NFRs.md).

### Follow-ups they will ask

**Q: My arithmetic is off by 3x. Does that matter?**
A: No. Order of magnitude is the whole point, and interviewers know it. Say "call it
ten thousand QPS, order of magnitude" and keep moving. What *does* hurt is being off by
1000x and not noticing, because it means you have no feel for scale.

**Q: Can I skip estimation?**
A: Only if you say so explicitly and give the reason: "The scale here doesn't change the
design — at 500 QPS this is a single-server CRUD app — so I'll skip the arithmetic unless
you want it." Skipping silently reads as inability.

### Red flags — do not say this

- ❌ Doing long division to three decimal places. → ✅ "Round it to 100,000 seconds — call it a thousand QPS."
- ❌ Producing numbers and never using them. → ✅ "…so 3 TB, which is why I'm *not* sharding."

---

## 0.5 Step 3 — Define the API (5 min)

> **One-liner:** Three to five endpoints with real request and response shapes, because
> the contract forces you to decide what the system actually does.

### Say this in the interview

> "Let me sketch the API surface — it forces the data contract before I start drawing
> boxes. I'll do REST here since this is a public client-facing service; internally I'd
> use gRPC between services for the lower latency and the generated clients.
>
> The interesting one is the write, so let me show its shape. Note the idempotency key —
> this is a create endpoint over an unreliable network, so the client generates a UUID
> and I dedupe on it. That way a client retry after a timeout can't double-create."

### Mental model

Show only the interesting endpoint in full. List the rest as one-liners.

```http
POST /v1/shorten
Idempotency-Key: 7c9e6679-7425-40de-944b-e07fc1f90ae7
Authorization: Bearer <token>

{ "url": "https://example.com/very/long/path", "ttl_days": 365 }

201 Created
{ "code": "aX9k2Q", "short_url": "https://sho.rt/aX9k2Q",
  "expires_at": "2027-09-01T00:00:00Z" }

GET  /{code}            → 302 Location: <long url>
GET  /v1/links?cursor=  → paginated list  (cursor, not offset — see Module 03 §3.3)
GET  /v1/links/{code}/stats
```

The details that earn points here, and each one is a hook the interviewer can pull on:

- **Idempotency key** on every create → you have thought about retries.
- **Cursor pagination**, never offset → you have thought about scale.
- **Versioned path** (`/v1/`) → you have thought about evolution.
- **302 vs 301** for the redirect → 301 is cached by browsers forever and kills your
  analytics; 302 keeps every click coming back to you. Mentioning this unprompted is a
  strong signal.

### Follow-ups they will ask

**Q: Why REST and not GraphQL?**
A: "The access pattern here is a small number of fixed, high-volume operations, and I
want HTTP caching on the redirect path — that's REST's strength. GraphQL earns its
complexity when clients need varied data shapes from many related resources, which isn't
the case here."

---

## 0.6 Step 4 — Design the data model (5 min)

> **One-liner:** Tables, keys, and indexes — chosen from the access patterns you just
> wrote down, not from habit.

### Say this in the interview

> "I'll derive the schema from the access patterns rather than from the entities. The
> dominant query is lookup-by-code at twelve thousand QPS, so `code` is the primary key
> and everything else is secondary. Creation is only a hundred and twenty writes a
> second, so I can afford a secondary index on `user_id` for the list endpoint.
>
> I'd put this in Postgres. Not because it's the biggest hammer — because I need a unique
> constraint on the short code to make creation safe under concurrency, and a unique index
> gives me that for free. That constraint is doing real work: it's what makes the
> idempotency guarantee true rather than aspirational."

### Mental model

State four things for each store, in this order:

1. **The store and why** — one sentence tying it to a requirement.
2. **The schema** — columns, types, primary key.
3. **The indexes** — and the specific query each one serves.
4. **The growth** — rows per day, and when the table becomes a problem.

```sql
CREATE TABLE links (
    code         VARCHAR(8)  PRIMARY KEY,     -- lookup path, 12k QPS
    long_url     TEXT        NOT NULL,
    user_id      BIGINT      NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at   TIMESTAMPTZ
);

-- serves GET /v1/links for a user, newest first, keyset-paginated
CREATE INDEX idx_links_user_created ON links (user_id, created_at DESC);

-- idempotency: one row per (user, key); the constraint IS the guarantee
CREATE TABLE idempotency_keys (
    user_id     BIGINT      NOT NULL,
    key         UUID        NOT NULL,
    response    JSONB       NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, key)
);
```

Then say the growth line: "100 million rows a month, 6 billion over five years at 500
bytes each — 3 TB. Postgres handles that on one node with partitioning by `created_at`.
I'd shard by `code` hash if we ever went 10x."

### Follow-ups they will ask

**Q: Why not DynamoDB — this is a pure key-value lookup?**
A: "It's a fair call and at 100x this scale I'd probably move. I'm choosing Postgres
because I also need the `user_id`-ordered list query and a real unique constraint for
idempotency, and doing both in DynamoDB means a GSI plus conditional writes. At 12k QPS
Postgres plus Redis is simpler to operate, and simplicity is worth a lot at this scale."

---

## 0.7 Step 5 — High-level architecture (15 min)

> **One-liner:** Start with the simplest thing that satisfies the requirements, then add
> each component only when you can name the specific number that forces it.

### Say this in the interview

> "I'm going to start deliberately simple and add components as the numbers force them,
> rather than drawing the final architecture and back-filling justifications.
>
> The minimum viable version is: client, load balancer, stateless API, Postgres. That
> genuinely handles the write path at a hundred and twenty QPS.
>
> Now the read path is twelve thousand QPS of key lookups, and Postgres would be doing
> nothing but repeating the same query, so I'll add Redis in front with cache-aside. At a
> ninety-five percent hit rate that leaves six hundred QPS on the database, which is
> nothing.
>
> Analytics is the last piece. I don't want a click write on the redirect path — that
> would double my p99 for data nobody reads in real time — so the redirect emits an event
> to a queue and a worker aggregates it asynchronously."

Notice the pattern in every paragraph: **number → problem → component**. Never
component-first.

### Mental model

```text
   ┌────────┐
   │ Client │
   └───┬────┘
       │ HTTPS
       ▼
  ┌─────────┐      static + redirects for hot codes
  │   CDN   │◄──────────────────────────────────────┐
  └────┬────┘                                       │
       ▼                                            │
 ┌──────────────┐   authn, rate limit, routing      │
 │ API Gateway  │                                   │
 └──────┬───────┘                                   │
        ▼                                           │
 ┌──────────────┐   stateless, autoscaled           │
 │  API servers │───────────────┐                   │
 └──────┬───────┘               │                   │
        │ cache-aside           │ click event       │
        ▼                       ▼                   │
   ┌─────────┐            ┌───────────┐             │
   │  Redis  │            │   Queue   │             │
   └────┬────┘            └─────┬─────┘             │
        │ miss (~5%)            ▼                   │
        ▼                 ┌───────────┐             │
 ┌──────────────┐         │  Workers  │             │
 │  PostgreSQL  │         └─────┬─────┘             │
 │  primary     │               ▼                   │
 └──────┬───────┘         ┌───────────┐             │
        │ async repl      │ Analytics │─────────────┘
        ▼                 │   store   │
 ┌──────────────┐         └───────────┘
 │ Read replica │
 └──────────────┘
```

**Then walk the two paths explicitly.** Interviewers want to hear data move, not see a
static picture.

> "Write path: client POSTs, gateway authenticates and rate-limits, API server checks the
> idempotency table, generates a code, inserts inside a transaction, writes through to
> Redis, returns 201.
>
> Read path: GET hits the CDN — for genuinely hot links that's where it ends. On a miss it
> reaches an API server, which checks Redis; ninety-five percent hit, return a 302. On a
> miss, read the replica, populate the cache, return. Either way the API server emits a
> click event to the queue and does not wait for it."

### The order to add components

Add each only when you can state the forcing number:

| Add | When the number says |
|---|---|
| Load balancer | More than one app instance (always) |
| Cache | Read QPS × repeat rate makes the DB the bottleneck |
| Read replicas | Read QPS exceeds one primary *and* staleness is acceptable |
| Queue + workers | Work is slow, bursty, or must survive the request |
| CDN | Static or geographically distributed content, or egress cost |
| Search index | You need text search or faceting a DB can't serve |
| Sharding | One node cannot hold the data or the write throughput |
| Microservices | Team or deploy contention, not code size |

Sharding and microservices are last for a reason. Reaching for them early is the most
common over-engineering tell.

### Red flags — do not say this

- ❌ Drawing the full architecture immediately and justifying backwards. → ✅ Start with four boxes, grow it.
- ❌ Silently drawing. → ✅ Narrate every box as you draw it.

---

## 0.8 Step 6 — Deep dive and stress test (10 min)

> **One-liner:** The interviewer picks a component; you show you have operated one.

### Say this in the interview

> "Which part would you like me to go deeper on? If you don't have a preference, I'd pick
> the cache layer, because it's the highest-risk part of this design — everything works
> until it doesn't, and then the database takes twelve thousand QPS at once."

Offering your own choice is important. If you let them pick every time, you never get to
show your strongest area.

### Mental model — the stress-test checklist

Run this against your own diagram. Out loud. This is where mid-level and senior separate.

**1. What breaks first, and at what number?**
> "The first thing to break is the single Postgres primary on writes, at around five
> thousand writes per second. That's 40x current, so I have room, but that's the ceiling
> and sharding by `code` hash is the answer when we get there."

**2. Kill each component in turn.**

| Kill | Consequence | Mitigation |
|---|---|---|
| Redis | 12k QPS hits Postgres, primary dies | Request coalescing, in-process L1 cache, and the DB is sized for a partial-miss burst |
| One API server | LB removes it on health check | Stateless + N+2 capacity |
| DB primary | Writes fail; reads survive on replicas | Automated failover, ~30 s RTO, and reads degrade gracefully |
| Queue | Click events back up | Bounded buffer, shed analytics before shedding redirects |
| A cloud region | Total outage | Out of scope at this tier, or active-passive with 15 min RTO |

**3. The specific failure modes worth naming.** Naming these correctly is disproportionately
valuable, because it proves you have seen them:

- **Cache stampede** — hot key expires, thousands of concurrent misses hit the DB.
  ([Module 07 §7.6](./07_Caching_And_CDN.md))
- **Retry storm** — three layers each retrying three times is 27x load on a struggling
  dependency. ([Module 09 §9.3](./09_Reliability_Patterns.md))
- **Hot partition** — one shard takes disproportionate traffic because the key is skewed.
  ([Module 06 §6.6](./06_Data_Distribution.md))
- **Dual write** — DB commit succeeds, event publish fails, systems diverge silently.
  ([Module 08 §8.11](./08_Messaging_And_Events.md))
- **Cascading failure** — slow dependency exhausts the thread pool, health checks fail,
  the LB removes nodes, load concentrates on the survivors, everything collapses.
  ([Module 09 §9.11](./09_Reliability_Patterns.md))
- **Thundering herd on cold start** — the fleet restarts into an empty cache.

**4. What do you monitor?** Two sentences, not a lecture: "I'd alert on p99 redirect
latency, cache hit rate, error rate and queue depth. The one that tells me something is
wrong before users notice is the cache hit rate — a drop there precedes a database
incident by a few minutes."

**5. Security and multi-tenancy.** One pass: authn at the gateway, per-tenant rate limits,
TLS everywhere, encryption at rest, and no cross-tenant data path.

### Follow-ups they will ask

**Q: They ask about something you genuinely don't know.**
A: Say so, then reason from principles. "I haven't operated Cassandra directly, so I'll
reason from the model rather than from experience — it's leaderless with tunable quorums,
which means I'd get availability during a partition at the cost of read repair and
possible stale reads. Is that the trade-off you're probing?" That answer is respected.
Bluffing is not, and interviewers detect it immediately.

---

## 0.9 Closing: the trade-off summary

> **One-liner:** Three sentences that name what you chose, what you gave up, and what you
> would change first.

### Say this in the interview

> "To summarise. I chose Postgres with Redis in front rather than a distributed store,
> because at three terabytes and twelve thousand QPS the operational simplicity is worth
> more than the headroom, and the unique constraint gives me correctness on creates for
> free.
>
> What I'm giving up is write scalability past roughly five thousand writes a second, and
> the fact that analytics are eventually consistent by a minute or so.
>
> If I had another week, the first thing I'd do is add request coalescing on the cache
> path, because right now a cache flush is an outage. The first thing I'd revisit at 10x
> is sharding by code hash."

That structure — **chose / gave up / would change** — is the single most repeatable way to
end strong. Prepare it as a template and fill it in for any design.

### Red flags — do not say this

- ❌ "And that's my design." (then silence) → ✅ The chose/gave-up/would-change summary.
- ❌ Claiming a design has no downsides. → ✅ Every design has a downside; naming yours first is what confidence looks like.

---

## 0.10 Whiteboard layout

> **One-liner:** Fixed zones so you never run out of room or lose the requirements.

### Mental model

Whether it is a physical whiteboard or Excalidraw, partition it before you start:

```text
┌────────────────────────┬──────────────────────────────────────────┐
│ REQUIREMENTS           │                                          │
│  Functional 1,2,3      │        HIGH-LEVEL ARCHITECTURE           │
│  NFR: QPS, latency,    │        (biggest zone — keep it clear)    │
│       availability     │                                          │
├────────────────────────┤                                          │
│ ESTIMATES              │                                          │
│  peak QPS              │                                          │
│  storage/5yr           │                                          │
├────────────────────────┼──────────────────────────────────────────┤
│ API                    │  DEEP DIVE / SCRATCH                     │
│  3-5 endpoints         │  (erase freely — this is the only zone   │
│ DATA MODEL             │   you erase)                             │
└────────────────────────┴──────────────────────────────────────────┘
```

Never erase the requirements or estimates zones. You will point at them repeatedly, and
every time you do, you are re-demonstrating that your design is grounded.

---

## 0.11 The bar at your level

> **One-liner:** At two years, you are being measured on solid fundamentals and honest
> reasoning — not on inventing Spanner.

### Mental model

| | Junior (fail) | **Mid / SDE-2 (your target)** | Senior |
|---|---|---|---|
| Requirements | Skips or accepts as given | **Elicits, quantifies, scopes down** | Negotiates scope against business value |
| Estimation | Cannot | **Order-of-magnitude, draws a conclusion** | Uses it to argue cost |
| Components | Names technologies | **Justifies each from a number** | Argues the ones to leave out |
| Failure | Happy path | **Kills each component, names the failure mode** | Reasons about correlated failure and metastability |
| Trade-offs | Unaware | **States them unprompted** | Quantifies them |
| Depth | Shallow everywhere | **Deep on 1-2 areas, credible elsewhere** | Deep on many, expert on some |
| Unknowns | Bluffs | **Says "I don't know", reasons from principles** | Same, plus knows where to look |

The single realistic difference-maker at your level is **depth in one or two areas that
you genuinely own**. For you, that is idempotency and retry semantics (you have shipped
it), async pipelines with queues and workers, and the entire AI/RAG surface in
[Module 14](./14_AI_LLM_System_Design.md) — where you can speak from real production
experience while most candidates recite blog posts. Steer toward those.

### Say this in the interview — using your own experience

> "I've actually hit this in production. We had a calling pipeline where a worker could
> crash after placing a call but before acknowledging the message, and the redelivery
> would call the candidate twice. We fixed it with an idempotency key on the provider
> request plus a unique constraint in Postgres, so the retry collided with the constraint
> instead of placing a second call. That's why I reach for at-least-once delivery plus an
> idempotent consumer rather than trying to get exactly-once out of the broker."

A specific, slightly scarred story like that outperforms any amount of theory. Prepare
three of them from your own work before the interview.

---

## 0.12 Recovery moves when you are stuck

> **One-liner:** Every stall has a scripted way out — use it instead of freezing.

| Situation | What to say |
|---|---|
| Mind blank at the start | "Let me start from the simplest thing that could work and grow it: client, load balancer, API, database. Now let me find where that breaks." |
| Don't know a technology | "I haven't run that in production. Can I reason about it from its model instead?" |
| Design has a hole they found | "You're right, that's a real gap. Let me fix it — [fix]. Thanks, that would have bitten us." *(Accepting a correction gracefully is a positive signal, not a negative one.)* |
| Lost in a rabbit hole | "I'm going deeper here than the time allows — let me note that I'd handle it with X and come back if we have time." |
| No idea how to start estimating | "Let me anchor on something I know: a single Postgres node does a few thousand simple writes a second. Where do we sit relative to that?" |
| Running out of time | "I have about five minutes left. Rather than start a new area, let me make sure I've covered failure handling, then summarise the trade-offs." |
| They keep pushing on one thing | They have found either your weak spot or their favourite topic. Either way, engage honestly and give your best structured reasoning — do not deflect. |

---

## Module 00 — self-test

Answer out loud, without notes.

1. Name the six steps and their time budgets.
2. What is the single question whose answer most shapes your design? *(read/write ratio)*
3. Convert 50 million DAU × 20 actions/day into peak QPS.
4. Why is drawing the architecture first the most common failure?
5. Give the three-sentence closing template.
6. Kill the cache in a 20,000 QPS read-heavy system. What happens, and what do you do?
7. What do you say when asked about a technology you have never used?
8. Name five failure modes you can reference by name.
9. What is the difference between a mid-level and a senior answer on trade-offs?
10. What are the three zones you never erase from the whiteboard?

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Interview length | 45 min (sometimes 60) |
| Time on requirements | 5 min — never zero |
| Seconds in a day | ~100,000 |
| Seconds in a month | ~2.5 million |
| Peak-to-average QPS factor | 2–3x (higher with daily spikes) |
| Cache hot-set rule of thumb | 20% of keys serve 80% of reads |
| Endpoints to define | 3–5, one shown in full |
| Deep dives to prepare for | 2–3 |
| Personal war stories to prepare | 3 |

---

**Next:** [Module 01 — Requirements, NFRs & Estimation](./01_Requirements_And_NFRs.md)
