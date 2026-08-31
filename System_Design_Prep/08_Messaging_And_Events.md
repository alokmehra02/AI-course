# Module 08 — Messaging, Kafka & Event-Driven Architecture

> **What this module makes you able to do:** Pick the right messaging primitive for any
> design — queue, pub/sub, or log — then defend the broker, the partitioning strategy,
> the delivery semantics, and what happens when a consumer is slow, a broker restarts, or
> you need to publish an event in the same transaction as a database write.
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** [Module 06 — Replication, Partitioning & Sharding](./06_Data_Distribution.md),
> [Module 07 — Caching, CDN & Object Storage](./07_Caching_And_CDN.md)

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 8.1 | [Why asynchronous messaging](#81-why-asynchronous-messaging) | ★★★★★ |
| 8.2 | [Synchronous vs asynchronous communication](#82-synchronous-vs-asynchronous-communication) | ★★★★★ |
| 8.3 | [Queue vs pub/sub vs log](#83-queue-vs-pubsub-vs-log) | ★★★★★ |
| 8.4 | [Message brokers compared](#84-message-brokers-compared) | ★★★★★ |
| 8.5 | [Kafka architecture](#85-kafka-architecture) | ★★★★★ |
| 8.6 | [Consumer groups](#86-consumer-groups) | ★★★★★ |
| 8.7 | [Partitioning and ordering](#87-partitioning-and-ordering) | ★★★★★ |
| 8.8 | [Delivery semantics](#88-delivery-semantics) | ★★★★★ |
| 8.9 | [Consumer patterns](#89-consumer-patterns) | ★★★★★ |
| 8.10 | [Retries and dead-letter queues](#810-retries-and-dead-letter-queues) | ★★★★☆ |
| 8.11 | [The dual-write problem & transactional outbox](#811-the-dual-write-problem--transactional-outbox) | ★★★★★ |
| 8.12 | [Event-driven architecture](#812-event-driven-architecture) | ★★★★☆ |
| 8.13 | [CQRS](#813-cqrs) | ★★★★☆ |
| 8.14 | [Event sourcing](#814-event-sourcing) | ★★★☆☆ |
| 8.15 | [Backpressure in messaging systems](#815-backpressure-in-messaging-systems) | ★★★★☆ |

---

## 8.1 Why asynchronous messaging

> **One-liner:** Async messaging decouples the moment a fact is recorded from the moment
> every downstream system has reacted to it — and that decoupling is what lets you survive
> spikes, partial outages, and work that takes longer than any HTTP timeout.

### Say this in the interview

> I reach for a message broker when the producer and the consumer have different throughput
> needs, different availability requirements, or different latency budgets — which is
> almost every multi-service system. The pattern is simple: the API commits the business
> fact, publishes an event, and returns 202 in under 50 milliseconds; a worker does the
> slow part — send the email, generate embeddings, call Stripe — at whatever rate it can
> sustain. That buys me three things at once. First, burst absorption: if signups spike
> from 200 per second to 2,000, the queue grows instead of the API timing out. Second,
> failure isolation: if the email provider is down for ten minutes, signups still succeed
> and the backlog drains when it recovers. Third, independent scaling: I scale consumers
> on queue depth, not on API RPS. The cost is that the user no longer gets a synchronous
> answer to "did the email send?" — I have to design for eventual consistency, idempotent
> consumers, and observability on lag. I would not add a broker for a read path that must
> return fresh data, or for a two-service system where a direct HTTP call with a timeout
> is simpler and easier to debug.

### Mental model

Synchronous calls form a **chain of fate**: every hop must succeed, within budget, right
now, or the whole operation fails. Async messaging forms a **buffered contract**: the
producer's obligation ends at durable enqueue; the consumer's obligation begins after
that.

```
  SYNC (tight coupling)                ASYNC (loose coupling)
  ---------------------                ----------------------

  Client --> API --> Worker --> SMTP   Client --> API --> [queue] --> Worker --> SMTP
              |                              |              |
              +-- if SMTP is slow,           +-- returns 202  +-- drains at worker pace
                  client waits                    in ~30 ms        (or grows backlog)
```

**The three decouplings:**

| Dimension | What sync couples | What async decouples |
|---|---|---|
| **Time** | Caller blocks until callee finishes | Caller returns after enqueue |
| **Space** | Caller must know callee's address | Producer publishes to a topic; consumers subscribe |
| **Availability** | Callee must be up now | Callee can be down; messages accumulate |

**When the math favours async.** If downstream work takes `W` seconds and arrives at
rate `λ` events per second, synchronous handling needs `λ × W` concurrent workers just
to keep up:

```
  λ = 500 events/s,  W = 2 s per event  ->  need ~1,000 in-flight workers
  λ = 500 events/s,  queue + 50 workers   ->  backlog grows at 500 - 25 = 475/s
                                              until you scale consumers or shed load
```

A queue does not make slow work fast — it makes slow work **bounded** and **recoverable**
instead of **blocking the user**.

**The consistency price.** Once you return 202, the system's state is "accepted, not yet
processed." Every read that depends on the side effect must either poll a status field,
subscribe to a completion event, or tolerate staleness. That is not a messaging detail; it
is a product contract.

### Enterprise production example

**Uber** documents moving trip-state updates through Kafka so that dispatch, pricing,
maps, and receipts consume the same stream of facts without the API service calling each
one synchronously. The design point worth stealing is not "they use Kafka" — it is that
the write path records *one* canonical event (`TripStatusChanged`) and every downstream
system derives its own materialised view at its own pace. When maps lag by two seconds,
rides still complete; when receipts lag by thirty seconds, the user still sees "trip
ended." The API's job is to accept the state transition durably, not to fan out to six
dependencies under a 500 ms SLA.

### Code

```python
# The API boundary: commit the fact, enqueue the work, return immediately.
@router.post("/documents", status_code=202)
async def ingest_document(req: IngestRequest, user=Depends(current_user), db=Depends(get_db)):
    doc_id = uuid4()
    async with db.transaction():
        await db.execute(
            """INSERT INTO documents (id, tenant_id, status, object_key)
               VALUES (:id, :t, 'QUEUED', :k)""",
            {"id": doc_id, "t": user.tenant_id, "k": req.object_key})
        # Outbox row in the SAME transaction — see §8.11 for the relay worker.
        await db.execute(
            """INSERT INTO outbox (id, aggregate_id, event_type, payload)
               VALUES (:oid, :aid, 'DocumentQueued', :payload)""",
            {"oid": uuid4(), "aid": doc_id,
             "payload": json.dumps({"doc_id": str(doc_id), "key": req.object_key})})

    return {"document_id": doc_id, "status": "QUEUED",
            "poll_url": f"/documents/{doc_id}"}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Downstream work is slow (>200 ms), bursty, or failure-prone | You need the answer in the same request (balance check, authz) | Eventual consistency, status polling, and consumer ops |
| Multiple independent consumers need the same fact | Only one consumer, and it must ack before the API responds | Duplicate delivery, ordering complexity, lag monitoring |
| You want to scale producers and consumers independently | Two services, low volume, team of three | Broker cost, schema evolution, on-call for the pipeline |

### Follow-ups they will ask

**Q: When would you NOT use a queue and just call the service directly?**
A: When the callee is fast, highly available, and on the critical path for the user's
answer — "is this JWT valid?" or "does this account have funds?" A 5 ms internal gRPC call
with a 100 ms timeout is simpler than a queue, a status table, and a polling endpoint.
The rule of thumb I use: if the user is staring at a spinner waiting for the result, stay
sync; if they clicked "upload" and can check back, go async.

**Q: How do you tell the user the async work finished?**
A: Three honest options. Polling a `status` field on the resource — simplest, works
everywhere. Server-Sent Events or WebSocket push — better UX, more infra. Email or push
notification — for long-running jobs measured in minutes. What I avoid is holding the
HTTP connection open for thirty seconds "just this once."

**Q: What metric tells you the async path is unhealthy?**
A: Consumer lag — the gap between the newest message timestamp and what the slowest
consumer group has committed. I alert on lag in seconds, not queue depth, because depth
without throughput context is meaningless: 10,000 messages at 5,000/s is two seconds of
lag; 10,000 at 10/s is seventeen minutes.

### Red flags — do not say this

- ❌ "We'll use Kafka to make it faster." → ✅ "We'll use a queue so the API returns in
  30 ms and the 8-second embedding job runs at consumer throughput instead of blocking
  the request."
- ❌ "Async means eventually consistent so we don't need transactions." → ✅ "The enqueue
  must be atomic with the database write — that's the transactional outbox — or I have
  lost events or double-sent them."
- ❌ "The queue guarantees delivery so the consumer doesn't need idempotency." → ✅ "The
  queue guarantees *at-least-once*; idempotency is what makes that safe. See
  [Module 09 §9.4](./09_Reliability_Patterns.md#94-idempotency)."

---

## 8.2 Synchronous vs asynchronous communication

> **One-liner:** Sync optimises for simplicity and immediate feedback; async optimises for
> resilience and throughput — and the wrong choice is almost always visible as either a
> timeout storm or an unnecessary queue.

### Say this in the interview

> I decide sync versus async by asking one question: does the caller need the side effect
> to have happened before it can do anything useful with the response? If yes — payment
> authorisation, inventory decrement, permission check — I keep it synchronous with a tight
> timeout and an idempotency key. If no — send welcome email, generate thumbnail, index for
> search — I make it async. The failure modes are different. In sync, a slow dependency
> becomes my problem immediately: with 50 workers and a 30-second timeout, I serve 1.7
> requests per second. In async, a slow dependency becomes backlog: the API stays healthy
> but lag grows until I scale consumers or the user notices stale state. I also watch for
> the hidden third option, which is sync-over-async: returning 202 but then having the
> client poll every 200 ms until done, which is just a badly implemented blocking call. If
> I need a near-real-time answer I use sync with streaming or a WebSocket; if I can wait,
> I use a queue and an honest status model.

### Mental model

```
                    NEED RESULT NOW?
                          |
            +-------------+-------------+
            |                           |
           YES                          NO
            |                           |
     +------+------+              +-----+-----+
     |             |              |           |
  FAST &        SLOW &         FIRE &      BATCH /
  CRITICAL      CRITICAL        FORGET      PIPELINE
     |             |              |           |
   SYNC         SYNC +          ASYNC       ASYNC
  (gRPC)      SAGA / 2PC       (queue)     (log)
              or redesign
```

**Sync communication patterns:**

| Pattern | Latency | Coupling | When |
|---|---|---|---|
| In-process call | μs | None | Monolith, same process |
| HTTP/REST | 1–50 ms | High (URL, schema, availability) | Service-to-service, external APIs |
| gRPC | 0.5–10 ms | Medium (protobuf contract) | Internal high-throughput RPC |
| GraphQL | 1–100 ms | Medium (schema, N+1 risk) | Client-driven aggregation |

**Async communication patterns:**

| Pattern | Durability | Fan-out | When |
|---|---|---|---|
| Task queue (SQS, Celery) | Yes | One consumer per message | Job processing |
| Pub/Sub (GCP Pub/Sub, SNS) | Yes | Many subscribers | Notifications, event broadcast |
| Log (Kafka, Kinesis) | Yes, replayable | Many consumer groups | Event sourcing, analytics, CDC |
| Redis Streams / Lists | Configurable | Limited | Lightweight, same-VPC async |

**The sync-over-async trap.** Client polls `GET /jobs/{id}` every 100 ms for thirty
seconds. That is 300 requests, sustained load on the API, and worse tail latency than one
sync call with a 30-second timeout. Either commit to async UX (spinner + notification) or
commit to sync (WebSocket progress stream).

### Enterprise production example

**Netflix** runs a famously async internal architecture: the API gateway accepts a
request, publishes commands and queries to internal buses, and services react. What they
do *not* do is make the user wait for the entire pipeline. Playback starts from a CDN
edge cache while recommendation updates, viewing-history writes, and A/B assignment
happen asynchronously. The product decision — "start playback in under 2 seconds" — drives
which operations stay on the critical path (manifest fetch, DRM licence) and which move
to the bus (telemetry, personalised row reordering).

### Code

```python
# Sync path: user needs the answer now. Tight timeout, idempotency key, no queue.
@router.post("/payments/authorize")
async def authorize(req: PayRequest, idem_key: str = Header(alias="Idempotency-Key")):
    if not idem_key:
        raise HTTPException(400, "Idempotency-Key required")
    cached = await idem_store.get(idem_key)
    if cached:
        return cached

    try:
        result = await stripe_client.authorize(
            req.amount_cents, req.payment_method,
            timeout=2.5,                    # 2-3x Stripe p99
            idempotency_key=idem_key)
    except TimeoutError:
        # Unknown outcome — never guess "failed". See Module 09 §9.2.
        return {"status": "PENDING", "reconcile": True}

    await idem_store.put(idem_key, result, ttl=86400)
    return result


# Async path: user does not need the side effect immediately.
@router.post("/users/{user_id}/welcome-email", status_code=202)
async def send_welcome(user_id: UUID, db=Depends(get_db)):
    await enqueue("notifications", {"type": "welcome", "user_id": str(user_id)})
    return {"status": "QUEUED"}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| The response body depends on the callee's result | The callee's result can arrive later without blocking UX | Sync: availability product of all hops. Async: consistency and status tracking |
| The operation is fast (p99 < 200 ms) and on the critical path | The operation is slow, bursty, or has unreliable third parties | Sync: tail latency amplification. Async: operational complexity |
| You need strong ordering within one request's workflow | You need to fan out to ten independent consumers | Sync: sequential latency sums. Async: no single "done" moment |

### Follow-ups they will ask

**Q: Your payment service calls fraud-check synchronously and it adds 800 ms. What do you do?**
A: First question: can the user complete checkout without the fraud score? If yes — and
often it can for low-value repeat customers — move fraud to async and hold the order in
`PENDING_REVIEW` with a semantic lock on the inventory. If no, I keep it sync but
bulkhead it: dedicated connection pool, 1-second timeout, circuit breaker, and a "manual
review" fallback rather than blocking checkout for everyone when fraud is slow.

**Q: gRPC or a message queue between two internal services?**
A: gRPC when the caller needs a response or an error right now — "reserve this seat,"
"fetch user profile." A queue when the caller is done once the message is durable —
"reindex this document," "send analytics event." If I find myself putting a correlation
ID in the message and blocking on a reply queue, I should have used gRPC.

**Q: How do you handle a chain of five sync calls?**
A: That's five failure points and five latency contributions — p99s don't add, but tail
risk compounds. I'd flatten with a saga orchestrator for writes, or an API gateway/BFF
aggregation for reads, or move non-critical hops to async. The smell is a request that
touches five services synchronously for something the user doesn't need atomically.

### Red flags — do not say this

- ❌ "Microservices should always communicate async." → ✅ "I pick per interaction: sync
  for queries and decisions that gate the response, async for side effects and fan-out."
- ❌ "HTTP is too slow, we'll use Kafka for everything." → ✅ "Kafka is for durable,
  replayable event streams. A request-response between two services is gRPC with a
  deadline, not a topic."
- ❌ "Async removes the need for timeouts." → ✅ "Consumers still need processing
  timeouts, poison-message handling, and DLQs — see §8.10 and
  [Module 09](./09_Reliability_Patterns.md)."

---

## 8.3 Queue vs pub/sub vs log

> **One-liner:** A queue delivers each message to exactly one worker; pub/sub delivers a
> copy to every subscriber; a log retains every message so any number of consumers can
> read at their own offset — and picking the wrong primitive is the most expensive
> messaging mistake you can make.

### Say this in the interview

> These three patterns solve three different fan-out problems. A **task queue** is
> work distribution: one message, one consumer, delete after ack — SQS, RabbitMQ work
> queues, Celery with Redis. I use it when I have a pool of interchangeable workers and
> each job should be done exactly once-ish. **Pub/Sub** is notification: one message,
> every subscriber gets a copy — GCP Pub/Sub, SNS+SQS fan-out, Redis Pub/Sub. I use it
> when independent services need to react to the same event without knowing about each
> other. A **log** is a durable, ordered, replayable stream — Kafka, Kinesis, Pulsar. I
> use it when consumers need to re-read history, when multiple independent consumer
> groups read the same data at different speeds, or when the log *is* the source of truth.
> The mistake I see constantly is using a queue when you need fan-out — so someone adds
> a second queue and a bridge — or using Kafka when you need simple job processing and
> now you're operating ZooKeeper. I'd start by asking how many consumers need this
> message and whether any of them need to replay last Tuesday.

### Mental model

```
  QUEUE (point-to-point)          PUB/SUB (broadcast)           LOG (durable stream)
  ----------------------          -------------------           --------------------

  [P] --> [Q] --> W1              [P] --> [T] --> S1          [P] --> [L] -----> CG1 (offset 42)
                  --> W2                      --> S2                  |
                  --> W3                      --> S3                  +-----> CG2 (offset 17)
                                                                      |
  each msg -> ONE worker          each msg -> ALL subs              +-----> CG3 (offset 99)
  deleted after ack               subs are independent              retained; replay any time
```

| Property | Queue | Pub/Sub | Log |
|---|---|---|---|
| Fan-out | 1 consumer | N subscribers | N consumer groups |
| Retention | Until consumed | Seconds to days (config) | Days to forever |
| Replay | No (consumed = gone) | Limited (seek in some) | Yes, by offset/timestamp |
| Ordering | Per-queue, mostly FIFO | Per-subscription, best-effort | Per-partition, strict |
| Backpressure | Visible (depth grows) | Subscribers can lag | Consumer lag metric |
| Complexity | Low | Medium | High |

**Hybrid patterns in production:**

- **SNS → SQS fan-out:** SNS broadcasts; each SQS queue is one subscriber's buffer.
  AWS's standard pattern for "one event, many independent workers."
- **Kafka compacted topics:** Log that keeps only the latest value per key — a hybrid of
  queue semantics (latest state) and log durability.
- **Redis Streams consumer groups:** Lightweight log with consumer-group semantics, but
  memory-bound — see [Module 07](./07_Caching_And_CDN.md#79-redis-in-production).

### Enterprise production example

**LinkedIn** created Kafka because their pipeline had outgrown point-to-point queues.
As described in the original Kafka design documents, they needed every product surface —
search indexing, analytics, monitoring, security — to consume the same activity stream
at different rates, with the ability to reprocess history when a bug shipped. A queue
delivers a message once and deletes it; that made "rebuild search from last month's
clicks" impossible without a separate archival pipeline. The log model — append-only,
partitioned, retained — turned the message bus into both transport and source of truth
for downstream materialisation.

### Code

```python
# Same business event, three primitives — pick deliberately.

# QUEUE: one worker processes each document parse job.
await sqs.send_message(QueueUrl=PARSE_QUEUE, MessageBody=json.dumps({"doc_id": doc_id}))

# PUB/SUB: every subscriber reacts independently — billing, analytics, search.
await pubsub.publish(
    topic=DOCUMENT_UPLOADED,
    data=json.dumps({"doc_id": doc_id, "tenant_id": tenant_id}).encode(),
    ordering_key=str(tenant_id),          # per-tenant ordering in Pub/Sub
)

# LOG: durable stream; multiple consumer groups read at their own pace.
producer.send(
    "document-events",
    key=tenant_id.encode(),
    value=json.dumps({"type": "DocumentUploaded", "doc_id": doc_id}).encode(),
)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Job queue: interchangeable workers, at-most-once-ish is fine with idempotency | You need every subscriber to get a copy | Queue: no fan-out, no replay |
| Pub/Sub: loose coupling, many independent reactions | You need strict ordering across all subscribers | Pub/Sub: limited replay, ordering is per-key best-effort |
| Log: replay, multiple read speeds, event sourcing, CDC | Simple background jobs for a team of five | Log: ops burden, partition planning, consumer-group coordination |

### Follow-ups they will ask

**Q: Can I use SQS as a pub/sub system?**
A: Not natively — SQS is one-consumer-per-message. The AWS pattern is SNS fan-out to
multiple SQS queues: one publish, N queues, each drained by its own consumer group. It
works well up to moderate scale; past millions of events per second you are reinventing
Kafka with more moving parts.

**Q: Why not Redis Pub/Sub for everything?**
A: Redis Pub/Sub is fire-and-forget: if no subscriber is connected, the message is
gone. No persistence, no replay, no ack. Fine for cache invalidation signals inside a
VPC; wrong for "charge the customer's card" or "index this document." Redis Streams adds
persistence and consumer groups but is memory-bound.

**Q: How do I choose between GCP Pub/Sub and Kafka on GCP?**
A: Pub/Sub if I want managed, global, and I don't need long retention or compacted
topics — it's the default for GCP-native eventing. Kafka (Confluent Cloud or self-hosted
on GKE) if I need replay over weeks, compacted changelog topics, Kafka Connect for CDC,
or exactly-once transactional produce. Pub/Sub's sweet spot is 10k–1M msg/s with minimal
ops; Kafka's is when the log is load-bearing infrastructure.

### Red flags — do not say this

- ❌ "We'll use Kafka because it's the industry standard." → ✅ "We need three independent
  consumer groups reading the same stream at different offsets with 7-day replay — that's
  a log, and Kafka is the managed option I'd pick on GCP."
- ❌ "Pub/Sub and Kafka are the same thing." → ✅ "Pub/Sub is a managed broadcast with
  per-subscription ack; Kafka is a partitioned log with consumer-group offsets and
  retention policies I control."
- ❌ "Queues guarantee exactly-once delivery." → ✅ "SQS is at-least-once with visibility
  timeout; exactly-once is an application property built with idempotent consumers."

---

## 8.4 Message brokers compared

> **One-liner:** The broker you pick is a decade-long ops commitment — match it to fan-out,
> retention, ordering, and who is on call, not to what appeared in a blog post last week.

### Say this in the interview

> I compare brokers on five axes: delivery semantics, ordering guarantees, retention and
> replay, operational model, and ecosystem fit. **SQS** is the default when I need a
> simple, managed work queue on AWS — at-least-once, visibility timeout, DLQ built in,
> no ordering unless I use FIFO queues at 300 msg/s per queue. **GCP Pub/Sub** is my
> default on GCP — global, managed, push or pull, ordering keys, dead-letter topics,
> scales to millions of msg/s without me running brokers. **RabbitMQ** is a flexible
> router — exchanges, routing keys, priority queues — great when I need complex routing
> in one cluster, but I am operating it. **Kafka** is a distributed log — partitioned,
> retained, replayable, consumer groups — the right answer when the stream is
> infrastructure, not just a job queue. **Redis Streams** is a lightweight same-VPC
> option for modest throughput. I pick Pub/Sub or SQS for 80% of greenfield work; I pick
> Kafka when replay, compaction, or Connect-based CDC is on the roadmap. The question I
> ask last is "who is on call for this at 3 a.m.?" — managed wins unless the team has
> Kafka operators.

### Mental model

```
  THROUGHPUT / RETENTION NEED
  ^
  |                                    Kafka / Pulsar
  |                                    (partitioned log)
  |
  |              GCP Pub/Sub / Kinesis
  |              (managed streaming)
  |
  |        RabbitMQ / NATS
  |        (flexible routing)
  |
  |   SQS / Redis Streams
  |   (simple queues)
  +----------------------------------------> OPS COMPLEXITY
```

| Broker | Model | Ordering | Retention | Typical scale | Managed option |
|---|---|---|---|---|---|
| **SQS** | Queue | FIFO: 300/s per queue | 14 days max | Massive | AWS only |
| **GCP Pub/Sub** | Pub/Sub | Per ordering key | 7 days default | Millions/s | GCP only |
| **RabbitMQ** | Exchange → queue | Per queue | Until consumed | 10k–100k/s | CloudAMQP, self-hosted |
| **Kafka** | Partitioned log | Per partition | Configurable (TB) | Millions/s | Confluent, MSK, self-hosted |
| **Redis Streams** | In-memory log | Per stream | Memory-bound | 100k/s per node | Memorystore, self-hosted |
| **NATS JetStream** | Queue + stream | Per stream | Configurable | High | Self-hosted, Synadia |

**Decision shortcuts:**

```
  One worker pool, job processing, AWS shop     -> SQS (+ SNS if fan-out)
  One worker pool, job processing, GCP shop     -> Pub/Sub pull subscription
  Many independent consumers, GCP, no replay    -> Pub/Sub
  Many consumer groups, replay, CDC, analytics    -> Kafka
  Complex routing (topic exchange, headers)      -> RabbitMQ
  Same-VPC, <50k/s, already run Redis            -> Redis Streams
```

### Enterprise production example

**Shopify** runs one of the largest Kafka deployments in the world — on the order of
millions of messages per second across thousands of topics — because commerce events
(orders, inventory, payments, fulfilment) fan out to search, analytics, fraud, and
third-party integrations, each at a different cadence. They also publish that they load-
test production with flash-sale traffic. The lesson is not "Shopify uses Kafka" — it is
that when event volume, fan-out, and replay are all load-bearing, you invest in a log and
the team to operate it. Smaller teams on GCP often run the same *patterns* on Pub/Sub
with shorter retention and accept that reprocessing means republishing from the database.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| SQS/Pub/Sub: managed, team has no broker ops capacity | You need multi-day replay from the bus itself | Vendor lock-in, limited ordering, per-message cost |
| Kafka: log is infrastructure, multiple consumer groups, CDC | A simple Celery task queue would suffice | Broker ops, partition rebalancing, rebalance storms |
| RabbitMQ: complex routing, moderate scale, AMQP ecosystem | You need TB-scale retention | Cluster management, memory pressure on large queues |
| Redis Streams: already on Redis, low latency, modest volume | Durability across AZ failure is critical | Memory cost, not a system of record |

### Follow-ups they will ask

**Q: SQS standard vs FIFO?**
A: Standard: best-effort ordering, unlimited throughput, at-least-once. FIFO: strict
ordering within a message group, exactly-once *processing* (dedup window 5 minutes), capped
at 3,000 msg/s per queue with batching (300/s without). I use FIFO when order matters
within one entity — `order_id` as message group — and standard for everything else.

**Q: How much does Kafka cost versus Pub/Sub at 100M messages per day?**
A: Ballpark: Pub/Sub at roughly $40 per TiB ingress — 100M × 2 KB ≈ 200 GB/day ≈ $8/day
ingress plus egress to subscribers. Kafka on Confluent Cloud is priced per CKU/partition
— often $1–3k/month minimum for a production cluster regardless of volume. Below ~50M
msg/day with no replay requirement, managed Pub/Sub is usually cheaper *and* cheaper to
operate. Above that with retention and multiple consumer groups, Kafka's unit economics
improve because you pay for the cluster, not per message.

**Q: Can I run Kafka on Kubernetes?**
A: Yes, with Strimzi or Confluent Operator — but you are now operating KRaft, disk I/O,
partition leadership, and rolling restarts. Fine if the team has platform engineers; a
trap if the backend team just wanted a task queue. Confluent Cloud trades money for sleep.

### Red flags — do not say this

- ❌ "We'll start with Kafka so we don't have to migrate later." → ✅ "We'll start with
  Pub/Sub and an outbox table; if we need 30-day replay from the bus, we migrate the
  outbox relay to Kafka — the outbox pattern survives the broker swap."
- ❌ "RabbitMQ is outdated, always use Kafka." → ✅ "RabbitMQ is the right tool for
  complex routing at moderate scale; Kafka is the right tool for retained logs at massive
  scale."
- ❌ "Managed queues are too expensive at scale." → ✅ "At scale the expensive part is
  the on-call engineer for self-hosted Kafka — I price that in."

---

## 8.5 Kafka architecture

> **One-liner:** Kafka is a distributed commit log — producers append to partitions,
> brokers replicate them, and consumers track their own offset — and every performance
> or ordering guarantee flows from that model.

### Say this in the interview

> Kafka's unit of scale is the **partition**: an ordered, append-only log segment on
> disk. A **topic** is a logical name for one or more partitions. Producers write to a
> specific partition — by key hash or explicit choice — and the broker appends the
> record with a monotonically increasing **offset**. Brokers replicate each partition
> across a **replication factor** (typically 3): one **leader** serves reads and writes,
> **followers** replicate from the leader. Consumers don't delete messages; they commit
> an **offset** per partition, and retention is time- or size-based. This is why Kafka
> can replay: the message is still on disk until retention expires. Throughput scales by
> adding partitions — each partition is a sequential write log, so one hot partition is
> one disk sequential write stream, which is why Kafka can do millions of writes per
> second on modest hardware. The costs are operational — you own partition count, rebalance
> behaviour, and consumer lag — and the constraint that ordering is **per partition only**.
> I'd size partition count at peak ingress divided by per-partition throughput with
> headroom, because reducing partitions later is painful.

### Mental model

```
  TOPIC: orders  (3 partitions, replication factor 3)

  Partition 0          Partition 1          Partition 2
  [0][1][2][3]...      [0][1][2]...         [0][1]...
     |                    |                    |
  Leader: B1           Leader: B2           Leader: B3
  Followers: B2,B3     Followers: B1,B3     Followers: B1,B2

  Producer (key=order_id) --hash--> partition = hash(key) % num_partitions

  Consumer Group "fulfillment"
    Consumer A  <-- assigned partitions [0, 2]
    Consumer B  <-- assigned partitions [1]

  Offsets committed: {0: 4, 1: 3, 2: 2}   ->  lag = high_watermark - committed
```

**Key internals:**

| Component | Role |
|---|---|
| **KRaft** | Cluster metadata, controller election (replaces ZooKeeper in Kafka 3.x+) |
| **Controller broker** | Partition leader election, ISR management |
| **ISR (in-sync replicas)** | Followers caught up enough to be promoted on leader failure |
| **`min.insync.replicas`** | Minimum replicas that must ack before produce is considered committed |
| **Segment files** | Log split into `.log` + `.index` files; sequential disk I/O |
| **Compaction** | For changelog topics: keep latest record per key, delete older |

**Produce acks:**

| `acks` | Behaviour | Durability |
|---|---|---|
| `0` | Fire and forget | None — may lose on broker crash |
| `1` | Leader ack | Lose if leader dies before replication |
| `all` | All ISR ack | Strongest; combined with `min.insync.replicas=2` on RF=3 |

### Enterprise production example

**Uber** publishes engineering detail on their Kafka usage at multi-datacenter scale —
trillions of messages, thousands of topics, and tooling built because moving Kafka
across regions is not a config toggle. The design lesson: Kafka's throughput comes from
partition-level parallelism, but **cross-datacenter replication** adds lag, cost, and
operational surface that you only pay when you genuinely need global consumption. For a
GCP single-region RAG pipeline, three brokers, RF=3, and twelve partitions is a sane
starting point; Uber's problems are not your day-one problems.

### Code

```python
# Producer: keyed for per-entity ordering, acks=all for durability.
from confluent_kafka import Producer

def delivery_report(err, msg):
    if err:
        log.error("delivery_failed", topic=msg.topic(), error=str(err))

producer = Producer({
    "bootstrap.servers": "kafka:9092",
    "acks": "all",
    "enable.idempotence": True,           # idempotent producer (EOS per partition)
    "compression.type": "lz4",
    "linger.ms": 5,                       # micro-batch for throughput
    "retries": 5,
})

def publish_order_event(order_id: str, event: dict):
    producer.produce(
        topic="order-events",
        key=order_id.encode(),            # same key -> same partition -> ordered
        value=json.dumps(event).encode(),
        on_delivery=delivery_report,
    )
    producer.poll(0)                      # serve delivery callbacks
```

```yaml
# Topic creation — partition count is a capacity decision, not a default.
partitions: 12              # ~1 MB/s per partition is a conservative planning number
replication.factor: 3
min.insync.replicas: 2
retention.ms: 604800000    # 7 days
cleanup.policy: delete     # or 'compact' for changelog topics (user-state, config)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| High-throughput event streaming with replay | Low-volume background jobs | Broker cluster ops, partition planning |
| Multiple consumer groups at different speeds | You need transactional job queues with priority | Ordering only per partition; hot partitions |
| CDC, log compaction, stream processing (Flink, ksqlDB) | Team has no Kafka experience and no time to acquire it | Rebalance storms, offset management, schema registry |

### Follow-ups they will ask

**Q: How many partitions should a topic have?**
A: Start from throughput: if I need 50 MB/s ingress and each partition sustains ~5–10
MB/s, I need 5–10 partitions minimum. Then multiply by consumer parallelism — I want at
least as many partitions as the maximum consumer instances in any group. Then add 2×
headroom because **increasing** partitions is easy and **decreasing** is not. Rule of
thumb for a new service: 6–12 partitions, revisit when lag or disk I/O says otherwise.

**Q: What happens when a broker dies?**
A: The controller elects a new leader for each partition that lost its leader, chosen
from the ISR. Produces and consumes to those partitions pause for seconds to tens of
seconds during election. With `acks=all` and `min.insync.replicas=2`, committed messages
on RF=3 survive a single broker loss. Consumers rebalance — which is its own incident
category; see §8.6.

**Q: ZooKeeper or KRaft?**
A: New clusters should use KRaft (Kafka Raft metadata mode) — Kafka 3.3+ production-ready,
removes the ZooKeeper dependency and simplifies ops. Legacy clusters still on ZK are
migrating. In an interview, saying "KRaft" signals current knowledge.

### Red flags — do not say this

- ❌ "Kafka stores messages in memory." → ✅ "Kafka stores messages on disk in sequential
  segment files; it relies on OS page cache for speed, which is why sequential write
  throughput is so high."
- ❌ "More partitions is always better." → ✅ "Each partition has broker overhead — file
  handles, memory, rebalance cost. Over-partitioning causes rebalance storms and leader
  election slowness."
- ❌ "Consumers delete messages when done." → ✅ "Consumers commit offsets; retention
  policy deletes or compacts segments independently."

---

## 8.6 Consumer groups

> **One-liner:** A consumer group is Kafka's load-balancing unit — each partition is
> consumed by at most one consumer in the group, so max parallelism equals partition count,
> and adding consumers beyond that idles extras.

### Say this in the interview

> Every Kafka consumer joins a **consumer group** identified by `group.id`. The group
> coordinator assigns partitions to members — one partition to one consumer at a time.
> If I have topic `orders` with 12 partitions and consumer group `fulfillment` with 4
> consumers, each consumer gets roughly 3 partitions. Scale to 12 consumers and I get
> 1:1 — maximum parallelism. Scale to 20 consumers and 8 sit idle. That is the single
> most important Kafka sizing fact. Rebalancing happens when consumers join, leave, or
> miss `session.timeout.ms` heartbeats — during rebalance, consumption pauses
> (`max.poll.interval.ms` violations also trigger it). I tune `fetch.min.bytes` and
> `fetch.max.wait.ms` for batching, keep processing under `max.poll.interval.ms`, and use
> **static membership** (`group.instance.id`) in Kubernetes to reduce unnecessary
> rebalances on pod restart. A second consumer group on the same topic — `analytics` —
> reads the same partitions independently with its own offsets; groups do not compete.

### Mental model

```
  Topic: 6 partitions (P0..P5)

  Group "fulfillment" (3 consumers)     Group "analytics" (2 consumers)
  -------------------------------       -------------------------------
  C1: P0, P1                            C1: P0, P1, P2
  C2: P2, P3                            C2: P3, P4, P5
  C3: P4, P5                            (separate offset commits)

  Add C4 to "fulfillment" --> REBALANCE --> ~1-2 partitions each
  Add C7 to "fulfillment" --> C7 IDLE (6 partitions, 7 consumers)
```

**Rebalance protocols:**

| Protocol | Behaviour | When |
|---|---|---|
| Range | Contiguous partition ranges per consumer | Default, can skew |
| RoundRobin | Even spread | Needs equal subscription |
| Cooperative sticky | Incremental, fewer stop-the-world pauses | Kafka 2.4+, preferred |
| Static membership | Same instance.id → same assignment after restart | K8s rolling deploys |

**Critical consumer timeouts:**

| Setting | Default | Failure mode if violated |
|---|---|---|
| `session.timeout.ms` | 45s | Missed heartbeats → consumer kicked → rebalance |
| `max.poll.interval.ms` | 5 min | Processing too slow between polls → kicked |
| `heartbeat.interval.ms` | 3s | Should be < session.timeout/3 |

### Enterprise production example

**Uber**'s **uForwarder** (open-sourced 2026, described in engineering posts) exists
because at **1,000+ downstream services** consuming Kafka, native consumer groups created
operational pain: partition count became the scalability ceiling for slow consumers,
head-of-line blocking in a partition stalled unrelated messages, and every service
reimplemented offset management. uForwarder replaces pull-based consumers with a gRPC
push proxy that centralises partition assignment and decouples consumer concurrency from
partition count — the lesson being that consumer groups are powerful but not free at
extreme scale with heterogeneous processing speeds.

### Code

```python
from confluent_kafka import Consumer

consumer = Consumer({
    "bootstrap.servers": "kafka:9092",
    "group.id": "document-processor",
    "group.instance.id": f"worker-{POD_NAME}",   # static membership
    "enable.auto.commit": False,                  # manual commit after processing
    "auto.offset.reset": "earliest",             # new group reads from start
    "partition.assignment.strategy": "cooperative-sticky",
    "max.poll.interval.ms": 300_000,
    "session.timeout.ms": 45_000,
})
consumer.subscribe(["documents"])
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Horizontal scale of identical workers | More consumers than partitions (wasted) | Rebalance pauses during deploys |
| One processing pipeline per group | Need each message processed by N different logic paths in one group | Use N groups instead |
| Cooperative sticky + static membership on K8s | Long GC pauses exceed max.poll.interval | Consumer kicked, duplicate processing after rebalance |

### Follow-ups they will ask

**Q: I have 6 partitions and need 100 parallel workers. What do I do?**
A: Increase partitions to at least 100 — but not in a panic. Adding partitions redistributes
keys; use a migration plan. Alternatively, decouple parallelism from partitions: Uber's
uForwarder, or process subtasks in an internal worker pool after a consumer reads the
batch (one partition → many goroutines, preserving order only if needed per key).

**Q: Why did my consumer get the same message twice after deploy?**
A: It committed offset N, then crashed before the broker recorded it — or a rebalance
assigned the partition to another consumer that had not committed. At-least-once is the
default. Fix: commit *after* side effects with idempotent handlers — see
[Module 09 §9.4](./09_Reliability_Patterns.md#94-idempotency).

**Q: Can two consumer groups read at different speeds?**
A: Yes — that is the point. `fulfillment` lagging by five minutes does not block
`analytics` at real-time, because offsets are per group. Monitor lag per group separately.

### Red flags — do not say this

- ❌ "I'll add consumers until lag goes away." → ✅ "I'll check partition count first —
  parallelism is capped at partitions; then scale consumers or repartition."
- ❌ "Rebalancing is fine, it only takes milliseconds." → ✅ "Stop-the-world rebalance
  pauses consumption; I use cooperative-sticky and static membership to shrink the blast
  radius on deploy."
- ❌ "One consumer group per microservice is always wrong." → ✅ "Multiple groups on one
  topic is correct; multiple consumers competing within one group is the load-sharing pattern."

---

## 8.7 Partitioning and ordering

> **One-liner:** Kafka guarantees order only within a partition — the partition key
> decides which log gets your messages, and a bad key choice creates hot partitions or
> false ordering guarantees.

### Say this in the interview

> Ordering in Kafka is per-partition, full stop. If I need all events for `order_id=42` to
> be processed in publish order, I set the message key to `order_id` — the default
> partitioner hashes the key to a partition consistently. If I need global order across
> an entire topic, I need one partition — which caps throughput to what one broker leader
> can write. The usual mistake is using a low-cardinality key like `country_code` — all of
> India lands on one partition and one consumer does 90% of the work. The other mistake is
> **one partition per customer** — at a million customers that is a million partitions,
> which destroys broker metadata and file handle limits; Uber documents ~200k partitions
> as a practical cluster ceiling. I pick a key with enough cardinality to spread load —
> `order_id`, `user_id`, `session_id` — and size partition count for target throughput
> and consumer parallelism, typically 12–48 to start, measuring bytes in/out per partition.

### Mental model

```
  GOOD key: order_id (high cardinality)     BAD key: status="NEW" (2 values)
  ------------------------------------     --------------------------------

  order_1 --> hash --> P3                  "NEW" --> hash --> P0  \
  order_2 --> hash --> P7                  "NEW" --> hash --> P0   > hot spot
  order_3 --> hash --> P3                  "NEW" --> hash --> P0  /
  order_1 events stay ordered on P3        all "NEW" orders on ONE partition

  WRONG: 1 partition per customer_id
  ---------------------------------
  1M customers -> 1M partitions -> broker metadata explosion, rebalancing nightmare
```

**Partition count sizing (rules of thumb):**

```
  target_write_throughput / per_partition_throughput  = min partitions
  target_consumer_parallelism                         = min partitions
  choose max of the above, round up, cap by cluster budget (~200k total)
```

Typical per-partition throughput: ~5–10 MB/s write (hardware and message size dependent).
LinkedIn's **7 million partitions** across **100+ clusters** — not one cluster with 7M.

**Custom partitioner.** When key hash skews — a few celebrity users dominate — use a
salted key (`user_id + random_bucket`) for writes where strict per-user order is not
required, or a dedicated hot-partition mitigation (async merge, separate topic).

### Enterprise production example

**Uber**'s Consumer Proxy blog walks through a concrete skew case: a billing topic where
each partition should sustain ~10k messages/s but slow payment RPCs at 1 msg/s forced
1000 partitions for 1000 events/s throughput — wasting partition budget. Their fix was
decoupling consumption concurrency from partition count via the proxy, not creating one
partition per ride. The interview takeaway: **partition count is a scarce resource**,
not a knob you turn to infinity.

### Code

```python
# Explicit partition — use sparingly (bypasses key hashing, you own balance)
producer.produce(topic="orders", partition=7, key=order_id.encode(), value=payload)

# Null key -> round-robin across partitions (NO ordering guarantee)
producer.produce(topic="audit-events", key=None, value=payload)
```

```python
# Detect skew: messages per partition (run in ops notebook or Kafka admin tool)
from confluent_kafka import Consumer
from collections import Counter

c = Consumer({"bootstrap.servers": "kafka:9092", "group.id": "skew-probe"})
parts = c.list_topics("orders").topics["orders"].partitions
# Compare log-end-offset deltas per partition over 5 minutes; flag if max/min > 3x
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Key = entity whose events must be ordered | Global order needed across all events | Low-cardinality key → hot partition |
| Partition count = planned consumer parallelism | One partition per entity at scale | More partitions → more broker metadata, longer rebalance |
| Null key for independent events | Order matters | Round-robin, no ordering |

### Follow-ups they will ask

**Q: How do you repartition a live topic?**
A: Create `orders-v2` with more partitions, dual-write or mirror from v1, migrate consumers,
cut over, deprecate v1. Kafka does not shrink or merge partitions in place. Keys still
map to `hash(key) mod num_partitions` — changing partition count remaps keys.

**Q: Ordering across two topics?**
A: Kafka does not guarantee it. Use a single topic with an envelope event type, or
correlation IDs and idempotent merging in the consumer, or Kafka Streams with a join
and grace period (watermarks).

**Q: GCP Pub/Sub ordering keys vs Kafka partitions?**
A: Pub/Sub ordering keys serialize delivery for that key within a region — similar intent,
different mechanics (no exposed partition count; throughput limits per key apply). Kafka
exposes partitions explicitly for sizing.

### Red flags — do not say this

- ❌ "Kafka guarantees ordering." → ✅ "Kafka guarantees ordering *within a partition*;
  the key picks the partition."
- ❌ "I'll use one partition per user for ordering." → ✅ "I'll key by user_id into a
  bounded partition set — enough cardinality for load spread, one consumer per partition
  for parallelism."
- ❌ "More partitions is always better." → ✅ "Each partition is a file set, a leader election
  unit, and rebalance overhead — I size from throughput and parallelism targets."

---
## 8.8 Delivery semantics

> **One-liner:** Brokers offer at-most-once, at-least-once, or effectively-once per
> partition — but your payment handler still needs an idempotency key because exactly-once
> end-to-end is a lie unless the database participates.

### Say this in the interview

> I think about delivery semantics at three layers: producer to broker, broker storage,
> and consumer processing. **At-most-once** means a message may be lost but never
> duplicated — `acks=0`, or commit offset before processing. **At-least-once** means a
> message may be delivered multiple times but not lost — the default for SQS, Pub/Sub,
> and Kafka with manual commit after processing. **Exactly-once** in Kafka means
> transactional produce + read-process-write with `isolation.level=read_committed` within
> one consumer group on one partition — it does not mean your Stripe charge won't double
> if you process the same event twice without an idempotency key. My default is
> at-least-once everywhere plus idempotent consumers — see
> [Module 09 §9.4](./09_Reliability_Patterns.md#94-idempotency). I only reach for
> Kafka transactions when I am writing back to another Kafka topic and need atomic
> read-process-write within the streaming layer. For a FastAPI service writing to Postgres,
> the idempotency table is simpler and broker-agnostic.

### Mental model

```
  AT-MOST-ONCE                    AT-LEAST-ONCE                 EXACTLY-ONCE (Kafka EOS)
  ------------                    -------------                 ------------------------

  commit offset FIRST             process, THEN commit          transactional consume +
  then process                    (or crash -> redeliver)       transactional produce
       |                                |                              |
       v                                v                              v
  may LOSE msg                      may DUPLICATE msg             no dup within stream
                                                                    processing pipeline
                                                                    (not your DB write)
```

| Layer | At-most-once | At-least-once | Exactly-once |
|---|---|---|---|
| **Producer → broker** | `acks=0` | `acks=all`, retries | Idempotent producer + transactions |
| **Broker** | RF=1, no replication | RF=3, `min.insync.replicas=2` | Same + transaction log |
| **Consumer** | Auto-commit before process | Commit after process | `read_committed` + transactional |
| **Your database** | Hope | Idempotency key / unique constraint | Idempotency key (still) |

**The dual-commit problem:** Consumer processes message → writes to DB → crashes before
committing offset → redelivered → duplicate DB write. Fix: idempotent write (unique
constraint on `event_id`) or transactional outbox (§8.11). Kafka EOS does not fix this
for external systems.

### Enterprise production example

**Confluent** documents Kafka's exactly-once semantics (KIP-98, idempotent producer KIP-98)
as applying to stream processing pipelines — Flink, Kafka Streams — where both input
and output are Kafka topics. Their own guidance for external sinks (JDBC, S3, HTTP) is
idempotent writes or the outbox pattern. That honesty is the interview answer: EOS is
real inside the Kafka ecosystem; outside it, you are back to at-least-once plus
idempotency.

### Code

```python
# At-least-once consumer that's safe because the handler is idempotent.
async def handle_event(event: dict, db) -> None:
    event_id = event["event_id"]
    inserted = await db.execute(
        """INSERT INTO processed_events (event_id, processed_at)
           VALUES (:eid, now())
           ON CONFLICT (event_id) DO NOTHING
           RETURNING event_id""",
        {"eid": event_id})
    if inserted is None:
        return                              # duplicate delivery — safe no-op

    await apply_business_logic(event, db)   # only runs once per event_id
```

```python
# Kafka idempotent producer — deduplicates retries within producer session.
producer = Producer({
    "enable.idempotence": True,
    "acks": "all",
    "retries": 5,
    "max.in.flight.requests.per.connection": 5,  # <= 5 with idempotence enabled
})
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| At-least-once + idempotency (default) | Losing a message is acceptable (metrics, sampling) | Duplicate-processing logic in every consumer |
| At-most-once | Any financial or inventory mutation | Silent data loss |
| Kafka transactions / EOS | Stream processor with Kafka-in, Kafka-out | Latency, throughput, complexity; doesn't cover external DB |

### Follow-ups they will ask

**Q: Kafka advertises exactly-once. Why does my payment consumer still need idempotency?**
A: Because EOS covers produce + consume + produce within Kafka's transactional boundary.
The moment you call Stripe or `INSERT INTO payments`, you are outside that boundary. A
crash between Stripe succeeding and offset commit means redelivery and a second charge
without an idempotency key.

**Q: SQS visibility timeout — how does that relate?**
A: SQS is at-least-once. After receive, the message is hidden for `visibility timeout`.
If you don't delete it before timeout — because processing crashed or was slow — it
reappears. Set timeout > p99 processing time, extend with `ChangeMessageVisibility` for
long jobs, and make the handler idempotent.

**Q: Can I get exactly-once with Pub/Sub?**
A: Pub/Sub guarantees at-least-once delivery. Ordering keys plus idempotent subscribers
are the production pattern. There is no transactional consume-and-publish in Pub/Sub
equivalent to Kafka EOS.

### Red flags — do not say this

- ❌ "We'll use Kafka exactly-once so duplicates aren't a problem." → ✅ "EOS covers the
  streaming pipeline; every external side effect still needs an idempotency key."
- ❌ "At-least-once is bad, we need exactly-once." → ✅ "At-least-once plus idempotent
  consumers is the industry default — simpler than distributed transactions."
- ❌ "Auto-commit gives exactly-once." → ✅ "Auto-commit before processing is
  at-most-once; after processing with retries it's at-least-once."

---


## 8.9 Consumer patterns

> **One-liner:** Production consumers manual-commit after durable side effects, bound
> processing time, route poison pills to a DLQ, and treat every handler as safe to run twice.

### Say this in the interview

> My consumer loop has five steps: poll with a timeout, deserialize and validate schema,
> check idempotency, process inside a transaction or with an outbox, commit offset only
> after success. On transient failure — 503, deadlock, timeout — I retry with exponential
> backoff and **do not** commit, so the message is redelivered. On permanent failure —
> schema violation, unknown event type, business rule rejection — I publish to a **DLQ**
> with the original payload plus metadata (error, stack, attempt count, source offset) and
> commit the offset so the main queue unblocks. I cap retries — usually three to five —
> because infinite retry is a sustaining effect that blocks the partition. I use
> `enable.auto.commit=False` always for anything that touches money or inventory. For
> Pub/Sub push, the same logic lives in the HTTP handler: return 500 to nack, 200 to ack,
> route to DLQ topic after N failures via Cloud Tasks or a dead-letter subscription.

### Mental model

```
  Consumer loop (at-least-once, safe)
  ----------------------------------

  +--------+    +----------+    +------------------+    +-------------+
  | poll   | -> | validate | -> | idempotent apply | -> | commit off  |
  +--------+    +----------+    +------------------+    +-------------+
                      | fail permanent              ^ fail transient
                      v                             | (no commit -> redeliver)
                 +---------+                        |
                 |  DLQ    | -----------------------+ (after max retries)
                 +---------+
```

### Enterprise production example

**Uber**'s **Chaperone** audits **20,000+ topics** (Hadoop Summit 2017 figures) —
consumers are expected to lag, retry, and occasionally fail; the platform verifies data
completeness rather than assuming every handler is perfect. Their later **uForwarder**
centralises retry and backpressure because 1,000 teams writing consumer loops independently
produced inconsistent failure handling.

### Code

```python
"""Production-shaped Kafka consumer: manual commit, retry, DLQ."""
import json
import time
from confluent_kafka import Consumer, Producer, KafkaError

MAX_RETRIES = 3
BACKOFF_BASE = 1.0

consumer = Consumer({
    "bootstrap.servers": "kafka:9092",
    "group.id": "order-processor",
    "enable.auto.commit": False,
    "auto.offset.reset": "earliest",
})
dlq = Producer({"bootstrap.servers": "kafka:9092", "acks": "all"})
consumer.subscribe(["orders"])

def send_dlq(msg, error: str, attempts: int):
    dlq.produce(
        "orders-dlq",
        key=msg.key(),
        value=json.dumps({
            "original": msg.value().decode(),
            "error": error,
            "attempts": attempts,
            "partition": msg.partition(),
            "offset": msg.offset(),
            "topic": msg.topic(),
        }).encode(),
    )
    dlq.flush(5)

def process_once(payload: dict) -> None:
    # raise TransientError / PermanentError from business layer
    ...

def handle_message(msg) -> None:
    payload = json.loads(msg.value())
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            process_once(payload)           # must be idempotent — Module 09 §9.4
            consumer.commit(msg)
            return
        except PermanentError as exc:
            send_dlq(msg, str(exc), attempt)
            consumer.commit(msg)            # skip poison pill
            return
        except TransientError:
            if attempt == MAX_RETRIES:
                send_dlq(msg, "max retries", attempt)
                consumer.commit(msg)
                return
            time.sleep(BACKOFF_BASE * (2 ** (attempt - 1)))

while True:
    msg = consumer.poll(1.0)
    if msg is None:
        continue
    if msg.error():
        if msg.error().code() == KafkaError._PARTITION_EOF:
            continue
        raise msg.error()
    handle_message(msg)
```

```python
# aiokafka variant — same semantics, async FastAPI worker
from aiokafka import AIOKafkaConsumer

consumer = AIOKafkaConsumer(
    "orders",
    bootstrap_servers="kafka:9092",
    group_id="order-processor",
    enable_auto_commit=False,
)
await consumer.start()
try:
    async for msg in consumer:
        await handle_message_async(msg)
        await consumer.commit({TopicPartition(msg.topic, msg.partition): msg.offset + 1})
finally:
    await consumer.stop()
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Manual commit after durable write | Fire-and-forget metrics | Duplicate processing on crash before commit |
| DLQ for poison messages | Every failure is transient | DLQ replay tooling and alerting |
| Bounded retries | Unbounded blocking retry | Messages land in DLQ that need human triage |

### Follow-ups they will ask

**Q: Commit before or after processing?**
A: After — always, for at-least-once with business side effects. Commit-before is
at-most-once. The duplicate window is "processed but not yet committed"; idempotency
closes it.

**Q: How do you replay a DLQ?**
A: Admin tool or script that reads DLQ, fixes root cause, republishes to the main topic
with a `replay=true` header, and tracks replayed IDs to avoid double application. Alert
if DLQ rate exceeds baseline — it is a symptom, not a storage bucket.

**Q: Push Pub/Sub equivalent?**
A: Return non-2xx to nack (redelivery with backoff). Configure `deadLetterTopic` on the
subscription after `maxDeliveryAttempts` (5–100). Handler must still be idempotent because
push can deliver twice before ack registers.

### Red flags — do not say this

- ❌ "Failed messages disappear if we commit." → ✅ "Permanent failures go to DLQ with
  metadata, then commit to unblock the partition."
- ❌ "Infinite retry shows we're resilient." → ✅ "Bounded retry then DLQ — infinite retry
  is head-of-line blocking for the whole partition."
- ❌ "Auto-commit simplifies ops." → ✅ "Auto-commit creates at-most-once or random
  duplicate windows — manual commit for anything that writes state."

---

## 8.10 Retries and dead-letter queues

> **One-liner:** Retries handle transients with backoff and a cap; DLQs quarantine
> permanents so one bad message cannot stall the pipeline — and both need metadata to
> be debuggable.

### Say this in the interview

> I separate **retry policy** from **DLQ routing**. Transient errors — connection reset,
> 503, lock timeout — get exponential backoff with jitter, capped at three to five
> attempts, ideally without committing the offset so Kafka redelivers. Permanent errors —
> JSON parse failure, unknown schema version, "insufficient funds" — go straight to DLQ.
> For high-volume topics I use **tiered retry topics**: `orders` → `orders-retry-1`
> (delay 1 min) → `orders-retry-2` (delay 5 min) → `orders-dlq`, implemented with
> separate topics and consumer delays rather than sleeping inside the consumer loop —
> sleeping holds the partition and blocks `max.poll.interval.ms`. Every DLQ message carries
> metadata: original topic/partition/offset, `event_id`, error class, stack trace,
> attempt count, first-seen timestamp, and consumer version. Without metadata, DLQ replay
> is archaeology. I alert on DLQ insert rate and oldest-unprocessed DLQ age, and I run
> a weekly DLQ review because unreviewed DLQs become permanent graveyards.

### Mental model

```
  Tiered retry (preferred over in-process sleep)
  ----------------------------------------------

  [main topic] --fail transient--> [retry-1] --(consumer waits 1m)--> reprocess
                                        |
                                   fail again
                                        v
                                   [retry-2] --(5m delay)--> reprocess
                                        |
                                   fail again
                                        v
                                   [DLQ] --> alert --> human / replay tool
```

**DLQ metadata schema (minimum viable):**

| Field | Why |
|---|---|
| `original_topic`, `partition`, `offset` | Traceability to source log |
| `event_id` / business key | Idempotent replay dedup |
| `error_type`, `message`, `stack` | Triage without reproducing |
| `attempt_count`, `first_failure_at` | Detect flaky vs permanent |
| `consumer_version`, `schema_version` | Deploy correlation |

### Enterprise production example

**Shopify** and other high-volume platforms document **poison pill** incidents where a
single malformed message blocked a queue for hours — the sustaining effect was consumers
retrying inline without a DLQ cap. The fix pattern across the industry: dead-letter
subscription (Pub/Sub), `RedrivePolicy` (SQS), or dedicated `*.dlq` Kafka topic with
monitoring — not "log and skip."

### Code

```python
# Tiered retry via scheduled republication (keeps consumer poll loop fast)
RETRY_DELAYS = {1: 60, 2: 300, 3: 1800}   # seconds

async def route_failure(msg, payload: dict, attempt: int, error: str):
    if attempt >= MAX_RETRIES or isinstance(error, PermanentError):
        await publish_dlq(msg, payload, error, attempt)
        return
    delay = RETRY_DELAYS.get(attempt, 300)
    await scheduler.enqueue(
        topic=f"orders-retry-{attempt}",
        payload=payload,
        deliver_at=utcnow() + timedelta(seconds=delay),
        headers={"attempt": attempt, "original_offset": msg.offset()},
    )
    consumer.commit(msg)   # main topic moves on; retry topic owns the next attempt
```

```yaml
# GCP Pub/Sub — dead-letter on subscription
deadLetterPolicy:
  deadLetterTopic: projects/my-proj/topics/orders-dlq
  maxDeliveryAttempts: 5
retryPolicy:
  minimumBackoff: 10s
  maximumBackoff: 600s
```

```json
// SQS redrive policy (via AWS console/Terraform)
{
  "deadLetterTargetArn": "arn:aws:sqs:...:orders-dlq",
  "maxReceiveCount": 3
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Tiered retry topics for Kafka | Low volume, inline retry is fine | More topics, scheduling infra |
| DLQ on every production pipeline | Prototype with discard-on-error | DLQ ops, replay runbooks |
| Rich metadata on every DLQ msg | Hand-wavy "check logs" | Slightly larger messages |

### Follow-ups they will ask

**Q: Should DLQ messages ever re-enter the main topic automatically?**
A: Only after the root cause is fixed, via a controlled replay job with dedup — not auto
loop, which recreates the poison pill infinite loop. Some teams use "DLQ retry" with a
manual approval gate.

**Q: Retry in the consumer vs separate retry topic?**
A: Separate topic when processing can exceed a few seconds or when `max.poll.interval.ms`
is a risk. In-process sleep blocks partition consumption — bad for Kafka; acceptable for
SQS visibility timeout extension in small jobs.

**Q: How does this connect to Module 09?**
A: Retries amplify duplicates — every redelivery needs
[idempotency](./09_Reliability_Patterns.md#94-idempotency). DLQ is
[Module 09 §9.6](./09_Reliability_Patterns.md#96-dead-letter-queues) from the reliability
angle; this section is the messaging-specific wiring.

### Red flags — do not say this

- ❌ "We'll just log errors and skip bad messages." → ✅ "Permanent failures go to DLQ
  with metadata; skipping without commit blocks the partition forever."
- ❌ "DLQ is S3 dump of failures." → ✅ "DLQ is an operable queue with alerts, replay tooling,
  and structured metadata."
- ❌ "Retry forever until it works." → ✅ "Cap retries, exponential backoff with jitter,
  then DLQ — see Module 09 on retry storms."

---

## 8.11 The dual-write problem & transactional outbox

> **One-liner:** Writing to the database and publishing to the broker in two separate
> steps guarantees inconsistency on partial failure — the transactional outbox makes
> event publication a row in the same database transaction as the business write.

### Say this in the interview

> The **dual-write problem** is this: I `INSERT` an order into Postgres, then `produce`
> to Kafka. If the produce fails, Postgres has an order with no downstream fulfillment
> event. If the produce succeeds and Postgres rolls back, downstream systems ship a ghost
> order. Two phase commit across Postgres and Kafka is not an option. The fix I use is
> the **transactional outbox**: in the same transaction as the business write, I insert
> a row into an `outbox` table. A separate **relay process** — polling or log-based CDC —
> reads unpublished outbox rows and publishes to Kafka, then marks them published. The
> relay is at-least-once, so consumers must be idempotent — but the business state and
> the intent to publish are never split. For CDC relay I mention **Debezium**: it tails
> Postgres WAL and publishes outbox inserts as Kafka events without polling load on the
> primary. Module 07 cross-links here for cache invalidation events that must not fire
> if the DB write rolled back.

### Mental model

```
  WRONG (dual write)                 RIGHT (transactional outbox)
  ------------------                 ----------------------------

  API --> Postgres COMMIT            API --> BEGIN
            |                              INSERT order
            v                              INSERT outbox (same TX)
        Kafka produce?                       COMMIT
            |                              |
     crash = INCONSISTENT              Relay --> Kafka --> mark published
                                            |
                                     crash = retry relay (at-least-once)
```

**Outbox table shape:**

```
  outbox
  ------
  id            UUID PK
  aggregate_id  UUID        -- order_id, document_id
  event_type    TEXT        -- OrderCreated
  payload       JSONB
  created_at    TIMESTAMPTZ
  published_at  TIMESTAMPTZ NULL
  UNIQUE (id)               -- relay dedup
```

### Enterprise production example

**Uber** uses Kafka for **database changelogs** to downstream subscribers — the pattern
is the same family as outbox/CDC: the database commit is the source of truth, and the
stream is derived. Their tier-0 billing data on Kafka implies the publish path cannot
be "best effort after commit." Debezium's Postgres connector is the standard open-source
implementation teams cite when they outgrow polling relays.

### Code

```sql
CREATE TABLE outbox (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_id  UUID NOT NULL,
    event_type    TEXT NOT NULL,
    payload       JSONB NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    published_at  TIMESTAMPTZ
);
CREATE INDEX outbox_unpublished_idx ON outbox (created_at)
    WHERE published_at IS NULL;
```

```python
# API: atomic business write + outbox insert
async def create_order(req: OrderRequest, db):
    order_id = uuid4()
    async with db.transaction():
        await db.execute(
            "INSERT INTO orders (id, ...) VALUES (:id, ...)", {"id": order_id, ...})
        await db.execute(
            """INSERT INTO outbox (aggregate_id, event_type, payload)
               VALUES (:aid, 'OrderCreated', :p)""",
            {"aid": order_id, "p": json.dumps({"order_id": str(order_id), ...})})
    return {"order_id": order_id}


# Relay: poll unpublished rows (simple; CDC is better at scale)
async def relay_loop(db, producer):
    while True:
        rows = await db.fetch(
            """SELECT id, aggregate_id, event_type, payload FROM outbox
               WHERE published_at IS NULL
               ORDER BY created_at LIMIT 100 FOR UPDATE SKIP LOCKED""")
        for row in rows:
            producer.produce(
                topic="domain-events",
                key=str(row["aggregate_id"]).encode(),
                value=row["payload"].encode(),
                headers=[("event_type", row["event_type"].encode())],
            )
            producer.flush(10)
            await db.execute(
                "UPDATE outbox SET published_at=now() WHERE id=$1", row["id"])
        await asyncio.sleep(0.5)
```

```json
// Debezium Postgres connector snippet (CDC relay — mention in interview)
{
  "name": "outbox-connector",
  "config": {
    "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
    "table.include.list": "public.outbox",
    "transforms": "outbox",
    "transforms.outbox.type": "io.debezium.transforms.outbox.EventRouter"
  }
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Event must reflect committed DB state | Event is the only source of truth (pure event sourcing) | Outbox table growth, relay ops |
| Polling relay for simplicity | High volume — use Debezium CDC | Polling load; CDC needs WAL retention tuning |
| Debezium for multi-table CDC | Single outbox, low rate | Kafka Connect cluster to operate |

### Follow-ups they will ask

**Q: Outbox vs change data capture on the whole table?**
A: Outbox is explicit — you choose exactly which events fire and their schema. Full-table
CDC captures every column change, which is noisy and couples consumers to table layout.
I use outbox for domain events; CDC on core tables when analytics wants everything.

**Q: How do you clean the outbox table?**
A: Archive or delete rows where `published_at` is older than N days. The relay marks
published; retention job prevents unbounded growth. Unpublished rows older than an hour
page — relay is stuck.

**Q: Does the outbox give exactly-once publish?**
A: At-least-once from relay to Kafka. Consumers dedupe on `outbox.id` or business
`event_id`. Same as everything else — see
[Module 09 §9.4](./09_Reliability_Patterns.md#94-idempotency).

### Red flags — do not say this

- ❌ "We'll write to DB then publish — it's usually fine." → ✅ "Partial failure is guaranteed
  at scale; outbox makes publish intent transactional with the write."
- ❌ "Two-phase commit between Postgres and Kafka." → ✅ "2PC across heterogeneous systems
  is not production-viable; outbox or saga instead."
- ❌ "The outbox replaces idempotent consumers." → ✅ "Outbox fixes the producer side;
  consumers still need idempotency for relay retries."

---

## 8.12 Event-driven architecture

> **One-liner:** Services communicate by publishing facts that already happened, not by
> chaining synchronous calls — which trades immediate consistency for independent scaling.

### Say this in the interview

> In event-driven architecture, a service commits its own state, publishes an event like
> `OrderPlaced`, and every interested consumer reacts independently. I use this when
> multiple downstream systems need the same fact, when work can be asynchronous, or when I
> want to add consumers without changing the producer. The cost is eventual consistency,
> harder debugging across traces, and duplicate events — so every consumer is idempotent.
> I distinguish three levels: **event notification** (thin event, consumers fetch state),
> **event-carried state transfer** (payload includes what consumers need), and **event
> sourcing** (the log is the source of truth — §8.14). For choreography vs orchestration:
> choreography is many services listening and reacting; orchestration is a central saga
> coordinator — choreography scales teams, orchestration makes failure paths visible.

### Enterprise production example

**Shopify** publishes domain events from core commerce flows so search, analytics, and
fulfillment evolve independently — the pattern is standard at their scale for decoupling
deploy boundaries.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Multiple consumers per fact | Strong cross-service transaction needed | Eventual consistency, trace complexity |
| Add consumers without API changes | Simple CRUD with one reader | Schema evolution, duplicate handling |

### Red flags — do not say this

- ❌ "Events replace all sync APIs." → ✅ "Events for facts many systems need; sync for queries and commands that need an immediate answer."

---

## 8.13 CQRS

> **One-liner:** CQRS splits the write model from the read model when their shapes and
> scaling needs genuinely diverge.

### Say this in the interview

> Command Query Responsibility Segregation means the model I use to accept writes is not
> the model I use to serve reads. I consider it when read patterns are radically different
> from writes — a write-normalised OLTP schema but a denormalised feed or dashboard table
> built by consumers. The read side is updated asynchronously from events, so the UI must
> tolerate seconds of lag or use read-your-writes routing for the author. I would not
> introduce CQRS for a simple CRUD API; I would when fan-out read models or multiple
> specialised views justify the operational cost.

### Red flags — do not say this

- ❌ "CQRS requires microservices." → ✅ "CQRS is a pattern inside one service or across many."

---

## 8.14 Event sourcing

> **One-liner:** Store every state change as an immutable event and derive current state by
> replay — powerful for audit, painful for deletes and schema changes.

### Say this in the interview

> Event sourcing keeps the log of `AccountDebited`, `AccountCredited` as truth; balance is
> a projection. I mention it for audit-heavy domains like payments ledgers, not as a
> default. Hard parts: GDPR deletion on an append-only log, replay time as events grow,
> and schema evolution across years of events. Often I use an append-only **business event
> table** without full ES — enough audit without rebuilding the world from scratch.

---

## 8.15 Backpressure & flow control

> **One-liner:** When producers outpace consumers, something must slow down — bounded
> queues, shed load, or scale consumers — or memory explodes.

### Say this in the interview

> Backpressure means the slowest stage controls the system. If workers process 2,000
> jobs/sec but producers emit 10,000/sec, an unbounded queue grows until disk or RAM fails.
> I use bounded queues with a defined drop or block policy, autoscale consumers on **lag**
> (KEDA on Kafka consumer lag, Pub/Sub backlog depth), and rate-limit producers at the API.
> The metric that matters is consumer lag, not CPU — lag rising for ten minutes is the
> alert, not 80% CPU.

### Mental model

```
Producer 10k/s ──► [bounded queue max 50k] ──► Consumer 2k/s
                         │
                    lag grows 8k/s
                         ▼
              scale consumers OR shed OR throttle producer
```

### Red flags — do not say this

- ❌ "Kafka will buffer forever." → ✅ "Retention is finite; unbounded lag is an outage in slow motion."

---

## Module 08 — self-test

Answer out loud, without notes.

1. When do you choose async over sync?
2. State the difference between queue, pub/sub, and log.
3. Why is max Kafka parallelism equal to partition count?
4. What do `acks=all` and `min.insync.replicas` buy you?
5. What is the dual-write problem and how does the outbox fix it?
6. At-least-once + what equals effectively-once?
7. What belongs in a DLQ message?
8. Choreography vs orchestration — one trade-off each.
9. When is CQRS worth it?
10. What metric do you alert on for pipeline health?

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Kafka partition parallelism cap | 1 consumer per partition per group |
| Typical Kafka partition throughput (order of magnitude) | tens of MB/s per partition |
| Consumer lag alert | sustained growth > 5–10 min |
| Outbox relay lag (healthy) | tens–hundreds of ms |
| Retry tiers (typical) | 3–5 attempts with backoff |

---

**Next:** [Module 09 — Reliability: Retries, Idempotency, Circuit Breakers & Backpressure](./09_Reliability_Patterns.md)

