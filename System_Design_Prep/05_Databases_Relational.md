# Module 05 — Databases: SQL, ACID, Transactions & Indexes

> **What this module makes you able to do:** choose a database from the access
> patterns instead of from fashion and defend the choice out loud; then reason
> concretely about transactions, isolation anomalies, locking, concurrency
> control, indexes, query plans, connection pools and zero-downtime migrations —
> with PostgreSQL specifics, because that is what you actually run.
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** working SQL. Nothing else in this guide is required, though
> [Module 01 — Requirements, NFRs & Estimation](./01_Requirements_And_NFRs.md)
> makes 5.1 easier.

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 5.1 | [How to actually choose a database](#51-how-to-actually-choose-a-database) | ★★★★★ |
| 5.2 | [Relational model & normalization](#52-relational-model--normalization) | ★★★★☆ |
| 5.3 | [NoSQL families](#53-nosql-families) | ★★★★★ |
| 5.4 | [ACID, letter by letter](#54-acid-letter-by-letter) | ★★★★★ |
| 5.5 | [Transactions in practice](#55-transactions-in-practice) | ★★★★☆ |
| 5.6 | [Isolation levels & anomalies](#56-isolation-levels--anomalies) | ★★★★★ |
| 5.7 | [Locking](#57-locking) | ★★★★☆ |
| 5.8 | [Optimistic vs pessimistic concurrency control](#58-optimistic-vs-pessimistic-concurrency-control) | ★★★★☆ |
| 5.9 | [Indexes](#59-indexes) | ★★★★★ |
| 5.10 | [Composite indexes & the leftmost-prefix rule](#510-composite-indexes--the-leftmost-prefix-rule) | ★★★★★ |
| 5.11 | [Reading query plans](#511-reading-query-plans) | ★★★★☆ |
| 5.12 | [When indexes hurt](#512-when-indexes-hurt) | ★★★★☆ |
| 5.13 | [Connection pooling](#513-connection-pooling) | ★★★★★ |
| 5.14 | [Schema migrations without downtime](#514-schema-migrations-without-downtime) | ★★★★☆ |

---

## 5.1 How to actually choose a database

> **One-liner:** You do not choose between SQL and NoSQL — you write down the
> access patterns, the consistency requirement and the data size, and the engine
> falls out of that list.

### Say this in the interview

> Before I pick a database I want the access patterns, because the access
> patterns decide the engine and almost nothing else does. So I ask four things:
> what are the top five queries by volume, is the hot path a point lookup by a
> known key or a range scan or an aggregation, how much data will there be in two
> years, and does any read need to see a write that just happened. If the answer
> is "a few terabytes, entities with real relationships, and I need transactions
> across two tables", that is PostgreSQL and I would need a strong reason to
> leave. If it is "hundreds of terabytes, every read is by one known key, and I
> never join", that is DynamoDB or Cassandra, and the price I pay is that any
> query I did not design the key for becomes a full table scan. The framing
> "SQL versus NoSQL" is the wrong one because it compares a query language to a
> storage topology; the real axis is whether the workload needs ad-hoc queries
> and multi-row transactions, or whether it needs to scale writes past one
> machine. Most systems I have worked on need both, so I default to Postgres for
> the source of truth and add a purpose-built store next to it — Redis for hot
> state, Elasticsearch for text, pgvector for embeddings — rather than trying to
> find one engine that does everything.

### Mental model

The decision is a funnel, and you run it in this order. Reversing the order is
how teams end up with Cassandra holding 40 GB of data that needed a join.

```
1. ACCESS PATTERNS   "top 5 queries, by volume"
        |            point lookup / range scan / aggregate / text / vector
        v
2. CONSISTENCY       "can this read be 3 seconds stale?"
        |            per-query, not per-system
        v
3. SIZE + GROWTH     "GB today, GB in 24 months"
        |            < ~5 TB single node is still fine in 2026
        v
4. WRITE THROUGHPUT  "peak writes/sec, and are they spread over keys?"
        |            one Postgres primary: ~10k-50k simple writes/sec
        v
5. OPERABILITY       "who pages at 3 a.m. and what can they debug?"
        |
        v
    ENGINE
```

Step 5 is the one candidates skip and interviewers weight heavily. A database
your team cannot debug is a database you do not have.

The questions to ask out loud, phrased the way you would actually ask them:

- "What are the five highest-volume queries, and what does the WHERE clause look
  like for each?"
- "Is there a natural single entity that almost every query filters on —
  a tenant, a user, a channel?" (That is your future partition key; see
  [Module 06 — Choosing a shard key](./06_Data_Distribution.md#67-choosing-a-shard-key).)
- "Which reads must be read-your-writes, and which can tolerate 500 ms of lag?"
- "How big is the biggest table in two years, in rows and in bytes?"
- "Do we ever need to change two rows atomically? Which two?"
- "What is the p99 latency budget for the hot path, end to end?"

### Workload → engine decision table

| Workload shape | Engine | Why it wins | What it costs you |
|---|---|---|---|
| Entities with relationships, ad-hoc queries, multi-row transactions, ≤ ~5–10 TB | **PostgreSQL** | Real transactions, joins, JSONB, GIN/GiST, pgvector, mature planner | One writable primary; connections are processes; you must plan sharding later |
| Same shape but you need proven online DDL and huge replica fleets | **MySQL/InnoDB** | `gh-ost`/`pt-osc` online schema change, Vitess for sharding | Weaker type system, no first-class JSONB indexing story |
| Every hot read is by one known key; scale must be effectively unbounded; no joins | **DynamoDB** | Single-digit-ms point reads at any size, no capacity ceiling to manage | Query patterns are frozen at design time; GSIs are eventually consistent; scans are ruinous |
| Write-heavy, time-ordered rows within a partition, multi-DC active-active | **Cassandra / ScyllaDB** | Leaderless writes, linear write scaling, tunable consistency | You model per query, duplicate data, and hot partitions hurt badly |
| Documents that are the whole aggregate; flexible/evolving fields; per-document atomicity | **MongoDB** | Natural fit for nested objects, easy horizontal scaling | Cross-document transactions are possible but expensive; schema drift is a real operational cost |
| Ephemeral hot state: counters, rate limits, leaderboards, sessions, locks, queues | **Redis** | Sub-millisecond ops (~0.2–0.5 ms p99 in-VPC), rich data structures | Memory-priced; durability is a spectrum, not a guarantee |
| Free-text relevance, fuzzy matching, faceting, log search | **Elasticsearch / OpenSearch** | Inverted index + BM25 scoring + aggregations | Near-real-time (default 1 s refresh), not a source of truth |
| Analytical scans and aggregations over billions of rows | **ClickHouse / BigQuery** | Columnar + vectorised execution; 100× less I/O per aggregate | No OLTP: single-row updates are unnatural, joins are limited |
| Embedding similarity search that also needs relational filters and joins | **PostgreSQL + pgvector** | One store, one transaction, `WHERE tenant_id = $1` + ANN in the same query | Index memory is real; HNSW build is slow; ~10M vectors per node is where you start planning |

Two rules that follow from the table:

1. **Postgres until it hurts, then Postgres plus one thing.** Postgres with
   JSONB, `pg_trgm`, `tsvector` and `pgvector` covers document, fuzzy-search and
   vector workloads well enough that a second engine is often premature.
2. **Do not put two workloads with different failure requirements in one
   engine.** A nightly analytics query that scans 200 GB does not belong on the
   primary that serves your checkout endpoint.

### Enterprise production example

**Uber**, 2014. Trip data lived in a single PostgreSQL instance growing roughly
20% per month and on track to exhaust disk and IOPS by year end. They evaluated
Cassandra and Riak and chose neither. They built **Schemaless**: a thin
key-value layer over *sharded MySQL*, with the dataset split into a fixed number
of logical shards (typically 4,096) and `shard = hash(row_key) % 4096`. The
explicit reasoning was operational, not theoretical — MySQL was the engine their
team could debug at 3 a.m., so they added the smallest possible coordination
layer on top instead of adopting a new storage engine. That is step 5 of the
funnel deciding the answer.

**Discord** ran the same funnel three times and got three answers. MongoDB was
fine until ~100 million messages, when the working index no longer fit in RAM.
Cassandra fit the write-heavy, time-ordered-per-channel pattern and carried them
to trillions of messages across 177 nodes — but by early 2022 JVM GC pauses and
compaction backlog made p99 reads swing between 40 ms and 125 ms. They moved to
**ScyllaDB** (same data model, C++, shard-per-core) and landed on 72 nodes with
a steady 15 ms p99 read and 5 ms p99 insert. The data model never changed; the
implementation did. That is the tell that the original modelling decision was
correct and the engine choice was the problem.

### Code

The artefact to produce before choosing anything. Write it down, put it in the
PR description, and the engine argument usually resolves itself.

```yaml
# access-patterns.yaml — the thing that actually picks the database
service: document-qa
patterns:
  - name: get_document_by_id
    query: "SELECT * FROM documents WHERE id = ?"
    qps_peak: 1200
    shape: point-lookup
    staleness_tolerated: 0s          # read-your-writes required after upload
  - name: list_documents_for_tenant
    query: "... WHERE tenant_id = ? ORDER BY created_at DESC LIMIT 50"
    qps_peak: 400
    shape: range-scan
    staleness_tolerated: 5s          # fine to serve from a read replica
  - name: semantic_search
    query: "... WHERE tenant_id = ? ORDER BY embedding <=> ? LIMIT 20"
    qps_peak: 150
    shape: vector-ann
    staleness_tolerated: 60s         # newly ingested chunks may lag
  - name: usage_rollup_daily
    query: "SELECT tenant_id, date, sum(tokens) ... GROUP BY 1,2"
    qps_peak: 0.01
    shape: aggregate-scan
    staleness_tolerated: 24h         # belongs somewhere else entirely
size:
  rows_today: 40_000_000
  rows_in_24_months: 400_000_000
  bytes_in_24_months: 900GB
transactions:
  - "document row + its chunk rows must be created atomically"
decision: >
  PostgreSQL primary with pgvector for the first three patterns (one engine, one
  transaction, tenant filter and ANN in the same query). usage_rollup_daily goes
  to BigQuery via nightly export so a 200 GB scan can never touch the primary.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Start on Postgres when the data has relationships and the scale is unproven | Avoid Postgres as the primary when peak writes exceed what one primary can take and the workload cannot be partitioned by a natural key | You will eventually pay for sharding, and you pay it under pressure |
| Reach for a key-value store when 100% of the hot path is `get(key)` | Avoid it when product managers keep inventing new filters | Every new access pattern needs a new table or index, written by hand |
| Add a second engine when the workload's failure mode differs from the primary's | Avoid a second engine to save 20 ms | Dual writes, drift, one more thing to page on |

### Follow-ups they will ask

**Q: You said Postgres. At what point do you actually leave it?**
A: I leave when one primary can no longer absorb the write rate and the working
set no longer fits in RAM — concretely, when I am past roughly 5–10 TB in the hot
tables, sustained writes are in the tens of thousands per second, and vacuum
cannot keep up. Notion's trigger was exactly this: the `block` table had passed
about 20 billion rows, autovacuum was stalling, and transaction-ID wraparound —
which stops all writes — became a real risk. That is when you shard, not when
someone reads a blog post.

**Q: Why not just use MongoDB for everything and skip the schema work?**
A: Because the schema does not disappear, it moves into application code where
nothing validates it. The real question is whether my aggregate boundary matches
my transaction boundary. If a document is exactly the unit I read and write
atomically, Mongo is a good fit. If I regularly need "charge this account and
credit that one", I want a database that makes that one statement, not a
distributed transaction I hand-roll.

**Q: The interviewer says "we need to handle 1 million writes per second".
What is your first move?**
A: Ask what the writes are, because the answer changes the engine completely. A
million metric points per second is a time-series or columnar problem —
ClickHouse, or Kafka into a rollup. A million financial ledger writes per second
is a sharded OLTP problem and I want to know the partition key before I say
anything else. And I would sanity-check the number: 1M/s sustained is about 86
billion rows a day, which is usually a sign the requirement includes something
that should be aggregated at the edge.

**Q: How do you choose between pgvector and a dedicated vector database?**
A: I stay on pgvector while the vector count is in the single-digit millions per
tenant and every search is filtered by tenant, because keeping embeddings in the
same transaction as the rows they describe removes an entire class of
consistency bug. I move to a dedicated store when the ANN index no longer fits
in RAM alongside the OLTP working set, or when I need features Postgres does not
have, like native multi-vector reranking.

### Red flags — do not say this

- ❌ "NoSQL is faster than SQL." → ✅ "A key-value get is faster than a join, but
  that is a data-model difference, not a technology difference. Postgres does a
  primary-key lookup in a few hundred microseconds too."
- ❌ "We'll use Cassandra because we need scale." → ✅ "Cassandra scales writes
  linearly if I can partition by a key with high cardinality and no hot spots.
  Can I? If the workload is 'show me all orders where status = pending', I
  cannot, and Cassandra is the wrong tool."
- ❌ "MongoDB is schemaless so we can move fast." → ✅ "Flexible schema moves the
  validation into my application. That is a real trade I'd make for
  fast-evolving nested documents and not for a normalised order model."
- ❌ "Let's start with a sharded cluster to be safe." → ✅ "I'd start with one
  primary and read replicas and instrument write throughput and table size, so
  I shard when the data says to, with the shard key the access patterns tell me."

---

## 5.2 Relational model & normalization

> **One-liner:** Normalize until every fact lives in exactly one place, then
> denormalize the handful of places where the read cost is proven and the write
> cost is acceptable.

### Say this in the interview

> I normalize by default to third normal form, because the point of
> normalization is that every fact has a single home — so an update is one row,
> and it is impossible for two copies of the same fact to disagree. Then I
> denormalize deliberately, in specific places, with a reason I can state. The
> classic one is a counter: if the feed shows a comment count on every post,
> computing `count(*)` on 50,000 comments per render is worse than keeping a
> `comment_count` column on the post and updating it in the same transaction as
> the insert. I have now traded correctness risk for read latency, so I need the
> denormalized value to be maintained inside the transaction or rebuilt by a
> reconciliation job — never updated by a second request that can fail
> independently. The rule I use is that normalization optimises writes and
> integrity, denormalization optimises reads, and you should only pay for the
> second one where you have measured the first one hurting.

### Mental model

The three normal forms, stated the way you would actually use them:

- **1NF** — one value per cell, no repeating groups. `phone_numbers` as a
  comma-separated string fails 1NF; a `phone_numbers` child table passes.
  (A JSONB column is a deliberate 1NF violation — fine when the contents are
  opaque to the database, bad when you filter on them constantly.)
- **2NF** — every non-key column depends on the *whole* primary key. Only bites
  composite keys: in `order_items(order_id, sku, qty, customer_email)`,
  `customer_email` depends on `order_id` alone. Move it to `orders`.
- **3NF** — no non-key column depends on another non-key column. `orders(id,
  customer_id, customer_city)` fails: `customer_city` depends on `customer_id`.
  Change a customer's city and you must chase every order row.

```
        NORMALIZED                        DENORMALIZED
   posts(id, title)                 posts(id, title, comment_count)
   comments(id, post_id)            comments(id, post_id)

   read feed:                       read feed:
     SELECT p.*,                      SELECT id, title, comment_count
       (SELECT count(*) FROM            FROM posts ORDER BY id DESC
        comments WHERE post_id=p.id)    LIMIT 20
     FROM posts LIMIT 20             -> 1 index scan, 20 rows touched
     -> 20 aggregate subqueries

   write comment:                   write comment:
     1 INSERT                         1 INSERT + 1 UPDATE, same txn
                                      -> row lock on posts, contention
                                         on hot posts
```

The trade in one sentence: **denormalization moves work from read time to write
time and moves risk from latency to correctness.**

Three denormalization patterns that are usually right, and one that is usually
wrong:

- Right: **maintained counters/aggregates** updated in the same transaction.
- Right: **immutable snapshots** — copying `unit_price` onto `order_items`,
  because the order must not change when the product's price changes. This is
  not really denormalization; the historical price is a different fact.
- Right: **materialized read models** for expensive joins, refreshed
  asynchronously with an explicit staleness budget.
- Wrong: **copying mutable reference data** (a user's current email onto every
  row they touched) with no reconciliation. That is how you get support tickets
  saying "it shows my old address in one screen".

### Enterprise production example

**Uber Schemaless** made denormalization the documented default. Secondary
indexes in Schemaless could carry a copy of the cell data inside the index
entry, so an index query hit exactly one shard for both the lookup *and* the
payload. Uber's own guidance to internal users was to denormalize into the index
anything they might need, explicitly framed as "trade storage for fast query
lookup". That is the normalization trade-off made at company scale: they gave up
single-home-per-fact and bought back single-shard reads, which in a sharded
system is worth far more.

### Code

```sql
-- Denormalized counter maintained transactionally. The UPDATE and the INSERT
-- must be one transaction or the count silently drifts.
BEGIN;
INSERT INTO comments (post_id, author_id, body)
VALUES ($1, $2, $3);

UPDATE posts
   SET comment_count = comment_count + 1,
       last_activity_at = now()
 WHERE id = $1;
COMMIT;

-- The reconciliation job that makes the drift detectable instead of permanent.
-- Run nightly; alert if it ever finds a row, do not silently fix and move on.
SELECT p.id, p.comment_count AS stored, c.actual
  FROM posts p
  JOIN (SELECT post_id, count(*) AS actual FROM comments GROUP BY post_id) c
    ON c.post_id = p.id
 WHERE p.comment_count <> c.actual;
```

For a hot post, `UPDATE posts SET comment_count = comment_count + 1` serialises
every commenter behind one row lock. If that becomes the bottleneck, the fix is
a sharded counter — insert into `post_comment_deltas(post_id, delta)` and roll
up periodically — which trades read freshness for write concurrency.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Normalize the write model: 3NF for anything a human edits | Do not normalize immutable historical facts (price at time of order) into a lookup | Joins on the read path, which is usually fine up to a few million rows |
| Denormalize a value read on every page and written rarely | Do not denormalize a value written as often as it is read on a hot row | A row lock on the hot row and a drift-detection job you must actually run |
| Use JSONB for genuinely open-ended attributes | Avoid JSONB for fields you filter or join on weekly | GIN index maintenance and no statistics on nested keys |

### Follow-ups they will ask

**Q: When is a JSONB column the right answer in Postgres rather than a table?**
A: When the shape is per-tenant or per-integration and the database never needs
to reason about it — webhook payloads, LLM tool-call arguments, provider
metadata. The moment a query filters on a key inside it every request, I promote
that key to a real column (or at minimum add an expression index), because the
planner has no selectivity statistics for keys inside a JSONB blob and will
guess.

**Q: Your comment_count is wrong in production. What went wrong and how do you
prevent it?**
A: Almost always the increment happened outside the insert's transaction — a
separate request, a queue consumer, or a retried request that incremented
twice. The prevention is to make it the same transaction, make the consumer
idempotent (see
[Module 09 — Idempotency](./09_Reliability_Patterns.md#94-idempotency)), and
run a nightly reconciliation that alerts rather than silently repairs, so drift
is a bug report and not a fact of life.

**Q: Is 4NF/5NF/BCNF worth knowing?**
A: Know that BCNF exists and tightens 3NF for overlapping candidate keys. In
practice 3NF plus judgement covers real schemas, and no interviewer I would want
to work for is grading me on 5NF.

### Red flags — do not say this

- ❌ "Joins are slow, so we denormalize." → ✅ "A join on an indexed foreign key
  over a few thousand rows costs microseconds. I denormalize when a *specific*
  query's plan shows the join is the cost, not on principle."
- ❌ "We store everything in JSONB so the schema is flexible." → ✅ "Stable,
  queried fields are columns; genuinely open-ended attributes are JSONB."

---

## 5.3 NoSQL families

> **One-liner:** There is no such thing as "NoSQL" — there are six or seven
> different data models, each built for one access pattern and hostile to the
> others.

### Say this in the interview

> "NoSQL" is not one thing, so I try to name the family instead. Key-value
> stores like DynamoDB and Redis give you `get` and `put` on a known key and
> nothing else, which is why they scale to any size — the routing is a hash.
> Document stores like MongoDB let the aggregate be the unit of storage, so if
> the thing you read and write atomically is one nested object, that is a good
> fit. Wide-column stores like Cassandra and ScyllaDB are the interesting ones:
> you do not model entities, you model queries, and you pick a partition key
> that decides which node owns the row plus a clustering key that decides the
> sort order inside the partition — so `WHERE channel_id = ? AND ts < ?
> ORDER BY ts DESC` is one disk seek and one sequential read. Search engines
> like Elasticsearch invert the index so you look up documents by term with a
> relevance score. Time-series and columnar stores like ClickHouse sort by time
> and compress by column so an aggregate over a billion rows reads only the
> columns it needs. Vector stores index embeddings for approximate nearest
> neighbour. The thing that makes any of them fast is the same thing that makes
> them narrow: they picked one access pattern and built the whole storage layout
> around it. So the honest way to choose is to name my access pattern first and
> see which family it matches.

### Mental model

```
FAMILY        UNIT           BUILT FOR                     HOSTILE TO
-----------   ------------   ---------------------------   ------------------
key-value     opaque blob    get/put by exact key          "find all where..."
              by key         O(1) routing via hash         range scans
-----------   ------------   ---------------------------   ------------------
document      nested doc     read/write a whole            joins across
              by _id         aggregate atomically          documents
-----------   ------------   ---------------------------   ------------------
wide-column   row inside     "all rows for this            anything not
              a partition    partition, in sort order"     prefixed by the
                             huge write throughput         partition key
-----------   ------------   ---------------------------   ------------------
graph         node + edge    "friends of friends of X",    bulk aggregates
                             variable-depth traversal      over all nodes
-----------   ------------   ---------------------------   ------------------
search        inverted       "documents containing         being a source
              index          these terms, ranked"          of truth
-----------   ------------   ---------------------------   ------------------
time-series   (series, ts)   append by time, downsample,   updating old
/ columnar    -> value       aggregate over columns        points; point reads
-----------   ------------   ---------------------------   ------------------
vector        embedding      "k nearest neighbours of      exact answers;
              + metadata     this vector"                  unfiltered recall
```

Now each one, with a real user and the honest weakness.

#### Key-value — DynamoDB, Redis

Data model: a primary key (optionally partition key + sort key) mapping to an
opaque item. Access pattern: `get(key)`, `put(key, value)`, and with a sort key,
`query(partition, sort-range)`. Real user: **Amazon** built DynamoDB because the
majority of their internal access patterns were single-key lookups where the
relational engine's flexibility bought nothing and cost availability. Bad at:
anything you did not design a key for. A DynamoDB `Scan` over a large table is
an operational incident, and Global Secondary Indexes are maintained
asynchronously, so a GSI read can be stale relative to the base item.

#### Document — MongoDB, Firestore

Data model: JSON-like documents in collections, indexes on any path, atomic
updates per document. Access pattern: fetch or modify a whole aggregate. Real
user: **Stripe** built **DocDB** on top of MongoDB Community Edition and runs
more than 5 million queries per second over petabytes of financial data, across
5,000+ collections on 2,000+ shards, at 99.9995% reliability. Note what they had
to add to make it work: a proxy layer, a routing metadata service mapping
logical databases to physical shards, and a custom data-movement platform.
Bad at: relationships. Once you are `$lookup`-ing across three collections you
have built a worse relational database.

#### Wide-column — Cassandra, ScyllaDB, HBase, Bigtable

This is the family interviewers probe hardest, because it forces you to think
about physical layout.

The data model is not "tables with flexible columns". It is: **a partition key
selects a node and a contiguous chunk of disk; a clustering key sorts rows
inside that chunk.** You do not write a query and hope the planner finds an
index — there is no planner worth the name. You decide the query first and let
it dictate the primary key.

```
CREATE TABLE messages (
    channel_id  bigint,       -- partition key: which node owns this
    bucket      int,          -- partition key: bounds partition size
    message_id  bigint,       -- clustering key: sort order on disk
    author_id   bigint,
    content     text,
    PRIMARY KEY ((channel_id, bucket), message_id)
) WITH CLUSTERING ORDER BY (message_id DESC);

        token(channel_id, bucket)  ->  node
        +--------------------------------------------------+
Node A  | partition (42, 202609)                           |
        |  msg 9931 | msg 9930 | msg 9929 | ...  (sorted!) |
        +--------------------------------------------------+
           ^                       ^
           |                       |
   "latest 50 in channel 42"  one seek + one sequential read
```

Query-driven modelling has three consequences you should say out loud:

1. **Every query needs its own table.** "Messages by channel" and "messages by
   author" are two tables, written to twice. Duplication is the design, not a
   smell.
2. **The partition must be bounded.** An unbounded partition (all messages ever
   in one channel) eventually becomes a multi-gigabyte partition that no single
   node can compact or serve. Hence the `bucket` column — a time bucket that
   caps partition size and rolls forward.
3. **You cannot filter on a non-key column** without `ALLOW FILTERING`, which is
   a full scan wearing a disguise. If you type it, you have modelled wrong.

Real user: **Discord**. Messages were stored in exactly this shape — partitioned
by `(channel_id, bucket)`, clustered by message ID descending — first on
Cassandra (177 nodes, trillions of messages), then on ScyllaDB (72 nodes, 9 TB
per node, 15 ms p99 reads). Bad at: hot partitions. A single very active channel
sent thousands of requests to one partition, overwhelming the nodes that owned
it and degrading unrelated queries on those same machines. Discord's fix was not
in the database — they put a Rust data-service layer in front that used
consistent hashing to route requests for the same partition to the same worker
and **coalesced** duplicate concurrent reads into one query. Notice this: even
after switching engines, the hot-partition problem needed an application-layer
answer.

#### Graph — Neo4j, Neptune

Data model: nodes, typed edges, properties on both. Access pattern: traversals
whose depth is not known at query time. Real user: fraud-detection and
identity-resolution systems, where "is this new account within three hops of a
known-bad account" is the actual question. Bad at: aggregate analytics over the
whole graph, and being your primary transactional store. In Postgres, a
recursive CTE handles two or three hops fine; reach for a graph database when
traversal depth is genuinely variable and the traversal *is* the product.

#### Search — Elasticsearch, OpenSearch

Data model: documents analysed into terms; an inverted index maps term → posting
list; BM25 scores relevance. Access pattern: "documents matching these terms,
ranked, with facet counts". Bad at: being the source of truth. Default refresh
interval is 1 second, so it is near-real-time, not real-time; there are no
cross-document transactions; and reindexing is a project. Feed it from Postgres
via change data capture and treat it as a derived, rebuildable index.

#### Time-series / columnar — TimescaleDB, ClickHouse, InfluxDB

Data model: `(series, timestamp) → value`, physically sorted by time and stored
column by column so each column compresses on its own. Access pattern: append
recent points, aggregate over ranges, downsample old data. Real user: every
metrics backend you have used. Bad at: updating old points, and single-row
lookups by a non-time key. In Postgres, a time-partitioned table with BRIN
indexes gets you a surprisingly long way before you need a separate engine.

#### Vector — pgvector, Pinecone, Qdrant, Milvus

Data model: a fixed-dimension float array per row, plus metadata for filtering.
Access pattern: approximate k-nearest-neighbour under cosine/L2/inner product.
The index is either a navigable small-world graph (HNSW) or inverted lists over
k-means centroids (IVFFlat). Bad at: exactness — you are choosing a recall
target, typically 95–99%, not a correct answer. Also bad at high-selectivity
metadata filters, where the ANN index and the filter fight each other and you
either over-fetch or fall back to a scan.

### Enterprise production example

**Discord's** three-engine journey is the cleanest single story to have ready,
because each move was forced by a specific limit:

| | 2015 (MongoDB) | 2017 (Cassandra) | 2022 (ScyllaDB) |
|---|---|---|---|
| Trigger | Index no longer fit in RAM at ~100M messages | GC pauses, compaction backlog at 177 nodes | — |
| Nodes | 1 replica set | 12 → 177 | 72 |
| Disk/node | — | ~4 TB | ~9 TB |
| p99 read | — | 40–125 ms | 15 ms |
| p99 insert | — | 5–70 ms | 5 ms (steady) |

The migration itself is a good detail to know: they rewrote ScyllaDB's data
migrator in Rust, hit 3.2 million records per second, and cut a projected
three-month migration to nine days.

### Code

Query-driven modelling for a chat product, written out as it would actually be
deployed. Same data, two tables, because there are two queries.

```sql
-- Query 1: "latest N messages in a channel"  (the hot path)
CREATE TABLE messages_by_channel (
    channel_id bigint, bucket int, message_id bigint,
    author_id bigint, content text,
    PRIMARY KEY ((channel_id, bucket), message_id)
) WITH CLUSTERING ORDER BY (message_id DESC);

-- Query 2: "everything this user posted"  (a different table, not an index)
CREATE TABLE messages_by_author (
    author_id bigint, bucket int, message_id bigint,
    channel_id bigint, content text,
    PRIMARY KEY ((author_id, bucket), message_id)
) WITH CLUSTERING ORDER BY (message_id DESC);
```

```python
# Both writes go out together. Cassandra's BATCH is not a transaction -- it is
# a logged group that will eventually apply. Idempotent writes make the retry
# safe; the primary key is the idempotency key.
BUCKET_SPAN_MS = 10 * 24 * 3600 * 1000  # 10 days per partition

def bucket_for(message_id: int) -> int:
    return (snowflake_timestamp_ms(message_id)) // BUCKET_SPAN_MS

async def store_message(session, msg) -> None:
    b = bucket_for(msg.id)
    await asyncio.gather(
        session.execute_async(INSERT_BY_CHANNEL,
                              (msg.channel_id, b, msg.id, msg.author_id, msg.content)),
        session.execute_async(INSERT_BY_AUTHOR,
                              (msg.author_id, b, msg.id, msg.channel_id, msg.content)),
    )

async def latest_in_channel(session, channel_id: int, limit: int = 50):
    """Walk buckets backwards so a quiet channel does not return an empty page."""
    out, b = [], bucket_for(snowflake_from_time(time.time()))
    for _ in range(4):                     # bound the fan-out; never unbounded
        rows = await session.execute_async(
            "SELECT * FROM messages_by_channel WHERE channel_id=%s AND bucket=%s "
            "LIMIT %s", (channel_id, b, limit - len(out)))
        out.extend(rows)
        if len(out) >= limit:
            break
        b -= 1
    return out[:limit]
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Wide-column when writes dominate, every read is prefixed by one key, and you accept table-per-query | Avoid when product requirements add new filters monthly | Every new query is a new table plus a backfill |
| Document when the aggregate is the transaction boundary | Avoid when you need atomicity across aggregates | `$lookup` chains, or distributed transactions you did not want |
| Search engine as a derived index over your source of truth | Never as the source of truth | A CDC pipeline and a reindex runbook |
| Vector store when semantic recall is the feature | Avoid when the answer must be exact | A recall target you must measure, and index memory |

### Follow-ups they will ask

**Q: In Cassandra, what actually happens when I query without the partition
key?**
A: The coordinator has no way to know which node owns the data, so it must ask
every node — that is what `ALLOW FILTERING` means. On a 72-node cluster that is
72 scans for one query, and it degrades every other query on those nodes.
If I need that access pattern I create a second table keyed for it, or a
materialised view, and pay the write cost.

**Q: How do you bound a Cassandra partition, and what happens if you do not?**
A: I put a time or hash bucket in the partition key — Discord bucketed messages
by time so `(channel_id, bucket)` stays bounded regardless of channel activity.
Without it, a busy channel's partition grows without limit; compaction of a
multi-gigabyte partition becomes expensive, reads of it blow through the row
cache, and the node owning it becomes a hotspot that you cannot fix by adding
nodes, because the partition cannot be split.

**Q: Cassandra is leaderless — so what happens on concurrent writes to the same
column?**
A: Last-write-wins by cell timestamp, which means a clock skew between
coordinators can silently lose a write. That is why Cassandra models favour
append-only, immutable rows keyed by something unique per write. If I genuinely
need read-modify-write I need lightweight transactions (Paxos per partition),
and those cost roughly four round trips instead of one — at which point I ask
whether the data belongs in Cassandra at all.

**Q: Tombstones — why do people complain about them?**
A: A delete in Cassandra is a write of a tombstone marker, not a removal. Until
compaction passes `gc_grace_seconds`, reads must scan the tombstones to know
what to exclude, so a partition you delete from heavily gets *slower*. Discord
hit exactly this during their migration: the last token ranges timed out because
they contained huge ranges of tombstones that had never been compacted away, and
they had to compact that range manually to finish.

### Red flags — do not say this

- ❌ "Cassandra is basically a distributed SQL database." → ✅ "Cassandra is a
  wide-column store where the primary key determines physical layout. I model
  one table per query."
- ❌ "We'll add an index for that in Cassandra." → ✅ "Secondary indexes in
  Cassandra are per-node and fan out to every node on read. For a real access
  pattern I create a second table keyed for that query."
- ❌ "Elasticsearch is our database." → ✅ "Elasticsearch is our search index,
  fed by CDC from Postgres, and it is rebuildable by design."

---

## 5.4 ACID, letter by letter

> **One-liner:** ACID is four separate guarantees with four separate
> implementations, and the C is the one everybody gets wrong.

### Say this in the interview

> Atomicity means the transaction is all-or-nothing — if the second statement
> fails, the first is undone, and there is no partial state anyone can observe.
> Consistency in ACID is narrower than people think: it only means the
> transaction moves the database from one state satisfying its declared
> constraints to another state satisfying them — foreign keys, unique
> constraints, check constraints, triggers. It is the database enforcing rules
> *I* declared. That is a completely different thing from consistency in CAP,
> which is about whether all replicas agree on the current value — the CAP C is
> really linearizability, a distributed-systems property. Same word, different
> concept, and mixing them up is the fastest way to give a confused answer about
> a distributed database. Isolation is about what concurrent transactions can
> see of each other, and it is a dial, not a boolean — Postgres defaults to Read
> Committed, which still allows lost updates and write skew, so if I need more I
> ask for it explicitly. Durability means once COMMIT returns, the data survives
> a crash, which in Postgres means the write-ahead log record is flushed to disk
> before the commit is acknowledged. Every one of those four has a cost, and
> durability is the one people quietly turn off — `synchronous_commit = off`
> makes commits much faster and gives you a window where an acknowledged write
> can vanish.

### Mental model

```
A  ATOMICITY     all-or-nothing
   mechanism:    WAL + undo. Postgres marks the transaction aborted; MVCC
                 row versions written by it are never visible to anyone.
   you break it: by doing half the work outside the transaction
                 (e.g. charging Stripe, then failing to INSERT).

C  CONSISTENCY   constraints hold before and after
   mechanism:    FK / UNIQUE / CHECK / NOT NULL / triggers -- rules YOU wrote.
   NOT:          "all replicas agree". That is CAP-C = linearizability.
   you break it: by enforcing invariants only in application code.

I  ISOLATION     concurrent transactions do not corrupt each other
   mechanism:    MVCC snapshots + row locks + (at SERIALIZABLE) predicate
                 tracking. A DIAL: Read Committed -> Serializable.
   you break it: by assuming the default level prevents lost updates.

D  DURABILITY    committed means survives a crash
   mechanism:    WAL record fsync'd before COMMIT returns; then replication.
   you break it: with synchronous_commit=off, or a single-node primary with
                 async replicas and a failover.
```

**The ACID-C vs CAP-C distinction, said precisely**, because this is a genuine
senior signal:

| | ACID Consistency | CAP Consistency |
|---|---|---|
| Scope | One database, one transaction | Many replicas, one object |
| Means | Declared constraints are not violated | Every read sees the latest committed write (linearizability) |
| Enforced by | The engine checking your FK/CHECK/UNIQUE | Coordination between nodes — consensus or quorum |
| Cost of having it | Constraint validation per write | A network round trip per operation, and unavailability during a partition |
| Who chose it | You, when you wrote the schema | The system's designers, when they picked CP or AP |

A single-node Postgres is fully ACID and says nothing about CAP, because there
is nothing to partition. A Cassandra cluster at `LOCAL_ONE` is not linearizable
(no CAP-C) but each individual write is still atomic and durable. The two axes
are orthogonal.

Durability is also a spectrum, not a bit. In Postgres:

| `synchronous_commit` | COMMIT returns after | You can lose |
|---|---|---|
| `off` | WAL is in memory | up to `wal_writer_delay` × 3 (~600 ms) of commits on OS/process crash |
| `local` | WAL fsync'd on primary | nothing on primary crash; everything not yet shipped on primary *loss* |
| `on` (default) | WAL fsync'd on primary **and** on the synchronous standby | nothing acknowledged, if you have a sync standby |
| `remote_apply` | standby has *applied* it, so replica reads see it | nothing; costs a full round trip plus replay |

### Enterprise production example

**Stripe's DocDB** is a good illustration that the ACID letters are chosen per
system, not inherited. It runs on MongoDB, which gives per-document atomicity —
and Stripe layered on what MongoDB alone does not provide: a proxy tier for
routing, and, during shard migrations, **fencing at the primary node** so that
the old shard stops accepting writes before the new one starts. Without fencing
you get two primaries briefly accepting writes for the same key range, and no
amount of per-document atomicity saves you. Their reliability target is 99.9995%
across $1.4 trillion in annual transactions, so "briefly" is not acceptable.

The mirror image is **GitHub, 21 October 2018**: a 43-second network partition
caused their automated MySQL failover to promote West Coast primaries while East
Coast primaries were still accepting writes. Both sides were individually ACID.
Both sides had writes the other did not. The result was 24 hours and 11 minutes
of degraded service, because durability at each node says nothing about the
cluster agreeing on one history. See
[Module 06 — Failover](./06_Data_Distribution.md#64-failover).

### Code

```python
# Atomicity is a property of the code block, not of the database. This function
# is atomic in Postgres and NOT atomic overall, because the Stripe charge is
# outside the transaction and cannot be rolled back.
async def checkout_wrong(conn, order_id: str, amount_cents: int) -> None:
    async with conn.transaction():
        await conn.execute("UPDATE orders SET status='paid' WHERE id=$1", order_id)
        await stripe.PaymentIntent.create(amount=amount_cents)   # <-- not atomic
        await conn.execute("INSERT INTO ledger (order_id, cents) VALUES ($1,$2)",
                           order_id, amount_cents)

# The fix: keep external effects out of the transaction. Commit the intent to
# act, then act, using an idempotency key so the retry cannot double-charge.
async def checkout_right(conn, order_id: str, amount_cents: int) -> None:
    async with conn.transaction():
        await conn.execute("UPDATE orders SET status='charging' WHERE id=$1", order_id)
        await conn.execute(
            "INSERT INTO outbox (topic, key, payload) VALUES ('charge', $1, $2)",
            order_id, json.dumps({"amount_cents": amount_cents}))
    # A separate worker reads outbox and calls Stripe with
    # Idempotency-Key: order_id, then marks the order paid.
```

That is the transactional outbox, and it is the practical answer to "I need
atomicity across a database and a third party". Full treatment in
[Module 06 — Distributed transactions](./06_Data_Distribution.md#613-distributed-transactions).

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Enforce invariants as DB constraints when correctness matters more than write latency | Avoid a FK on an ultra-hot insert path where the parent is guaranteed by construction | A lookup and a lock on the referenced row per insert |
| `synchronous_commit = on` with a sync standby for money-shaped data | Avoid it for high-volume append-only telemetry | An extra network round trip per commit — often 1–3 ms in-AZ |
| `synchronous_commit = off` for logs, analytics events, cache-like tables | Never for anything you would need to reconcile | A ~600 ms window of acknowledged-but-lost commits on crash |

### Follow-ups they will ask

**Q: Is a single-node Postgres CP or AP?**
A: Neither — CAP is about behaviour during a network partition between replicas,
and a single node has no partition to survive. If it is up you get consistency
and availability; if it is down you get neither. That is a durability and
availability conversation, not a CAP one.

**Q: Where exactly does Postgres make a commit durable?**
A: At COMMIT, the WAL record for the transaction is flushed to disk (`fsync`)
before the commit is acknowledged; the actual data pages are written later by
the checkpointer. That is why WAL is on fast storage and why
`synchronous_commit = off` is so much faster — it skips waiting for that flush,
at the cost of a window of acknowledged writes that a crash can eat.

**Q: My write succeeded, then the primary failed over, and the row is gone. Was
durability violated?**
A: Not at the node level — the WAL was flushed on the primary that is now gone.
It was violated at the *system* level because replication was asynchronous, so
the promoted replica never received that WAL. Durability of the cluster requires
synchronous or semi-synchronous replication, which is exactly the change GitHub
made after the 2018 incident.

**Q: Does "ACID" mean anything for MongoDB or DynamoDB?**
A: Yes, but scoped. Both give atomicity and isolation at single-item/document
granularity by default, and both offer multi-item transactions with real limits
and cost. The useful question is always "atomic over what unit?" — if my
invariant spans two items in DynamoDB, I need `TransactWriteItems`, which is
capped in size and priced higher, and that constraint should shape the data
model rather than be discovered later.

### Red flags — do not say this

- ❌ "SQL databases are ACID and NoSQL databases are not." → ✅ "Atomicity and
  isolation are scoped to a unit — a row, a document, a partition. The question
  is what unit, not which family."
- ❌ "The C in CAP is the C in ACID." → ✅ "ACID-C is constraint validity in one
  database. CAP-C is linearizability across replicas. Different problems."
- ❌ "Once COMMIT returns the data can never be lost." → ✅ "It is durable on the
  node that acknowledged it. Surviving the loss of that node is a replication
  configuration, not a property of COMMIT."

---
## 5.5 Transactions in practice

> **One-liner:** A transaction is a lock you are holding and a snapshot you are
> pinning, so the only correct scope is the smallest one that preserves the
> invariant.

### Say this in the interview

> The mechanical part is easy — BEGIN, do the work, COMMIT, or ROLLBACK on
> error. What matters in production is scope. While a transaction is open it
> holds every row lock it has taken and it pins a snapshot, and in Postgres
> pinning a snapshot means vacuum cannot reclaim any row version newer than that
> transaction's start, anywhere in the database — not just in the tables it
> touched. So a transaction someone left open for twenty minutes causes table
> bloat in tables it never read. The rules I follow are: never do network I/O
> inside a transaction, because a slow third-party API turns into a lock held
> for its timeout; never wait for user input inside one; do the reads that do
> not need to be consistent before BEGIN; and set
> `idle_in_transaction_session_timeout` so an application bug cannot hold a
> snapshot forever. On one service I set that to 30 seconds and it turned a
> recurring bloat incident into a logged error with a stack trace. Savepoints
> are the escape hatch when I need one statement inside a transaction to be
> allowed to fail without discarding the whole thing — that is what an ORM's
> nested transaction actually compiles to.

### Mental model

```
BEGIN  <-- snapshot taken here; xmin horizon pinned here
  |
  |  UPDATE accounts SET ... WHERE id=1;   -> row lock on id=1 HELD from now
  |
  |  await stripe.charge(...)              -> 8 s p99, sometimes 30 s timeout
  |                                           lock still held, snapshot pinned
  |
  |  UPDATE accounts SET ... WHERE id=2;
  |
COMMIT  <-- locks released, snapshot unpinned, WAL fsync'd

WHAT THE 8-SECOND CALL COST YOU
  1. every writer to accounts.id=1 blocked for 8 s
  2. autovacuum cannot remove ANY dead tuple newer than BEGIN, in the
     WHOLE database -> bloat in unrelated tables
  3. on a standby with hot_standby_feedback=on, the SAME hold applies
     to the primary's vacuum horizon
  4. one pooled connection is unavailable for 8 s -> pool exhaustion
     arrives long before the database is the bottleneck
```

Why long transactions are specifically dangerous in Postgres, in the order they
bite you:

1. **Lock holding.** Row locks are held until COMMIT, always. There is no
   partial release.
2. **Vacuum starvation.** MVCC keeps old row versions until no snapshot can see
   them. The oldest running transaction sets that horizon globally. Long
   transaction → dead tuples accumulate → tables and indexes bloat → sequential
   scans get slower → in the extreme, transaction-ID wraparound protection
   forces the database into a shutdown to prevent data loss. Notion's sharding
   project was triggered by exactly this on their `block` table.
3. **Replication lag.** A long-running query on a hot standby conflicts with WAL
   replay that would remove rows the query still needs. Either replay pauses
   (lag grows) or the query is cancelled with "canceling statement due to
   conflict with recovery" — controlled by `max_standby_streaming_delay`.
4. **Pool exhaustion.** Covered in [5.13](#513-connection-pooling), but note the
   ordering: you run out of pool slots before you run out of database capacity.

Savepoints give you partial rollback inside a transaction:

```
BEGIN
  INSERT a          ok
  SAVEPOINT sp1
  INSERT b          -> unique violation
  ROLLBACK TO sp1   -> b undone; a survives; txn still alive
  INSERT c          ok
COMMIT              -> a and c committed
```

Every savepoint consumes a subtransaction ID. Thousands of them in one
transaction (an ORM looping over rows with per-row exception handling) causes
the well-known subtransaction overflow problem, where every other backend's
snapshot checks get slower. Use savepoints deliberately, not in a loop.

### Enterprise production example

**Notion**, 2021. Their Postgres monolith had carried five years and four orders
of magnitude of growth when the `block` table — past 20 billion rows — started
defeating the instance underneath it. `VACUUM` stalled consistently, and behind
a stalled vacuum sits transaction-ID wraparound, the Postgres safety mechanism
that stops **all writes** to protect data. That was the forcing function for
their entire sharding project: 480 logical shards across 32 physical databases,
keyed by workspace ID. The lesson worth stating in an interview is that vacuum
health, not query latency, was the thing that actually forced a re-architecture.

### Code

```python
# FastAPI + asyncpg. Correct transaction scope: the external call happens
# before BEGIN, and the transaction contains only database work.
async def approve_refund(pool: asyncpg.Pool, refund_id: str) -> None:
    # 1. Slow, non-transactional work FIRST, outside any transaction.
    risk = await risk_service.score(refund_id, timeout=2.0)

    # 2. Short, purely-database transaction.
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT amount_cents, status FROM refunds WHERE id=$1 FOR UPDATE",
                refund_id)
            if row is None or row["status"] != "pending":
                return                                   # idempotent no-op
            await conn.execute(
                "UPDATE refunds SET status='approved', risk=$2 WHERE id=$1",
                refund_id, risk)
            await conn.execute(
                "INSERT INTO outbox (topic, key, payload) VALUES ('refund.approved',$1,$2)",
                refund_id, "{}")
    # 3. Effects on the outside world happen after COMMIT, driven by the outbox.
```

The guardrails that make this enforceable rather than aspirational — set them on
the role, not per session, so a new service inherits them:

```sql
ALTER ROLE app_service SET statement_timeout = '10s';
ALTER ROLE app_service SET lock_timeout = '3s';
ALTER ROLE app_service SET idle_in_transaction_session_timeout = '30s';

-- The query you run when bloat appears. Anything here with a large age is
-- the reason autovacuum is not reclaiming space.
SELECT pid, state, now() - xact_start AS txn_age, left(query, 60) AS query
  FROM pg_stat_activity
 WHERE xact_start IS NOT NULL
   AND now() - xact_start > interval '1 minute'
 ORDER BY xact_start;
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Wrap multi-row invariants in one transaction | Never wrap an HTTP call or a queue publish in one | Lock hold time equal to the slowest thing inside |
| Use savepoints for a genuinely optional sub-step | Avoid one savepoint per row in a loop | Subtransaction IDs; past ~64 per transaction, snapshot overhead grows for everyone |
| Set `idle_in_transaction_session_timeout` everywhere | — | Occasional aborted transactions, which is the point: a loud failure instead of silent bloat |

### Follow-ups they will ask

**Q: Why does one long-running read transaction cause bloat in tables it never
touched?**
A: Because the xmin horizon is global. Vacuum may only remove row versions that
no live snapshot could need, and the oldest transaction in the cluster defines
that boundary for every table. A 30-minute analytics query on one table freezes
reclamation everywhere, which is why long reads belong on a replica — and why,
if you set `hot_standby_feedback = on` to stop those reads being cancelled, you
have moved the problem back onto the primary.

**Q: A worker crashed mid-transaction. What state is the database in?**
A: The connection drops, the backend exits, and the transaction is aborted, so
no partial effects are visible — atomicity holds. The subtle failure is a
crashed worker that *held* a lock and whose TCP connection has not been noticed
as dead yet; other writers block until TCP keepalives or
`idle_in_transaction_session_timeout` clean it up, which is a reason to set both.

**Q: Should retry logic live inside or outside the transaction?**
A: Outside, always, and it must re-run the whole unit of work including the
reads. Postgres explicitly does not offer automatic retry because it cannot know
which application logic depended on the values read. Retrying only the failed
statement on an aborted transaction gets you SQLSTATE `25P02`, "current
transaction is aborted, commands ignored until end of transaction block".

### Red flags — do not say this

- ❌ "We wrap the whole request handler in a transaction for safety." → ✅ "The
  transaction covers only the statements that must be atomic together; the
  external calls happen before or after it."
- ❌ "Long transactions are just slow." → ✅ "Long transactions block vacuum
  cluster-wide, hold locks, and can stall replica replay. They are a
  correctness-adjacent problem, not only a latency problem."

---

## 5.6 Isolation levels & anomalies

> **One-liner:** Isolation is a dial from "fast and subtly wrong" to "correct and
> occasionally aborted", and Postgres's default sits at the fast end.

### Say this in the interview

> Postgres defaults to Read Committed, which means every statement sees a fresh
> snapshot of committed data. That prevents dirty reads but permits three things
> people assume it prevents: non-repeatable reads, phantoms, and lost updates
> when you do a read-modify-write across two statements. Repeatable Read in
> Postgres is really snapshot isolation — one snapshot for the whole
> transaction, so it also prevents phantoms, which is stronger than the SQL
> standard requires — but it still permits write skew, where two transactions
> read an overlapping set, each writes a different row, each is individually
> valid, and together they break the invariant. The classic is two doctors both
> cancelling their on-call shift after each checks that someone else is on call.
> Serializable in Postgres uses Serializable Snapshot Isolation: it tracks
> read-write dependencies between live transactions and aborts one when it
> detects a cycle no serial order could produce, and you get SQLSTATE 40001. So
> Serializable is not free and it is not blocking — it is optimistic, and the
> price is that every transaction needs a retry loop that re-runs the entire
> unit of work, not just the failed statement. For a booking or ledger
> invariant I will pay that price; for a feed read I will not.

### Mental model — the four anomalies, as timelines

**Dirty read** — reading data that was never committed.

```
T1: BEGIN                                 T2: BEGIN
T1: UPDATE accounts SET bal=0 WHERE id=7
                                          T2: SELECT bal WHERE id=7 -> 0 (!)
T1: ROLLBACK   (bal is 500 again)
                                          T2: acted on a value that
                                              never existed
```
Postgres never allows this, at any isolation level, including when you *ask* for
Read Uncommitted — it silently gives you Read Committed instead.

**Non-repeatable read** — the same row read twice in one transaction differs.

```
T1: BEGIN
T1: SELECT bal WHERE id=7  -> 500
                                    T2: UPDATE accounts SET bal=400 WHERE id=7
                                    T2: COMMIT
T1: SELECT bal WHERE id=7  -> 400   (!) same query, different answer
T1: COMMIT
```
Allowed at Read Committed. Prevented at Repeatable Read and above.

**Phantom read** — the same *range* query returns a different set of rows.

```
T1: BEGIN
T1: SELECT count(*) FROM bookings
      WHERE room=3 AND day='2026-09-04'  -> 0
                              T2: INSERT bookings(room=3, day='2026-09-04')
                              T2: COMMIT
T1: SELECT count(*) ...              -> 1   (!) a row appeared
T1: INSERT bookings(room=3, day=...)      double-booked
```
Allowed at Read Committed. **Prevented by Postgres at Repeatable Read**, because
snapshot isolation freezes the whole visible set — this is where Postgres is
stronger than the SQL standard. MySQL InnoDB prevents it at Repeatable Read too,
but by a different mechanism: next-key (gap) locks on locking reads.

**Lost update** — two read-modify-write cycles, one silently overwritten.

```
T1: BEGIN                                T2: BEGIN
T1: SELECT stock FROM items WHERE id=9   -> 10
                                         T2: SELECT stock WHERE id=9 -> 10
T1: UPDATE items SET stock = 10 - 1
T1: COMMIT                               (stock = 9)
                                         T2: UPDATE items SET stock = 10 - 3
                                         T2: COMMIT       (stock = 7)
                                         two units vanished: should be 6
```
Allowed at Read Committed. At Repeatable Read Postgres detects it and aborts T2
with `40001`. Avoidable at any level with `SELECT ... FOR UPDATE`, or by writing
`SET stock = stock - 3` so the arithmetic happens in the database.

**Write skew** — the anomaly snapshot isolation cannot see.

```
INVARIANT: at least one doctor must be on call.
Currently: Alice on_call=true, Bob on_call=true.

T1 (Alice)                              T2 (Bob)
BEGIN ISOLATION LEVEL REPEATABLE READ   BEGIN ISOLATION LEVEL REPEATABLE READ
SELECT count(*) FROM doctors
  WHERE on_call = true;  -> 2
                                        SELECT count(*) FROM doctors
                                          WHERE on_call = true;  -> 2
  (2 >= 2, safe to leave)                 (2 >= 2, safe to leave)
UPDATE doctors SET on_call=false
  WHERE name='Alice';
                                        UPDATE doctors SET on_call=false
                                          WHERE name='Bob';
COMMIT                                  COMMIT

RESULT: zero doctors on call. Neither transaction wrote a row the other
read, so there is no write-write conflict for snapshot isolation to catch.
```
This is *only* prevented by SERIALIZABLE (or by materialising the conflict —
locking a shared row, or taking `SELECT ... FOR UPDATE` on all candidate rows).
Under Postgres SERIALIZABLE, SSI sees that each transaction read a set the other
wrote into, forms a dangerous read-write dependency structure, and aborts one
with `40001`.

### The matrix

ANSI SQL standard — what each level *permits*:

| Level | Dirty read | Non-repeatable read | Phantom | Lost update | Write skew |
|---|---|---|---|---|---|
| Read Uncommitted | possible | possible | possible | possible | possible |
| Read Committed | no | possible | possible | possible | possible |
| Repeatable Read | no | no | possible | no* | possible |
| Serializable | no | no | no | no | no |

PostgreSQL — what actually happens:

| Level | Dirty read | Non-repeatable | Phantom | Lost update | Write skew | Aborts with 40001 |
|---|---|---|---|---|---|---|
| Read Uncommitted | no (= Read Committed) | yes | yes | yes | yes | no |
| **Read Committed** (default) | no | yes | yes | yes | yes | no |
| Repeatable Read (= snapshot isolation) | no | no | **no** | no (aborts) | **yes** | yes |
| Serializable (SSI) | no | no | no | no | no | yes, more often |

Two Postgres-specific facts worth saying unprompted:

- **Read Committed takes a new snapshot per statement**, not per transaction. So
  two identical `SELECT`s in one transaction can legitimately differ, and a
  multi-statement `SELECT` then `UPDATE` is a race unless you lock.
- **An `UPDATE` at Read Committed re-reads the row** if another transaction
  changed it while it waited on the lock, then re-evaluates the `WHERE`. That is
  why `UPDATE items SET stock = stock - 1 WHERE id = 9 AND stock >= 1` is safe
  at the default level but `SELECT` then `UPDATE` in the app is not.

### Enterprise production example

Postgres shipped **Serializable Snapshot Isolation in 9.1 (2011)**, from Dan
Ports and Kevin Grittner's research, and it is the reason SERIALIZABLE is
usable in Postgres at all: before SSI, true serializability meant strict
two-phase locking and readers blocking writers. SSI is optimistic — it lets
transactions run at snapshot isolation, tracks read-write dependencies through
predicate locks (SIREAD locks), and aborts a transaction only when a *dangerous
structure* forms. The practical consequences you should know:

- Predicate tracking is more precise with an index than with a sequential scan,
  so an index on the columns in your `WHERE` clause reduces false aborts.
- A genuinely read-only transaction declared `READ ONLY DEFERRABLE` will never
  abort with `40001`; it waits until it can take a safe snapshot instead. This
  is the right setting for a long report against a serializable workload.
- The abort can surface at the conflicting statement *or* at COMMIT, depending
  on when the structure is detected. Do not write code that assumes one.

### Code

The retry loop is not optional at Repeatable Read or Serializable. This is the
version to memorise: full re-execution, bounded attempts, exponential backoff
with jitter.

```python
import asyncio, random
import asyncpg

SERIALIZATION_FAILURE = "40001"
DEADLOCK_DETECTED     = "40P01"

async def in_serializable_txn(pool: asyncpg.Pool, unit_of_work, max_attempts=5):
    """Re-runs the ENTIRE unit of work on 40001. Postgres cannot retry for you
    because it does not know which application decisions depended on the reads."""
    for attempt in range(max_attempts):
        try:
            async with pool.acquire() as conn:
                tx = conn.transaction(isolation="serializable")
                await tx.start()
                try:
                    result = await unit_of_work(conn)   # re-reads + re-decides
                    await tx.commit()
                    return result
                except BaseException:
                    await tx.rollback()
                    raise
        except asyncpg.PostgresError as e:
            if e.sqlstate not in (SERIALIZATION_FAILURE, DEADLOCK_DETECTED):
                raise
            if attempt == max_attempts - 1:
                raise
            # 20ms, 40ms, 80ms, 160ms +/- jitter. Jitter matters: without it,
            # the two conflicting transactions retry in lockstep and re-collide.
            await asyncio.sleep((0.02 * 2 ** attempt) * (0.5 + random.random()))

async def leave_on_call(conn, doctor: str):
    n = await conn.fetchval(
        "SELECT count(*) FROM doctors WHERE on_call AND shift_id = 1")
    if n < 2:
        raise ValueError("cannot leave: you are the last doctor on call")
    await conn.execute(
        "UPDATE doctors SET on_call = false WHERE name = $1", doctor)

# await in_serializable_txn(pool, lambda c: leave_on_call(c, "Alice"))
```

Node.js equivalent, same shape:

```javascript
const RETRYABLE = new Set(['40001', '40P01']);

async function inSerializableTxn(pool, work, maxAttempts = 5) {
  for (let attempt = 0; ; attempt++) {
    const client = await pool.connect();
    try {
      await client.query('BEGIN ISOLATION LEVEL SERIALIZABLE');
      const out = await work(client);           // re-reads on every attempt
      await client.query('COMMIT');
      return out;
    } catch (err) {
      await client.query('ROLLBACK').catch(() => {});
      if (!RETRYABLE.has(err.code) || attempt >= maxAttempts - 1) throw err;
      const backoff = 20 * 2 ** attempt * (0.5 + Math.random());
      await new Promise(r => setTimeout(r, backoff));
    } finally {
      client.release();
    }
  }
}
```

Instrument the retries. A rising 40001 rate is a design signal — usually a
contended row that wants a different data model, not a bigger retry budget.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Read Committed for ~95% of endpoints | Avoid it for multi-statement read-modify-write on money or inventory | Lost updates and write skew that only appear under concurrency |
| Repeatable Read for a report that must see one consistent snapshot | Avoid it for anything long-running against a hot table | Snapshot pinned for the whole transaction, plus 40001 on write conflicts |
| Serializable for invariants across rows (booking, ledger, quota) | Avoid it on high-contention hot paths without measuring the abort rate | A mandatory retry loop, higher latency under contention, and aborts that increase superlinearly with concurrency |

### Follow-ups they will ask

**Q: Postgres and MySQL both say "Repeatable Read". Are they the same?**
A: No. Postgres's Repeatable Read is snapshot isolation: one snapshot for the
transaction, so phantoms are impossible, and a conflicting write aborts you with
40001. MySQL InnoDB's Repeatable Read uses consistent-read snapshots for plain
`SELECT` but next-key locks for locking reads, so it prevents phantoms by
locking gaps rather than by snapshot, and a plain read followed by an update can
still lose an update rather than abort. Same name, materially different
behaviour under concurrency.

**Q: If Serializable is correct, why is anything else the default?**
A: Because SSI's cost scales with conflict rate, not with throughput. Under low
contention the overhead is small; under high contention on the same rows, aborts
climb and effective throughput can fall as retries pile on. Postgres defaults to
Read Committed because most statements are single-statement and safe, and it
puts the burden of asking for more on the specific transactions that need it.

**Q: How do you fix write skew without going to Serializable?**
A: Materialise the conflict so snapshot isolation can see it. Either lock all
the rows you read with `SELECT ... FOR UPDATE` (lock every doctor row in the
shift before deciding), or introduce a row that represents the invariant — a
`shifts` row you lock — so both transactions collide on a real write-write
conflict. Or express the invariant as a constraint the database can enforce,
such as an exclusion constraint for overlapping bookings, which turns write skew
into a unique/exclusion violation instead.

**Q: What's the difference between 40001 and 40P01?**
A: `40001` is a serialization failure — no circular wait, Postgres simply cannot
order the transactions serially, so it aborts one. `40P01` is deadlock detected
— an actual cycle in the lock wait-for graph, found by the deadlock detector
after `deadlock_timeout` (default 1 second). Both are retryable, but they tell
you different things: 40001 says "your isolation level is doing its job",
40P01 says "your lock ordering is inconsistent".

**Q: Can I get read-your-writes with isolation levels?**
A: Not across connections — isolation is per transaction on one node. Reading
your own writes on a replica is a replication problem, handled in
[Module 06 — Read replicas](./06_Data_Distribution.md#63-read-replicas--the-read-after-write-problem).

### Red flags — do not say this

- ❌ "We use SERIALIZABLE so we don't have to think about concurrency." → ✅ "We
  use SERIALIZABLE on the transactions with cross-row invariants, and every one
  of them has a retry loop, because 40001 is expected, not exceptional."
- ❌ "Repeatable Read prevents all anomalies." → ✅ "It prevents non-repeatable
  reads and, in Postgres, phantoms — but not write skew."
- ❌ "Postgres supports Read Uncommitted." → ✅ "You can request it, and Postgres
  gives you Read Committed. Dirty reads are not implementable in its MVCC."

---

## 5.7 Locking

> **One-liner:** Locks are how the database serialises access to a row; deadlocks
> are what happens when two transactions take the same locks in different orders.

### Say this in the interview

> Postgres takes row-level locks automatically on every write and holds them
> until COMMIT. What I control is whether I take them early and explicitly.
> `SELECT ... FOR UPDATE` takes an exclusive row lock at read time, which turns
> a read-modify-write race into a queue — the second transaction waits instead
> of overwriting. The variant I use most is `FOR UPDATE SKIP LOCKED`, because it
> turns a table into a work queue: each worker claims rows nobody else has
> locked and skips the contended ones instead of blocking, so N workers pull
> disjoint batches with no coordination service. Deadlocks happen when two
> transactions grab the same two rows in opposite orders; Postgres detects the
> cycle after `deadlock_timeout`, which defaults to one second, and kills one
> transaction with SQLSTATE 40P01. The database resolves it — my job is to make
> it rare, and the way to do that is consistent lock ordering: if a transfer
> touches two accounts, always lock the lower account ID first. That one rule
> eliminates the entire class. Table-level locks matter mostly for DDL, where an
> ACCESS EXCLUSIVE lock blocks reads and writes, and a lock request that has to
> wait will queue every subsequent query behind it — which is how a one-second
> ALTER TABLE becomes a five-minute outage.

### Mental model

```
LOCK GRANULARITY

  row-level    taken by UPDATE/DELETE/SELECT FOR UPDATE
               held until COMMIT; stored in the tuple header + lock table
               N concurrent writers to N different rows = no contention

  table-level  taken by DDL, VACUUM FULL, and implicitly by DML (weak modes)
               ACCESS SHARE (SELECT) ... ACCESS EXCLUSIVE (ALTER TABLE)
               conflict matrix decides who waits


ROW LOCK MODES IN POSTGRES (weakest to strongest)

  FOR KEY SHARE     "I depend on this row's key existing"  (FK checks)
  FOR SHARE         "read it, nobody may change it"
  FOR NO KEY UPDATE "I will update non-key columns"
  FOR UPDATE        "I will update or delete it"           <- the usual one

  FOR UPDATE conflicts with everything. FOR SHARE conflicts only with
  the two UPDATE modes -- many readers can hold FOR SHARE at once.
```

**The lock queue is the part people miss.** Postgres lock requests are FIFO. A
weak lock does not jump ahead of a strong lock that is already waiting:

```
t0  long SELECT on orders (holds ACCESS SHARE, runs 5 min)
t1  ALTER TABLE orders ...  requests ACCESS EXCLUSIVE -> WAITS
t2  a normal SELECT         requests ACCESS SHARE     -> WAITS behind t1
t3  every subsequent query  -> WAITS
t4  connection pool exhausted -> the whole service is down

The ALTER never even started. This is why `SET lock_timeout` before DDL
is not optional.
```

**Deadlock, concretely:**

```
T1: BEGIN                            T2: BEGIN
T1: UPDATE accounts WHERE id=1  (locked)
                                     T2: UPDATE accounts WHERE id=2 (locked)
T1: UPDATE accounts WHERE id=2  -> waits on T2
                                     T2: UPDATE accounts WHERE id=1
                                           -> waits on T1
     ... 1 second (deadlock_timeout) ...
Postgres detects the cycle, kills the cheaper victim with 40P01.

FIX: order by primary key, always.
     T1 and T2 both lock id=1 then id=2. The second one simply waits.
```

### Enterprise production example

The queue-in-a-table pattern built on `SKIP LOCKED` is one of the most widely
deployed uses of Postgres locking in production. It backs **Sidekiq's Postgres
adapter, Solid Queue (Rails 8's default), Oban (Elixir), River (Go), Hatchet,
and pgmq**, and Postgres added `SKIP LOCKED` in 9.5 (2016) specifically to make
this pattern correct without advisory locks. The reason it matters
architecturally: for workloads under roughly a few thousand jobs per second, it
removes an entire component — no Redis, no RabbitMQ, no separate durability
story — and it makes job state transactional with your business data, which
kills the "job enqueued but the row was rolled back" class of bug outright. The
honest limit is that it is a polling consumer competing for the same rows, so
throughput ceilings and index bloat on the queue table arrive long before Kafka
would break a sweat.

### Code

The queue-in-a-table, production shaped — batch claim, visibility timeout,
attempt limit, and a dead-letter path.

```sql
CREATE TABLE jobs (
    id           bigserial PRIMARY KEY,
    queue        text        NOT NULL,
    payload      jsonb       NOT NULL,
    state        text        NOT NULL DEFAULT 'ready',   -- ready|running|dead
    run_after    timestamptz NOT NULL DEFAULT now(),
    attempts     int         NOT NULL DEFAULT 0,
    locked_until timestamptz
);

-- Partial index: only rows that can actually be claimed are indexed, so the
-- index stays small even when the table holds millions of finished jobs.
CREATE INDEX idx_jobs_claimable ON jobs (queue, run_after, id)
    WHERE state = 'ready';
```

```sql
-- Claim a batch. One statement: lock, update, and return the rows.
-- SKIP LOCKED means worker B does not wait on worker A -- it takes the next
-- unlocked rows. NOWAIT would error instead; plain FOR UPDATE would serialise
-- every worker behind one lock and destroy your parallelism.
UPDATE jobs
   SET state        = 'running',
       attempts     = attempts + 1,
       locked_until = now() + interval '5 minutes'
 WHERE id IN (
       SELECT id FROM jobs
        WHERE queue = $1
          AND state = 'ready'
          AND run_after <= now()
        ORDER BY run_after, id
        FOR UPDATE SKIP LOCKED
        LIMIT $2
 )
RETURNING id, payload, attempts;
```

```python
# The worker. Note: the transaction ends when the claim commits -- the job is
# executed OUTSIDE it, so a 30-second job does not hold a row lock for 30 s.
# `locked_until` is the visibility timeout that survives a worker crash.
async def run_worker(pool, queue: str, batch: int = 10):
    while True:
        async with pool.acquire() as conn:
            jobs = await conn.fetch(CLAIM_SQL, queue, batch)   # commits here
        if not jobs:
            await asyncio.sleep(1.0 + random.random())          # jittered poll
            continue
        for job in jobs:
            try:
                await handle(job["payload"])
                await pool.execute("DELETE FROM jobs WHERE id=$1", job["id"])
            except Exception:
                # Exponential backoff, then dead-letter. Never retry forever.
                if job["attempts"] >= 5:
                    await pool.execute(
                        "UPDATE jobs SET state='dead' WHERE id=$1", job["id"])
                else:
                    await pool.execute(
                        "UPDATE jobs SET state='ready', "
                        "run_after = now() + (interval '10 s' * 2^attempts) "
                        "WHERE id=$1", job["id"])

# Reaper: a crashed worker leaves rows in 'running' past locked_until.
RECLAIM = ("UPDATE jobs SET state='ready' "
           "WHERE state='running' AND locked_until < now()")
```

Consistent lock ordering, which removes deadlocks by construction:

```sql
-- Always lock in primary-key order, regardless of transfer direction.
BEGIN;
SELECT id, balance FROM accounts
 WHERE id IN ($from, $to)
 ORDER BY id                    -- <-- the entire fix
   FOR UPDATE;

UPDATE accounts SET balance = balance - $amt WHERE id = $from;
UPDATE accounts SET balance = balance + $amt WHERE id = $to;
COMMIT;
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `FOR UPDATE` when you must read-then-write the same row | Avoid it on a row every request touches (a global counter) | Serialised throughput on that row; everyone queues |
| `FOR UPDATE SKIP LOCKED` for queues and batch claims | Avoid when strict FIFO ordering is required — skipping breaks order | Polling overhead and index bloat on the queue table |
| Table-level locks only for DDL, always with `lock_timeout` | Never `LOCK TABLE` in application code | An ACCESS EXCLUSIVE wait queues the entire workload behind it |

### Follow-ups they will ask

**Q: `SKIP LOCKED` vs `NOWAIT` vs plain `FOR UPDATE` — when each?**
A: Plain `FOR UPDATE` waits, which is what you want for a transfer: the second
transaction should see the first one's result. `NOWAIT` errors immediately,
which is right when the caller has something better to do and you want to fail
fast rather than queue. `SKIP LOCKED` silently omits locked rows, which is only
correct when the rows are interchangeable — a job queue, a batch of pending
webhooks. Using `SKIP LOCKED` where rows are not interchangeable means silently
skipping work.

**Q: How does Postgres pick the deadlock victim?**
A: The backend that runs the deadlock detector — the one whose lock wait hit
`deadlock_timeout` — aborts itself. It is not "the cheapest transaction" in any
sophisticated sense, so do not design around which one survives. Design so the
cycle cannot form.

**Q: We're seeing deadlocks on a single-table UPDATE with no explicit locks. How?**
A: Usually a multi-row `UPDATE ... WHERE id IN (...)` where two transactions
supply the same IDs in different orders, so they acquire row locks in different
orders. Also common: foreign keys, where inserting a child row takes a
`FOR KEY SHARE` lock on the parent, and two inserts touching two parents in
opposite orders deadlock. Sorting IDs before the statement fixes the first;
inserting parents in a canonical order fixes the second. `log_lock_waits = on`
plus the deadlock detail in the log tells you which two statements collided.

**Q: What about advisory locks?**
A: `pg_advisory_lock` is an application-defined mutex keyed by an integer — good
for "only one instance runs this migration/cron". Two cautions: use the
transaction-scoped variant `pg_advisory_xact_lock`, because it releases at
COMMIT even if your code panics, and know that **session-scoped advisory locks
are broken under PgBouncer transaction pooling**, since the next statement may
land on a different backend. See [5.13](#513-connection-pooling).

### Red flags — do not say this

- ❌ "We use SELECT FOR UPDATE everywhere to be safe." → ✅ "I lock the rows I am
  about to modify, in a consistent order, and I keep the transaction short."
- ❌ "Deadlocks mean the database is broken." → ✅ "Deadlocks are detected and
  resolved automatically after `deadlock_timeout`. A rising rate means my lock
  ordering is inconsistent."
- ❌ "We'll use Redis for the job queue because Postgres can't do queues." →
  ✅ "`FOR UPDATE SKIP LOCKED` gives a transactional queue in Postgres up to a
  few thousand jobs/sec; past that, or when I need fan-out and replay, I move to
  a broker."

---

## 5.8 Optimistic vs pessimistic concurrency control

> **One-liner:** Pessimistic locking assumes you will collide and makes everyone
> queue; optimistic locking assumes you will not and makes the loser retry.

### Say this in the interview

> Pessimistic means I take the lock before I do the work — `SELECT ... FOR
> UPDATE` — so the second writer waits and always sees the first writer's
> result. Optimistic means I do not lock at all: I read a version number with
> the row, I do my work, and my UPDATE includes `WHERE version = the value I
> read`. If somebody else committed in between, the version has moved and my
> update matches zero rows, so I know I lost and I retry from the read. The
> choice is driven entirely by contention and by how long the work takes.
> Pessimistic wins when contention is high and the transaction is short —
> decrementing inventory, where retry storms would be worse than a queue.
> Optimistic wins when contention is low, or when the work between read and
> write is long or involves a human. Editing a document in a web form is the
> canonical case: I am not going to hold a database row lock for the four
> minutes somebody spends typing, so I version the row and tell the second saver
> that the document changed underneath them. The cost of optimistic is that
> under real contention it degrades badly — every conflicting writer does the
> work and throws it away — so I always instrument the conflict rate, and if it
> goes above a few percent that is a signal to change the data model, not to add
> retries.

### Mental model

```
PESSIMISTIC                          OPTIMISTIC
                                     
T1: SELECT ... FOR UPDATE  [LOCK]    T1: SELECT id, qty, version -> v=7
T2: SELECT ... FOR UPDATE  [WAIT]    T2: SELECT id, qty, version -> v=7
T1: UPDATE                           T1: UPDATE ... WHERE version=7  -> 1 row
T1: COMMIT         [LOCK RELEASED]   T1: COMMIT              (version now 8)
T2:   ...proceeds, sees T1's value   T2: UPDATE ... WHERE version=7  -> 0 rows
T2: UPDATE                           T2: detects 0 rows -> RETRY from SELECT
T2: COMMIT                           T2: re-reads v=8, recomputes, succeeds

cost: waiting (latency, and a          cost: wasted work (CPU, round trips)
      lock held across your slowest          and a retry loop you must write
      statement)
```

The decision rule, in one line each:

- **Contention high + transaction short** → pessimistic. A queue is cheaper than
  a retry storm.
- **Contention low** → optimistic. Locks you never needed cost latency on every
  request; retries you rarely take cost nothing on the happy path.
- **Long think-time between read and write (a human, an LLM call, a workflow)**
  → optimistic, always. Never hold a row lock across something you do not
  control the duration of.
- **The write is a pure function of the current value** → neither. Write
  `SET qty = qty - $1 WHERE id = $2 AND qty >= $1` and let the database do the
  arithmetic atomically in one statement. This is the answer people forget.

Optimistic locking also gives you something pessimistic does not: a *meaningful
error*. "This document was modified by someone else" is a UX affordance. "Your
request took 4 seconds waiting for a lock" is not.

### Enterprise production example

Optimistic concurrency is the default in every major ORM and in most cloud
data stores, because it is the only model that works when the client is remote
and might disappear. **Hibernate/JPA** has `@Version`, **Django** has
`select_for_update()` alongside conditional updates, **Rails** has
`lock_version`, **DynamoDB** has conditional writes
(`ConditionExpression: version = :expected`), **Etcd** has compare-and-swap on
`mod_revision`, and **HTTP itself** has it as `ETag` + `If-Match`, which returns
`412 Precondition Failed` — the same algorithm, one layer up. When an
interviewer asks how you would stop two users overwriting each other in a
collaborative editor, saying "ETag/If-Match at the API layer, backed by a
version column in Postgres, so the conflict is detected at the edge" is a
noticeably stronger answer than "a lock".

### Code

```sql
ALTER TABLE documents ADD COLUMN version integer NOT NULL DEFAULT 1;
```

```python
class StaleWriteError(Exception):
    """The row changed between our read and our write."""

async def save_document(pool, doc_id: str, expected_version: int, body: str,
                        editor_id: str) -> int:
    """Compare-and-swap. Returns the new version, or raises StaleWriteError.

    No lock is held while the user is typing -- expected_version came from the
    GET that rendered the editor, possibly minutes ago.
    """
    new_version = await pool.fetchval(
        """
        UPDATE documents
           SET body       = $3,
               version    = version + 1,
               updated_by = $4,
               updated_at = now()
         WHERE id = $1
           AND version = $2          -- the compare half of compare-and-swap
        RETURNING version
        """,
        doc_id, expected_version, body, editor_id)

    if new_version is None:
        # Zero rows matched: either the row is gone or somebody else won.
        current = await pool.fetchrow(
            "SELECT version, updated_by, updated_at FROM documents WHERE id=$1",
            doc_id)
        if current is None:
            raise LookupError(doc_id)
        raise StaleWriteError(
            f"document at version {current['version']}, you had {expected_version}; "
            f"last edited by {current['updated_by']} at {current['updated_at']}")
    return new_version
```

Surfacing it over HTTP, which is where it belongs for a human-facing edit:

```python
@app.put("/documents/{doc_id}")
async def put_document(doc_id: str, body: DocBody, request: Request):
    if_match = request.headers.get("if-match")
    if if_match is None:
        raise HTTPException(428, "If-Match header required")   # 428 Precondition Required
    try:
        v = await save_document(pool, doc_id, int(if_match.strip('"')),
                                body.text, request.state.user_id)
    except StaleWriteError as e:
        raise HTTPException(412, str(e))                        # 412 Precondition Failed
    return Response(status_code=204, headers={"ETag": f'"{v}"'})
```

And the case where neither is needed, because the database can do it in one
atomic statement:

```sql
-- No SELECT, no version column, no retry: the WHERE clause IS the guard.
-- Returns 0 rows if stock is insufficient, which the app treats as "sold out".
UPDATE inventory
   SET qty = qty - $2
 WHERE sku = $1 AND qty >= $2
RETURNING qty;
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Optimistic when conflicts are rare, or think-time is long/human | Avoid optimistic on a hot row many writers hit per second | Wasted work on every conflict; a retry loop; degrades superlinearly with contention |
| Pessimistic when contention is high and the transaction is milliseconds | Never hold the lock across network I/O or user input | Serialised throughput on the locked row; a lock-wait tail in your p99 |
| Single-statement conditional update when the new value derives from the old | Not applicable when the new value depends on external computation | Nothing — this is strictly the best option when it applies |

### Follow-ups they will ask

**Q: What do you actually use as the version — an integer, a timestamp, or a
hash?**
A: A monotonic integer, incremented by the same UPDATE. Timestamps are tempting
because they are already there, but clock resolution and clock skew make two
updates in the same millisecond indistinguishable, and `updated_at` is often
touched by unrelated code. A content hash works and doubles as a natural ETag,
at the cost of hashing the body on every read. Postgres's `xmin` system column
also works as a free version, though it changes on any update, including ones
your business logic considers a no-op.

**Q: Your optimistic retry rate hits 30%. What do you do?**
A: Stop adding retries and change the shape of the write. Thirty percent means
many writers are contending for one row, so I look at whether the row is really
one thing: a global counter becomes N sharded counters summed on read; a
per-tenant hot row becomes an append-only event table rolled up asynchronously;
a document that many people edit at once needs operational transforms or CRDTs,
not a version column. Optimistic concurrency is a detector of a modelling
problem as much as a solution.

**Q: How is this different from what SERIALIZABLE does?**
A: It is the same idea at a different layer. SSI is optimistic concurrency
control implemented by the database across whole transactions, detecting
read-write dependency cycles and aborting with 40001. A version column is
optimistic concurrency control implemented by me, on one row, with the conflict
made explicit as "zero rows updated". The version column is cheaper, works
across HTTP requests and connections, and gives me a domain-meaningful error;
SSI protects invariants that span rows I cannot enumerate.

### Red flags — do not say this

- ❌ "Optimistic locking is faster." → ✅ "Optimistic is faster when conflicts
  are rare and much worse when they are not. It's a bet on contention."
- ❌ "We lock the row while the user edits the form." → ✅ "We never hold a
  database lock across user think-time; we version the row and return 412 to the
  loser."

---

## 5.9 Indexes

> **One-liner:** An index is a second, sorted copy of one or more columns that
> turns a scan of N rows into roughly four page reads — and you pay for it on
> every write, forever.

### Say this in the interview

> A B-tree index is a balanced tree of 8-kilobyte pages where each internal page
> holds a few hundred keys, so the fan-out is high and the depth is tiny — even
> a table with a billion rows is about four levels deep, and the top two levels
> are almost always in cache. That is where the O(log n) comes from, and in
> practice it means a point lookup is three or four page reads instead of
> scanning gigabytes. The cost is that the index is a second data structure the
> database must keep in sync: every insert writes into every index on the table,
> every non-HOT update writes a new index entry in every index, and each index
> takes disk and memory that would otherwise be page cache. So the real question
> is never "should I index this column" but "does this index pay for itself on
> the queries that matter". Beyond plain B-trees, the ones I actually reach for
> are partial indexes — index only the rows a query cares about, like `WHERE
> status = 'pending'`, which keeps the index tiny on a huge table — expression
> indexes for things like `lower(email)`, covering indexes with INCLUDE so the
> query never touches the heap, and GIN for JSONB and full-text search. For the
> RAG work I do, pgvector adds HNSW, which is a navigable graph rather than a
> tree, and gives approximate nearest-neighbour in roughly logarithmic hops with
> a recall target you tune rather than a correct answer you get.

### Mental model — why B-tree is O(log n), with the arithmetic

```
Page = 8 KB. A bigint key + 6-byte heap pointer + overhead ~ 20-30 bytes,
so an internal page holds roughly 250-400 keys. Call it 250 to be safe.

  level 1 (root)       250 keys
  level 2              250^2 =        62,500
  level 3              250^3 =    15,625,000
  level 4              250^4 = 3,906,250,000     <- 3.9 BILLION rows

  => a 4-level B-tree covers essentially any OLTP table.
  => root and level 2 are permanently in shared_buffers.
  => a cold point lookup is ~2 physical reads; a warm one is 0.

         [ root ]                       <- always cached
        /   |    \
   [ ]    [ ]     [ ]                   <- almost always cached
   /|\    /|\     /|\
 leaves (sorted keys -> heap TIDs)      <- 1 read
                    |
                    v
              heap page                 <- 1 read (unless index-only scan)
```

A sequential scan of the same table reads every page: 100 GB at ~500 MB/s of
effective sequential throughput is roughly 200 seconds. That is the actual
difference the index is buying, and it is why "just add an index" works so
often — and why it is worth understanding when it does not
([5.12](#512-when-indexes-hurt)).

**Clustered vs non-clustered.** In MySQL InnoDB the primary key *is* the table:
rows are stored inside the PK B-tree (clustered), and every secondary index
stores the PK value, so a secondary lookup is two B-tree descents. **Postgres
has no clustered index at all** — rows live in an unordered heap and every index,
including the primary key, is a secondary index pointing at heap tuple IDs. Three
consequences to say out loud:

- Postgres primary keys can be random UUIDs without the insert-hotspot penalty
  that random PKs cause in InnoDB's clustered structure (though UUIDv7 is still
  better for cache locality and index density).
- Postgres index-only scans need the **visibility map** — the planner can skip
  the heap only for pages known all-visible, which is why an index-only scan
  degrades right after a bulk update until `VACUUM` runs.
- `CLUSTER table USING index` physically reorders the heap once, but it is not
  maintained; new rows go wherever there is room.

**The index types that earn their place in a Postgres schema:**

| Type | Answers | Use it for |
|---|---|---|
| **B-tree** (default) | `=`, `<`, `>`, `BETWEEN`, `IN`, prefix `LIKE 'abc%'`, `ORDER BY` | ~90% of everything |
| **Hash** | `=` only | Rarely worth it; B-tree also does `=` and does more. Only for very large keys where the smaller index matters |
| **GIN** | "does this composite value contain X" | JSONB `@>`, arrays, full-text `tsvector`, trigram `LIKE '%mid%'` |
| **GiST** | overlap / nearest-neighbour on ranges, geometry | `tstzrange &&` exclusion constraints, PostGIS |
| **BRIN** | min/max per block range | Huge append-only tables correlated with physical order (time-series). Tiny: kilobytes for a table of gigabytes |
| **HNSW** (pgvector) | approximate k-NN on embeddings | RAG retrieval; graph-based, ~O(log N) hops |
| **IVFFlat** (pgvector) | approximate k-NN via k-means lists | Large, mostly static vector corpora where build time and memory dominate |

**Partial and expression indexes** are the two highest-leverage tricks:

- A partial index indexes only rows matching a predicate. On a `jobs` table with
  50 million finished rows and 2,000 pending ones,
  `CREATE INDEX ... WHERE state = 'ready'` produces an index with 2,000 entries
  instead of 50 million. It is smaller, stays in cache, and costs nothing to
  maintain for the 99.99% of writes that do not match the predicate.
- An expression index indexes the *result* of a function. The planner will only
  use it when the query contains the identical expression, so
  `CREATE INDEX ON users (lower(email))` requires the query to say
  `WHERE lower(email) = $1`.

### Enterprise production example

**Discord's** move to ScyllaDB is usually told as a database-swap story, but the
indexing lesson underneath it is sharper: their read path was already a perfect
index lookup — partition key plus a sorted clustering key — and it was *still*
too slow, because thousands of concurrent requests for the same hot partition
piled onto the nodes owning it. Their fix was a Rust data-service layer that
used consistent hashing to route all requests for a given channel to the same
worker, then **coalesced** concurrent identical reads into a single database
query and fanned the result back out. The generalisable point for an interview:
an index reduces the cost of *one* query; it does nothing about issuing the same
query ten thousand times. Request coalescing and caching are the tools for that,
and they are complementary to indexing, not alternatives.

### Code

```sql
-- 1. Partial index: 2,000 entries instead of 50,000,000.
CREATE INDEX CONCURRENTLY idx_jobs_ready
    ON jobs (queue, run_after)
 WHERE state = 'ready';

-- 2. Expression index for case-insensitive login. The query MUST match.
CREATE UNIQUE INDEX CONCURRENTLY idx_users_email_lower
    ON users (lower(email));
-- uses it:      WHERE lower(email) = lower($1)
-- does NOT:     WHERE email ILIKE $1

-- 3. Covering index -> index-only scan. INCLUDE columns are stored in the
--    leaf but are not part of the key, so they do not affect ordering or
--    uniqueness and do not bloat internal pages.
CREATE INDEX CONCURRENTLY idx_orders_customer_covering
    ON orders (customer_id, created_at DESC) INCLUDE (status, total_cents);
--    SELECT status, total_cents FROM orders
--     WHERE customer_id=$1 ORDER BY created_at DESC LIMIT 20;
--    -> Index Only Scan, zero heap fetches (once VACUUM has set the vis. map)

-- 4. GIN on JSONB, for containment queries on semi-structured metadata.
--    jsonb_path_ops is ~3x smaller than the default opclass and supports @>.
CREATE INDEX CONCURRENTLY idx_events_payload
    ON events USING gin (payload jsonb_path_ops);
--    WHERE payload @> '{"type":"invoice.paid"}'

-- 5. Full-text search, generated column so it can never drift from the source.
ALTER TABLE documents ADD COLUMN tsv tsvector
    GENERATED ALWAYS AS (to_tsvector('english', coalesce(title,'') || ' ' ||
                                                coalesce(body,''))) STORED;
CREATE INDEX CONCURRENTLY idx_documents_tsv ON documents USING gin (tsv);

-- 6. Trigram index for substring / fuzzy match, which B-tree cannot do.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY idx_customers_name_trgm
    ON customers USING gin (name gin_trgm_ops);
--    WHERE name ILIKE '%acme%'   -> index scan instead of seq scan
```

The RAG-relevant one, with the parameters that actually matter:

```sql
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE chunks ADD COLUMN embedding vector(1536);

-- HNSW: graph index. m = links per node, ef_construction = build-time search
-- width. Both are immutable after build, so choose deliberately.
-- Raise maintenance_work_mem first or the build spills to disk and crawls.
SET maintenance_work_mem = '4GB';
CREATE INDEX CONCURRENTLY idx_chunks_embedding
    ON chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ef_search is the query-time recall/latency dial -- the only one you can
-- change without rebuilding. Default 40; 64 for interactive, 128-256 for batch.
SET LOCAL hnsw.ef_search = 64;

SELECT id, content, 1 - (embedding <=> $1) AS similarity
  FROM chunks
 WHERE tenant_id = $2                     -- pre-filter; see the follow-up below
 ORDER BY embedding <=> $1
 LIMIT 20;
```

Concrete tuning facts for pgvector worth carrying into an interview: HNSW is the
right default for live data because it absorbs inserts without recall
degradation and reaches 95%+ recall out of the box, at roughly 2–5× the memory
of IVFFlat. IVFFlat builds far faster and is much smaller, but its recall drifts
as data shifts away from the original k-means centroids, so it suits large,
mostly static corpora you can afford to reindex. In one published 500k-vector,
384-dimension benchmark, IVFFlat built in 47 seconds versus HNSW's 3m12s, while
HNSW returned 98.7% recall at 18 ms p99 against IVFFlat's 94.2% at 45 ms p99 —
the shape of that trade holds even though the absolute numbers are
hardware-specific.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| B-tree on any column in a selective `WHERE` or `ORDER BY` on a hot query | Avoid on low-cardinality columns (`status` with 3 values) unless partial | ~10–20% of table size per index, plus a write to it on every insert |
| Partial index when the hot query always carries the same predicate | Avoid when the predicate varies per caller | The planner uses it only when it can prove the query implies the predicate |
| Covering/INCLUDE when a hot query reads 2–3 small columns | Avoid stuffing wide columns into INCLUDE | Larger leaf pages; index-only scans need vacuum to keep the visibility map fresh |
| GIN for JSONB containment and full-text | Avoid GIN on a write-hot table without tuning | GIN updates are expensive; the pending-list (`fastupdate`) trades write speed for read spikes |
| HNSW for production vector search | Avoid when the index cannot fit in RAM | Memory, slow builds, and a recall target rather than an exact answer |

### Follow-ups they will ask

**Q: Why is my index not being used?**
A: Five usual causes, in the order I check them. One, the query does not match
the index expression — `WHERE lower(email)=` needs an index on `lower(email)`, and
a function or implicit cast around the column defeats it. Two, the leading column
of a composite index is not in the predicate ([5.10](#510-composite-indexes--the-leftmost-prefix-rule)).
Three, the query is not selective enough — if it returns 30% of the table, a
sequential scan genuinely is faster and the planner is right. Four, statistics
are stale, so run `ANALYZE`. Five, a type mismatch: a `bigint` column compared to
a text parameter, or `varchar` compared under a different collation.

**Q: How does a filtered vector search interact with the HNSW index?**
A: Badly, if the filter is very selective, and this bites RAG systems
constantly. The ANN graph traversal does not know about your `WHERE tenant_id =
$1`, so pgvector walks the graph and discards non-matching neighbours, which can
return fewer than `LIMIT` rows or force a fallback to a full scan. The mitigations
are: raise `hnsw.ef_search` so more candidates survive the filter, use pgvector
0.8+ iterative index scans which re-enter the graph when the filter eats the
results, or physically partition the table by tenant so each partition has its
own smaller HNSW index. For strict multi-tenant isolation, partitioning is the
answer that also solves the security question.

**Q: What is a HOT update and why should I care?**
A: A Heap-Only Tuple update — when the new row version fits on the same page and
**no indexed column changed**, Postgres links the new version to the old within
the page and skips writing to any index. That is the difference between an
update costing one page write and costing one write per index. It is a direct
argument against indexing columns that change frequently, and an argument for
leaving `fillfactor` below 100 on update-heavy tables so there is room on the
page.

**Q: Should the primary key be a UUID?**
A: In Postgres it is fine, because there is no clustered index to fragment, but
random UUIDv4 keys still hurt: they scatter inserts across the whole B-tree, so
the working set of dirty leaf pages is large and the index compresses poorly.
UUIDv7 is time-ordered, so inserts land at the right edge of the tree like a
bigserial while remaining globally unique and non-guessable. That is my default
when I need client-generated IDs.

**Q: How many indexes is too many?**
A: The number where write latency on your hot table stops meeting its budget.
The way to find dead weight is `pg_stat_user_indexes`: any index with
`idx_scan = 0` after a full business cycle is pure cost. Also look for redundant
prefixes — if you have `INDEX(a, b)` you almost never also need `INDEX(a)`.

### Red flags — do not say this

- ❌ "Index every column in the WHERE clauses." → ✅ "I index the columns the
  high-volume queries filter and sort on, then remove the ones
  `pg_stat_user_indexes` shows are never scanned."
- ❌ "Indexes make the database faster." → ✅ "Indexes make reads faster and
  writes slower. On a write-heavy table that trade can go the wrong way."
- ❌ "We added an index and the query is still slow, so indexes don't help." →
  ✅ "Let me read the plan — either the index does not match the predicate, the
  query is not selective, or the cost is heap fetches, which a covering index
  would remove."

---
## 5.10 Composite indexes & the leftmost-prefix rule

> **One-liner:** A composite index is sorted by column A, then by B within equal
> A — so it can answer anything that starts with A, and nothing that starts with
> B.

### Say this in the interview

> A composite index on (a, b) is one sorted structure: it orders by a, and
> within each equal value of a it orders by b. That single sentence explains
> every rule people memorise. It can serve `WHERE a = 1`, because that is a
> contiguous range. It can serve `WHERE a = 1 AND b = 2`, because within a = 1
> the b values are sorted. It cannot efficiently serve `WHERE b = 2` alone,
> because the b values are scattered across every a group — that is the
> leftmost-prefix rule, and it is why INDEX(a, b) is not INDEX(b, a). For
> ordering the columns I put equality predicates first, then the range or sort
> column last, because once you hit a range the index can no longer use later
> columns to narrow the scan. So for `WHERE tenant_id = ? AND status = ? ORDER
> BY created_at DESC`, the index is (tenant_id, status, created_at DESC), and it
> serves the filter and the sort in one scan with no sort node in the plan. The
> mistake I see most is ordering by cardinality alone — people put the most
> selective column first as a reflex — when what actually matters is whether the
> column is used with equality or with a range.

### Mental model

```
INDEX (tenant_id, status, created_at)   -- physical order in the leaf pages

  tenant=1, status='open',   2026-08-01
  tenant=1, status='open',   2026-08-14
  tenant=1, status='open',   2026-09-01   <-- contiguous: one range scan
  tenant=1, status='closed', 2026-07-02
  tenant=1, status='closed', 2026-08-30
  tenant=2, status='open',   2026-06-11
  tenant=2, status='open',   2026-09-01
  ...

WHERE tenant_id=1                              -> range scan       YES
WHERE tenant_id=1 AND status='open'            -> tighter range    YES
WHERE tenant_id=1 AND status='open'
      ORDER BY created_at DESC                 -> range, no sort   YES
WHERE tenant_id=1 AND created_at > '2026-08'   -> scans BOTH status
                                                  groups, filters  PARTIAL
WHERE status='open'                            -> scattered        NO
                                                  (seq scan, or a
                                                   slow full index scan)
```

**The ordering rule, in priority order:**

1. **Equality predicates first.** Every `col = value` in the hot query.
2. **Then the range or inequality column**, and only one of them — the index
   stops narrowing after the first range.
3. **Then the `ORDER BY` column**, matching its direction, so the plan has no
   Sort node.
4. **Then `INCLUDE` columns** the query selects but never filters on, to get an
   index-only scan.

Cardinality only breaks ties *within* the equality group. If both `tenant_id`
and `status` are equality predicates, put the more selective one first so the
scanned range is smaller — but never promote a low-selectivity equality column
above a high-selectivity one at the cost of breaking rule 2.

**Direction matters for multi-column sorts.** An index on `(a ASC, b DESC)` can
serve `ORDER BY a ASC, b DESC` and, read backwards, `ORDER BY a DESC, b ASC`. It
cannot serve `ORDER BY a ASC, b ASC` without a sort. Postgres reads indexes
backwards for free, so a single-column `ORDER BY x DESC` never needs a `DESC`
index — the direction only matters when mixing.

### Enterprise production example

**Uber Schemaless** turned the leftmost-prefix rule into an architectural
constraint. Every Schemaless secondary index designates one of its fields as the
**shard field**, and that field must be supplied at query time — because it
determines which shard holds the index entry. An index on
`(driver_partner_uuid, city)` cannot answer a query that supplies only `city`,
not because of an optimiser limitation but because the system would not know
which of the 4,096 shards to ask. This is the same rule as a local B-tree
prefix, promoted to the distribution layer, and it is a good thing to name in a
sharding interview: **the leftmost prefix of your index and the partition key of
your cluster are the same idea at two scales.**

### Code

Worked example — a multi-tenant orders table, four real queries, and the two
indexes that serve them.

```sql
-- The queries, in descending order of volume.
-- Q1 (2,400 rps): tenant's recent orders page
SELECT id, total_cents, status FROM orders
 WHERE tenant_id = $1 AND status = 'open'
 ORDER BY created_at DESC LIMIT 50;

-- Q2 (300 rps): one customer's order history
SELECT * FROM orders WHERE tenant_id = $1 AND customer_id = $2
 ORDER BY created_at DESC LIMIT 20;

-- Q3 (40 rps): reconciliation sweep over a time window, all statuses
SELECT id, total_cents FROM orders
 WHERE tenant_id = $1 AND created_at BETWEEN $2 AND $3;

-- Q4 (2 rps): global admin lookup by external reference
SELECT * FROM orders WHERE external_ref = $1;
```

```sql
-- Serves Q1 fully: two equality columns, then the sort column in matching
-- direction, then the payload. No Sort node, no heap fetch.
CREATE INDEX CONCURRENTLY idx_orders_tenant_status_created
    ON orders (tenant_id, status, created_at DESC)
    INCLUDE (total_cents);

-- Serves Q2 fully and Q3 partially. Q3 supplies tenant_id (equality) and a
-- created_at range; this index scans that range and filters customer_id out,
-- which is acceptable at 40 rps. A third index would not pay for itself.
CREATE INDEX CONCURRENTLY idx_orders_tenant_customer_created
    ON orders (tenant_id, customer_id, created_at DESC);

-- Q4 is low volume but the alternative is a full scan of a huge table.
CREATE UNIQUE INDEX CONCURRENTLY idx_orders_external_ref
    ON orders (external_ref);

-- NOT created, deliberately:
--   (status, tenant_id, created_at)  -- status is 4 values; wrong leading col
--   (tenant_id)                      -- redundant prefix of the first index
--   (created_at)                     -- no query filters on time alone
```

Proving the ordering matters, on a 10-million-row table:

```sql
-- WRONG ORDER: index on (created_at, tenant_id, status)
EXPLAIN (ANALYZE) SELECT ... WHERE tenant_id=42 AND status='open'
                              ORDER BY created_at DESC LIMIT 50;

  Limit (actual time=812.443..812.470 rows=50 loops=1)
    ->  Index Scan Backward using idx_wrong on orders
          (actual time=812.441..812.462 rows=50 loops=1)
          Filter: ((tenant_id = 42) AND (status = 'open'))
          Rows Removed by Filter: 1284119          <-- scanned 1.28M to find 50

-- RIGHT ORDER: index on (tenant_id, status, created_at DESC)
  Limit (actual time=0.038..0.061 rows=50 loops=1)
    ->  Index Only Scan using idx_orders_tenant_status_created on orders
          (actual time=0.036..0.053 rows=50 loops=1)
          Index Cond: ((tenant_id = 42) AND (status = 'open'))
          Heap Fetches: 0                          <-- scanned exactly 50
```

Same columns, same table, 13,000× fewer rows examined. `Rows Removed by Filter`
is the number to look for: it is the index telling you it could not narrow.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| One composite index serving filter + sort of a top query | Avoid creating one index per query variation | Each index is a full write cost; three narrow indexes usually lose to one well-ordered composite |
| Add `INCLUDE` columns to reach an index-only scan | Avoid including wide text/JSONB columns | Leaf pages grow, the index falls out of cache, and you lose the benefit |
| Put a low-cardinality equality column in the middle of the key | Avoid it as the leading column | A leading `status` column with 4 values means every scan starts by picking one of 4 huge ranges |

### Follow-ups they will ask

**Q: I have INDEX(a, b). Do I also need INDEX(a)?**
A: No — `WHERE a = 1` uses the leftmost prefix of the composite index directly.
The only reason to keep a separate `INDEX(a)` is if it is dramatically smaller
and the query is extremely hot, and even then the composite index is usually
already in cache. Redundant prefix indexes are the most common form of dead
index weight I find in real schemas.

**Q: Then why not one giant index on every column?**
A: Because the index size grows with every column, so fewer entries fit per
page, the tree gets deeper and colder, and every write pays to maintain all of
it. A composite index also only helps queries whose predicates form a prefix, so
a six-column index mostly serves the same queries a three-column one would.

**Q: Postgres can combine two separate indexes — doesn't that solve it?**
A: It can, via a **Bitmap And**: scan both indexes, build bitmaps of matching
heap pages, intersect them, then do a bitmap heap scan. That is genuinely useful
for ad-hoc combinations, but it is strictly worse than one composite index for a
known hot query, because it reads two indexes and then visits heap pages in
physical order, losing your sort order — so an `ORDER BY ... LIMIT 50` still
needs a full sort of the matched set.

**Q: How does the index interact with pagination?**
A: This is where composite indexes pay off twice. `OFFSET 100000` makes the
database walk and discard 100,000 index entries, so page 2,000 is 2,000× slower
than page 1. Keyset pagination — `WHERE (created_at, id) < ($1, $2) ORDER BY
created_at DESC, id DESC LIMIT 50` — uses the index to jump straight to the
right position, so every page costs the same. The tuple comparison needs the
index columns in exactly that order, which is another reason to get the ordering
right.

### Red flags — do not say this

- ❌ "Put the most selective column first." → ✅ "Equality columns first, then
  the range or sort column. Selectivity only orders the equality columns among
  themselves."
- ❌ "The order of columns in an index doesn't really matter." → ✅ "It decides
  which queries the index can serve at all."

---

## 5.11 Reading query plans

> **One-liner:** `EXPLAIN` shows what the planner intends; `EXPLAIN (ANALYZE,
> BUFFERS)` shows what actually happened — and the gap between estimated and
> actual rows is where the bug usually is.

### Say this in the interview

> I run `EXPLAIN (ANALYZE, BUFFERS)` and read it inside out, because the deepest
> node runs first. Three things tell me almost everything. First, the ratio
> between estimated rows and actual rows — if the planner expected 100 rows and
> got 90,000, every decision above that node is built on a wrong number, and the
> fix is usually stale statistics, a correlated pair of columns the planner
> assumes are independent, or a filter it cannot estimate. Second, `Rows Removed
> by Filter`: if a node examined nine million rows to return ninety, the index
> is not narrowing and I need a different one. Third, `Buffers` — shared hit
> versus read tells me whether I am CPU-bound on cached pages or I/O-bound, and
> whether the fix is a better index or more memory. The scan types themselves
> are not good or bad in isolation: a sequential scan on a small table is
> correct, a bitmap heap scan is the planner combining indexes or hitting many
> scattered rows, and a nested loop is right for a handful of outer rows and
> catastrophic for a million, which is exactly what a bad row estimate causes.

### Mental model

```
READ IT INSIDE OUT AND BOTTOM UP. Deepest indentation = executed first.

Limit
  -> Sort                      \
       -> Hash Join             |  each arrow is "feeds into"
            -> Seq Scan         |
            -> Hash             /
                 -> Seq Scan

EVERY NODE PRINTS:
  (cost=START..TOTAL rows=EST width=BYTES)
  (actual time=FIRST_ROW..LAST_ROW rows=ACTUAL loops=N)

  cost      arbitrary planner units. Only useful for comparing plans.
  rows=EST  what the planner believed.
  rows=ACT  what happened.  EST vs ACT off by >10x  ==  investigate.
  loops=N   the node ran N times. TOTAL time = actual time x loops.
            (This is the single most misread number in EXPLAIN output.)
```

**Scan types, and what each one is telling you:**

| Node | Means | Good when | Alarm when |
|---|---|---|---|
| `Seq Scan` | Read every page | Small table, or returning >~10–20% of rows | Large table + tiny result + `Rows Removed by Filter` in the millions |
| `Index Scan` | Walk the index, fetch each heap row | Few, selective rows | Thousands of loops — random heap I/O dominates |
| `Index Only Scan` | Answer entirely from the index | Best case | `Heap Fetches` is high → visibility map stale, run `VACUUM` |
| `Bitmap Index Scan` + `Bitmap Heap Scan` | Collect matching TIDs, sort by page, then read the heap sequentially | Medium selectivity, scattered rows | `Recheck Cond` with `lossy=` blocks → `work_mem` too small |

**Join types:**

| Node | Algorithm | Right when | Disaster when |
|---|---|---|---|
| `Nested Loop` | For each outer row, probe inner | Outer side is tiny (tens of rows) and inner has an index | The row estimate on the outer side was wrong — 100 expected, 1M actual, so you do 1M index probes |
| `Hash Join` | Build a hash of the smaller side, probe with the larger | Both sides large, equality join, hash fits in `work_mem` | `Batches: 8` — the hash spilled to disk |
| `Merge Join` | Both inputs sorted, zip them | Both sides already sorted by an index | A `Sort` node underneath sorting a huge input |

### Enterprise production example

**Figma's DBProxy** shows what query plans look like once you leave a single
node. DBProxy is a Go service that parses each SQL statement into an AST, has a
logical planner extract the query type and target shard IDs from that AST, then
a physical planner map logical shards to physical databases and rewrite the
query for each. It also implements **scatter-gather**, so `SELECT * FROM table`
fans out to every shard and merges the results. The reason to know this: on a
single Postgres node, the planner is invisible infrastructure; the moment you
shard, somebody has to write a second planner, and that planner is much dumber
than Postgres's. Every cross-shard join and every unfiltered `ORDER BY` becomes
your problem, in your code. That is a substantial part of the true cost of
sharding — see
[Module 06 — Cross-shard problems](./06_Data_Distribution.md#68-cross-shard-problems).

### Code

A real annotated plan. Query: the last 50 shipped orders in the past week, with
the customer name. Table: 10 million orders, 130,000 customers.

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT o.id, o.total_cents, c.name
  FROM orders o
  JOIN customers c ON c.id = o.customer_id
 WHERE o.status = 'shipped'
   AND o.created_at >= now() - interval '7 days'
 ORDER BY o.created_at DESC
 LIMIT 50;
```

**Before — 3.2 seconds:**

```
Limit  (cost=254318.42..254318.55 rows=50 width=44)
       (actual time=3184.221..3184.238 rows=50 loops=1)
  Buffers: shared hit=1204 read=182367                      -- (5)
  ->  Sort  (cost=254318.42..254515.09 rows=78667 width=44)
            (actual time=3184.219..3184.229 rows=50 loops=1)
        Sort Key: o.created_at DESC
        Sort Method: top-N heapsort  Memory: 32kB           -- (4)
        ->  Hash Join  (cost=3891.00..251703.88 rows=78667 width=44)
                       (actual time=41.902..3106.744 rows=91204 loops=1)
              Hash Cond: (o.customer_id = c.id)
              ->  Seq Scan on orders o                      -- (1)
                    (cost=0.00..247218.00 rows=78667 width=24)
                    (actual time=0.312..3020.118 rows=91204 loops=1)
                    Filter: ((status = 'shipped'::text)
                             AND (created_at >= (now() - '7 days'::interval)))
                    Rows Removed by Filter: 9908796         -- (2)
              ->  Hash  (cost=2266.00..2266.00 rows=130000 width=28)
                        (actual time=41.402..41.403 rows=130000 loops=1)
                    Buckets: 131072  Batches: 1  Memory Usage: 8974kB  -- (3)
                    ->  Seq Scan on customers c
                          (actual time=0.008..18.221 rows=130000 loops=1)
Planning Time: 0.284 ms
Execution Time: 3184.401 ms
```

1. **Seq Scan on a 10M-row table.** Not automatically wrong — but look at (2).
2. **`Rows Removed by Filter: 9,908,796`.** It read 10 million rows to keep
   91,204. That is a missing index, stated numerically.
3. **`Batches: 1`** — the hash of `customers` fit in `work_mem`. If this said
   `Batches: 8`, the join spilled to disk and raising `work_mem` would help.
4. **`top-N heapsort`** — the planner knew about the `LIMIT 50` and kept only 50
   rows, so the sort is cheap. `Sort Method: external merge Disk: 148MB` would
   mean it spilled.
5. **`read=182367`** — 182k pages (~1.4 GB) came from disk, not cache. This is an
   I/O-bound plan, and the estimate/actual ratio (78,667 vs 91,204) is
   *fine* — the estimate was not the problem. The access path was.

**The fix:**

```sql
CREATE INDEX CONCURRENTLY idx_orders_shipped_recent
    ON orders (created_at DESC)
    INCLUDE (customer_id, total_cents)
 WHERE status = 'shipped';
```

**After — 1.5 milliseconds:**

```
Limit  (cost=0.56..214.83 rows=50 width=44)
       (actual time=0.061..1.402 rows=50 loops=1)
  Buffers: shared hit=214                                   -- all cached
  ->  Nested Loop  (cost=0.56..337.12 rows=79 width=44)
                   (actual time=0.059..1.381 rows=50 loops=1)
        ->  Index Only Scan Backward using idx_orders_shipped_recent on orders o
              (actual time=0.031..0.140 rows=50 loops=1)
              Index Cond: (created_at >= (now() - '7 days'::interval))
              Heap Fetches: 0                               -- covering worked
        ->  Index Scan using customers_pkey on customers c
              (actual time=0.021..0.022 rows=1 loops=50)    -- loops=50!
              Index Cond: (id = o.customer_id)
Planning Time: 0.331 ms
Execution Time: 1.489 ms
```

Note the `loops=50` on the inner side: the reported `actual time=0.021..0.022`
is *per loop*, so the true cost of that node is 50 × 0.022 ≈ 1.1 ms — most of
the query. Nested Loop is correct here precisely because the outer side is
exactly 50 rows. If the row estimate had been wrong and the outer side were a
million rows, this same plan would take twenty minutes.

**How to spot a bad row estimate, and what to do:**

```sql
-- The tell: estimated rows and actual rows differ by >10x on any node.
--   rows=100 ... actual rows=91204        <-- planner is flying blind

-- 1. Stale stats. Cheapest fix, try first.
ANALYZE orders;

-- 2. Correlated columns. The planner multiplies selectivities assuming
--    independence, so (country='JP' AND city='Tokyo') is estimated far too
--    low. Extended statistics teach it the correlation.
CREATE STATISTICS orders_geo (dependencies, ndistinct)
    ON country, city FROM orders;
ANALYZE orders;

-- 3. Skewed column with more distinct values than the sample sees.
ALTER TABLE orders ALTER COLUMN tenant_id SET STATISTICS 1000;  -- default 100
ANALYZE orders;

-- 4. Find the queries worth doing this to, instead of guessing.
SELECT calls, round(mean_exec_time::numeric, 2) AS mean_ms,
       round(total_exec_time::numeric / 1000, 1) AS total_s,
       left(query, 70) AS query
  FROM pg_stat_statements
 ORDER BY total_exec_time DESC
 LIMIT 20;   -- optimise by TOTAL time, not by slowest single call
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `EXPLAIN (ANALYZE, BUFFERS)` as the first step of any slow-query investigation | Never run bare `EXPLAIN ANALYZE` on a `DELETE`/`UPDATE` in production — it executes | Wrap in a transaction and `ROLLBACK`, or use plain `EXPLAIN` |
| Extended statistics for known-correlated columns | Avoid adding them everywhere | Extra `ANALYZE` time and planning time |
| `auto_explain` to capture plans of slow queries in production | Avoid `log_min_duration = 0` on a busy system | Log volume; use a threshold and `auto_explain.log_analyze` sparingly |

### Follow-ups they will ask

**Q: What does a bad row estimate actually break?**
A: Join order and join method, which are chosen from the estimates. The classic
failure is a Nested Loop chosen because the planner expected 20 outer rows;
1 million arrive, and now you are doing a million index probes in a loop. The
query does not get 50,000× slower because the data is bigger — it gets slower
because the *plan* was chosen for a different data size.

**Q: The plan is fine in staging and terrible in production. Why?**
A: Different statistics and different data distributions, usually. Also check
whether production is using a generic plan: with prepared statements, Postgres
switches to a generic plan after five executions if it looks safe, which can be
badly wrong for a skewed parameter — `plan_cache_mode = force_custom_plan`
diagnoses it. And check `work_mem`: the same plan spills to disk on one box and
not the other.

**Q: When is a sequential scan the right answer?**
A: When the query returns a large fraction of the table — past roughly 10–20%,
reading pages sequentially beats thousands of random index-plus-heap fetches, so
the planner is making the correct call. Also on small tables, where the whole
thing is one or two pages. Forcing an index scan there with
`enable_seqscan = off` makes the query slower and is only a diagnostic tool, not
a fix.

**Q: You have five seconds and one query. What do you look at?**
A: `Rows Removed by Filter` and the estimated-versus-actual ratio on the deepest
node. Those two numbers identify a missing index and a statistics problem
respectively, and between them they explain most slow OLTP queries.

### Red flags — do not say this

- ❌ "Seq Scan means a missing index." → ✅ "Seq Scan on a large table returning
  a tiny fraction means a missing index. On a small table it is the right plan."
- ❌ "The cost number says 254318, so it takes 254 seconds." → ✅ "Cost is in
  arbitrary planner units and is only meaningful for comparing plans. `actual
  time` is the real measurement."
- ❌ "The inner node took 0.02 ms, so it's free." → ✅ "That is per loop, and it
  ran 50 times, so it is 1.1 ms of the 1.5 ms total."

---

## 5.12 When indexes hurt

> **One-liner:** Every index is a tax on every write to that table, paid forever,
> whether or not any query uses it.

### Say this in the interview

> An index is a second data structure the database has to keep consistent, so
> every insert writes to the table and to every index on it, and every update
> that touches an indexed column writes a new entry in every index — that is
> write amplification. On a table with eight indexes an insert is doing nine
> writes, and it is doing them to nine different places in the storage, so it is
> also nine sets of dirty pages and nine sets of WAL records. The specific cases
> where an index is actively harmful are: low-cardinality columns, where a
> boolean index cannot narrow anything so the planner ignores it while you still
> pay to maintain it; redundant prefixes, where `INDEX(a)` sits next to
> `INDEX(a, b)` doing nothing; and indexes on columns that change on every
> update, because that turns what would have been a cheap heap-only update into
> a full index write. Bloat is the other half — Postgres never updates an index
> entry in place, so a churning table accumulates dead entries until the index is
> several times the size it needs to be and no longer fits in cache. I audit with
> `pg_stat_user_indexes` for `idx_scan = 0` and drop what nothing uses, and I
> `REINDEX CONCURRENTLY` when the bloat estimate gets bad rather than letting the
> index silently fall out of memory.

### Mental model

```
ONE INSERT INTO a table with 5 indexes

  heap:     1 page write   + WAL
  index 1:  1 leaf write   + WAL   (+ page split, sometimes)
  index 2:  1 leaf write   + WAL
  index 3:  1 leaf write   + WAL
  index 4:  1 leaf write   + WAL
  index 5:  1 leaf write   + WAL
  --------------------------------
            6 writes, 6 WAL records, 6 dirty pages, 6 random I/Os

ONE UPDATE, and why HOT matters so much:

  no indexed column changed AND the page has free space
      -> HOT update: new tuple on the same page, indexes untouched
      -> 1 write

  ANY indexed column changed (or the page is full)
      -> new tuple + a new entry in EVERY index
      -> 6 writes, and the old entries become dead weight until VACUUM
```

**The five ways an index costs you more than it gives:**

1. **Write amplification** on a hot insert path. This is the big one, and the
   only honest way to size it is to measure — but the direction is guaranteed,
   and on write-saturated tables the effect is large enough to see in p99.
2. **Low cardinality.** An index on `is_active` where 97% of rows are `true`
   cannot narrow the scan, so the planner correctly ignores it — and you pay to
   maintain it on every write anyway. The fix is a *partial* index on the rare
   value: `WHERE is_active = false`.
3. **Too many indexes.** Every one competes for `shared_buffers`. Nine indexes
   on a table means the useful three are being evicted by the six that are not.
4. **Bloat.** Postgres marks index entries dead rather than removing them.
   Repeated update/delete churn leaves an index physically much larger than its
   live contents, which pushes it out of cache. `REINDEX CONCURRENTLY` (PG12+)
   rebuilds without blocking writes.
5. **Blocking HOT updates.** Indexing `updated_at` or `last_seen_at` — columns
   written on every single update — converts every cheap in-page update into a
   full multi-index write. This one is subtle and common.

### Enterprise production example

**Uber's** move off Postgres to MySQL for Schemaless was driven substantially by
write amplification, and the mechanism is worth knowing because it is the
sharpest published example of this trade. In Postgres, every update writes a new
physical row version and therefore **a new entry in every index**, because
indexes point at physical tuple locations. In MySQL InnoDB, secondary indexes
point at the *primary key*, not at a physical location, so updating a
non-indexed column does not require touching secondary indexes at all — the row
moves within the clustered index and the secondary indexes still point at the
same PK. For Uber's update-heavy trip records, that difference in index
maintenance cost — combined with the WAL/replication volume it generated — was a
first-order concern, not a micro-optimisation. Postgres's HOT-update
optimisation covers the same case when no indexed column changed and the page
has room, which is exactly why `fillfactor` and not indexing `updated_at` are
real tuning levers.

### Code

The audit queries. Run these quarterly; they routinely find 20–40% of indexes
are dead weight.

```sql
-- 1. Never-used indexes. Check uptime first: stats reset on restart, and a
--    quarterly report's index will show 0 scans if you only look at a week.
SELECT s.schemaname, s.relname AS table, s.indexrelname AS index,
       s.idx_scan,
       pg_size_pretty(pg_relation_size(s.indexrelid)) AS size
  FROM pg_stat_user_indexes s
  JOIN pg_index i ON i.indexrelid = s.indexrelid
 WHERE s.idx_scan = 0
   AND NOT i.indisunique                 -- never drop a constraint's index
   AND NOT i.indisprimary
 ORDER BY pg_relation_size(s.indexrelid) DESC;

-- 2. Write amplification per table: how much index maintenance is this
--    table's write traffic actually causing?
SELECT relname,
       n_tup_ins + n_tup_upd + n_tup_del AS writes,
       n_tup_hot_upd,
       round(100.0 * n_tup_hot_upd / NULLIF(n_tup_upd, 0), 1) AS hot_pct,
       pg_size_pretty(pg_indexes_size(relid)) AS index_bytes,
       pg_size_pretty(pg_table_size(relid))   AS table_bytes
  FROM pg_stat_user_tables
 ORDER BY writes DESC
 LIMIT 20;
-- hot_pct below ~50% on an update-heavy table means indexed columns are
-- changing on most updates. Find out which, and whether that index is worth it.

-- 3. Rebuild a bloated index without blocking writes (PG 12+).
REINDEX INDEX CONCURRENTLY idx_orders_tenant_status_created;

-- 4. Leave room on the page so updates can stay HOT.
ALTER TABLE sessions SET (fillfactor = 80);
VACUUM FULL sessions;   -- takes ACCESS EXCLUSIVE; schedule it, or use pg_repack
```

Replacing a useless index with a useful one:

```sql
-- BEFORE: 50M rows, 97% are 'completed'. This index is never chosen.
--   CREATE INDEX idx_jobs_state ON jobs (state);

-- AFTER: 12,000 entries instead of 50,000,000, and it is maintained only for
-- the 0.02% of writes whose state matches the predicate.
CREATE INDEX CONCURRENTLY idx_jobs_state_active
    ON jobs (state, created_at)
 WHERE state IN ('ready', 'running');
DROP INDEX CONCURRENTLY idx_jobs_state;
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Keep an index that appears in the plan of a high-volume query | Drop anything with `idx_scan = 0` over a full business cycle | Dropping a seasonal report's index means one slow quarter-end |
| Partial index instead of a full one on skewed columns | Avoid when the query predicate does not always include the partial condition | The planner silently falls back to a scan when it cannot prove the implication |
| `fillfactor` 80–90 on update-heavy tables | Avoid on append-only tables | 10–20% more disk in exchange for HOT updates |

### Follow-ups they will ask

**Q: How do you safely drop an index you think is unused?**
A: Confirm with `pg_stat_user_indexes` over a full business cycle, check the
stats-reset timestamp so you are not reading a week of data. Then, if you want a
reversible step first, `UPDATE pg_index SET indisvalid = false` makes the planner
ignore it while keeping it maintained — you can flip it back instantly if latency
regresses. Once you are confident, `DROP INDEX CONCURRENTLY`. And never drop an
index backing a unique or primary-key constraint.

**Q: What actually causes index bloat, and does `VACUUM` fix it?**
A: Update and delete churn. Old index entries stay until `VACUUM` removes them,
and even then the freed space is reused only within the same page — the index
does not shrink. So `VACUUM` stops bloat from growing but does not reverse it;
`REINDEX CONCURRENTLY` does, by building a fresh index and swapping it in.

**Q: Does the same reasoning apply to GIN indexes on JSONB?**
A: More so. GIN inserts are expensive because one document produces many index
entries. Postgres mitigates this with a pending list (`fastupdate = on`, the
default): inserts are appended cheaply and merged in bulk later. The catch is
that reads must also scan the pending list, so latency spikes as it grows, and
the merge happens during someone's unlucky INSERT. On a write-heavy table with
GIN, tune `gin_pending_list_limit` or turn `fastupdate` off and accept slower,
more predictable writes.

**Q: You're adding a 9th index to a table that takes 8,000 inserts/sec. What do
you say?**
A: I ask which query needs it and how often that query runs, then I check
whether an existing composite index can be reordered or extended with `INCLUDE`
to serve it instead. If the query is low-volume and the table is write-hot, the
right answer is often to serve it from a read replica, a denormalised read
model, or an asynchronous search index rather than to tax every insert.

### Red flags — do not say this

- ❌ "Indexes only cost disk space." → ✅ "They cost a write on every insert and
  on every update that touches the indexed column, plus cache they take from
  indexes you actually use."
- ❌ "Add an index on every foreign key." → ✅ "Index a foreign key when you
  query by it or delete from the parent — otherwise the cascade check does a
  scan. Not reflexively."

---

## 5.13 Connection pooling

> **One-liner:** A Postgres connection is an operating-system process, so the
> right pool is small, shared, and sized to the database's cores — not to your
> number of app instances.

### Say this in the interview

> Postgres forks a backend *process* per connection, not a thread, so each one
> costs a few megabytes of memory before it does any work, and every one of them
> participates in snapshot and lock bookkeeping that other backends have to walk.
> That means connections are not free and more of them is not more throughput —
> past the point where you have saturated CPU and disk, additional connections
> only add context switching and contention, so throughput flattens and latency
> climbs. The sizing rule I use is roughly cores times two plus the number of
> effective spindles, which on an 8-core box with SSDs lands around 16 to 20
> connections, and the more precise version is Little's Law: peak transactions
> per second times average transaction duration. Five hundred transactions a
> second at twenty milliseconds each needs ten busy connections, so I'd
> provision fifteen. The number that surprises people is that fifteen database
> connections can serve thousands of concurrent HTTP requests, because each one
> holds the connection only for the milliseconds it is executing. When I have
> many app instances or anything serverless I put PgBouncer in transaction mode
> in front, so a connection is borrowed for the duration of a transaction rather
> than a session — and then I have to give up session state: session-level SET,
> LISTEN, session advisory locks, and server-side PREPARE all break, because the
> next statement may land on a different backend.

### Mental model

```
WITHOUT A POOLER
  40 app pods x 20 connections each = 800 connections
  Postgres max_connections = 500      -> "too many clients already"
  Even if it fit: 800 processes x ~7 MB = ~5.6 GB before any query runs,
  and 800 backends each scanning the proc array on every snapshot.

WITH PGBOUNCER (transaction mode)
   app pods              pgbouncer                postgres
  +---------+
  | pod 1   |  20 conns \
  | pod 2   |  20 conns  \   cheap client conns    real backends
  |  ...    |    ...      >------ 800 ------> [ pool of 20 ] --> 20 procs
  | pod 40  |  20 conns  /       (~2 KB each)
  +---------+           /
                                 A backend is BORROWED for the duration
                                 of a TRANSACTION, then returned. A pod
                                 sitting idle between queries holds nothing.

THROUGHPUT vs POOL SIZE (the shape everyone gets wrong)

  tps  |          ___________
       |        /            \______      <- more connections, LESS throughput
       |      /                      \___
       |    /
       |  /
       +---------------------------------- pool size
          ^ ~ (cores * 2) + spindles
```

**Sizing, two ways that should agree:**

- Rule of thumb: `connections = (core_count * 2) + effective_spindle_count`.
  On an 8-vCPU instance with network SSD: `8*2 + 1 ≈ 17`. Round to 20.
- Little's Law: `connections = peak_tps × mean_transaction_seconds`.
  500 tps × 0.020 s = 10, plus 30–50% headroom = 15.

If those two disagree by a lot, the transactions are too long — that is the
finding, not the pool size.

**And the constraint that binds everything:**

```
sum(all pool sizes across all services and all replicas)
    + reserved superuser connections
    + your migration tooling
    + your BI tool
  <  max_connections
```

**What breaks under PgBouncer transaction pooling** — memorise this list,
it is a very common follow-up:

| Feature | Session mode | Transaction mode |
|---|---|---|
| `SET` / `RESET` (session-level) | works | **broken** — use `SET LOCAL` |
| `LISTEN` / `NOTIFY` (listening) | works | **broken** — needs a stable session |
| `PREPARE` / `DEALLOCATE` (SQL-level) | works | **broken** |
| Protocol-level prepared statements | works | works **only** with `max_prepared_statements > 0` (PgBouncer 1.21+; default-on at 200 since 1.24) |
| Session advisory locks (`pg_advisory_lock`) | works | **broken** — use `pg_advisory_xact_lock` |
| `WITH HOLD` cursors | works | **broken** |
| Temp tables surviving a transaction | works | **broken** |

Each of these breaks *silently and intermittently*, which is the worst failure
mode: it works in dev with one connection and fails under load when the pool
starts multiplexing.

### Enterprise production example

**Figma** put PgBouncer in the path early, then found it was not enough. By 2023
their hottest shards were at roughly 90% CPU, IOPS was the ceiling, and
**PgBouncer was approaching its connection limits** — which is the specific
signal that you have run out of runway on a single primary. Their answer was
DBProxy, a Go service that sits *between* the application and PgBouncer and does
query parsing, routing, load-shedding and request hedging. Note the layering:
`app → DBProxy → PgBouncer → Postgres`. The pooler did not go away; a smarter
layer went in front of it.

**Notion** hit the same wall from the other direction: after sharding to 480
logical shards, the backend had to talk to many databases at once, and PgBouncer
was what stopped the application from opening a pool per shard per pod. When
they went from 32 to 96 physical databases, the pooling tier is what made the
connection count tractable.

### Code

Python / FastAPI, SQLAlchemy async with asyncpg:

```python
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

# Direct to Postgres: pool in the app.
engine = create_async_engine(
    "postgresql+asyncpg://app@db.internal/prod",
    pool_size=10,          # steady-state connections THIS process keeps open
    max_overflow=5,        # burst headroom; 15 total per process, hard ceiling
    pool_timeout=3,        # fail fast when saturated -- do NOT queue forever
    pool_recycle=1800,     # under a proxy/LB, reconnect before it kills idle conns
    pool_pre_ping=True,    # cheap liveness check; survives a failover
    connect_args={
        "timeout": 5,                       # connect timeout
        "command_timeout": 10,              # per-statement ceiling
        "server_settings": {
            "application_name": "orders-api",       # shows in pg_stat_activity
            "idle_in_transaction_session_timeout": "30000",
        },
    },
)

# Behind PgBouncer in TRANSACTION mode: do NOT pool twice. Let PgBouncer own
# the backend pool; the app opens cheap client connections on demand.
engine_via_pgbouncer = create_async_engine(
    "postgresql+asyncpg://app@pgbouncer.internal:6432/prod",
    poolclass=NullPool,
    connect_args={
        # asyncpg caches prepared statements by default; that breaks under
        # transaction pooling unless PgBouncer 1.21+ has max_prepared_statements
        # set. Disabling is the safe default.
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    },
)
```

`pool_timeout=3` matters more than it looks: with an unbounded wait, a slow
database turns into an unbounded queue of requests holding memory. Failing fast
lets the load balancer shed load and keeps the failure legible.

Node.js with `pg`:

```javascript
const { Pool } = require('pg');

const pool = new Pool({
  host: 'pgbouncer.internal',
  port: 6432,
  max: 10,                          // per Node process, NOT per cluster
  min: 2,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 3_000,   // fail fast under saturation
  statement_timeout: 10_000,
  query_timeout: 10_000,
  idle_in_transaction_session_timeout: 30_000,
  application_name: 'orders-api',
});

// A pool error is not a query error: it fires for idle clients that die
// (failover, PgBouncer restart). Unhandled, it crashes the process.
pool.on('error', (err) => log.error({ err }, 'idle pg client error'));

// Export saturation. waitingCount > 0 for a sustained period is the single
// best early warning that the pool is undersized or transactions are too long.
setInterval(() => {
  metrics.gauge('pg.pool.total',   pool.totalCount);
  metrics.gauge('pg.pool.idle',    pool.idleCount);
  metrics.gauge('pg.pool.waiting', pool.waitingCount);
}, 10_000);
```

PgBouncer config, with the reasoning inline:

```ini
[databases]
prod = host=10.0.1.20 port=5432 dbname=prod

[pgbouncer]
pool_mode = transaction
max_client_conn = 5000        ; cheap: ~2 KB each on the pgbouncer side
default_pool_size = 20        ; REAL backends per (db,user). This is the number
                              ; that must respect (cores*2 + spindles).
reserve_pool_size = 5         ; burst headroom
reserve_pool_timeout = 3
max_prepared_statements = 200 ; 1.21+: keeps protocol-level prepares working
server_idle_timeout = 600
query_wait_timeout = 5        ; fail fast instead of queuing forever
```

```sql
-- The saturation check, on the PgBouncer admin console.
--   cl_waiting > 0 sustained  -> pool too small OR transactions too long
--   sv_idle high              -> pool too large, wasting max_connections
SHOW POOLS;
```

**Serverless** (Cloud Run, Lambda, Cloud Functions) breaks the model completely:
each instance may open its own connection, instances scale to hundreds in
seconds, and there is no coordination. Three workable answers, in order of
preference: put PgBouncer (or Cloud SQL Auth Proxy with a pooler, or RDS Proxy,
or Supabase's Supavisor) between the functions and Postgres and set the function
pool to 1–2; use a data-proxy HTTP API (Neon serverless driver, PlanetScale
HTTP) so there is no TCP session at all; or keep the connection-hungry work in a
long-lived service and let the serverless tier call it.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Transaction pooling for stateless web/API traffic | Avoid when you need `LISTEN`, session advisory locks, or temp tables | Silent, intermittent breakage of session-scoped features |
| Session pooling for workers that need session state | Avoid for high-fanout web tiers | You lose most of the multiplexing benefit — concurrency is capped at pool size |
| A small pool (10–20 per DB) | Never size the pool to expected concurrent users | A big pool feels safer and measurably lowers throughput past saturation |
| `pool_timeout` of a few seconds | Avoid unbounded waits | Some requests get a fast 503 instead of a slow timeout — which is the correct behaviour |

### Follow-ups they will ask

**Q: We have 200 app pods. What pool size per pod?**
A: You do not answer per pod, you answer per database, then divide. If the
database can usefully serve 40 concurrent backends, 200 pods × even 2 each is
400, which is ten times too many. So the answer is PgBouncer in transaction
mode with `default_pool_size = 40`, and the pods open cheap client connections
that PgBouncer multiplexes. Sizing per pod without a pooler is how you get "too
many clients already" during a deploy, when old and new pods are both running.

**Q: Why does throughput go *down* when I raise the pool size?**
A: Because past saturation you are not adding capacity, you are adding
contention: more backends time-slicing the same cores, more processes in the
lock manager, more concurrent snapshots, and more memory pressure since each
sort can take `work_mem`. The queue has to exist somewhere — the choice is
whether it queues cheaply in the pooler or expensively inside Postgres.

**Q: `pg_advisory_lock` stopped working after we moved to PgBouncer. Why?**
A: Session-scoped advisory locks are bound to a backend, and in transaction mode
the next statement may run on a different backend — so you take the lock on one
and "release" it against another. The fix is `pg_advisory_xact_lock`, which is
transaction-scoped and releases at COMMIT. Rails users hit this specifically
because Rails uses session advisory locks for migration coordination by default
and needs `advisory_locks: false` in `database.yml`.

**Q: How do you detect pool exhaustion before users do?**
A: Three signals. In the app, `pool.waitingCount` (Node) or SQLAlchemy's checkout
wait time — sustained above zero means requests are queuing. In PgBouncer,
`SHOW POOLS` with `cl_waiting > 0`. In Postgres, a rising count of sessions in
`pg_stat_activity` with `wait_event_type = 'Lock'` or, more tellingly, state
`idle in transaction`, which usually means the application is holding
connections across non-database work.

**Q: `max_connections` is 500 and we are at 480. Is raising it the fix?**
A: Almost never. 480 active backends on a normal instance means the pool is
oversized or transactions are being held open. Raising `max_connections` raises
the memory floor and the per-snapshot bookkeeping for every backend, so it
usually makes latency worse. The fix is a pooler and shorter transactions.

### Red flags — do not say this

- ❌ "We set the pool to 200 so we can handle 200 concurrent users." → ✅ "Pool
  size is about concurrent *transactions*, not concurrent users. Fifteen
  connections at 20 ms each serve 750 transactions per second."
- ❌ "Connections are cheap, just open more." → ✅ "Each Postgres connection is a
  process with a few megabytes of overhead, and past core count they cost
  throughput."
- ❌ "We'll add PgBouncer, nothing else changes." → ✅ "In transaction mode I
  need to check for session `SET`, LISTEN, session advisory locks and server-side
  prepared statements first."

---

## 5.14 Schema migrations without downtime

> **One-liner:** Never change a schema in one step — expand, migrate, contract,
> with a `lock_timeout` on every DDL statement so a blocked migration fails
> instead of taking the site down.

### Say this in the interview

> The rule is that the schema and the code are deployed separately and every
> intermediate state has to be valid, because during a rolling deploy the old
> and new code run at the same time against one database. That gives you
> expand-contract: first expand, adding the new column or table so both versions
> work; then migrate, backfilling in batches and switching the code to read the
> new thing; then contract, dropping the old thing in a later deploy. The
> operational detail that actually prevents outages is `lock_timeout`. Most
> `ALTER TABLE` statements need an ACCESS EXCLUSIVE lock, and if a long-running
> query is holding the table, the ALTER waits — and because the Postgres lock
> queue is FIFO, every subsequent query queues behind the waiting ALTER, even
> plain SELECTs. So a one-millisecond migration becomes a total outage while it
> waits. Setting `lock_timeout` to two or three seconds means it fails and I
> retry, instead of taking the service down. The other two things I always do:
> `CREATE INDEX CONCURRENTLY`, never a plain CREATE INDEX, because the plain one
> holds a write lock for the whole build; and adding NOT NULL via a `NOT VALID`
> check constraint that I validate separately, because a direct `SET NOT NULL`
> scans the entire table under an exclusive lock.

### Mental model

```
EXPAND -> MIGRATE -> CONTRACT, across three deploys

  deploy 1  DDL: add new column (nullable, no volatile default)
            code: writes BOTH old and new; reads OLD
            <- rollback safe: new column is ignored by old code

  deploy 2  job: backfill in batches, throttled on replication lag
            code: writes BOTH; reads NEW
            <- rollback safe: old column is still current

  deploy 3  code: writes NEW only
            DDL: drop the old column
            <- point of no return; do this a week later, not an hour


THE LOCK QUEUE -- why lock_timeout is not optional

  t=0    SELECT ... FROM orders     (ACCESS SHARE, runs 4 minutes)
  t=1s   ALTER TABLE orders ...     (wants ACCESS EXCLUSIVE) -> QUEUED
  t=1.1s SELECT ... FROM orders     (ACCESS SHARE) -> QUEUED BEHIND THE ALTER
  t=1.2s every query on orders      -> QUEUED
  t=5s   connection pool exhausted  -> the service is down

  With `SET lock_timeout = '3s'` the ALTER dies at t=4s and nothing else
  ever queues. You retry in a quieter minute.
```

**Postgres DDL lock reference** — the table to know cold:

| Operation | Lock | Duration on a big table | Safe? |
|---|---|---|---|
| `ADD COLUMN` (nullable, no default) | ACCESS EXCLUSIVE | instant, catalog only | yes |
| `ADD COLUMN ... DEFAULT <constant>` (PG11+) | ACCESS EXCLUSIVE | instant, default stored in catalog | yes |
| `ADD COLUMN ... DEFAULT now()` (volatile) | ACCESS EXCLUSIVE | full table rewrite | **no** |
| `DROP COLUMN` | ACCESS EXCLUSIVE | instant (marked dropped, space reclaimed by vacuum) | yes |
| `SET NOT NULL` | ACCESS EXCLUSIVE | full table scan | **no** (use the CHECK trick) |
| `ADD CONSTRAINT ... NOT VALID` | SHARE UPDATE EXCLUSIVE | instant | yes |
| `VALIDATE CONSTRAINT` | SHARE UPDATE EXCLUSIVE | full scan, reads/writes continue | yes |
| `CREATE INDEX` | ACCESS EXCLUSIVE (blocks writes) | full build | **no** |
| `CREATE INDEX CONCURRENTLY` | SHARE UPDATE EXCLUSIVE | ~2× longer, two passes | yes |
| `ALTER COLUMN TYPE` | ACCESS EXCLUSIVE | full rewrite | **no** (expand-contract) |
| `ADD FOREIGN KEY` | SHARE ROW EXCLUSIVE on both tables | validates every row | use `NOT VALID` + `VALIDATE` |
| `RENAME COLUMN` | ACCESS EXCLUSIVE | instant — but it breaks running code | **no** |

### Enterprise production example

**Notion's** shard migration is the best-documented version of this playbook at
scale, and every phase maps onto expand-contract. They tried logical replication
first and it could not keep up, so they **double-wrote via an audit log**: the
application wrote to both the old monolith and the new shards, with the audit
log making the second write durable and replayable rather than best-effort. Then
a **three-day backfill on 96 CPUs**. Then **verification** — sampled comparison
plus dark reads, deliberately implemented by *different people* than those who
wrote the migration, so a shared misunderstanding could not validate itself. Then
a **five-minute switchover**, which their own retrospective says could have been
zero. Two details worth borrowing: the audit-log double-write, and having a
different person write the verifier.

**Figma** separated the risky part from the reversible part in a different way.
They implemented "logical sharding" using Postgres **views** — `CREATE VIEW
table_shard1 AS SELECT * FROM table WHERE hash(shard_key) >= min AND < max`,
which accepts both reads and writes — so they could roll out shard *routing*
against a single unsharded database and roll it back with a config flag in
seconds. Only once routing was proven did they do the physical split. Their first
horizontally sharded table went live in September 2023 with about 10 seconds of
partial primary-availability impact and zero replica impact.

### Code

The safety preamble for every migration file:

```sql
-- Every migration starts with these three lines.
SET lock_timeout = '3s';       -- do not queue the world behind a blocked DDL
SET statement_timeout = '0';   -- but let a long backfill actually finish
SET LOCAL synchronous_commit = 'local';  -- optional: faster bulk DDL/backfill
```

**Adding a NOT NULL column safely** — four steps, three deploys:

```sql
-- Step 1 (deploy 1): add nullable. Instant in PG11+ even with a constant
-- default, because the default is stored in the catalog, not written to rows.
ALTER TABLE orders ADD COLUMN currency text DEFAULT 'USD';

-- Step 2: backfill existing rows in batches (see the batching script below).
--         Application is already writing the column for new rows.

-- Step 3: add the constraint as NOT VALID -- instant, only takes
--         SHARE UPDATE EXCLUSIVE, and enforces the rule for NEW rows.
ALTER TABLE orders
  ADD CONSTRAINT orders_currency_not_null CHECK (currency IS NOT NULL) NOT VALID;

-- Step 4: validate. Full scan, but reads and writes continue throughout.
ALTER TABLE orders VALIDATE CONSTRAINT orders_currency_not_null;

-- Step 5 (optional, PG12+): now SET NOT NULL is instant, because the planner
-- can prove it from the already-validated CHECK constraint.
ALTER TABLE orders ALTER COLUMN currency SET NOT NULL;
ALTER TABLE orders DROP CONSTRAINT orders_currency_not_null;
```

**Batched backfill, throttled on replication lag** — the part people skip and
then page themselves at 2 a.m.:

```python
async def backfill_currency(pool, batch_size: int = 5_000) -> None:
    """Backfill in bounded batches, each its own transaction, throttled on
    replica lag. Never `UPDATE orders SET ...` unqualified on a big table:
    that is one transaction, one giant lock set, and hours of WAL."""
    last_id = 0
    while True:
        rows = await pool.fetch(
            """
            WITH batch AS (
                SELECT id FROM orders
                 WHERE id > $1 AND currency IS NULL
                 ORDER BY id
                 LIMIT $2
            )
            UPDATE orders o
               SET currency = coalesce(t.default_currency, 'USD')
              FROM batch b JOIN tenants t ON t.id = o.tenant_id
             WHERE o.id = b.id
            RETURNING o.id
            """,
            last_id, batch_size)
        if not rows:
            break
        last_id = max(r["id"] for r in rows)

        lag = await pool.fetchval(
            "SELECT coalesce(max(EXTRACT(epoch FROM replay_lag)), 0) "
            "FROM pg_stat_replication")
        # Back off hard if replicas fall behind: the backfill is not urgent,
        # the read path is.
        await asyncio.sleep(2.0 if lag and lag > 5 else 0.05)
        log.info("backfilled", last_id=last_id, replica_lag_s=lag)
```

**Index creation and the failure mode nobody warns you about:**

```sql
-- CONCURRENTLY cannot run inside a transaction block. Most migration tools
-- wrap each file in BEGIN/COMMIT -- you must disable that per migration
-- (Alembic: with op.get_context().autocommit_block(); Rails:
--  disable_ddl_transaction!; node-pg-migrate: { transaction: false }).
CREATE INDEX CONCURRENTLY idx_orders_currency ON orders (currency);

-- If it fails partway (lock_timeout, deadlock, cancelled deploy) it leaves an
-- INVALID index behind that is maintained on every write but used by nothing.
-- ALWAYS check after a failed concurrent build:
SELECT c.relname
  FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid
 WHERE NOT i.indisvalid;
-- then: DROP INDEX CONCURRENTLY <name>;  and retry.
```

**Renaming a column, which you must never do in one step:**

```sql
-- deploy 1: expand
ALTER TABLE users ADD COLUMN email_address text;
CREATE OR REPLACE FUNCTION sync_email() RETURNS trigger AS $$
BEGIN
  NEW.email_address := coalesce(NEW.email_address, NEW.email);
  NEW.email         := coalesce(NEW.email, NEW.email_address);
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER users_sync_email BEFORE INSERT OR UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION sync_email();
-- deploy 2: backfill, then switch reads to email_address
-- deploy 3: drop the trigger, drop `email`
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Expand-contract for any backwards-incompatible change | Avoid it for genuinely additive changes (a new nullable column) | Three deploys instead of one, and a dual-write window |
| `lock_timeout` on every DDL | Never omit it in production | Some migrations fail and must be retried — which is the entire point |
| `CREATE INDEX CONCURRENTLY` always | Avoid in an initial migration on an empty table (pointless overhead) | ~2× build time and the possibility of an INVALID index to clean up |
| Backfill in batches with lag throttling | Avoid one big `UPDATE` on a large table | A longer backfill (hours instead of minutes) that nobody notices |

### Follow-ups they will ask

**Q: Why is a two-millisecond `ALTER TABLE` capable of causing an outage?**
A: Because acquiring the lock is the slow part, not the change. `ALTER TABLE`
requests ACCESS EXCLUSIVE; if any transaction holds even ACCESS SHARE on the
table — an autovacuum, a long analytics SELECT, an idle-in-transaction
connection — the ALTER waits, and Postgres's FIFO lock queue makes every
subsequent query wait behind it. The table becomes completely unavailable while
a statement that has not started yet sits in the queue.

**Q: How do you roll back a migration that has already been applied?**
A: You mostly do not — you roll *forward*. That is the reason for
expand-contract: at every intermediate state, both the old and new code work, so
rolling back the *application* is always safe and you never need to reverse a
DDL under pressure. The only genuinely irreversible step is contract, which is
why it happens days later, after the new path has been running in production.

**Q: How do you add a `UNIQUE` constraint without locking the table?**
A: Build the index first with `CREATE UNIQUE INDEX CONCURRENTLY`, then attach it
with `ALTER TABLE ... ADD CONSTRAINT ... UNIQUE USING INDEX <name>`. The attach
takes ACCESS EXCLUSIVE but only for a moment, because the index already exists
and no validation scan is needed. Doing `ALTER TABLE ... ADD CONSTRAINT UNIQUE
(col)` directly builds the index *under* that exclusive lock.

**Q: Your backfill is causing replication lag. What do you do?**
A: Reduce the batch size and increase the sleep between batches, throttled on
`pg_stat_replication.replay_lag` as in the script above. Every batch is WAL that
every replica must receive and replay, so a backfill is a WAL-generation
problem, not a CPU problem. On managed Postgres also watch WAL storage and any
replication-slot retention, because a lagging replica with a slot can fill the
primary's disk — which turns a slow backfill into an outage.

**Q: Does MySQL make this easier?**
A: Differently. MySQL 8 supports genuinely instant `ADD COLUMN` and has mature
external tools — `gh-ost` and `pt-online-schema-change` — that build a shadow
table, copy rows, tail the binlog for concurrent changes, and swap atomically.
Postgres's answer is more built-in (`CONCURRENTLY`, `NOT VALID`) plus `pg_repack`
for rewrites. The discipline — expand, migrate, contract, with a lock timeout —
is identical either way.

### Red flags — do not say this

- ❌ "We take a maintenance window for schema changes." → ✅ "Expand-contract
  means the schema change and the code deploy are independent, so no window is
  needed for anything but the final drop."
- ❌ "It's just adding a column, it's instant." → ✅ "Adding a nullable column or
  one with a constant default is instant in PG11+. With a volatile default it
  rewrites the table."
- ❌ "The migration ran fine in staging." → ✅ "Staging has no concurrent load, so
  it cannot reproduce a lock queue. I set `lock_timeout` and run it against
  production traffic patterns."

---

## Module 05 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Walk through the five questions you ask before choosing a database, in order,
   and say why "SQL vs NoSQL" is the wrong first question.
2. Explain the difference between the C in ACID and the C in CAP in two
   sentences, without using the word "consistency" ambiguously.
3. Draw the two-transaction timeline for write skew and say which isolation
   level prevents it and by what mechanism.
4. Postgres's Repeatable Read is not the SQL standard's Repeatable Read. What
   is different, and in which direction?
5. You get SQLSTATE 40001 in production. What is it, what must the retry do
   differently from a normal retry, and what is the difference from 40P01?
6. Why is `INDEX(a, b)` not the same as `INDEX(b, a)`? Give a query that each
   one serves and the other does not.
7. Why does a single long-running SELECT cause bloat in tables it never read?
8. What breaks when you move from PgBouncer session pooling to transaction
   pooling? Name at least four things.
9. An `ALTER TABLE` that takes two milliseconds took the site down for five
   minutes. Explain the mechanism and the one setting that prevents it.
10. Design a job queue in Postgres. Which lock clause, which index, and what
    happens when a worker crashes mid-job?
11. Given an `EXPLAIN ANALYZE` node showing `rows=100 ... actual rows=91204`,
    what is wrong, what does it break downstream, and what are your three fixes?
12. When would you deliberately denormalize, and what must you build alongside
    the denormalized value?

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| B-tree fan-out per 8 KB page (bigint key) | ~250–400 entries |
| B-tree depth covering ~4 billion rows | 4 levels → ~2 physical reads warm |
| Postgres default isolation level | Read Committed |
| Postgres serialization failure / deadlock SQLSTATE | `40001` / `40P01` |
| Postgres `deadlock_timeout` default | 1 second |
| Postgres default `max_connections` | 100 |
| Memory cost per Postgres backend process | ~5–10 MB before `work_mem` |
| Connection pool sizing rule | `(cores × 2) + effective_spindles` |
| Pool sizing via Little's Law | `peak_tps × mean_txn_seconds` (+30–50%) |
| PgBouncer client connection overhead | ~2 KB each |
| PgBouncer prepared-statement support in transaction mode | 1.21+ via `max_prepared_statements` (default 200 since 1.24) |
| `synchronous_commit = off` loss window | up to ~3 × `wal_writer_delay` (~600 ms) |
| `CREATE INDEX CONCURRENTLY` cost vs plain | ~2× build time, no write lock |
| Redis GET, same VPC | ~0.2–0.5 ms p99 |
| Stripe DocDB scale | 5M+ queries/sec, 2,000+ shards, 5,000+ collections, 99.9995% |
| Uber Schemaless logical shards | 4,096 fixed, `shard = hash(row_key) % 4096` |
| Discord Cassandra → ScyllaDB | 177 → 72 nodes; p99 read 40–125 ms → 15 ms |
| Discord migration throughput | 3.2M records/sec; 3 months → 9 days |
| Notion `block` table at sharding time | >20 billion rows; 480 logical shards / 32 DBs |
| pgvector HNSW defaults | `m=16`, `ef_construction=64`, `ef_search=40` |
| pgvector HNSW vs IVFFlat memory | HNSW ~2–5× the raw vectors; IVFFlat ~1.1× |

---

**Next:** [Module 06 — Replication, Partitioning, Sharding & Consistency](./06_Data_Distribution.md)
