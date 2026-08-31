# Module 06 — Replication, Partitioning, Sharding & Consistency

> **What this module makes you able to do:** say precisely why you are copying
> or splitting data, pick a shard key and defend it, explain what breaks once
> data lives on more than one machine, and state CAP and PACELC correctly
> instead of reciting the two-out-of-three myth.
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** [Module 05 — Databases](./05_Databases_Relational.md),
> especially transactions and isolation.

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 6.1 | [Why distribute data at all](#61-why-distribute-data-at-all) | ★★★★☆ |
| 6.2 | [Replication](#62-replication) | ★★★★★ |
| 6.3 | [Read replicas & the read-after-write problem](#63-read-replicas--the-read-after-write-problem) | ★★★★★ |
| 6.4 | [Failover](#64-failover) | ★★★★☆ |
| 6.5 | [Partitioning vs sharding](#65-partitioning-vs-sharding) | ★★★★☆ |
| 6.6 | [Sharding strategies](#66-sharding-strategies) | ★★★★★ |
| 6.7 | [Choosing a shard key](#67-choosing-a-shard-key) | ★★★★★ |
| 6.8 | [Cross-shard problems](#68-cross-shard-problems) | ★★★★★ |
| 6.9 | [Resharding without downtime](#69-resharding-without-downtime) | ★★★★☆ |
| 6.10 | [Consistency models](#610-consistency-models) | ★★★★★ |
| 6.11 | [CAP theorem — and PACELC](#611-cap-theorem--and-pacelc) | ★★★★★ |
| 6.12 | [Quorum reads and writes](#612-quorum-reads-and-writes) | ★★★★★ |
| 6.13 | [Distributed transactions](#613-distributed-transactions) | ★★★★★ |
| 6.14 | [Multi-region data](#614-multi-region-data) | ★★★★☆ |

---

## 6.1 Why distribute data at all

> **One-liner:** There are exactly three reasons to put data on more than one
> machine — capacity, throughput, availability — and they have different
> solutions, so conflating them produces designs that solve none of them.

### Say this in the interview

> Before I distribute anything I want to know which of three problems I am
> solving, because they need different answers. If the problem is capacity — the
> data does not fit on one machine's disk — replication does not help at all,
> since every replica holds a full copy; that needs partitioning. If the problem
> is read throughput, replicas help a lot and partitioning is overkill. If the
> problem is write throughput, replicas actively hurt, because every replica
> replays every write, so adding nodes adds work without adding write capacity —
> that also needs partitioning. And if the problem is availability or user
> latency, I need copies in different failure domains, which is replication
> again, but placed by blast radius and geography rather than by load. The
> reason this matters is that the failure I see most often is a team adding read
> replicas because the database is "slow", when the actual bottleneck is write
> IOPS or table size, and replicas make both slightly worse. So my first move is
> to name the constraint numerically — gigabytes, reads per second, writes per
> second, or minutes of downtime per year — and then pick the mechanism that
> moves that specific number.

### Mental model

```
                 THE ONLY THREE DRIVERS

  1. CAPACITY          data > one machine's disk / RAM / vacuum budget
     solution:         PARTITION.  Replication does NOT help --
                       every replica holds 100% of the data.

  2. THROUGHPUT
     2a. reads         solution: REPLICATE (read replicas, caches)
     2b. writes        solution: PARTITION. Replication makes it WORSE:
                       every replica replays every write.

  3. AVAILABILITY /    a machine, rack, AZ or region will fail; users
     LATENCY           are 150 ms away
     solution:         REPLICATE across failure domains / geographies


  WHAT EACH MECHANISM ACTUALLY BUYS

               capacity   read tput   write tput   availability
  replication     no         YES         no*          YES
  partitioning    YES        yes         YES          no**

  *  strictly negative: replicas add replay work, not write capacity
  ** more machines = more things that can fail; partitioning alone
     LOWERS availability unless each shard is itself replicated
```

Almost every real system needs both, composed: **partition for capacity and
write throughput, then replicate each partition for availability.** That is
exactly the shape of Cassandra (token ranges × replication factor 3), of Uber
Schemaless (4,096 shards, each a MySQL primary plus two cross-datacentre
replicas), and of Notion (480 logical shards on 32 physical databases, each with
RDS replicas).

The order matters too. Distribution is a one-way door in terms of complexity, so
the honest sequence is:

```
1. index and query better      (free, minutes)
2. cache                       (cheap, hours)      -> Module 07
3. vertical scale              (money, one restart)
4. read replicas               (moderate, days)
5. vertical partitioning       (split tables by domain onto separate DBs)
6. horizontal sharding         (months, and it never gets simpler)
```

Figma is a useful data point on that last step: they described horizontal
sharding as "an order of magnitude more complex than our previous scaling
efforts" and took roughly nine months to ship the first sharded table. They ran
steps 1 through 5 first, including a dozen vertically partitioned databases, and
only then sharded.

### Enterprise production example

**Figma's** scaling ladder from 2020 to 2024 is the cleanest published example
of running the drivers in order. In 2020 they were on a single Postgres instance
on AWS's largest available RDS box. As load grew they added caching and read
replicas (throughput-reads), then split the database *vertically* by domain —
files, organisations, and so on — onto a dozen separate database servers
(capacity plus write throughput, cheaply). That carried them while they built
horizontal sharding, which shipped its first table in September 2023. Their
database stack grew roughly 100× over that period, and they only paid for
horizontal sharding when the cheaper mechanisms were exhausted.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Replicate when reads dominate and staleness is tolerable | Never replicate to fix a write bottleneck | Replication lag, and read-after-write bugs |
| Partition when the dataset or the write rate exceeds one node | Avoid partitioning before you have exhausted vertical scale | Cross-shard queries, resharding, a routing layer you now own |
| Both, composed, for anything at real scale | — | The union of both failure modes |

### Follow-ups they will ask

**Q: Our database is at 85% CPU. Do we add a read replica?**
A: Only if the CPU is being spent on reads. I would check `pg_stat_statements`
for where total execution time is going and whether the load is read or write
shaped. If it is a few unindexed queries, a replica just gives you two servers
running the same bad query. If it is write and vacuum work, a replica adds
nothing and I look at partitioning, batching, or removing indexes.

**Q: Does replication improve durability?**
A: Yes, but only if it is synchronous, and only up to the correlation of the
failure. An async replica is a copy that may be seconds behind, so it improves
your recovery point objective, not your durability guarantee. And two replicas
in the same availability zone protect against a machine failure, not against the
AZ. Durability is really a question of "how many independent failure domains
hold an acknowledged copy".

### Red flags — do not say this

- ❌ "We'll add read replicas to handle more traffic." → ✅ "Read replicas add
  read capacity. If the bottleneck is writes or table size, they make it worse."
- ❌ "Let's shard for scalability." → ✅ "Sharding solves capacity and write
  throughput. Which of those is our constraint, and what is the number?"

---

## 6.2 Replication

> **One-liner:** Replication is copying writes to other nodes; every design
> choice reduces to who may accept a write and whether the commit waits for the
> copy.

### Say this in the interview

> There are three topologies and they differ in exactly one thing: who is
> allowed to accept a write. Single-leader means one node takes all writes and
> ships them to followers, which is what Postgres, MySQL and most managed
> databases do — you get a simple consistency story and no write conflicts, and
> the cost is that the leader is a single write bottleneck and failover is a
> real event. Multi-leader means several nodes accept writes and replicate to
> each other, which is what you use across regions when you cannot afford a
> cross-ocean round trip on every write — and the cost is conflicts, because two
> regions can write the same row at the same time and someone has to decide who
> wins. Leaderless, the Dynamo style used by Cassandra and DynamoDB, means the
> client writes to several replicas directly and reads from several, and you
> tune consistency with the quorum rule W plus R greater than N. Orthogonal to
> the topology is whether the commit waits: asynchronous returns as soon as the
> leader has the write, so it is fast and you can lose acknowledged writes if the
> leader dies; synchronous waits for a replica to confirm, so you cannot lose the
> write but every commit pays a network round trip and the leader stalls if the
> replica is slow. In Postgres I would set `synchronous_standby_names` to `ANY 1`
> of two standbys, which gives me durability against losing the primary without
> tying my write latency to one specific machine.

### Mental model

```
SINGLE-LEADER (Postgres, MySQL, SQL Server, most managed DBs)

   writes ---> [ LEADER ] --WAL--> [ follower 1 ]  <-- reads
                    |     --WAL--> [ follower 2 ]  <-- reads
                    +-------------> reads

   + no write conflicts, one obvious source of truth
   + reads scale horizontally
   - one write bottleneck; failover is a real, risky event
   - followers are stale by the replication lag


MULTI-LEADER (cross-region active-active, CouchDB, BDR)

  us-east wr -> [ LEADER A ] <===bidirectional===> [ LEADER B ] <- eu wr
                     |                                  |
                 followers                          followers

   + writes are local: no 70 ms cross-ocean hop on the write path
   + a region can keep serving writes when the link is down
   - CONFLICTS: both regions update user 42's email at the same time.
     Somebody must resolve. LWW loses data; CRDTs constrain the data model.


LEADERLESS / DYNAMO (Cassandra, ScyllaDB, DynamoDB, Riak)

   client --write--> [ R1 ] [ R2 ] [ R3 ]   send to all, wait for W acks
   client --read---> [ R1 ] [ R2 ] [ R3 ]   ask all, wait for R responses

   N = replicas, W = write acks required, R = read responses required
   W + R > N  =>  read and write sets overlap  =>  read sees latest write*
   * with real caveats -- see 6.12

   + no failover: any node can serve; node loss is a non-event
   + tunable per query
   - no transactions across keys; conflict resolution is your problem
```

**Sync vs async vs semi-sync**, which is the axis interviewers actually push on:

```
ASYNC                          SEMI-SYNC / QUORUM         SYNC (remote_apply)
leader fsyncs WAL              leader fsyncs, then        leader waits for the
returns COMMIT                 waits for >=1 replica      replica to APPLY it
                               to FLUSH it
commit latency: ~1 ms          ~1 ms + 1 RTT (1-3 ms      ~1 ms + RTT + replay
                               in-AZ; 70 ms cross-ocean)
on leader loss:                on leader loss:            on leader loss:
lose everything not yet        lose NOTHING that was      lose nothing; and a
shipped (RPO = lag)            acknowledged (RPO = 0)     replica read sees it
if a replica stalls:           if ALL sync replicas       same, worse
nothing happens                stall, WRITES STOP
```

The trap in synchronous replication is the last line: with one synchronous
standby, a slow or wedged standby stops the primary from committing. That is why
`ANY 1 (s1, s2)` — quorum commit — is the production setting: you need *any one*
of two to acknowledge, so losing one standby costs you nothing.

**Postgres streaming replication, concretely:**

```
  PRIMARY                                     STANDBY
  +---------------------+                     +--------------------+
  | backend: COMMIT     |                     |                    |
  |   -> WAL buffer     |                     |                    |
  |   -> fsync pg_wal   |                     |                    |
  +----------+----------+                     +--------------------+
             |                                          ^
        walsender  ---- TCP, WAL byte stream --->  walreceiver
             |                                          |
             |                                    write -> flush -> replay
             |                                          |
             +<--- feedback: write_lsn, flush_lsn, replay_lsn

  LSN = Log Sequence Number: a monotonic byte offset into the WAL.
        "0/16B3748". It is the clock of the whole system, and it is
        what you use to answer "has the replica caught up to my write?"

  wal_level = replica            minimum for streaming
  synchronous_commit = on        + synchronous_standby_names = 'ANY 1 (s1,s2)'
  replication slot               primary retains WAL until the standby has it
                                 -> guards against a standby falling behind
                                 -> DANGER: a dead standby with a slot fills
                                    the primary's disk. Set
                                    max_slot_wal_keep_size.
```

**Physical vs logical replication** in Postgres, because it comes up:
physical streams raw WAL bytes, so the standby is a byte-identical copy — all
databases, same version, no writes, cheap. Logical decodes WAL into row-level
changes published per table, so you can replicate a subset, across major
versions, into a different schema, or into Kafka via Debezium. Logical is what
you use for zero-downtime upgrades and CDC; physical is what you use for HA.

### Enterprise production example

**Uber Schemaless** shows single-leader replication with a deliberate twist.
Each of the 4,096 shards is its own MySQL cluster: one master plus two minions,
with the minions placed in *different data centres* so a datacentre loss does
not take a shard's data with it. On top of that they added **buffered writes** —
a second cluster that absorbs writes when a MySQL master is unavailable, so a
master failure degrades to a buffered write rather than a write error. The
architectural point worth stealing: they did not try to make one giant replicated
cluster highly available; they made 4,096 small ones, each with a boring,
well-understood single-leader setup.

**GitHub** changed exactly this setting after their 2018 outage. They had
asynchronous MySQL replication across coasts, so when failover promoted a West
Coast replica, several seconds of East Coast writes existed nowhere on the new
primary. Their remediation included moving to semi-synchronous replication, so
a write is acknowledged by a local replica before the client sees a commit. That
is the async-to-semi-sync trade made under maximum pressure: they accepted extra
commit latency to make RPO zero. See [6.4](#64-failover).

### Code

```sql
-- PRIMARY: quorum commit across two standbys. `ANY 1` is the important part:
-- with `FIRST 1 (s1, s2)` a slow s1 stalls every commit even though s2 is fine.
ALTER SYSTEM SET wal_level = 'replica';
ALTER SYSTEM SET synchronous_commit = 'on';
ALTER SYSTEM SET synchronous_standby_names = 'ANY 1 (standby_a, standby_b)';
ALTER SYSTEM SET max_wal_senders = 10;
ALTER SYSTEM SET max_slot_wal_keep_size = '64GB';   -- do NOT let a dead
                                                    -- standby fill the disk
SELECT pg_reload_conf();

-- Per-transaction override: a telemetry insert does not need to wait for a
-- replica, and this is safe because the durability choice is per transaction.
BEGIN;
SET LOCAL synchronous_commit = 'off';
INSERT INTO request_log (ts, route, ms) VALUES (now(), $1, $2);
COMMIT;
```

```sql
-- PRIMARY: the single most useful replication query. Run it before you believe
-- anything about your HA setup.
SELECT application_name,
       state,                                  -- streaming | catchup | startup
       sync_state,                             -- sync | async | quorum
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS replay_bytes_behind,
       write_lag, flush_lag, replay_lag
  FROM pg_stat_replication;

--  application_name | state     | sync_state | replay_bytes_behind | replay_lag
-- ------------------+-----------+------------+---------------------+-----------
--  standby_a        | streaming | quorum     |               24576 | 00:00:00.004
--  standby_b        | streaming | quorum     |             8912896 | 00:00:02.31
--  analytics_ro     | streaming | async      |           412876800 | 00:04:52.9
--
-- Read it as: standby_b is 8.9 MB / 2.3 s behind (fine). The analytics replica
-- is 5 minutes behind -- almost certainly a long query blocking WAL replay.

-- REPLICA: wall-clock lag. Returns NULL on an idle primary, so alert on
-- coalesce(...) and on replay_bytes_behind, not on this alone.
SELECT now() - pg_last_xact_replay_timestamp() AS lag_interval,
       pg_last_wal_replay_lsn()                AS replayed_to;
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Single-leader for anything with a transactional invariant | Avoid when write throughput exceeds one node, or writes must be local in two regions | A write bottleneck and a failover procedure that must actually be tested |
| Multi-leader when regions must accept local writes during a partition | Avoid whenever you can tolerate a 70–150 ms cross-region write | Conflict resolution, which either loses data (LWW) or constrains your data model (CRDTs) |
| Leaderless when node loss must be a non-event and per-query tuning is valuable | Avoid when you need multi-key transactions or read-modify-write | No cross-key atomicity; last-write-wins by timestamp; repair machinery to operate |
| Sync/quorum commit for money-shaped data | Avoid for high-volume telemetry | One network round trip per commit: ~1–3 ms in-AZ, ~70 ms cross-Atlantic |

### Follow-ups they will ask

**Q: What exactly is lost when an async primary dies?**
A: Every transaction the primary acknowledged but had not yet shipped to the
promoted replica — so your RPO equals your replication lag at the moment of
failure, which is a number you should be graphing. That is the whole GitHub
2018 story: a few seconds of writes existed only on the old primary, and
reconciling them by hand was part of what turned 43 seconds into 24 hours.

**Q: Why is my Postgres replica lagging even though the network is fine?**
A: The most common cause is that WAL replay on the standby is essentially
single-threaded, so a primary with many parallel writers can generate WAL faster
than one recovery process applies it. The other big ones are a long-running query
on the standby conflicting with replay (replay pauses, or the query is cancelled,
depending on `max_standby_streaming_delay`), bulk operations like index builds
or a big `VACUUM` producing WAL in a burst, and simply slower disks on the
replica than on the primary.

**Q: `synchronous_commit = remote_apply` — when is that worth it?**
A: When you want reads on that standby to be read-your-writes without any
application-side LSN tracking, because the commit does not return until the
standby has applied the change and made it visible. The price is a full round
trip plus replay time on the critical path of every commit, and any replay stall
becomes a write stall. I would use it for a small, high-value table, not
cluster-wide.

**Q: What's the risk of a replication slot?**
A: A slot guarantees the primary keeps WAL until the consumer has it, which is
what stops a standby from falling irrecoverably behind. The failure mode is that
a standby that is *gone* still has a slot, so the primary retains WAL forever and
fills its disk — a full disk on the primary is a hard outage. Set
`max_slot_wal_keep_size` and alert on inactive slots with growing
`pg_replication_slots.safe_wal_size`.

### Red flags — do not say this

- ❌ "We have replicas, so we can't lose data." → ✅ "With async replication, RPO
  equals replication lag. Zero RPO needs synchronous or quorum commit."
- ❌ "We'll use multi-master so writes scale." → ✅ "Multi-leader makes writes
  *local*, not more numerous. Every leader still applies every write, and now I
  own conflict resolution."
- ❌ "Synchronous replication is safer, so turn it on everywhere." → ✅ "With one
  sync standby, a stalled standby stops all commits. I'd use `ANY 1` of two."

---

## 6.3 Read replicas & the read-after-write problem

> **One-liner:** Read replicas multiply read capacity and divide nothing else —
> and the first bug they cause is a user who saves something and does not see it.

### Say this in the interview

> Read replicas work because most applications are read-heavy, so moving reads
> off the primary frees it to do writes. The maths is less generous than people
> assume, though: every replica replays one hundred percent of the write stream,
> so if writes already consume thirty percent of a node's capacity, each replica
> only contributes seventy percent of a node's worth of reads, and as the write
> fraction rises the marginal value of a replica goes to zero. Replicas scale
> reads; they never scale writes. The thing that actually bites in production is
> replication lag causing read-after-write failures: a user updates their
> profile, the write commits on the primary, the next request reads from a
> replica that is eighty milliseconds behind, and the UI shows the old value —
> which users report as "it didn't save". There are four real fixes. Route reads
> to the primary for a short window after that user writes, usually a few
> seconds, keyed per user. Pin a user to one replica so they at least get
> monotonic reads and never see time go backwards. Capture the LSN — or the GTID
> in MySQL — at write time, pass it back to the client, and have the read wait
> until the replica has replayed past it, which is the only one that is exactly
> correct. Or explicitly decide the staleness is acceptable and render the
> user's own write optimistically on the client. I default to the write-window
> routing because it is a few lines and it covers the case users actually
> notice.

### Mental model

```
THE READ-SCALING MATH

  node capacity  C = 10,000 ops/s
  write rate     W =  3,000 ops/s   (every node must apply all of these)

  read capacity per replica = C - W = 7,000 ops/s
  total with k replicas     = k x (C - W)

     W = 1,000  ->  each replica gives  9,000 reads/s   (great)
     W = 3,000  ->  each replica gives  7,000 reads/s   (fine)
     W = 8,000  ->  each replica gives  2,000 reads/s   (barely worth it)
     W = 9,500  ->  each replica gives    500 reads/s   (pointless)

  => read replicas are a read-throughput tool ONLY, and their value
     collapses as the write fraction rises. That collapse is the signal
     to partition.


THE BUG

  t=0    POST /profile   -> PRIMARY   name = "Aalok"   COMMIT
  t=0.01 302 redirect
  t=0.02 GET /profile    -> REPLICA (80 ms behind)     name = "A."
  t=0.10                    replica replays the write
                            user has already seen the old value and
                            filed a bug that says "it didn't save"
```

**What actually causes lag**, in the order you should check:

1. **Single-threaded replay.** One recovery process applies WAL that many
   backends produced in parallel. A write burst on the primary is a lag spike
   on the replica, with no network problem at all.
2. **Query/replay conflicts.** A long read on the standby blocks replay of WAL
   that would remove rows it still needs. Either replay pauses (lag grows) or
   the query is cancelled — governed by `max_standby_streaming_delay`. Turning
   on `hot_standby_feedback` avoids the cancellation but pushes the vacuum
   horizon back onto the *primary*, causing bloat there.
3. **Bulk operations.** `VACUUM`, index builds, and unbatched backfills emit WAL
   far faster than steady OLTP traffic.
4. **Network bandwidth** and **slower disks on the replica** — replicas are
   frequently provisioned smaller than the primary, which is a false economy.

**The four fixes, precisely:**

| Fix | Guarantee | Cost | Use when |
|---|---|---|---|
| 1. Route to primary for a window after a write | Read-your-writes for that user | Primary takes some read load; needs per-user write timestamps | Default. Simple, covers the visible case |
| 2. Sticky replica per user (hash user → replica) | Monotonic reads (never goes backwards) — **not** read-your-writes | Uneven replica load; breaks on replica loss | Feeds, timelines, anything where "time going backwards" is the bad symptom |
| 3. LSN/GTID token: capture at write, wait or route on read | Exactly correct read-your-writes | Extra round trips; a token to plumb through the API | Correctness-critical reads that must come off a replica |
| 4. Tolerate it | None | Zero | The read genuinely does not need the write — analytics, search, recommendations |

### Enterprise production example

**Notion's** re-sharding in 2023 is a good illustration of what read replicas
could not fix. By then their hottest shards were at roughly **90% CPU**, disk
IOPS was the ceiling, and PgBouncer was near its connection limits. Adding more
read replicas would have added more nodes each replaying the same write stream
against the same IOPS ceiling. Instead they redistributed their 480 logical
shards from 32 physical databases onto 96, roughly tripling backend database
capacity with no application downtime, and CPU and IOPS on the hot shards fell
from about 90% back toward 20%. No query changed, because a block's *logical*
shard never moved — only the machine hosting it did.

The Postgres-specific read-your-writes tooling is worth knowing accurately,
because it is a common trap: `pg_wal_replay_wait()` was committed for Postgres
18 and then **reverted**, so no released version ships it. Postgres 19 adds a
`WAIT FOR LSN` command instead. Until you are on 19, the portable approach is to
compare `pg_last_wal_replay_lsn()` on the replica against the LSN you captured
on the primary, and fall back to the primary if it is behind. MySQL has had
`WAIT_FOR_EXECUTED_GTID_SET()` for years, which does exactly this.

### Code

Fix 1 — write-window routing, the one to implement first:

```python
import time
import redis.asyncio as redis

WRITE_WINDOW_S = 5   # >= p999 replication lag, with headroom

class Router:
    """Routes reads to a replica unless this user wrote recently."""

    def __init__(self, primary, replicas, kv: redis.Redis):
        self.primary, self.replicas, self.kv = primary, replicas, kv

    async def note_write(self, user_id: str) -> None:
        # Redis, not a local dict: the next request may hit a different pod.
        await self.kv.set(f"rw:{user_id}", "1", ex=WRITE_WINDOW_S)

    async def for_read(self, user_id: str):
        if await self.kv.exists(f"rw:{user_id}"):
            return self.primary                      # read-your-writes
        return random.choice(self.replicas)

    async def for_write(self, user_id: str):
        await self.note_write(user_id)
        return self.primary
```

Fix 3 — LSN token, the exactly-correct version:

```python
async def write_profile(primary, user_id: str, name: str) -> str:
    """Returns an opaque consistency token the client echoes on the next read."""
    async with primary.acquire() as conn:
        async with conn.transaction():
            await conn.execute("UPDATE profiles SET name=$2 WHERE id=$1",
                               user_id, name)
        # Captured AFTER commit: this LSN is at or past our write.
        return await conn.fetchval("SELECT pg_current_wal_lsn()::text")


async def read_profile(primary, replicas, user_id: str, token: str | None):
    """Serve from a replica only if it has replayed past the client's token."""
    if token:
        for replica in random.sample(replicas, len(replicas)):
            async with replica.acquire() as conn:
                caught_up = await conn.fetchval(
                    "SELECT pg_last_wal_replay_lsn() >= $1::pg_lsn", token)
                if caught_up:
                    return await conn.fetchrow(
                        "SELECT * FROM profiles WHERE id=$1", user_id)
        # No replica has it yet -- fall back rather than poll. Never block a
        # user request waiting for replication.
    async with primary.acquire() as conn:
        return await conn.fetchrow("SELECT * FROM profiles WHERE id=$1", user_id)
```

```http
# Over HTTP, the token travels like an ETag. On PG19+, the replica can block
# with `WAIT FOR LSN '0/18724C0' WITH (MODE 'standby_replay', TIMEOUT '200ms')`
# instead of the check-and-fall-back loop above.
PUT /profile              -> 200, X-Consistency-Token: 0/16B3748
GET /profile              <- X-Consistency-Token: 0/16B3748
```

The lag alert that makes all of this operable:

```sql
-- Alert when any replica taking traffic exceeds the write window.
SELECT application_name,
       pg_wal_lsn_diff(pg_current_wal_lsn(), replay_lsn) AS bytes_behind,
       extract(epoch FROM replay_lag)                    AS seconds_behind
  FROM pg_stat_replication
 WHERE replay_lag > interval '2 seconds';
-- Pull a replica from the load balancer above ~2x WRITE_WINDOW_S rather than
-- serving increasingly stale reads from it.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Send analytics, search, and list views to replicas | Never send a read that immediately follows the user's own write | Stale reads and the support tickets they generate |
| Write-window routing as the default fix | Avoid when a single user's write must be visible to *other* users instantly | Some read load returns to the primary |
| LSN tokens for correctness-critical replica reads | Avoid plumbing tokens through every endpoint | An extra round trip and API surface |
| Dedicate a replica to analytics with `hot_standby_feedback = off` | Avoid running long reports on a replica serving users | Long queries get cancelled with "conflict with recovery" — which is the correct outcome |

### Follow-ups they will ask

**Q: How many read replicas can you usefully add?**
A: Until either the write-replay share of each node's capacity makes the
marginal replica worthless, or the primary's WAL-shipping bandwidth becomes the
constraint. In practice single-digit replicas per primary is normal; if you need
dozens, use cascading replication so replicas feed replicas, or accept that you
have a partitioning problem rather than a replication problem.

**Q: A user reports "I saved it but it disappeared, then came back." What
happened?**
A: Almost certainly non-monotonic reads: two consecutive requests hit two
different replicas with different lag, so the second read went *backwards* in
time. Read-your-writes routing fixes the first read; making reads monotonic
requires pinning that user to one replica for the session, which is fix 2.

**Q: Can you use a replica for writes-adjacent work, like a background job?**
A: For reads inside the job, yes, and it is usually the right place for them.
But be careful with jobs that read on a replica and then write on the primary
based on what they read — that is a lost-update race across two nodes with no
transaction spanning them. Either read on the primary inside the write
transaction, or make the write conditional (`WHERE version = $1`) so a stale read
fails loudly.

**Q: How do you decide the write-window length?**
A: From the p99.9 of `replay_lag`, plus headroom, capped at something a user
would not notice. If p99.9 lag is 300 ms, a 3–5 second window is generous and
costs almost no primary read load, because only users who wrote in the last few
seconds are routed there. If p99.9 lag is 30 seconds, the window is not the
problem — the replica is.

### Red flags — do not say this

- ❌ "We'll add read replicas to scale." → ✅ "Replicas scale reads. Every
  replica still applies every write, so the write ceiling does not move."
- ❌ "Replication lag is usually a few milliseconds, so it's fine." → ✅ "It is a
  few milliseconds at the median and seconds at the tail during a write burst or
  a vacuum, and the tail is what users hit."
- ❌ "We'll just read from the primary to be safe." → ✅ "I route the reads that
  need read-your-writes to the primary, for a bounded window, per user."

---

## 6.4 Failover

> **One-liner:** Failover is where availability actually dies — not because nodes
> fail, but because two nodes disagree about which of them is the leader.

### Say this in the interview

> Failover is promoting a replica when the primary is gone, and the hard part is
> never the promotion — it is deciding that the primary is really gone. A
> network partition looks identical to a dead primary from the outside, so an
> automated system that promotes on unreachability will sometimes promote while
> the old primary is still alive and still accepting writes. That is split
> brain, and it is worse than downtime, because now you have two divergent
> histories and a manual reconciliation problem. The defences are quorum and
> fencing: quorum means only a majority of nodes may elect a leader, so a
> minority partition cannot promote; fencing means the old primary is actively
> stopped or cut off from clients before the new one starts, whether that is
> STONITH at the hardware level, revoking its network route, or a database-level
> fence. GitHub's 2018 outage is the canonical case — a forty-three second
> network partition caused their orchestrator to promote West Coast primaries
> while East Coast primaries were still taking writes, and reconciling those two
> histories took twenty-four hours and eleven minutes. The trade I make is that
> automated failover is right inside a region, where the network is reliable and
> the round trip is under a millisecond, and cross-region failover should require
> a human, because the probability that a cross-region link flapped is much
> higher than the probability that an entire region died. That is exactly the
> conclusion GitHub reached afterwards.

### Mental model

```
THE FAILOVER TIMELINE -- every phase is unavailability

  t=0     primary dies (or the network to it dies)
          |
  t=0..D  DETECTION       health checks must fail N times.
          |               Too fast -> flapping. Too slow -> long outage.
          |               Patroni default: ttl 30s, loop_wait 10s.
  t=D     ELECTION        which replica? most advanced LSN wins.
          |               Must have QUORUM or you get split brain.
  t=D+E   FENCING         old primary demoted / STONITH'd / route pulled.
          |               SKIP THIS AND YOU GET TWO PRIMARIES.
  t=D+E+F PROMOTION       replica opens for writes, new timeline
          |
  t=..    CLIENT REDIRECT DNS TTL, connection pool reset, pooler reload.
                          Often the LONGEST phase. Apps cache DNS.

  Typical totals: managed Postgres/MySQL HA ~60-120 s; Patroni-tuned
  clusters ~30-60 s; Aurora-style shared-storage failover tens of seconds.


SPLIT BRAIN

           network partition
   +-------------------+   X   +--------------------+
   |  DC-A             |   X   |  DC-B              |
   |  primary (alive!) |   X   |  replica -> PROMOTED|
   |  still taking     |   X   |  now taking writes  |
   |  writes from      |   X   |  from clients that  |
   |  clients on its   |   X   |  can reach DC-B     |
   |  side             |   X   |                     |
   +-------------------+   X   +--------------------+

   partition heals -> two divergent write histories, no automatic merge.
   THIS is the failure mode. Downtime is recoverable; divergence is not.
```

**The three defences, and what each one actually does:**

- **Quorum election.** Leadership requires a majority of a known member set, so
  at most one partition can elect. This is Raft, and it is what Patroni gets by
  storing leader state in etcd/Consul/ZooKeeper, and what Orchestrator uses. The
  key property: a minority partition *cannot* promote, so it fails closed. See
  [Module 09 — Leader election](./09_Reliability_Patterns.md#913-leader-election)
  for the general pattern.
- **Leader leases.** The leader holds a time-bounded lease it must renew. If it
  cannot renew (because it is partitioned from the store), it **demotes itself**
  before the lease expires. Patroni does this — the old primary shuts down its
  own writes without anyone reaching it, which is the elegant part.
- **Fencing / STONITH.** "Shoot The Other Node In The Head" — actively prevent
  the old primary from serving: power it off via IPMI, revoke its VIP, remove it
  from the load balancer, or revoke its database credentials. Fencing is what
  makes promotion *safe* rather than merely *fast*. Stripe applies the same idea
  in DocDB shard migration: they **fence at the primary node** so the source
  shard stops accepting writes before the target starts.

**Automatic vs manual:**

| | Automatic | Manual |
|---|---|---|
| MTTR | 30–120 s | 5–60 min (paging a human) |
| Risk | Promotes on a transient partition | Human error under pressure |
| Right for | Intra-region, sub-millisecond network, quorum available | Cross-region, or any topology where split brain is unrecoverable |

The reason cross-region automatic failover is usually wrong: the base rate. A
cross-region link degrading is far more likely than a region actually dying, so
most automatic cross-region promotions are false positives — and each false
positive costs you a divergence incident.

### Enterprise production example

**GitHub, 21 October 2018.** Routine maintenance to replace failing 100G optical
equipment cut connectivity between the US East Coast network hub and the primary
US East Coast data centre. Connectivity came back in **43 seconds**. In that
window:

1. The East Coast MySQL primaries kept accepting writes from clients on their
   side of the partition.
2. Orchestrator nodes in the West Coast data centre and in the East Coast public
   cloud formed a Raft quorum, concluded the East Coast primary was gone, and
   **promoted West Coast replicas**.
3. Because replication was **asynchronous** across the country, the West Coast
   replicas were missing several seconds of East Coast writes.
4. When the network healed, the application tier immediately started writing to
   the new West Coast primaries. Now each side had writes the other did not.

By 23:13 UTC they chose data integrity over availability and put the site into a
degraded, largely read-only mode. Restoring multi-terabyte MySQL clusters from
remote cloud backups and re-synchronising replicas took the rest of the day. Total:
**24 hours and 11 minutes** of degraded service, with over 5 million webhook
events and 80,000 GitHub Pages builds queued for reprocessing. No user data was
ultimately lost, but a few seconds of database writes required manual
reconciliation.

Their remediations are the checklist worth memorising: **restrict automated
failover to intra-region only**, require human involvement for cross-region, and
move to **semi-synchronous replication** so an acknowledged write exists on more
than one node before the client is told it committed.

### Code

```yaml
# patroni.yml -- the parts that decide correctness, not the parts that decide
# convenience. Patroni stores leader state in etcd; the leader holds a lease.
scope: orders-cluster
namespace: /service/

etcd3:
  hosts: [etcd-1:2379, etcd-2:2379, etcd-3:2379]   # 3 nodes = tolerates 1 loss

bootstrap:
  dcs:
    ttl: 30              # leader lease. Old primary DEMOTES ITSELF if it
                         # cannot renew within 30 s -- this is the fence.
    loop_wait: 10        # how often each node re-evaluates
    retry_timeout: 10    # must satisfy: ttl >= loop_wait + 2*retry_timeout
    maximum_lag_on_failover: 1048576   # 1 MB. A replica further behind than
                                       # this is NOT eligible: bounds data loss.
    synchronous_mode: true             # only a synchronous standby may be
                                       # promoted -> RPO = 0
    synchronous_mode_strict: false     # if no sync standby exists, keep
                                       # accepting writes (availability over
                                       # RPO). Set true to fail closed instead.
    postgresql:
      parameters:
        synchronous_commit: 'on'
        synchronous_standby_names: 'ANY 1 (*)'
```

The two settings that define your policy are `synchronous_mode` and
`maximum_lag_on_failover`. Together they say: *never promote a node that could
lose more than 1 MB of writes, and prefer a node that is guaranteed current.*
That is the setting GitHub did not have.

```python
# Application side: a failover is a burst of connection errors, not a clean
# signal. Handle it as retryable, with a bounded window, and reset the pool.
RETRYABLE_SQLSTATES = {
    "57P01",   # admin_shutdown -- the primary was demoted under you
    "57P02",   # crash_shutdown
    "57P03",   # cannot_connect_now -- replica still in recovery
    "08006", "08001", "08004",       # connection failures
    "25006",   # read_only_sql_transaction -- you reached a demoted node
}

async def with_failover_retry(pool, work, budget_s: float = 30.0):
    deadline, attempt = time.monotonic() + budget_s, 0
    while True:
        try:
            async with pool.acquire() as conn:
                return await work(conn)
        except (asyncpg.PostgresError, OSError) as e:
            code = getattr(e, "sqlstate", None)
            if code not in RETRYABLE_SQLSTATES and not isinstance(e, OSError):
                raise
            if time.monotonic() > deadline:
                raise
            # Every pooled connection points at the OLD primary. Drop them all
            # or you will retry into the same dead socket for the full budget.
            await pool.expire_connections()
            await asyncio.sleep(min(0.1 * 2 ** attempt, 2.0) * (0.5 + random.random()))
            attempt += 1
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Automatic failover intra-region with quorum + fencing | Never automatic across regions without a human | False-positive promotions on transient partitions |
| `synchronous_mode: true` so only a current replica is promotable | Avoid `synchronous_mode_strict` if availability outranks RPO | Writes stop when no synchronous standby is available |
| Short detection windows (10–30 s) | Avoid sub-5-second detection | Flapping: a GC pause or a brief network blip triggers a promotion |
| Managed HA (RDS Multi-AZ, Cloud SQL HA) | Avoid rolling your own unless you have a reason | Less control, and a failover time you do not set |

### Follow-ups they will ask

**Q: How do you actually prevent split brain?**
A: Three things together, and all three are needed. Quorum, so a minority
partition cannot elect. A leader lease with self-demotion, so the old primary
stops taking writes even if nobody can reach it. And fencing at the client
boundary — pull the VIP, update the pooler, revoke credentials — so clients
cannot keep writing to a node that thinks it is still primary. Quorum alone
prevents a *second* election; it does not stop the *first* primary from
continuing.

**Q: Why does failover often take longer than the promotion itself?**
A: Client redirection. DNS records have TTLs and clients cache beyond them,
connection pools hold sockets to the dead primary, and the pooler needs a
reload. This is why a virtual IP, a proxy layer, or a pooler that follows the
leader (PgBouncer with a Patroni callback, or an HAProxy pointed at Patroni's
health endpoints) beats DNS-based failover — the client's view of "where is the
primary" updates in seconds, not minutes.

**Q: What is the relationship between failover and RPO/RTO?**
A: RTO is the total failover timeline: detection plus election plus fencing plus
promotion plus client redirect. RPO is set by your replication mode — async means
RPO equals lag at the moment of failure, sync or quorum commit means RPO is
zero. They trade against each other: `synchronous_mode_strict` gives RPO zero
and can make RTO infinite, because with no eligible standby the cluster refuses
writes rather than losing them.

**Q: Should the application know a failover happened?**
A: It should not need to know *which* node it is talking to, but it must handle
the symptoms: a burst of connection errors, `57P01` admin shutdown on in-flight
statements, and `25006` read-only errors if it reaches a demoted node. The
important detail is expiring the whole pool — otherwise every pooled connection
retries into a socket pointing at the old primary.

**Q: How do you test failover?**
A: Trigger it on purpose, on a schedule, in production or in an environment with
production-shaped traffic. GitHub's postmortem notes they tested their backup
*procedure* daily and still found that restoring multiple terabytes from remote
storage took many hours — the procedure worked, the *time* was the surprise.
Untested failover is not a capability, it is a hope, and an untimed restore is
an unknown RTO.

### Red flags — do not say this

- ❌ "We have a standby, so we're highly available." → ✅ "We have a standby and
  a tested, fenced, quorum-gated promotion path with a measured RTO."
- ❌ "Automatic failover everywhere is safest." → ✅ "Automatic inside a region,
  human-gated across regions, because a cross-region link flap is far more
  likely than a region loss."
- ❌ "Split brain is rare, we'll deal with it if it happens." → ✅ "Split brain
  produces divergent histories that cannot be merged automatically. It is the
  one failure I design specifically to prevent."

---
## 6.5 Partitioning vs sharding

> **One-liner:** Partitioning splits a table into pieces; sharding puts those
> pieces on different machines — the first is a database feature, the second is
> a distributed system.

### Say this in the interview

> I use the words precisely because the distinction is the whole point.
> Partitioning means splitting one logical table into physical pieces — in
> Postgres that is declarative partitioning by range, list or hash, and all the
> partitions still live in one database, so I keep transactions, joins, foreign
> keys and the query planner. What I get is partition pruning, so a query with a
> date filter reads one partition instead of the whole table, and cheap
> lifecycle management: dropping last year's data is a `DETACH` and a `DROP`
> instead of a `DELETE` of two hundred million rows. Sharding means those pieces
> live on different database servers with no shared transaction manager, so I
> lose cross-shard joins, cross-shard transactions and globally unique
> constraints, and I gain a routing layer I now own. There is also vertical
> partitioning, which is splitting a table by *column* — moving a rarely-read
> BLOB or a wide JSONB column into a side table so the hot row stays narrow —
> and at a system level, splitting the whole database by domain onto separate
> servers, which is what Figma did before they sharded. The reason I care about
> the distinction in an interview is that partitioning solves a lot of
> "we need to shard" problems at a fraction of the cost, so I always ask whether
> the constraint is table size, in which case partition, or total write
> throughput, in which case shard.

### Mental model

```
VERTICAL PARTITIONING (split by COLUMN)

   users(id, email, name, avatar_blob, preferences_jsonb, bio_text)
     |  hot row is 40 KB, so 8 KB pages hold ~0 rows, every scan is TOAST
     v
   users(id, email, name)                    <- narrow, cache-friendly
   user_profiles(user_id, avatar_blob, preferences_jsonb, bio_text)

   + hot table fits in cache; index-only scans become possible
   - a join when you need both (usually you do not)


HORIZONTAL PARTITIONING (split by ROW), one database

   orders  ------ declarative partitioning by created_at (monthly)
     +-- orders_2026_07
     +-- orders_2026_08
     +-- orders_2026_09   <- WHERE created_at >= '2026-09-01' reads only this
     +-- orders_default

   + planner prunes partitions; indexes and vacuum are per-partition
   + DROP a month in milliseconds instead of DELETE-ing 200M rows
   + still ONE database: joins, FKs, transactions all intact


SHARDING (horizontal partitioning across MACHINES)

              +-- router / proxy --+
              |         |          |
        [ shard 0 ] [ shard 1 ] [ shard 2 ]      separate PG instances
        tenant hash  tenant hash  tenant hash
          0-1364      1365-2729    2730-4095

   + write throughput and capacity scale with machine count
   - no cross-shard transactions, joins, or unique constraints
   - routing, rebalancing, and a second query planner are now YOURS
```

**Postgres declarative partitioning**, and what it does *not* do:

- **Does** give partition pruning at plan time and at execution time, per
  partition indexes, per-partition `VACUUM`, and instant `DETACH`/`ATTACH`.
- **Does not** give you more machines. All partitions are in one database
  cluster, sharing its CPU, memory, WAL and connection limit.
- **Requires** the partition key to be part of every primary key and unique
  constraint. This is the constraint people trip over: you cannot have a
  globally unique `orders.id` on a table partitioned by `created_at` unless the
  key is `(id, created_at)`.

| Strategy | Key looks like | Use for |
|---|---|---|
| `PARTITION BY RANGE` | dates, monotonically increasing IDs | Time-series, log/event tables, anything with a retention policy |
| `PARTITION BY LIST` | region, country, tenant tier | Small, known, stable sets of values |
| `PARTITION BY HASH` | `tenant_id`, `user_id` | Spreading write load evenly when there is no natural range |

### Enterprise production example

**Figma** did vertical partitioning at the *system* level for years before
sharding horizontally, and it is the underrated step. From 2020 to 2022 they
split their single Postgres database into about a dozen separate database
servers by domain — files here, organisations there — each vertically scaled.
That handled capacity and write throughput per domain, kept every domain's
transactions intact, and required no routing layer beyond "which connection
string". It bought them the runway to build DBProxy properly rather than under
emergency conditions.

When they did shard horizontally, they kept a related idea: **colos**, groups of
related tables that share the same sharding key and the same physical layout.
Tables within a colo support cross-table joins and full transactions **as long
as the query is restricted to a single sharding key**. Their shard keys came
from a deliberately small set — `user_id`, `file_id`, `org_id` — because most
tables at Figma naturally belong to one of those. That is vertical partitioning
thinking applied to a sharded world.

### Code

```sql
-- RANGE partitioning for a time-series table with a retention policy.
CREATE TABLE events (
    id          bigserial,
    tenant_id   bigint      NOT NULL,
    created_at  timestamptz NOT NULL,
    kind        text        NOT NULL,
    payload     jsonb       NOT NULL,
    PRIMARY KEY (id, created_at)     -- partition key MUST be in the PK
) PARTITION BY RANGE (created_at);

CREATE TABLE events_2026_09 PARTITION OF events
    FOR VALUES FROM ('2026-09-01') TO ('2026-10-01');
CREATE TABLE events_2026_10 PARTITION OF events
    FOR VALUES FROM ('2026-10-01') TO ('2026-11-01');
CREATE TABLE events_default PARTITION OF events DEFAULT;   -- catch-all: alert
                                                           -- if it is not empty

-- Index defined on the parent is created on every partition, now and future.
CREATE INDEX ON events (tenant_id, created_at DESC);

-- Retention: milliseconds, and no dead tuples for vacuum to chase.
ALTER TABLE events DETACH TABLE events_2025_09 CONCURRENTLY;
DROP TABLE events_2025_09;
```

```sql
-- Proof that pruning works. `Subplans Removed` is the number to look for.
EXPLAIN (ANALYZE, COSTS OFF)
SELECT count(*) FROM events
 WHERE created_at >= '2026-09-15' AND created_at < '2026-09-16'
   AND tenant_id = 42;

--  Aggregate (actual time=0.412..0.413 rows=1 loops=1)
--    ->  Index Only Scan using events_2026_09_tenant_id_created_at_idx
--          on events_2026_09 events_1 (actual time=0.031..0.298 rows=1841)
--          Index Cond: ((tenant_id = 42) AND (created_at >= ...))
--  Subplans Removed: 23           <-- 23 other partitions never touched
--  Execution Time: 0.451 ms
--
-- If the query omits created_at, ALL partitions are scanned. Partitioning
-- without the partition key in the predicate is strictly worse than no
-- partitioning at all.
```

```sql
-- HASH partitioning to spread multi-tenant write load evenly inside one DB.
CREATE TABLE documents (
    tenant_id bigint NOT NULL,
    id        uuid   NOT NULL,
    body      text,
    PRIMARY KEY (tenant_id, id)
) PARTITION BY HASH (tenant_id);

-- 16 partitions: the same "many logical buckets" idea as sharding, one level
-- down. Splitting later means rewriting data, so pick generously up front.
DO $$ BEGIN
  FOR i IN 0..15 LOOP
    EXECUTE format(
      'CREATE TABLE documents_p%s PARTITION OF documents
         FOR VALUES WITH (MODULUS 16, REMAINDER %s)', i, i);
  END LOOP;
END $$;
```

```sql
-- Vertical partitioning: keep the hot row narrow.
-- Before: every SELECT of a user pulls a 30 KB avatar through the buffer cache.
CREATE TABLE user_profiles (
    user_id     bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    avatar_blob bytea,
    bio         text,
    preferences jsonb
);
-- users is now ~80 bytes/row: ~100 rows per 8 KB page instead of ~0,
-- so the whole hot table and its indexes stay resident.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Range-partition any table with a time dimension and a retention policy | Avoid when queries rarely filter on the partition key | Every query without the key scans all partitions |
| Hash-partition to spread write hotspots within one database | Avoid if you need range scans across the key | No pruning for range predicates on a hash key |
| Vertical partitioning to keep hot rows narrow | Avoid when both halves are read together on the hot path | An extra join, and two rows to keep consistent |
| Shard only when one machine genuinely cannot hold the data or the writes | Avoid before exhausting partitioning and vertical splits | Cross-shard everything, plus a routing tier you maintain |

### Follow-ups they will ask

**Q: How many partitions is too many?**
A: Planning time grows with partition count because the planner must consider
pruning across all of them, and each partition consumes relation cache entries
and a lock during planning. Modern Postgres handles a few thousand acceptably,
but I would design for tens to low hundreds — monthly partitions with a
retention window, not hourly ones kept forever — and use sub-partitioning only
when there is a measured reason.

**Q: Can I have a globally unique constraint on a partitioned table?**
A: Only on a key that includes the partition column. Postgres enforces
uniqueness per partition, so `UNIQUE (email)` on a table partitioned by
`created_at` is not expressible — you would need `UNIQUE (email, created_at)`,
which is not the constraint you wanted. The workarounds are a separate,
unpartitioned lookup table holding just the unique column, or partitioning by
the column you need unique. This is the same problem sharding has, one scale
down; see [6.8](#68-cross-shard-problems).

**Q: What is the difference between Postgres partitioning and Citus?**
A: Postgres declarative partitioning splits a table within one cluster. Citus is
an extension that distributes those partitions across *worker nodes* with a
coordinator that plans and pushes down queries — actual sharding, with a query
planner that understands it. Notion evaluated Citus and Vitess and chose
application-level sharding instead, specifically for control over routing and
migrations.

### Red flags — do not say this

- ❌ "We partitioned the table so now it scales." → ✅ "Partitioning gave us
  pruning and cheap retention. All partitions are still on one machine, so the
  write ceiling has not moved."
- ❌ "Partitioning and sharding are the same thing." → ✅ "Partitioning is within
  a database. Sharding is across databases, and that is where you lose
  transactions and joins."

---

## 6.6 Sharding strategies

> **One-liner:** Every sharding strategy answers one question — given a key, which
> machine holds it — and each answer has a different rebalancing story and a
> different way of going wrong.

### Say this in the interview

> There are four strategies and I choose between them on how routing works and
> what happens when I add a node. Range sharding assigns contiguous key ranges
> to shards, which makes range scans efficient because they touch one shard, but
> it hot-spots badly on monotonically increasing keys — shard by timestamp and
> every write in the world goes to the newest shard. Hash sharding hashes the
> key and takes it modulo the shard count, which distributes evenly but destroys
> range scans, and naive modulo hashing is a rebalancing disaster: going from
> ten shards to eleven moves about ninety percent of the keys. Consistent
> hashing fixes that by placing nodes on a ring so adding a node only moves
> roughly one over N of the keys, and virtual nodes smooth out the distribution.
> Directory-based sharding keeps an explicit lookup table from key to shard,
> which is the most flexible option — you can move one noisy tenant to its own
> shard with a single row update — at the cost of a lookup on every request and
> a new critical dependency you must cache aggressively. Geo or entity-based
> sharding assigns by region or by a business entity, which is what you use for
> data residency. The pattern that dominates in practice, though, is a
> combination: hash into a large fixed number of *logical* shards, then keep a
> small directory mapping logical shards to physical machines. Uber fixed 4,096
> logical shards, Notion chose 480, and both of them can add hardware by moving
> shard ownership without rehashing a single row.

### Mental model

```
1. RANGE
   routing:      binary search a range map.  A-F -> s0, G-M -> s1, ...
   rebalance:    split a range in two, move half its rows.  Localised.
   good at:      range scans, ORDER BY on the shard key, time queries
   FAILURE:      monotonic keys. Shard by created_at and 100% of writes
                 hit the newest shard. This is the classic hot shard.

   writes ---->  [s0 old] [s1 old] [s2 old] [s3 ALL WRITES HERE]

2. HASH (modulo)
   routing:      shard = hash(key) % N.  Stateless, zero lookups.
   rebalance:    CATASTROPHIC. N -> N+1 moves N/(N+1) of all keys:
                 10 -> 11 relocates ~91% of the dataset.
   good at:      even distribution, point lookups
   FAILURE:      resharding. And range scans become scatter-gather.

3. CONSISTENT HASHING
   routing:      hash key onto a ring, walk clockwise to the next node.
   rebalance:    adding a node moves only ~1/N of keys (its arc).
   virtual nodes: each physical node owns ~100-256 arcs, so load is even
                 and a departing node's share spreads over everyone.

        0 -----------------------------------  2^32
        |   vA1    vB3   vC2   vA7   vB1   vC5 |
        key -> hash -> walk right -> owner
   used by:      Cassandra, DynamoDB, Riak, memcached clients
   FAILURE:      still no range scans; hot KEYS still hit one node.

4. DIRECTORY / LOOKUP TABLE
   routing:      SELECT shard FROM shard_map WHERE tenant_id = ?
   rebalance:    move the rows, then UPDATE one row in the map. Surgical.
   good at:      per-tenant placement, isolating a noisy neighbour,
                 data residency, gradual migration
   FAILURE:      the directory is a new SPOF and a per-request lookup.
                 Cache it hard, version it, and make it small enough to
                 fit in memory everywhere.

5. GEO / ENTITY
   routing:      region or entity attribute decides the shard.
   good at:      GDPR/residency, and local latency
   FAILURE:      wildly uneven load (us-east is 10x eu-west) and
                 cross-region queries when an entity moves.
```

**The pattern that wins: fixed logical shards + a small directory.**

```
   key --hash--> logical shard (FIXED, e.g. 0..4095) --map--> physical node

   tenant 91721 -> hash % 4096 = 1337 -> logical shard 1337 -> pg-07

   Adding hardware moves SHARD OWNERSHIP, not rows-by-hash:
     pg-07 holds shards {1300..1400}; move {1350..1400} to pg-12.
     Zero rows are rehashed. Routing logic never changes.
     The directory is 4,096 rows -- it fits in every process's memory.
```

**Hot partitions and the celebrity problem**, concretely. Even a perfect hash
gives you an even distribution *of keys*, not of *traffic*:

```
   1,000,000 tenants hashed across 16 shards -> 62,500 tenants each. Even!
   But one tenant is 40% of all requests, so its shard is 40% loaded
   and the other 15 share 60%.

   Discord: one very active channel = one partition = one set of nodes
            taking thousands of requests per second while the rest idle.

   FIXES, in the order I would reach for them:
   1. cache the hot key (Module 07) -- removes most of the read load
   2. request coalescing: N identical in-flight reads -> 1 DB query
   3. split the key: channel_id -> (channel_id, bucket) so one channel
      spans many partitions
   4. give the celebrity its own shard (directory sharding earns its keep)
   5. write-path: shard the counter, sum on read
```

### Enterprise production example

**Uber Schemaless** made the fixed-logical-shard trick explicit and load-bearing.
The dataset is split into a fixed number of shards — typically 4,096, set at
instance creation — with `shard = hash(row_key) % 4096`. Because the count never
changes, **worker nodes compute routing locally with no coordination service in
the request path**: no metadata lookup, no directory hop, no consistent-hashing
ring to gossip about. Capacity is added by moving shards onto more MySQL hosts;
Uber's documented expansion path is literally "split each MySQL server in two".
Cells are never rehashed — only shard *ownership* moves.

**Notion** made the same choice with a different number and a stated reason:
480 logical shards across 32 physical databases, 15 shards per database. They
picked 480 rather than 512 **because of its divisors** — it divides by 2, 3, 4,
5, 6, 8 and every useful count up to 240, so the fleet can grow 32 → 40 → 48 →
96 while keeping shards evenly spread. A power of two would force doubling the
fleet at every step. That payoff arrived in 2023: they went from 32 physical
databases to 96, five logical shards each, still 480 total, tripling capacity
with zero application downtime and no query changes.

**Shopify** shows directory sharding with a hard isolation requirement on top.
A **pod** is a fully isolated set of datastores — one MySQL shard plus its own
Redis, its own Memcached, its own cron runners — serving a subset of shops with
**zero cross-pod communication**. Routing happens in a Lua/OpenResty layer in
the load balancers called the **Sorting Hat**, which looks up the shop, decides
the pod, and injects `X-Sorting-Hat-PodId` and `X-Sorting-Hat-ShopId` headers
that downstream app servers use to pick datastores. The motivating failure was
"Redismageddon": sharding MySQL had solved write throughput, but a single shared
Redis could still take down every shop on the platform. Pods contain the blast
radius, and a flash-sale merchant can be given a dedicated pod so its spike
cannot touch anyone else — which is exactly the celebrity fix, implemented as
architecture.

### Code

```python
# Fixed logical shards + a cached directory. This is the shape you should
# reach for by default: stateless hashing, surgical placement.
import hashlib
from bisect import bisect

LOGICAL_SHARDS = 4096          # NEVER changes. Choose big and divisible.

def logical_shard(key: str) -> int:
    # NOT Python's hash(): it is salted per process, so routing would differ
    # between pods. Use a stable hash, always.
    digest = hashlib.blake2b(key.encode(), digest_size=8).digest()
    return int.from_bytes(digest, "big") % LOGICAL_SHARDS


class ShardRouter:
    """Maps logical shard -> physical DSN. The map is 4,096 entries and is
    refreshed from a control-plane table; it is small enough to hold in every
    process, so the directory is never in the hot path."""

    def __init__(self, control_plane_pool):
        self._cp = control_plane_pool
        self._map: list[str] = []          # index = logical shard
        self._version = -1

    async def refresh(self) -> None:
        rows = await self._cp.fetch(
            "SELECT logical_shard, dsn, map_version FROM shard_map "
            "ORDER BY logical_shard")
        if not rows or len(rows) != LOGICAL_SHARDS:
            raise RuntimeError("incomplete shard map; refusing to swap")
        self._map = [r["dsn"] for r in rows]
        self._version = rows[0]["map_version"]

    def pool_for(self, key: str):
        return POOLS[self._map[logical_shard(key)]]

# Background refresh every 30 s, and on a version-bump notification. Never
# fetch the map inline: a control-plane blip must not become a request error.
```

```python
# Consistent hashing with virtual nodes -- what you implement when nodes come
# and go frequently (a cache tier), rather than when you place shards.
class HashRing:
    def __init__(self, nodes: list[str], vnodes: int = 160):
        self._ring: dict[int, str] = {}
        for node in nodes:
            for i in range(vnodes):
                self._ring[self._h(f"{node}#{i}")] = node
        self._keys = sorted(self._ring)

    @staticmethod
    def _h(s: str) -> int:
        return int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(),
                              "big")

    def node_for(self, key: str) -> str:
        i = bisect(self._keys, self._h(key))            # walk clockwise
        return self._ring[self._keys[i % len(self._keys)]]

# 160 vnodes per physical node keeps the load imbalance within a few percent.
# With 1 vnode per node the imbalance is routinely 2-3x.
```

```sql
-- Directory sharding: the control-plane table. `map_version` lets every
-- process detect a stale map; `state` supports online moves (see 6.9).
CREATE TABLE shard_map (
    logical_shard int PRIMARY KEY CHECK (logical_shard BETWEEN 0 AND 4095),
    dsn           text NOT NULL,
    state         text NOT NULL DEFAULT 'active',  -- active|migrating|frozen
    target_dsn    text,                            -- set during a move
    map_version   bigint NOT NULL
);

-- Moving a noisy tenant's shard to dedicated hardware: one row, one version
-- bump, no rehash.
UPDATE shard_map
   SET dsn = 'pg-dedicated-01', map_version = map_version + 1
 WHERE logical_shard = 1337;
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Range when range scans on the shard key are the dominant query | Never on a monotonically increasing key | Hot shard on the newest range; manual split management |
| Hash into fixed logical shards | Avoid raw `% physical_node_count` | Range scans become scatter-gather across every shard |
| Consistent hashing when membership changes often | Overkill when placement is deliberate and rare | Ring bookkeeping; still no range scans |
| Directory when you need per-tenant placement or residency | Avoid without aggressive caching | A lookup on the hot path and a control plane to keep available |
| Geo/entity for data residency | Avoid as your only strategy — load is never geographically even | Cross-region queries when entities span regions |

### Follow-ups they will ask

**Q: Why 4,096 or 480 and not just "the number of servers"?**
A: Because the number of servers changes and the number of logical shards must
not. If the shard count is the server count, every capacity change rehashes the
dataset. With a large fixed logical count you add hardware by reassigning shard
ownership, which moves rows in whole-shard units and never changes the routing
function. Notion additionally chose a highly divisible number — 480 rather than
512 — so the fleet can grow in small increments and still divide evenly.

**Q: What is the actual cost of `hash(key) % N` when N changes?**
A: Going from N to N+1 shards relocates N/(N+1) of all keys — 10 → 11 moves
about 91%. That is not a rebalance, it is a full data migration under load. This
one number is the entire argument for consistent hashing and for fixed logical
shards.

**Q: You have one tenant generating 40% of traffic. Walk me through it.**
A: First I confirm whether it is read or write load. If reads, caching plus
request coalescing usually removes most of it before I touch the topology —
Discord's fix for hot channels was a Rust service that consistently-hashed
requests to a worker and coalesced identical concurrent reads into one query. If
it is write load, or if the tenant is large enough to be a capacity problem too,
I move it to a dedicated shard, which is exactly what directory-based routing
makes cheap and what Shopify does by giving flash-sale merchants their own pod.

**Q: Doesn't consistent hashing solve hot partitions?**
A: No — it solves uneven *key* distribution and cheap membership changes. A
single hot key still hashes to one place no matter how the ring is arranged.
Hot keys are fixed by caching, coalescing, or splitting the key into sub-keys
(`channel_id` becomes `(channel_id, bucket)`), never by the hash function.

**Q: Where does the routing logic live — client, proxy, or database?**
A: All three exist and the trade is operational. In the client (Notion,
Schemaless workers) it is fastest — no extra hop — but every language and every
service must implement it identically, and a routing change is a fleet-wide
deploy. In a proxy (Figma's DBProxy, Stripe's DocDB proxy, Vitess) you get one
place to change routing, cross-shard query support and load shedding, at the
cost of a hop and a tier to run. In the database (Citus, CockroachDB) it is
transparent but you have adopted a different database.

### Red flags — do not say this

- ❌ "We'll shard with `user_id % num_servers`." → ✅ "I'd hash into a large
  fixed number of logical shards and map those to servers, so adding capacity
  never rehashes data."
- ❌ "Consistent hashing solves rebalancing, so we're done." → ✅ "It bounds
  rebalancing to ~1/N of keys. It does nothing for hot keys or range scans."
- ❌ "We'll shard by timestamp so recent data is together." → ✅ "That puts every
  write on the newest shard. I'd hash the entity and use time only as a
  partition key *within* a shard."

---

## 6.7 Choosing a shard key

> **One-liner:** The shard key is the one decision you cannot cheaply reverse —
> pick the entity that appears in the `WHERE` clause of your highest-volume
> query and in the boundary of your transactions.

### Say this in the interview

> The shard key is the most consequential choice in the whole design, because
> changing it later means rewriting every row. I judge a candidate key on four
> criteria. Cardinality: there must be far more distinct values than shards, so
> `country` with two hundred values across four thousand shards is unusable.
> Uniformity: the distribution of *traffic*, not just of keys, has to be
> reasonably even — a perfect hash still gives you a hot shard if one tenant is
> forty percent of your load. Query alignment: the hot-path queries must include
> the key, otherwise every read becomes a scatter-gather across every shard, and
> at that point sharding has made you slower. And transaction alignment: rows
> that must commit together must live on the same shard, because there is no
> cross-shard transaction. For a multi-tenant SaaS the answer is almost always
> `tenant_id`, because it satisfies all four at once — every query is already
> scoped to a tenant, and a tenant's data is the natural transaction boundary.
> For chat it is `channel_id`, not `user_id`, because you read a channel's
> history far more often than a user's. For orders it is `customer_id` rather
> than `order_id`, because "show me my orders" is the hot query and `order_id`
> would scatter one customer's orders across every shard. And whatever key I
> pick, I hash it into a large fixed number of logical shards rather than
> hashing directly onto machines.

### Mental model

```
THE FOUR CRITERIA -- a candidate key must pass ALL of them

  1. CARDINALITY      distinct values >> shard count (aim 1000x)
                      country (200)      -> FAIL
                      tenant_id (1M)     -> PASS

  2. UNIFORMITY       of TRAFFIC, not just of key values
                      check the p99 tenant, not the median

  3. QUERY ALIGNMENT  the key appears in the WHERE clause of the
                      queries that carry your volume
                      if the hot query lacks it -> scatter-gather ->
                      you have made every read N times more expensive

  4. TRANSACTION      rows that commit together share the key
     ALIGNMENT        else you need 2PC or a saga for a normal update


THE TEST: write your top 5 queries and mark each one

   Q1  SELECT ... WHERE tenant_id=? AND status=?     single-shard  60% qps
   Q2  SELECT ... WHERE tenant_id=? AND id=?         single-shard  25% qps
   Q3  SELECT ... WHERE tenant_id=? ORDER BY ...     single-shard  10% qps
   Q4  SELECT ... WHERE external_ref=?               SCATTER        4% qps
   Q5  SELECT count(*) ... GROUP BY tenant_id        SCATTER        1% qps

   96% single-shard  ->  tenant_id is the right key.
   Q4 gets a global secondary index; Q5 goes to the warehouse.

   If that table were 60% scatter, the key is WRONG.
```

**Worked example 1 — multi-tenant SaaS: `tenant_id`.**

Passes all four. Cardinality is high, every query already filters by tenant
because of authorization, and a tenant is the transaction boundary. The failure
mode is tenant size skew: your largest customer may be 1,000× your median. The
mitigations are directory-based placement so a whale gets its own shard, and a
per-tenant sub-key (`(tenant_id, entity_id)`) if a *single* tenant outgrows one
machine. This is Notion's choice — workspace ID, with every table transitively
related to `block` sharded on the same key so transactions never cross hosts.

**Worked example 2 — chat: `channel_id`, not `user_id`.**

The hot query is "the last 50 messages in this channel", at far higher volume
than "everything this user posted". Sharding by `channel_id` makes the hot query
single-shard. Sharding by `user_id` would make it a scatter-gather across every
shard that has a member of the channel, which is catastrophic. The cost is that
"my messages across all channels" becomes a fan-out — solved with a second table
keyed by author, written at message time. The other cost is celebrity channels,
which is why Discord's partition key is `(channel_id, bucket)`, not `channel_id`
alone: the bucket bounds partition size and spreads a busy channel over many
partitions.

**Worked example 3 — orders: `customer_id`, not `order_id`.**

| Key | "My orders" (hot) | "Order by ID" | Transactions | Distribution |
|---|---|---|---|---|
| `order_id` | **scatter to all shards** | single-shard | order + items together only if items share the key | perfectly even |
| `customer_id` | **single-shard** | single-shard *if* you embed the customer in the ID | order + items + addresses + payment methods all co-located | even, unless one customer is enormous |

`customer_id` wins, and the trick that makes "look up order by ID" still work is
to **encode the shard in the ID**: generate `order_id` so the customer's shard is
recoverable from it, or prefix it, so a bare `order_id` routes without a lookup.
That is a five-minute decision at design time and a migration if you skip it.

**Worked example 4 — when there is no good key.** If the hot query genuinely
has no common entity — a global search, a cross-entity analytics dashboard —
that workload does not belong on the sharded store. Send it to a search index or
a warehouse fed by CDC, and keep the sharded store for the access patterns that
align with the key.

### Enterprise production example

**Notion's** key selection is worth reciting because their reasoning is fully
public. The `block` table was the obvious sharding target, but blocks reference
`space` (workspaces) and `discussion`, which references `comment`, and so on.
Sharding `block` alone would have created cross-shard queries throughout the
product. So they **sharded every table transitively related to `block`, on the
same key**: workspace ID. Their stated reasoning was that Notion is a team
product, every block belongs to exactly one workspace, and users query within
one workspace at a time — which is criteria 3 and 4 in one sentence. They set
self-imposed bounds of 500 GB per table and 10 TB per physical database, needed
at least 60,000 total IOPS, and arrived at 480 logical shards on 32 physical
databases.

**Figma** narrowed the problem the same way: rather than letting each table pick
its own key, they chose a small set — `user_id`, `file_id`, `org_id` — and
grouped tables into "colos" sharing one key and one physical layout, so
cross-table joins and full transactions still work **as long as the query is
restricted to a single sharding key**. Constraining the key space is itself a
design decision worth mentioning.

**Uber's** contribution is the routing property: with a fixed 4,096 logical
shards and `shard = hash(row_key) % 4096`, routing is **stateless** — every
worker computes it locally, with no coordination service in the request path.
The shard count being fixed at instance creation is not a limitation they
tolerated, it is the property they wanted.

### Code

```python
# Encoding the shard into the ID so a bare entity ID routes without a lookup.
# 4 bits are plenty for a directory-mapped logical shard; here we use 12 bits
# for 4,096 logical shards, Snowflake-style.
SHARD_BITS = 12
SEQ_BITS   = 10
TS_SHIFT   = SHARD_BITS + SEQ_BITS

def make_order_id(customer_id: str, seq: int) -> int:
    shard = logical_shard(customer_id)              # 0..4095
    ms    = int(time.time() * 1000) - EPOCH_MS
    return (ms << TS_SHIFT) | (shard << SEQ_BITS) | (seq % (1 << SEQ_BITS))

def shard_of_order(order_id: int) -> int:
    return (order_id >> SEQ_BITS) & ((1 << SHARD_BITS) - 1)

# Now BOTH hot queries are single-shard:
#   GET /customers/{cid}/orders  -> logical_shard(cid)
#   GET /orders/{oid}            -> shard_of_order(oid)     no directory hop
```

```python
# The skew audit. Run it BEFORE committing to a key, and on a schedule after.
# Even key distribution is not the same as even traffic distribution.
SKEW_SQL = """
SELECT tenant_id,
       count(*)                                              AS rows,
       round(100.0 * count(*) / sum(count(*)) OVER (), 3)     AS pct_rows
  FROM orders
 GROUP BY tenant_id
 ORDER BY rows DESC
 LIMIT 20
"""

async def audit_skew(pool, shards: int = 4096) -> None:
    top = await pool.fetch(SKEW_SQL)
    for r in top:
        # A single tenant above ~1/shards * 50 means one shard will be
        # measurably hotter than its peers. Above ~1% it needs its own shard.
        if r["pct_rows"] > 1.0:
            log.warning("shard-key skew", tenant=r["tenant_id"],
                        pct=float(r["pct_rows"]),
                        logical_shard=logical_shard(str(r["tenant_id"])))
    # Do the same over REQUEST counts from your APM, not just row counts.
    # Row skew and traffic skew are different distributions and both matter.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `tenant_id`/`workspace_id` for B2B SaaS | Avoid when a single tenant can exceed one machine | Whale tenants need dedicated shards or a sub-key |
| `channel_id`/`conversation_id` for chat | Avoid `user_id` — the hot read is per channel | "All my messages" becomes a second table or a fan-out |
| `customer_id` for commerce, with the shard encoded in `order_id` | Avoid `order_id` alone | Cross-customer reporting is a scatter or a warehouse job |
| Hash into ≥1,000× more logical shards than machines | Avoid hashing straight onto machine count | A directory to maintain — small, but real |

### Follow-ups they will ask

**Q: What happens if you pick the wrong shard key?**
A: You rewrite the data. There is no in-place fix, because the key determines
physical placement of every row. That is why the analysis is worth doing
carefully up front, and why the mitigation is to buy optionality: fixed logical
shards, an abstraction layer for routing, and the key embedded in generated IDs.
Figma's view-based logical sharding exists precisely so routing decisions can be
validated and rolled back with a config flag before any data moves.

**Q: One tenant grows to be 30% of the database. Now what?**
A: Directory-based placement gives it its own physical shard first — one row
update, no rehash, which is the Shopify dedicated-pod move. If that tenant alone
exceeds a machine, I introduce a sub-key so their data spreads across shards
(`(tenant_id, region)` or `(tenant_id, entity_bucket)`), accepting that queries
for *that* tenant become multi-shard while every other tenant stays
single-shard. That is a deliberate asymmetry and it is the right one.

**Q: How do you support "find by email" when you shard by `tenant_id`?**
A: A global secondary index — a small, separately sharded table mapping
`email → (tenant_id, user_id)` — that you look up first and then route with. It
is eventually consistent unless you write it in the same transaction, which you
cannot across shards, so you either accept lag or use the outbox pattern to make
the index write durable and idempotent. See [6.8](#68-cross-shard-problems).

**Q: The interviewer says "shard by hash of the primary key". What do you say?**
A: I ask what the primary key is and whether the hot queries include it. Hashing
the row's own ID gives perfect distribution and makes every query that is not a
point lookup by that ID a scatter-gather. Distribution is the easiest criterion
to satisfy and the least important of the four.

### Red flags — do not say this

- ❌ "We'll shard by user ID." (for a chat app) → ✅ "The hot read is a channel's
  history, so `channel_id` keeps it single-shard. User-scoped reads get their own
  table."
- ❌ "The hash distributes evenly so there are no hot shards." → ✅ "It
  distributes keys evenly. Traffic follows a power law, so I check the p99
  tenant's share and plan for a dedicated shard."
- ❌ "We can change the shard key later." → ✅ "Changing it rewrites every row.
  I'd rather spend a day on the access-pattern analysis now."

---

## 6.8 Cross-shard problems

> **One-liner:** Sharding does not make queries slower — it makes some queries
> impossible, and your job is to make sure none of those are on the hot path.

### Say this in the interview

> The moment data lives on more than one database, five things you took for
> granted stop working. Joins across shards have no query planner to execute
> them, so either your proxy does a scatter-gather and merges in application
> memory, or you denormalize so the join is unnecessary. Transactions across
> shards have no shared transaction manager, so you are choosing between
> two-phase commit, which blocks if the coordinator dies, and a saga with
> compensating actions, which is what almost everyone actually does. Unique
> constraints stop being global, because each shard only knows its own rows — so
> a unique email address needs a separate lookup table that acts as the
> authority, or a key derived from the shard key. Aggregate queries like counts
> and sums have to fan out to every shard and merge, which turns a millisecond
> query into a query whose latency is the slowest shard's latency. And secondary
> indexes split into local, which live on each shard and require you to already
> know the shard, and global, which are a separate sharded table you maintain
> asynchronously and which is therefore eventually consistent. The way real
> systems handle all five is the same: make the hot path single-shard by design,
> denormalize aggressively, push anything genuinely cross-cutting to an
> asynchronous derived store, and accept eventual consistency where a human
> cannot tell.

### Mental model

```
FAN-OUT LATENCY -- why scatter-gather is worse than it looks

  one shard:  p50 = 2 ms,  p99 = 40 ms
  query 32 shards in parallel and wait for ALL of them:
     P(all fast) = 0.99^32 = 0.72
     => 28% of requests hit at least one p99 shard
     => the FAN-OUT's p50 is roughly the SHARD's p99

  Fan-out converts tail latency into median latency. This is the single
  most important number in cross-shard design.

  MITIGATIONS: hedged requests (Figma's DBProxy does this), partial
  results with a deadline, or -- best -- do not fan out on the hot path.


THE FIVE PROBLEMS AND THE REAL ANSWERS

  JOIN across shards
    dodge:   co-locate (same shard key for related tables -- Figma "colos",
             Notion shards everything transitively related to `block`)
    dodge:   denormalize the joined column onto the row
    pay:     scatter-gather + merge in the proxy
    pay:     reference-table replication (small dim tables on EVERY shard)

  TRANSACTION across shards
    dodge:   pick a shard key that puts co-committing rows together
    pay:     2PC   -> blocking, slow, avoided by most
    pay:     SAGA  -> compensating actions, eventual consistency (6.13)
    pay:     OUTBOX -> local txn + reliable async effect (the usual answer)

  UNIQUE constraint across shards
    dodge:   make the unique column derive from the shard key
             ("acme.com/alice" is unique within acme's shard)
    pay:     a separate `unique_emails` table, itself sharded BY EMAIL,
             written first as a claim, then the real row. Two-step, and
             you need a reaper for abandoned claims.

  AGGREGATE across shards
    dodge:   maintain a counter per shard, sum N numbers instead of
             scanning N shards
    pay:     scatter-gather with a deadline and partial results
    dodge:   push it to a warehouse via CDC and answer from there

  SECONDARY INDEX
    LOCAL:   index lives on the shard, covers only that shard's rows.
             Free and consistent -- but you must already know the shard.
    GLOBAL:  a separate sharded table keyed by the index column.
             Answers "which shard has X" -- but it is a second write, so
             it is eventually consistent unless you use the outbox.
```

### Enterprise production example

**Uber Schemaless** solved cross-shard indexes by forbidding them. Every
secondary index designates one field as the **shard field**, which must be
supplied at query time, so "the index query only need go to a single shard".
Then they went further and let the index carry a **denormalized copy of the cell
data**, so one shard answers both the lookup and the payload with no second hop.
Their internal guidance was explicit: denormalize into the index anything you
might need, trading storage for single-shard queries.

**Figma's DBProxy** took the opposite approach — build the missing planner. It
parses SQL into an AST, extracts the target shard IDs, and for queries that
cannot be routed to one shard, performs **scatter-gather**: fan out to every
shard and merge the results. They also built **request hedging** and dynamic
**load-shedding** into the same layer, which tells you what scatter-gather costs
in practice: you need hedging because the fan-out inherits the slowest shard's
latency, and load-shedding because a single expensive cross-shard query can
saturate the whole fleet.

**Stripe's DocDB** keeps the routing metadata service — logical database to
physical shard — out of band, with the proxy tier holding a route version. During
a shard move the coordinator bumps the version, the proxy fetches new routes, and
traffic switches in **milliseconds to at most 2 seconds**. The lesson is that the
routing layer is a first-class, versioned system, not a config file.

### Code

Global uniqueness across shards, done correctly — claim first, then create:

```python
# The `email_claims` table is sharded BY EMAIL (a different key from the main
# data), so it is the single authority for "who owns this address".
async def register_user(router, email: str, tenant_id: str, name: str) -> str:
    email = email.strip().lower()
    claim_pool = router.pool_for(email)           # sharded by email
    data_pool  = router.pool_for(tenant_id)       # sharded by tenant
    user_id    = str(uuid7())

    # Step 1: claim the email. UNIQUE on the claims shard makes this atomic.
    # `expires_at` lets a reaper clean up claims whose step 2 never happened.
    try:
        await claim_pool.execute(
            """INSERT INTO email_claims (email, user_id, tenant_id, state, expires_at)
               VALUES ($1, $2, $3, 'pending', now() + interval '2 minutes')""",
            email, user_id, tenant_id)
    except asyncpg.UniqueViolationError:
        existing = await claim_pool.fetchrow(
            "SELECT state, expires_at FROM email_claims WHERE email=$1", email)
        if existing["state"] == "pending" and existing["expires_at"] < datetime.now(UTC):
            raise RetryableError("stale claim being reaped; retry")
        raise EmailTakenError(email)

    # Step 2: create the real row on the tenant's shard.
    try:
        async with data_pool.acquire() as conn, conn.transaction():
            await conn.execute(
                "INSERT INTO users (id, tenant_id, email, name) VALUES ($1,$2,$3,$4)",
                user_id, tenant_id, email, name)
    except Exception:
        # Best-effort release. The reaper is the real guarantee, because this
        # process can die between the two steps.
        await claim_pool.execute(
            "DELETE FROM email_claims WHERE email=$1 AND user_id=$2", email, user_id)
        raise

    # Step 3: confirm the claim. Now it is permanent.
    await claim_pool.execute(
        "UPDATE email_claims SET state='confirmed', expires_at=NULL "
        "WHERE email=$1 AND user_id=$2", email, user_id)
    return user_id
```

Scatter-gather with a deadline and partial results — the honest version:

```python
async def count_across_shards(router, sql: str, *args,
                              deadline_s: float = 0.5) -> tuple[int, int]:
    """Returns (total, shards_answered). NEVER wait for a slow shard on a user
    request: report coverage and let the caller decide what to show."""
    async def one(pool):
        async with asyncio.timeout(deadline_s):
            return await pool.fetchval(sql, *args)

    results = await asyncio.gather(*(one(p) for p in router.all_pools()),
                                   return_exceptions=True)
    ok = [r for r in results if isinstance(r, int)]
    if len(ok) < len(results):
        metrics.increment("shard.fanout.partial",
                          tags={"missing": len(results) - len(ok)})
    return sum(ok), len(ok)
```

Maintaining a global secondary index via the outbox, so it cannot silently drift:

```sql
-- On the DATA shard, in the same transaction as the row itself.
BEGIN;
INSERT INTO documents (id, tenant_id, external_ref, body) VALUES (...);
INSERT INTO outbox (topic, key, payload)
VALUES ('gsi.documents.external_ref',
        $external_ref,
        jsonb_build_object('external_ref', $external_ref,
                           'tenant_id',    $tenant_id,
                           'doc_id',       $doc_id));
COMMIT;
-- A relay reads `outbox` and upserts into the index shard keyed by
-- external_ref. The index is eventually consistent -- typically sub-second --
-- but it can never be permanently wrong, because the outbox row is durable
-- and the upsert is idempotent on (external_ref).
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Co-locate related tables under one shard key | Avoid when two entities genuinely have different natural keys | One of the two access patterns becomes a fan-out |
| Scatter-gather for low-QPS admin and reporting queries | Never on a hot path | Fan-out p50 ≈ shard p99; one slow shard degrades every such query |
| Global secondary index via outbox | Avoid when the index must be read-your-writes | Eventual consistency, typically sub-second, plus a relay to operate |
| Claim table for global uniqueness | Avoid when the unique value can be derived from the shard key | Two writes, a reaper, and a retryable failure window |

### Follow-ups they will ask

**Q: Why is fanning out to 32 shards in parallel not just as fast as one shard?**
A: Because you wait for the slowest. With a 1% chance any given shard is slow,
32 shards give you a 28% chance that at least one is — so the fan-out's *median*
approximates a single shard's p99. That is why Figma built request hedging into
DBProxy, and why the real answer is to design the hot path to be single-shard
rather than to make fan-out fast.

**Q: How do you paginate across shards?**
A: Offset pagination is unusable — page 10 requires each shard to produce rows
1–500 so you can discard 450 of them. Keyset pagination works: send the same
`WHERE (sort_key, id) < ($1, $2) ORDER BY ... LIMIT k` to every shard, merge the
N×k results, take the top k, and use the last one as the next cursor. You still
over-fetch by a factor of N, which is another argument for putting the sort key
in the shard key when the listing matters.

**Q: What is a reference table and when do you use it?**
A: A small, slowly-changing dimension table — currencies, plan definitions,
feature flags, country codes — replicated in full to *every* shard so joins
against it stay local. It works when the table is small enough to copy (kilobytes
to a few megabytes) and changes rarely enough that eventual propagation is fine.
Citus formalises this as `create_reference_table`; in an application-sharded
system it is a deploy-time or CDC-driven copy.

**Q: Is 2PC ever the right answer for cross-shard writes?**
A: Rarely, and I would want a specific reason. Its failure mode is that
participants hold locks in the prepared state until the coordinator tells them
what to do, so a coordinator crash leaves rows locked indefinitely and the
system unavailable for those keys. Most systems pick a saga or an outbox instead
and design the business process to tolerate a brief inconsistency — see
[6.13](#613-distributed-transactions).

### Red flags — do not say this

- ❌ "We'll just join across shards in the application." → ✅ "That is a
  scatter-gather with an in-memory merge, and its latency is the slowest
  shard's. Fine at 5 rps, not at 5,000."
- ❌ "We'll add a unique constraint on email." → ✅ "Uniqueness is per shard. A
  global unique needs a separate authority table keyed by that column."
- ❌ "Counts are cheap." → ✅ "A `count(*)` is cheap on one shard and a fan-out
  across all of them otherwise. I'd maintain per-shard counters and sum them."

---

## 6.9 Resharding without downtime

> **One-liner:** Double-write, backfill, verify, cut over, then keep the old copy
> around — and if you have logical shards, most of this is just moving ownership.

### Say this in the interview

> The playbook is five phases and the order is not negotiable. First, double
> write: the application writes to both the old location and the new one, so from
> that moment forward nothing new is missing from the target. Second, backfill:
> copy the historical data in batches, throttled on replication lag, and make the
> copy idempotent so a re-run is safe. Third, verify: compare the two copies —
> sampled at first, then a full pass — and run dark reads, where you read from
> both and compare but still serve the old result. Fourth, cut over: flip reads
> to the new location behind a percentage flag so you can roll back in seconds.
> Fifth, contract: stop double-writing and drop the old copy, days later, not
> hours. The thing that makes this survivable is a logical shard layer. If shards
> are logical and the map is versioned, moving a shard between machines is a
> data copy plus a one-row map update, and the application never learns that
> anything moved. Notion did exactly this — they went from thirty-two physical
> databases to ninety-six by redistributing four hundred and eighty logical
> shards, with zero application downtime and no query changes. The detail I
> would steal from their write-up is that the verification was implemented by
> different people than the migration, so a shared misunderstanding could not
> validate itself.

### Mental model

```
THE FIVE-PHASE PLAYBOOK

  PHASE 1  DOUBLE WRITE          (deploy, reversible)
    app --write--> OLD  (authoritative, read from here)
        --write--> NEW  (shadow; failures logged, not surfaced)
    Do this via an outbox/audit log, not two inline writes: an inline
    second write that fails leaves a gap you will not find for months.
    Notion tried logical replication first, could not keep up, and
    switched to double-writing through an audit log.

  PHASE 2  BACKFILL              (hours to days)
    for each batch (bounded by PK, ORDER BY id):
        copy -> NEW with ON CONFLICT DO NOTHING     (idempotent)
        sleep if replication lag > threshold
    Notion: 3 days on 96 CPUs. Budget for days, not hours.

  PHASE 3  VERIFY                (do not skip; do not self-verify)
    a) row counts and checksums per shard
    b) sampled row-by-row comparison
    c) DARK READS: read both, compare, serve OLD, log mismatches
    Notion had DIFFERENT PEOPLE write the verifier than the migration.

  PHASE 4  CUT OVER              (seconds, reversible for a while)
    flip reads: 1% -> 10% -> 50% -> 100%, per shard, behind a flag
    keep writing to BOTH so rollback stays instant
    Notion's switchover took 5 minutes; their own retrospective says it
    could have been zero. Stripe's traffic switch is milliseconds to 2 s.

  PHASE 5  CONTRACT              (days later, irreversible)
    stop double-writing, drop the old data, remove the flag


WITH LOGICAL SHARDS, MOVING A SHARD IS MOSTLY BOOKKEEPING

  before:  shard 1337 -> pg-07
  1. copy shard 1337's data pg-07 -> pg-12 (logical replication / dump)
  2. mark shard 1337 'migrating': writes go to BOTH pg-07 and pg-12
  3. wait for lag ~= 0, then FREEZE writes to 1337 for ~1 second
  4. UPDATE shard_map SET dsn='pg-12', map_version=map_version+1
  5. unfreeze; clients with a stale map version get an error and refresh
  after:   shard 1337 -> pg-12      (application code unchanged)
```

The one-second freeze in step 3 is the whole game: it is short enough to hide
behind a retry, and it makes the cutover a clean point in the write history
rather than a race. Stripe implements the equivalent with **fencing at the
primary node** — the source shard stops accepting writes before the target
starts — and their whole coordination completes in milliseconds to at most two
seconds.

### Enterprise production example

**Notion, 2021** (monolith → 480 shards). Logical replication could not keep up,
so they double-wrote through an audit log. The backfill ran **three days on 96
CPUs**. Verification was sampled comparison plus dark reads, deliberately built
by different engineers. Switchover took five minutes.

**Notion, 2023** (32 → 96 physical databases). This is the payoff for having a
logical layer. Hot shards were at ~90% CPU with IOPS as the ceiling. They
redistributed the same 480 logical shards from 32 hosts to 96, five per host —
**roughly tripling capacity, zero application downtime, no query changes**,
because a block's logical shard never moved, only the machine hosting it. CPU
and IOPS on the hot shards fell from about 90% toward 20%.

**Stripe DocDB** operationalised this as a product. Their Data Movement Platform
runs a six-phase migration designed around three principles: downtime shorter
than a node failover, minimal impact on live queries, and support for shards from
tiny to tens of terabytes. The traffic switch works by route versioning: the
client queries through the proxy at version one; the coordinator sets version
two and verifies replication sync; the proxy fetches new routes and starts
querying at version two, while the **source shard keeps receiving updates to
preserve a rollback path**. They have used it to upgrade their entire fleet of
2,000+ shards and to migrate petabytes.

**Discord's** migration is the counter-example on speed: they rewrote ScyllaDB's
data migrator in Rust, hit **3.2 million records per second**, and cut a
projected three-month migration to **nine days**. The last 0.0001% still stalled
— the final token ranges contained huge ranges of uncompacted tombstones and
timed out — which they fixed by compacting that range manually. Budget for the
long tail of a migration; it is never the linear part that surprises you.

### Code

```python
# PHASE 1: double-write through the outbox, not two inline writes.
async def create_document(pool, doc) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "INSERT INTO documents (id, tenant_id, body) VALUES ($1,$2,$3)",
            doc.id, doc.tenant_id, doc.body)
        # Same transaction => the shadow write can never be silently lost.
        # A relay drains this to the target shard, retrying until it succeeds.
        await conn.execute(
            "INSERT INTO outbox (topic, key, payload) VALUES ($1,$2,$3)",
            "shard.migrate.documents", str(doc.id), doc.as_json())
```

```python
# PHASE 2: idempotent, resumable, lag-throttled backfill.
async def backfill_shard(src, dst, logical_shard: int, batch: int = 2_000):
    cursor = await load_checkpoint(logical_shard)      # resumable after a crash
    while True:
        rows = await src.fetch(
            "SELECT * FROM documents WHERE shard = $1 AND id > $2 "
            "ORDER BY id LIMIT $3", logical_shard, cursor, batch)
        if not rows:
            break
        await dst.executemany(
            """INSERT INTO documents (id, tenant_id, body, updated_at)
               VALUES ($1,$2,$3,$4)
               ON CONFLICT (id) DO UPDATE
                 SET body = EXCLUDED.body, updated_at = EXCLUDED.updated_at
               WHERE documents.updated_at < EXCLUDED.updated_at""",
            # ^ last-writer-wins on updated_at: the live double-write may have
            #   already inserted a NEWER version. Never clobber it with history.
            [(r["id"], r["tenant_id"], r["body"], r["updated_at"]) for r in rows])
        cursor = rows[-1]["id"]
        await save_checkpoint(logical_shard, cursor)

        lag = await dst.fetchval(
            "SELECT coalesce(max(extract(epoch FROM replay_lag)),0) "
            "FROM pg_stat_replication")
        await asyncio.sleep(5.0 if lag > 5 else 0.02)
```

```python
# PHASE 3: dark reads. Serve OLD, compare with NEW, alert on drift.
async def read_document(router, doc_id: str, tenant_id: str):
    old = await router.old_pool(tenant_id).fetchrow(SELECT_DOC, doc_id)
    if random.random() < settings.DARK_READ_SAMPLE:        # e.g. 0.05
        asyncio.create_task(_compare(router, doc_id, tenant_id, old))
    return old

async def _compare(router, doc_id, tenant_id, old):
    try:
        new = await router.new_pool(tenant_id).fetchrow(SELECT_DOC, doc_id)
        if _digest(old) != _digest(new):
            # Never fail the user request on a dark-read mismatch. Count it.
            metrics.increment("reshard.dark_read.mismatch")
            log.error("dark read mismatch", doc_id=doc_id,
                      old=_digest(old), new=_digest(new))
    except Exception as e:
        metrics.increment("reshard.dark_read.error")
```

```sql
-- PHASE 4: the cutover, with a version-fenced map. A client holding an old
-- map_version is told to refresh instead of writing to the wrong shard.
BEGIN;
SELECT pg_advisory_xact_lock(hashtext('shard_map_cutover'));
UPDATE shard_map
   SET dsn = target_dsn, target_dsn = NULL, state = 'active',
       map_version = (SELECT max(map_version) + 1 FROM shard_map)
 WHERE logical_shard = $1 AND state = 'migrating';
COMMIT;
-- Clients poll map_version every few seconds and refresh on a bump; any write
-- carrying a stale version is rejected with a retryable error.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Double-write via outbox | Never two inline writes with no durable record | An outbox table and a relay to operate |
| Dark reads before cutover | Avoid skipping them to save a week | Extra read load on both sides during the comparison window |
| Percentage-based cutover per shard | Avoid a big-bang flip | A longer migration in exchange for a seconds-long rollback |
| Keep the old copy for days after cutover | Avoid dropping it the same day | Double storage cost for a week — trivially worth it |

### Follow-ups they will ask

**Q: How do you verify two copies of a large table actually match?**
A: In layers, cheapest first. Row counts per shard, then a rolling checksum over
ranges of the primary key (`md5` over a concatenation, computed batch by batch,
which parallelises and resumes), then sampled row-by-row comparison weighted
toward recently written rows, then dark reads on live traffic. Counts catch gross
errors; dark reads catch the subtle ones that only appear under concurrency,
which are the ones that matter.

**Q: What happens to in-flight writes during the cutover?**
A: That is what the brief freeze is for. Mark the shard read-only, wait for
in-flight transactions to drain and replication to catch up, flip the map, then
release. Clients see a retryable error for a second or so and retry into the new
shard. Without a freeze you get a window where two nodes accept writes for the
same keys, which is split brain by another name — Stripe's answer is fencing at
the primary, and it is the same idea.

**Q: Can you use logical replication instead of double-writing?**
A: Sometimes, and it is much less application work when it fits. Notion tried it
and it could not keep up with their write volume, which is the standard failure:
logical decoding is single-threaded per slot, so a high-write monolith outruns
it. Test it against production write rates early, because discovering it cannot
keep up in month three of a migration is expensive.

**Q: How do you roll back after cutover?**
A: You keep double-writing after the flip, so the old copy stays current and
rollback is another map update. Stripe does exactly this — during the switch,
the source shard continues receiving updates specifically to preserve a rollback
path. The point of no return is phase 5, and it should be days after the traffic
has been at 100%.

### Red flags — do not say this

- ❌ "We'll take a maintenance window and copy the data." → ✅ "Double-write,
  backfill, verify with dark reads, then a per-shard cutover with a
  seconds-long rollback."
- ❌ "The backfill will take a couple of hours." → ✅ "Notion's took three days
  on 96 CPUs. I'd measure a sample and plan for the long tail."
- ❌ "We verified with row counts." → ✅ "Counts catch missing rows. Dark reads
  catch wrong ones, which is the failure that actually reaches users."

---
## 6.10 Consistency models

> **One-liner:** Consistency models are a ladder of promises about what a read is
> allowed to return, and each rung down buys latency and availability by allowing
> one more thing a user might notice.

### Say this in the interview

> I think of consistency as a ladder, and I try to name the rung rather than say
> "strong" or "eventual". At the top is linearizability: every operation appears
> to take effect at a single instant between its call and its return, so once a
> write returns, every subsequent read anywhere sees it — that is what a single
> Postgres primary gives you, and what a consensus system like etcd or Spanner
> gives you across nodes, and it costs a coordination round trip on every
> operation. Below that is sequential consistency, where everyone agrees on one
> order but that order need not match real time. Below that is causal
> consistency, which is the most useful rung in practice: operations that are
> causally related are seen in order by everyone, so a reply never appears
> before the comment it replies to, while genuinely concurrent operations can be
> seen in different orders. Then the two client-centric guarantees:
> read-your-writes, where a user always sees their own writes even if others do
> not yet, and monotonic reads, where a user never sees time go backwards.
> Eventual consistency at the bottom promises only that replicas converge if
> writes stop, which is almost no promise at all in isolation. The practical
> insight is that most products do not need linearizability — they need
> read-your-writes plus monotonic reads, which are session guarantees I can
> implement with routing rather than with consensus, and which cost almost
> nothing compared to a global coordination round trip.

### Mental model

```
STRONGEST                                                     WEAKEST
   |                                                             |
   v                                                             v

LINEARIZABLE     "there is one copy, and writes are instant"
  user-visible:  Alice posts. Bob refreshes 1 ms later, anywhere in
                 the world. Bob sees it. Guaranteed.
  cost:          consensus round trip per op. Cross-region = 70 ms+.
  examples:      etcd, ZooKeeper, Spanner, single-primary Postgres,
                 DynamoDB with ConsistentRead=true

SEQUENTIAL       "everyone agrees on ONE order, maybe not real time"
  user-visible:  everyone sees the same feed order, but it may lag
                 real time. Two users' posts may be ordered oddly.

CAUSAL           "cause is seen before effect, everywhere"
  user-visible:  Bob's reply NEVER appears before Alice's comment.
                 Two unrelated posts may appear in different orders
                 to different people -- and nobody notices.
  cost:          track happens-before (version vectors), no consensus
  examples:      MongoDB causally consistent sessions, COPS-style stores

READ-YOUR-       "you always see your OWN writes"
WRITES           user-visible:  you edit your profile and see the new
  (session)                     value. Others may still see the old.
  cost:          route that user to the primary for a window (6.3)

MONOTONIC        "time never goes backwards for one user"
READS            user-visible:  you see a comment, refresh, and it is
  (session)                     still there. It does not vanish.
  cost:          pin the user to one replica

EVENTUAL         "replicas converge IF writes stop"
  user-visible:  anything, in any order, for an unbounded time.
                 Alone, this is almost no promise at all.
  cost:          none. This is the default of an async replica.
```

**The point most candidates miss:** read-your-writes and monotonic reads are
*session* guarantees, not global ones. They are about what one client sees over
time, which means you can implement them with routing and sticky sessions rather
than with coordination. That is why they are cheap and why they are usually the
right target. "Eventual consistency with read-your-writes and monotonic reads
per session" is a far better answer than "strong consistency" for most products,
and it says you have thought about what the user actually perceives.

**Mapping each rung to a user-visible bug:**

| Missing guarantee | What the user reports |
|---|---|
| Linearizability | "Two people both got the last ticket" |
| Causal | "I see a reply to a comment that isn't there" |
| Read-your-writes | "I saved it and it didn't save" |
| Monotonic reads | "My comment appeared, then disappeared, then came back" |
| Convergence at all | "Two devices show different data, permanently" |

### Enterprise production example

**Discord** is a good study in choosing rungs per feature. Messages are stored in
a wide-column store with tunable consistency, and reads of channel history do
not need linearizability — if your client is 50 ms behind, nobody can tell,
because the next WebSocket push corrects it. But the *client's own message* must
appear immediately, so the sending client renders it optimistically from local
state (read-your-writes, implemented in the UI rather than the database) and
reconciles when the server acknowledges. That is the pattern to name: satisfy
the session guarantees at the edge, and let the storage layer be eventually
consistent.

**MongoDB** ships causal consistency as an explicit, first-class session
setting: create a session with `causalConsistency: true` and the driver tracks
the `operationTime` of each operation and attaches `afterClusterTime` to
subsequent reads, so the server blocks the read until its cluster time has
advanced past it. That is causal consistency implemented as a client-side token
plus a server-side wait — structurally the same mechanism as the LSN token in
[6.3](#63-read-replicas--the-read-after-write-problem), which is a nice thing to
point out because it shows the idea generalises.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Linearizable for money, inventory, locks, leader election | Avoid for feeds, search, recommendations, analytics | A coordination round trip per operation; unavailability during a partition |
| Causal for social features and collaborative apps | Avoid when a global total order is genuinely required | Version-vector metadata on every object |
| Read-your-writes + monotonic reads as the default target | Avoid claiming they are "strong consistency" | Routing complexity, sticky sessions |
| Eventual for derived data (search indexes, counters, caches) | Never for the authoritative record of a financial event | Windows where two users disagree |

### Follow-ups they will ask

**Q: Is eventual consistency ever the right answer for money?**
A: For the *ledger*, no — the record of what happened must be linearizable at
the account level. For everything derived from it, usually yes: a displayed
balance can be a second stale, a monthly statement is eventually consistent by
construction, and fraud scoring reads a replica. The trick is to make the
authoritative write single-shard and linearizable, and let the read models be
eventual.

**Q: What is the difference between linearizability and serializability?**
A: Serializability is about *transactions*: the outcome is equivalent to running
them one at a time in some order, with no requirement that the order match real
time. Linearizability is about *single objects* and real time: once a write
returns, all later reads see it. They are orthogonal, and the combination —
strict serializability — is what Spanner provides and what makes it expensive.
Postgres SERIALIZABLE on one node gives you both in practice because there is
only one node.

**Q: How do you decide which rung a feature needs?**
A: I write the bug report the user would file if the guarantee were missing. "I
saved it and it didn't save" means read-your-writes. "Two people booked the same
seat" means linearizability at that key. "My comment vanished on refresh" means
monotonic reads. If I cannot write a plausible bug report, the feature is fine
with eventual consistency and I should not pay for more.

### Red flags — do not say this

- ❌ "We need strong consistency." → ✅ "This write needs to be linearizable at
  the account key; the profile read only needs read-your-writes."
- ❌ "Eventual consistency means it'll be consistent in a second." → ✅ "Eventual
  consistency promises convergence with no time bound. If I need a bound, I
  measure lag and set an SLO on it."

---

## 6.11 CAP theorem — and PACELC

> **One-liner:** CAP is not a menu of two — it says that *during a network
> partition* you must choose between refusing requests and returning possibly
> stale data, and PACELC adds the choice you make the other 99.99% of the time.

### Say this in the interview

> CAP is stated badly almost everywhere, so I like to state it precisely: when a
> network partition splits your nodes, a distributed system must choose between
> remaining consistent — meaning it refuses requests it cannot serve correctly,
> so it is unavailable — or remaining available, meaning it answers with data
> that may be stale or that may later conflict. That is the whole theorem. It is
> not "pick two of three", because partition tolerance is not a property you
> choose; the network will partition whether you like it or not, so a "CA
> system" is just a system that has not decided what it does during a partition.
> Single-node Postgres is sometimes called CA, but that only means there is
> nothing to partition — the moment you add a replica in another rack, you have
> to answer the question. The more useful model is PACELC: if there is a
> Partition, choose Availability or Consistency; Else — in normal operation,
> which is almost all the time — choose Latency or Consistency. That second half
> is where you actually live. DynamoDB and Cassandra are PA/EL: available during
> partitions, and even when the network is fine they default to returning fast
> rather than coordinating. Spanner and etcd are PC/EC: they refuse rather than
> diverge, and they pay a coordination round trip on every operation even when
> nothing is wrong. GitHub's 2018 outage is what happens when you have not
> decided: the system chose availability automatically by promoting a new
> primary, then the humans chose consistency and took the site read-only for
> twenty-four hours to reconcile.

### Mental model

```
THE CORRECT STATEMENT

  A network partition happens. Node A cannot reach node B.
  A client sends a request to A.

     A can either:
       (C) refuse, because it cannot confirm it has the latest data
           -> the system is UNAVAILABLE for that request
       (A) answer from its local state
           -> the answer may be STALE, and a concurrent write on B's
              side may later conflict

  That is CAP. It says nothing about normal operation.


WHY "CA" DOES NOT EXIST

  P is not a choice. Cables get cut, switches get replaced, a routing
  change blackholes a subnet, GC pauses look like partitions. You do
  not choose whether partitions happen; you only choose your behaviour
  when they do. A system marketed as "CA" is one whose partition
  behaviour is undefined -- which in practice means "split brain".

  GitHub 2018: a 43-SECOND partition. Not a data centre fire. Routine
  maintenance on optical equipment. Cost: 24 h 11 min of degradation.


PACELC -- the model to actually use

    if (P)  then  A  or  C          <- rare: during a partition
    else          L  or  C          <- always: normal operation

  +-------------+---------+-------------------------------------------+
  | System      | PACELC  | What that means concretely                |
  +-------------+---------+-------------------------------------------+
  | DynamoDB    | PA / EL | stays up in a partition; default reads are|
  |             |         | eventually consistent and ~half the cost  |
  | Cassandra / | PA / EL | tunable per query; LOCAL_QUORUM is the    |
  | ScyllaDB    |         | usual setting: fast, not linearizable     |
  | MongoDB     | PC / EC | majority write concern + majority read    |
  |             |         | concern; a minority partition takes no    |
  |             |         | writes                                    |
  | Spanner     | PC / EC | refuses rather than diverge; pays a       |
  |             |         | Paxos round trip and TrueTime commit wait |
  | etcd / ZK   | PC / EC | a minority partition serves no writes at  |
  |             |         | all -- by design; this is the point       |
  | Postgres    | PC / EC | one primary: a partitioned replica cannot |
  | (1 primary) |         | accept writes; sync commit adds an RTT    |
  +-------------+---------+-------------------------------------------+
```

**The EL/EC half is the one that shows up in your latency graphs.** Partitions
are rare; the choice between latency and consistency is made on every single
request. A team that says "we're AP" and then reads at `QUORUM` in a
three-region cluster has chosen EC without realising it, and is paying a
cross-region round trip on every read.

**CAP applies per operation, not per system.** DynamoDB is PA/EL by default and
strongly consistent when you pass `ConsistentRead=true`. Cassandra is
per-statement. Postgres lets you choose `synchronous_commit` per transaction.
The mature answer is "this operation is CP, that one is AP", not "our database
is AP".

### Enterprise production example

**GitHub, October 2018** is the best CAP case study in the industry because
every element is documented. The partition lasted 43 seconds. Orchestrator, a
Raft-based failover system, correctly formed a quorum among the nodes it could
reach and promoted West Coast primaries — an *availability* choice, made
automatically. Because replication was asynchronous, the East Coast had writes
the West Coast did not, and vice versa once traffic moved. When the partition
healed, the humans made the opposite choice: at 23:13 UTC they prioritised data
integrity and put the site into a degraded, largely read-only state for **24
hours and 11 minutes** while they restored from backups and reconciled. Their
remediations were, precisely, PACELC decisions: restrict automatic failover to
intra-region (do not let the system choose A during a cross-region partition),
and adopt semi-synchronous replication (choose C over L in normal operation).

The instructive contrast is **Shopify's pods**. By making each pod a fully
isolated set of datastores with **zero cross-pod communication**, a partition
affecting one pod cannot cascade: the CAP choice is made independently per pod,
and the blast radius of choosing either way is one pod's shops rather than the
platform. That is the architectural move that makes the CAP trade-off tolerable
— not choosing better, but choosing smaller.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| CP for ledgers, inventory, locks, config, leader election | Avoid CP for a global feed or a session store | Unavailability during a partition; a coordination RTT always |
| AP for feeds, presence, telemetry, caches, shopping carts | Avoid AP for anything where two conflicting outcomes are unrecoverable | Conflicts you must resolve, and windows of stale reads |
| Per-operation choice (DynamoDB `ConsistentRead`, Cassandra CL) | Avoid one global setting for a mixed workload | You must reason about it query by query |
| Isolating the blast radius (pods, cells, shards) | — | More infrastructure, less cross-tenant sharing |

### Follow-ups they will ask

**Q: Is Postgres CP or AP?**
A: A single instance is neither, because CAP is about behaviour during a
partition between nodes. A primary with replicas is CP for writes: a replica
that cannot reach the primary will not accept writes, so a partitioned minority
is unavailable for writes rather than divergent. It becomes AP-flavoured only if
you configure automatic failover badly enough to allow two primaries, which is
the bug, not the design.

**Q: If partitions are so rare, why does CAP matter?**
A: Two reasons. First, "rare" means seconds-to-minutes a few times a year, and
what a system does in those seconds determines whether you have an incident or a
data-reconciliation project — GitHub's ratio was 43 seconds to 24 hours. Second,
the EL/EC half of PACELC is not rare at all: it is every request, and it is
where your p99 comes from.

**Q: Doesn't Spanner beat CAP?**
A: No, and Google's own papers are explicit about this. Spanner is CP: during a
partition, the minority side cannot commit. Its practical availability is very
high because Google controls the network and engineers it to make partitions
extremely rare, not because the theorem is avoided. It also pays a real cost in
the EC direction — the TrueTime commit-wait adds latency to every read-write
transaction.

**Q: What does "tunable consistency" actually tune?**
A: How many replicas must respond before the operation is considered done, which
moves you along the PACELC axes per query. `ONE` is maximum availability and
minimum latency; `QUORUM` gives you the overlap property; `ALL` gives the
strongest read but makes any single node's failure an outage for that key.
Crucially, quorum is still not linearizability — see [6.12](#612-quorum-reads-and-writes).

### Red flags — do not say this

- ❌ "CAP says pick two of three." → ✅ "CAP says that during a partition you
  pick between consistency and availability. Partition tolerance is not
  optional."
- ❌ "We built a CA system." → ✅ "There is no CA system in a network. We are CP
  for writes and AP for these specific reads."
- ❌ "We're AP so we're always available." → ✅ "We're AP for these reads, which
  means we accept stale data and conflict resolution. Writes to the ledger are
  CP."

---

## 6.12 Quorum reads and writes

> **One-liner:** `W + R > N` guarantees the read set and the write set overlap, so
> at least one responding replica has the newest value — which is much weaker
> than linearizability, for reasons worth naming.

### Say this in the interview

> In a leaderless system there are N replicas for each key, a write waits for W
> acknowledgements, and a read waits for R responses. If W plus R is greater
> than N, the two sets must overlap in at least one node, so the read is
> guaranteed to *see* the latest acknowledged write in at least one response —
> and it picks the newest by version or timestamp. Common configurations: N of
> three with W and R both two is the balanced default; W of one and R of one is
> fastest and gives no overlap guarantee at all; W of three and R of one makes
> reads cheap but any node being down blocks writes. What matters more than the
> arithmetic is that quorum is not linearizability, and there are four concrete
> reasons. Sloppy quorums accept writes on nodes outside the key's home replica
> set when those are unreachable, which breaks the overlap property by
> definition. A write that fails partway is not rolled back, so a subsequent
> read may or may not see it, and two reads can disagree. Concurrent writes are
> resolved by last-write-wins on a timestamp, so clock skew silently discards
> data. And read repair happens after the fact, so there is no ordering
> guarantee between concurrent operations. So I would say quorum gives you a
> strong probability of freshness and eventual convergence, and if I need
> linearizability I need consensus — Paxos or Raft — which in Cassandra means
> lightweight transactions and roughly four round trips instead of one.

### Mental model

```
N = 3, W = 2, R = 2      W + R = 4 > 3      -> sets must overlap

  write "v2":  [R1 v2 ok] [R2 v2 ok] [R3 v1 -- slow/down, ack not waited]
  read:        ask R2 and R3  -> {v2, v1} -> newest wins -> v2  CORRECT
  read:        ask R1 and R3  -> {v2, v1} -> v2                 CORRECT
  read:        ask R2 and R1  -> {v2, v2} -> v2                 CORRECT
                       no read pair can miss R1 AND R2

  W=1, R=1  (W+R=2, NOT > 3):
  write v2 -> R1 only.  read from R3 -> v1.  STALE. No guarantee.


THE CONFIGURATIONS AND WHAT EACH IS FOR

  N  W  R  | W+R>N | profile
  ---------+-------+---------------------------------------------------
  3  2  2  |  yes  | the default. Survives 1 node down for both r & w.
  3  3  1  |  yes  | cheap reads, but ANY node down blocks ALL writes.
  3  1  3  |  yes  | cheap writes, any node down blocks all reads.
  3  1  1  |  NO   | fastest, fully eventual. Cassandra CL=ONE.
  3  2  1  |  NO   | common in practice + read repair. Fast, not safe.


CASSANDRA CONSISTENCY LEVELS (per statement, not per cluster)

  ONE / LOCAL_ONE   1 replica. Lowest latency, no guarantee.
  QUORUM            floor(RF/2)+1 across ALL datacentres.
                    In a 2-DC cluster this crosses the WAN: ~70 ms.
  LOCAL_QUORUM      quorum within the LOCAL datacentre only.
                    <-- the production default for multi-DC. No WAN hop.
  EACH_QUORUM       quorum in EVERY datacentre (writes only). Expensive.
  ALL               every replica. One node down = outage for that key.

DYNAMODB is the same idea with two buttons:
  eventually consistent read  -> ~half the cost, may be stale
  strongly consistent read    -> full cost, not available on GSIs,
                                 and not supported cross-region


WHY QUORUM != LINEARIZABLE  (name these four)

  1. SLOPPY QUORUM. If the home replicas are unreachable, the write is
     accepted by ANY W reachable nodes and stored as a HINT. The read
     quorum over the home nodes then does not overlap it at all.
       node down -> write goes to a stand-in -> HINTED HANDOFF replays
       it later. Great for availability, fatal to the overlap proof.

  2. PARTIAL WRITES ARE NOT ROLLED BACK. A write that reached 1 of 3
     and then failed leaves that value on 1 node. A later read may or
     may not see it, and two reads in a row can disagree.

  3. LAST-WRITE-WINS BY TIMESTAMP. Two concurrent writes are resolved
     by cell timestamp. Clock skew between coordinators silently
     discards the "loser" -- which may be the one that happened later.

  4. NO ORDERING. Quorum says a read sees SOME recent write. It does
     not order concurrent operations, so it cannot support
     read-modify-write. That needs consensus: Cassandra's lightweight
     transactions use Paxos per partition -- roughly 4 round trips.


REPAIR: how replicas converge despite all of the above

  read repair      during a read, the coordinator notices a stale
                   replica and pushes the newer value to it
  hinted handoff   a coordinator stores writes for a down node and
                   replays them when it returns (bounded window!)
  anti-entropy     `nodetool repair`: Merkle-tree comparison between
                   replicas. MUST be run regularly -- within
                   gc_grace_seconds -- or deleted data can resurrect.
```

That last point is a genuinely good detail to know: if you do not run repair
within `gc_grace_seconds`, a node that was down while a delete was tombstoned
can come back and re-propagate the deleted row, because its tombstone has
already been compacted away elsewhere. Deleted data resurrecting is the
canonical Cassandra operational horror story.

### Enterprise production example

**Discord** ran Cassandra with replication factor 3 at trillions of messages
across 177 nodes, and the thing that broke was not the quorum arithmetic — it
was operational load: JVM garbage-collection pauses and compaction backlogs,
which made p99 reads swing between 40 ms and 125 ms and required regular manual
intervention. Moving to **ScyllaDB** kept the identical data model, replication
factor and consistency semantics but replaced the JVM with a C++ shard-per-core
implementation: 72 nodes, 9 TB each, steady 15 ms p99 reads and 5 ms p99 writes.
The lesson for a quorum discussion is that in leaderless systems the failure you
actually hit is a *slow* node, not a *dead* one — quorum handles dead nodes
gracefully and slow nodes badly, because you wait for R responses and a garbage
collecting node is still responding, just late.

### Code

```python
# Cassandra/ScyllaDB: set consistency PER STATEMENT. A cluster-wide default is
# a design smell -- different operations have different requirements.
from cassandra import ConsistencyLevel
from cassandra.query import SimpleStatement
from cassandra.policies import DCAwareRoundRobinPolicy, TokenAwarePolicy

session = cluster.connect("chat")

# Hot read: LOCAL_QUORUM keeps the request inside the datacentre. Plain QUORUM
# in a 2-DC cluster crosses the WAN and adds ~70 ms to every read.
read_recent = SimpleStatement(
    "SELECT * FROM messages_by_channel WHERE channel_id=%s AND bucket=%s "
    "LIMIT 50",
    consistency_level=ConsistencyLevel.LOCAL_QUORUM)

# Telemetry write: ONE. Losing a metric point is acceptable; latency is not.
write_metric = SimpleStatement(
    "INSERT INTO metrics (series, ts, value) VALUES (%s,%s,%s)",
    consistency_level=ConsistencyLevel.ONE)

# Read-modify-write: quorum CANNOT do this. IF NOT EXISTS triggers a
# lightweight transaction -- Paxos per partition, ~4 round trips, and it
# serialises every LWT on that partition. Use it rarely and deliberately.
claim_username = SimpleStatement(
    "INSERT INTO usernames (name, user_id) VALUES (%s,%s) IF NOT EXISTS",
    serial_consistency_level=ConsistencyLevel.LOCAL_SERIAL,
    consistency_level=ConsistencyLevel.LOCAL_QUORUM)

result = session.execute(claim_username, (name, user_id))
if not result.one().applied:
    raise UsernameTakenError(name)
```

```python
# DynamoDB: the same two choices, different names. Note that a strongly
# consistent read is NOT available on a Global Secondary Index -- GSIs are
# always eventually consistent, which is a very common production surprise.
resp = table.get_item(Key={"pk": f"USER#{uid}"}, ConsistentRead=True)

# Conditional write = optimistic concurrency at the API layer. This is how you
# get read-modify-write safety without a transaction (see Module 05, 5.8).
try:
    table.update_item(
        Key={"pk": f"USER#{uid}"},
        UpdateExpression="SET credits = credits - :n, version = :new",
        ConditionExpression="version = :cur AND credits >= :n",
        ExpressionAttributeValues={":n": 5, ":cur": v, ":new": v + 1},
    )
except client.exceptions.ConditionalCheckFailedException:
    raise StaleWriteError("re-read and retry")
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `LOCAL_QUORUM` as the multi-DC default | Avoid plain `QUORUM` across datacentres on the hot path | ~70 ms per operation when the quorum crosses an ocean |
| `ONE` for telemetry, logs, presence | Never for data a user will notice missing | Silent loss and stale reads |
| Lightweight transactions / conditional writes for read-modify-write | Avoid on a hot partition | ~4 round trips, and LWTs on one partition serialise |
| Sloppy quorum + hinted handoff for write availability | Avoid when you were relying on the overlap proof | Writes land outside the home replica set; reads can miss them |

### Follow-ups they will ask

**Q: `W + R > N` — so why is a quorum read not linearizable?**
A: Four reasons I would name in order. Sloppy quorums put writes on nodes
outside the replica set, so the overlap proof does not hold. Failed writes are
not rolled back, so two consecutive reads can disagree. Concurrent writes are
resolved by last-write-wins on a timestamp, so clock skew loses data. And there
is no ordering between concurrent operations, so read-modify-write is unsafe.
Quorum gives you a strong freshness *probability* and eventual convergence, not
a real-time guarantee.

**Q: What is hinted handoff and what is its failure mode?**
A: When a replica is down, the coordinator stores the write locally as a "hint"
and replays it when the node returns. It preserves write availability. The
failure mode is that hints have a bounded retention window — if the node stays
down past it, the hints are dropped, and that replica is now permanently missing
those writes until an anti-entropy repair fixes it. Hinted handoff is a
convenience, not a durability mechanism.

**Q: You increase replication factor from 3 to 5. What actually changes?**
A: Storage and write cost go up proportionally, since every write goes to five
nodes. Quorum becomes 3 instead of 2, so you tolerate two node failures instead
of one — better availability. But read and write latency get slightly worse
because you wait for more responses, and you are now more exposed to the slowest
of a larger set. RF 3 with LOCAL_QUORUM is the default for a reason.

**Q: Why must you run `nodetool repair` regularly?**
A: Because read repair only fixes rows that are actually read, and hinted
handoff only covers bounded outages. Anti-entropy repair compares Merkle trees
between replicas and reconciles everything. If you skip it beyond
`gc_grace_seconds`, tombstones get compacted away on the nodes that have them
while a node that missed the delete still holds the row — and when it comes
back, the deleted data resurrects.

### Red flags — do not say this

- ❌ "We use quorum so reads are strongly consistent." → ✅ "Quorum guarantees
  the read and write sets overlap. Sloppy quorums, partial writes and LWW mean
  it is not linearizable."
- ❌ "We'll set consistency to ALL to be safe." → ✅ "`ALL` means one slow or
  dead replica is an outage for that key. `QUORUM` gives the overlap property
  and tolerates a failure."
- ❌ "Cassandra supports transactions." → ✅ "Lightweight transactions give
  compare-and-set per partition via Paxos, at roughly four round trips. There
  are no multi-partition transactions."

---

## 6.13 Distributed transactions

> **One-liner:** There is no good way to commit atomically across two databases,
> so the practical answer is to make one local transaction durable and everything
> else asynchronous, idempotent and compensatable.

### Say this in the interview

> Two-phase commit is the textbook answer and it is the one I would argue
> against. A coordinator asks every participant to prepare; each one does the
> work, takes the locks and votes yes; then the coordinator tells everyone to
> commit. The problem is the window between prepare and commit: participants are
> holding locks and cannot decide unilaterally, so if the coordinator dies after
> the prepare, they block — indefinitely — waiting to be told what to do. That is
> why availability under 2PC is worse than the availability of any single
> participant, and why most large systems avoid it. The pattern that replaced it
> is the saga: model the operation as a sequence of local transactions, each
> with a compensating action that semantically undoes it. Choreography means each
> service emits an event and the next one reacts, which is simple for three steps
> and unreadable at seven because no single place describes the flow.
> Orchestration means a coordinator explicitly drives each step and issues
> compensations on failure, which is what I would use past three steps because
> the state machine is inspectable. The critical detail is that a compensation is
> not a rollback — you cannot un-send an email, so you send a cancellation, and
> you cannot un-charge a card in the same way, so you issue a refund. And
> underneath all of it, the piece I would actually build first is the
> transactional outbox: write the business row and the intent-to-publish in one
> local transaction, then have a relay deliver it at least once. That turns
> "database and message broker must commit together" — which is a distributed
> transaction — into one local commit plus a retry loop.

### Mental model

```
TWO-PHASE COMMIT, and exactly where it hurts

  coordinator          participant A          participant B
       |--- PREPARE ------->|                      |
       |--- PREPARE ---------------------------->  |
       |<-- yes (locks held)|                      |
       |<-- yes (locks held) ---------------------  |
       |                                            |
       X  <-- COORDINATOR DIES HERE                 |
       |                                            |
       |    A and B are PREPARED. They hold locks. They may not
       |    commit (B might have voted no) and may not abort
       |    (B might have voted yes). They BLOCK. Forever, until
       |    a human resolves it.

  => availability(2PC) < availability(least available participant)
  => in Postgres these are `PREPARE TRANSACTION` entries visible in
     pg_prepared_xacts; a forgotten one holds locks AND blocks vacuum
     cluster-wide, indefinitely. This is why max_prepared_transactions
     defaults to 0.


SAGA -- a sequence of local transactions + compensations

  T1 reserve inventory   -> C1 release inventory
  T2 charge card         -> C2 refund charge
  T3 create shipment     -> C3 cancel shipment
  T4 send confirmation   -> C4 send cancellation email

  T3 fails  ->  run C2, then C1, in reverse order.

  NOT a rollback: the charge HAPPENED and the refund is a second,
  visible event. Sagas trade atomicity for a semantically-correct
  eventual outcome, and the intermediate states are user-visible.


CHOREOGRAPHY                        ORCHESTRATION
  Order --OrderCreated-->             +-- Orchestrator --+
  Payment --Charged----->             |  step 1 -> Inventory
  Shipping --Shipped---->             |  step 2 -> Payment
                                      |  step 3 -> Shipping
  + no central component              |  on failure: compensate
  + services stay decoupled           +-------------------
  - the flow exists NOWHERE           + one place describes the flow
  - debugging = reading 5 logs        + state is queryable
  - cycles are easy to create         - the orchestrator is a component
  use for: <= 3 steps                 use for: 4+ steps, or money


TRANSACTIONAL OUTBOX -- the piece to build first

  BEGIN
    INSERT INTO orders ...            <- business state
    INSERT INTO outbox  (topic, key, payload, created_at)
  COMMIT                              <- ONE local, atomic commit
       |
       v
  relay: SELECT ... FROM outbox WHERE published_at IS NULL
         ORDER BY id FOR UPDATE SKIP LOCKED LIMIT 100
      -> publish to Kafka/Pub-Sub
      -> UPDATE outbox SET published_at = now()
       |
       v
  consumer: idempotent (dedupe on the message key)

  Guarantees AT-LEAST-ONCE delivery of an event that is atomic with
  the database write. It does NOT guarantee exactly-once -- the relay
  can crash after publishing and before marking, so the consumer MUST
  be idempotent. See Module 09 -- Idempotency.
```

### Enterprise production example

**Stripe's DocDB** shows what it takes to avoid a distributed transaction during
a data migration: rather than committing across two shards, they use
**bidirectional replication** between source and target with a custom MongoDB
patch that filters writes to prevent replication loops, plus **fencing at the
primary** so only one side accepts writes at the switch point. The entire
coordination completes in milliseconds to at most two seconds. Every element
there — fencing, versioned routing, keeping the source updated for rollback — is
chosen specifically so no operation ever needs to be atomic across two
databases.

The orchestration pattern has well-known production implementations worth
naming: **Temporal** (originating from Uber's Cadence), **Netflix Conductor**,
and **AWS Step Functions**. All three exist because hand-rolled orchestration
state machines are where sagas go wrong — you need durable execution state,
retries with backoff, timeouts, and a way to inspect a stuck workflow. For the
outbox side, **Debezium** reads the Postgres or MySQL write-ahead log and
publishes outbox rows to Kafka, which is the standard production implementation
of the relay.

### Code

The outbox, end to end. This is the highest-value 60 lines in the module.

```sql
CREATE TABLE outbox (
    id           bigserial PRIMARY KEY,
    topic        text        NOT NULL,
    key          text        NOT NULL,        -- partition + dedupe key
    payload      jsonb       NOT NULL,
    created_at   timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz
);

-- Partial index: only unpublished rows are indexed, so the relay's claim
-- query stays fast even with millions of published rows awaiting cleanup.
CREATE INDEX idx_outbox_unpublished ON outbox (id) WHERE published_at IS NULL;
```

```python
# Producer: business state and the intent to publish, in ONE transaction.
async def place_order(pool, order: Order) -> None:
    async with pool.acquire() as conn, conn.transaction():
        await conn.execute(
            "INSERT INTO orders (id, customer_id, total_cents, status) "
            "VALUES ($1,$2,$3,'pending')",
            order.id, order.customer_id, order.total_cents)
        await conn.execute(
            "INSERT INTO outbox (topic, key, payload) VALUES ($1,$2,$3)",
            "order.placed", str(order.id), order.as_json())
    # If the process dies here, the row and the outbox entry are both durable.
    # If the transaction rolls back, NEITHER exists. That is the whole point.


# Relay: at-least-once delivery. SKIP LOCKED lets N relays run concurrently.
async def relay(pool, producer, batch: int = 100):
    while True:
        async with pool.acquire() as conn, conn.transaction():
            rows = await conn.fetch(
                """SELECT id, topic, key, payload FROM outbox
                    WHERE published_at IS NULL
                    ORDER BY id
                    FOR UPDATE SKIP LOCKED
                    LIMIT $1""", batch)
            if not rows:
                await asyncio.sleep(0.2)
                continue
            for r in rows:
                # Publish INSIDE the transaction that holds the row lock, so a
                # crash before COMMIT leaves the row unpublished and it is
                # simply retried. Duplicates are possible; that is by design.
                await producer.send(r["topic"], key=r["key"],
                                    value=r["payload"],
                                    headers=[("msg-id", str(r["id"]).encode())])
            await conn.execute(
                "UPDATE outbox SET published_at = now() WHERE id = ANY($1)",
                [r["id"] for r in rows])


# Consumer: idempotent, because at-least-once means duplicates WILL arrive.
async def on_order_placed(pool, msg) -> None:
    async with pool.acquire() as conn, conn.transaction():
        inserted = await conn.fetchval(
            "INSERT INTO processed_messages (msg_id) VALUES ($1) "
            "ON CONFLICT DO NOTHING RETURNING 1", msg.headers["msg-id"])
        if inserted is None:
            return                                  # already handled; no-op
        await handle(conn, msg)                     # same txn as the dedupe row
```

An orchestrated saga with real compensations:

```python
@dataclass
class Step:
    name: str
    do: Callable
    undo: Callable | None      # None = irreversible; order steps accordingly

SAGA = [
    Step("reserve_inventory", inventory.reserve,  inventory.release),
    Step("charge_payment",    payments.charge,    payments.refund),
    Step("create_shipment",   shipping.create,    shipping.cancel),
    Step("notify",            email.send_confirm, email.send_cancellation),
]

async def run_saga(pool, saga_id: str, ctx: dict) -> None:
    """Every transition is persisted BEFORE the call, so a crashed
    orchestrator resumes from the durable state rather than replaying."""
    done: list[Step] = []
    for step in SAGA:
        try:
            await record(pool, saga_id, step.name, "started")
            # Idempotency key = (saga_id, step) so a retry cannot double-charge.
            ctx |= await step.do(ctx, idempotency_key=f"{saga_id}:{step.name}")
            await record(pool, saga_id, step.name, "done")
            done.append(step)
        except Exception as e:
            await record(pool, saga_id, step.name, "failed", error=str(e))
            for finished in reversed(done):          # compensate in reverse
                if finished.undo is None:
                    log.error("irreversible step needs manual review",
                              saga=saga_id, step=finished.name)
                    continue
                # Compensations must be retried until they succeed. A failed
                # compensation is a data-integrity incident, not a log line.
                await retry_forever(finished.undo, ctx,
                                    idempotency_key=f"{saga_id}:undo:{finished.name}")
            raise
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Outbox for "database write + publish an event" | Almost never avoid it — this is the default | An outbox table, a relay, and idempotent consumers |
| Choreographed saga for ≤3 steps between decoupled services | Avoid past 3 steps | The flow is described nowhere; debugging spans every service's logs |
| Orchestrated saga (Temporal/Step Functions) for 4+ steps or money | Avoid for a two-step flow | An orchestrator to run, and durable workflow state |
| 2PC when all participants are one vendor's engine and the flow is short | Avoid across services or across a WAN | Blocking on coordinator failure; locks held through the prepare window |

### Follow-ups they will ask

**Q: Does the outbox give exactly-once delivery?**
A: No — it gives at-least-once delivery that is *atomic with the database
write*, which is the part that is otherwise impossible. The relay can publish
and then crash before marking the row published, so duplicates are guaranteed
eventually. Exactly-once is achieved at the consumer, by deduplicating on a
message ID in the same transaction as the effect. See
[Module 09 — Idempotency](./09_Reliability_Patterns.md#94-idempotency).

**Q: Why not just publish to Kafka and write the database row after?**
A: Because that is a distributed transaction with no coordinator. Publish then
write: the process dies in between and you have an event for an order that does
not exist. Write then publish: the process dies and the order exists with no
event, silently, forever. The outbox exists precisely to remove that window by
making both parts of one local commit.

**Q: What does a compensating transaction look like when the action is
irreversible?**
A: You reorder the saga so irreversible steps come last, after everything that
can fail has already succeeded. If that is impossible — you must send the email
before you know the shipment succeeded — the compensation is a semantic one: a
cancellation email, a refund, a credit note. And you accept that the
intermediate state was visible to the user, which is a product decision, not a
technical one, and worth surfacing explicitly in a design interview.

**Q: When would you actually use 2PC?**
A: Inside one vendor's cluster where the coordinator is highly available and the
prepare window is short — Kafka's transactional producer coordinating a
read-process-write cycle across partitions is a legitimate example. Across
independent services over a network, essentially never: the coordinator becomes
a single point of failure whose crash leaves locks held, and in Postgres a
forgotten prepared transaction also blocks vacuum cluster-wide.

**Q: How do you monitor a saga in production?**
A: Persist every state transition, then alert on sagas stuck in a non-terminal
state past a deadline, on compensation rates by step, and on any saga that
failed a compensation — that last one is a data-integrity incident and belongs
in a queue a human works, not in a log. This is why Temporal and Step Functions
exist: durable, queryable workflow state is most of the value. The failure and
retry machinery around each step is covered in
[Module 09 — Saga pattern](./09_Reliability_Patterns.md#914-saga-pattern-and-compensating-transactions).

### Red flags — do not say this

- ❌ "We'll use a distributed transaction across the two services." → ✅ "There
  is no cross-service transaction. I'd use a saga with compensations, driven by
  an outbox so the first write and its event are atomic."
- ❌ "The saga rolls back on failure." → ✅ "It compensates. The charge happened
  and the refund is a second visible event; the intermediate state was real."
- ❌ "Our consumer is exactly-once because we use Kafka." → ✅ "Delivery is
  at-least-once. Exactly-once *effects* come from deduplicating at the consumer
  in the same transaction as the effect."

---

## 6.14 Multi-region data

> **One-liner:** Going multi-region means accepting a latency floor set by physics
> and a conflict problem set by the fact that two regions can write the same row
> at the same time.

### Say this in the interview

> Multi-region is two decisions. First, active-passive or active-active.
> Active-passive means one region takes all writes and the other is a warm
> standby you fail over to, which keeps a single write path and one consistent
> history — the cost is that failover is a real event with a real RPO, and users
> far from the primary pay the round trip on every write. Active-active means
> both regions accept writes, which gives local write latency and survives a
> region loss, and the price is conflicts: two regions can update the same row
> concurrently and something has to decide who wins. Last-write-wins by
> timestamp is simple and silently loses data when clocks disagree. Vector
> clocks detect concurrency correctly but hand the conflict back to the
> application. CRDTs make conflicts mathematically impossible to lose by
> restricting the data types to ones that merge commutatively — counters, sets,
> registers, sequences — which works beautifully for collaborative editing and
> not at all for "is there inventory left". The second decision is set by physics:
> light in fibre travels at about two-thirds of c, so New York to London, five
> and a half thousand kilometres, has a theoretical round-trip floor near
> fifty-six milliseconds, and the measured AWS number between us-east-1 and
> eu-west-1 is about sixty-eight. That is not an engineering problem, it is a
> budget. So any design where a user request makes a synchronous cross-Atlantic
> call has already spent seventy milliseconds, and if it makes three of them it
> has spent two hundred. That is the number I design around, along with data
> residency, which for GDPR often means the data cannot leave the region at all —
> which turns the problem from replication into partitioning by geography.

### Mental model

```
THE PHYSICS FLOOR

  light in vacuum      299,792 km/s
  light in fibre     ~ 200,000 km/s   (~2/3 c, refractive index ~1.47)

  New York <-> London, great circle:      ~5,585 km
     one way  = 5585 / 200000 = 27.9 ms
     RTT      = 55.9 ms          <-- THEORETICAL FLOOR
     measured AWS us-east-1 <-> eu-west-1: ~68 ms
     (the gap is cable routing, not going in a straight line, plus
      switching and queuing hops)

  MEASURED AWS INTER-REGION MEDIAN RTT (2026 dataset, p50)
     us-east-1  <-> eu-west-1        68 ms
     us-east-1  <-> us-west-2        61 ms
     us-east-1  <-> ap-northeast-1  149 ms
     us-east-1  <-> ap-south-1      196 ms
     eu-west-1  <-> ap-south-1      120 ms
     eu-west-1  <-> ap-northeast-1  203 ms
     within a region                 0.1 - 0.7 ms

  => a synchronous write from Mumbai to a us-east-1 primary costs
     ~196 ms before the database does ANY work. Three round trips of
     application chatter and you are at 600 ms.


ACTIVE-PASSIVE                      ACTIVE-ACTIVE

  us-east (PRIMARY)                   us-east (LEADER) <==> eu-west (LEADER)
     | async replication                  |                     |
     v                                 local writes         local writes
  eu-west (standby, reads)             ~2 ms                 ~2 ms

  + one write history, no conflicts   + write latency is LOCAL everywhere
  + simple to reason about            + survives losing an entire region
  - EU writes pay 68 ms               - CONFLICTS are now your problem
  - failover has RPO > 0              - "which region has the truth?" has
  - the standby is idle capacity        no single answer


CONFLICT RESOLUTION, cheapest to most correct

  LWW (last write wins)
    keep the write with the highest timestamp.
    SIMPLE. Silently loses the other write. Clock skew decides your
    data. Fine for: presence, cache entries, "last seen".
    Never for: anything a user typed.

  VECTOR CLOCKS / VERSION VECTORS
    each replica keeps a counter; comparing vectors tells you whether
    A happened-before B or they are CONCURRENT.
    Correctly DETECTS conflicts -- then hands them to you. The app (or
    the user) must merge. Riak's siblings; Dynamo's original design.

  CRDTs (conflict-free replicated data types)
    restrict the type so merge is commutative, associative, idempotent
    -- so any order of application converges.
      G-Counter    grow-only counter (merge = per-replica max, then sum)
      PN-Counter   increments + decrements as two G-Counters
      LWW-Register single value + timestamp
      OR-Set       add/remove with unique tags: add wins over concurrent
                   remove, so an element cannot be lost
      RGA / text   ordered sequences -- the basis of collaborative editors
    Automerge and Yjs are the well-known libraries; Redis Enterprise
    Active-Active implements CRDT-backed types across regions.
    COST: metadata grows with the number of writers, and you can only
    express invariants the type supports. "Stock must not go below zero"
    is not a CRDT.
```

**Data residency changes the shape of the problem.** GDPR and similar regimes
(India's payment-data localisation, China's PIPL) can require that certain
personal data is *stored and processed* in a specific jurisdiction. That is not
a replication requirement, it is a **partitioning** requirement: the EU tenant's
rows must live only in the EU region, which means your shard key needs a region
dimension and your routing layer must enforce it. Practical consequences:

- Shard by `(region, tenant_id)`, with region chosen at tenant creation and
  effectively immutable — moving a tenant across regions is a migration.
- Keep a small, globally replicated **directory** of `tenant_id → region` so any
  entry point can route. That directory contains no personal data.
- Global aggregates must be computed from region-local aggregates, not from raw
  rows crossing borders.
- Backups, logs, and your observability pipeline are data too. This is where
  residency programmes usually fail an audit.

### Enterprise production example

**Shopify** pairs each pod with two data centres — one active, one recovery —
so failover is scoped to a pod rather than the platform, and a region event
moves a subset of shops rather than all of them. That is active-passive done at
pod granularity, and it is a good pattern to cite because it shows the choice is
not global: you can be active-passive per shard and active in many regions
overall.

**Uber Schemaless** distributes each shard's two minions **across multiple data
centres**, specifically to survive a catastrophic datacentre outage. Note what
that is not: it is not active-active. The master for a shard is in one place;
the copies are elsewhere for durability. Multi-datacentre replication for
durability and multi-region active-active for write locality are different
designs, and conflating them is a common interview error.

**Stripe's DocDB** is the reminder that the highest-reliability financial systems
usually keep a single write path per shard. They run 2,000+ shards at 99.9995%
reliability, and the elaborate machinery — proxy routing, versioned topology,
fencing, millisecond traffic switches — exists to move a shard's *single*
primary safely, not to let two primaries take writes at once.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Active-passive for anything with a strict invariant | Avoid when users far from the primary need fast writes | 68–200 ms write latency for remote users; a failover with RPO > 0 |
| Active-active when write locality or region survival is a hard requirement | Avoid when the data has invariants a CRDT cannot express | Conflict resolution, and a much harder mental model |
| CRDTs for collaborative documents, counters, sets, presence | Avoid for inventory, balances, seat booking | Metadata growth per writer; only expressible invariants |
| Region-partitioned data for residency | Avoid globally replicating anything personal | Cross-region queries become aggregations of local results |

### Follow-ups they will ask

**Q: Why can't you just replicate synchronously across regions?**
A: You can, and Spanner does, but every commit then pays the cross-region round
trip — 68 ms to Europe, 196 ms to Mumbai — plus the consensus protocol's own
overhead. For a checkout flow doing five sequential writes that is half a second
of pure network. It is a real option when correctness dominates and you can
batch, and it is the wrong default for an interactive product.

**Q: What actually breaks with last-write-wins?**
A: Silent data loss driven by clock skew. Two regions write the same row within
the clock-skew window; the one with the larger timestamp wins regardless of
which actually happened later, and the loser is discarded with no error, no log,
and no way to recover it. It is acceptable when the value is naturally
overwritten anyway — a presence heartbeat, a cache entry — and unacceptable for
anything a human typed.

**Q: Can you do active-active for an e-commerce inventory system?**
A: Not for the inventory count itself, because "stock must not go below zero" is
a global invariant and there is no CRDT for it. What you can do is partition the
invariant: allocate a slice of stock to each region as its own local counter, so
each region decrements locally and can only oversell its own slice, with
rebalancing between regions out of band. That converts a global invariant into
local ones, which is the general technique — and it is exactly what escrow or
reservation patterns do.

**Q: How do you route a user to the right region?**
A: Anycast or latency-based DNS gets them to the nearest edge, but the
authoritative routing is by data location, not by proximity: look up the
tenant's home region in a globally replicated directory and route there. A user
travelling from Berlin to Singapore must still reach the EU region if that is
where their data lives — otherwise you have violated residency to save 150 ms.

**Q: What is the realistic RPO and RTO for active-passive across regions?**
A: RPO equals your cross-region replication lag at the moment of failure, which
with asynchronous replication over a 68 ms link is typically sub-second in
steady state and seconds-to-minutes during a write burst — so you should graph
it and state it as an SLO, not assume it. RTO is dominated by detection plus the
decision, and because cross-region failover should be human-gated (that is
GitHub's post-2018 policy), realistic RTO is minutes, not seconds.

### Red flags — do not say this

- ❌ "We'll go multi-region for high availability." → ✅ "Multi-region buys
  survival of a region loss and local latency. It costs conflict resolution or
  a 68 ms write path, and I'd say which one we are choosing."
- ❌ "Active-active means writes scale." → ✅ "Active-active makes writes local.
  Each region still applies every write."
- ❌ "We'll resolve conflicts with timestamps." → ✅ "Last-write-wins loses data
  under clock skew. For anything a user typed I need a CRDT or an
  application-level merge."
- ❌ "GDPR just means we encrypt the data." → ✅ "Residency can require the data
  never leaves the region, which makes it a partitioning problem — including
  backups and logs."

---

## Module 06 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Name the three reasons to distribute data and say which mechanism solves
   each. Which one does replication actively make worse?
2. A user saves their profile and the next page shows the old value. Give four
   different fixes and say which you would ship first and why.
3. Why does a replica still lag when the network is healthy? Give two
   mechanisms.
4. Explain split brain and the three defences against it. Which one does quorum
   *not* provide?
5. State CAP correctly in two sentences, then state PACELC and say which half
   affects your latency graphs.
6. `hash(key) % N` and you go from 10 to 11 shards. How much data moves, and
   what is the standard fix?
7. Why did Notion pick 480 logical shards rather than 512?
8. Walk through choosing a shard key for a chat product. Why `channel_id` and
   not `user_id`, and what does that cost you?
9. You fan out a query to 32 shards, each with p99 = 40 ms and p50 = 2 ms. What
   is the fan-out's approximate p50, and why?
10. `W + R > N` is satisfied. Name three concrete reasons the read is still not
    linearizable.
11. Describe the transactional outbox and say exactly what it guarantees and
    what it does not.
12. Why is a saga's compensation not a rollback? Give an example where the
    difference is visible to a user.
13. What is the theoretical minimum round trip between New York and London, and
    what is the measured AWS number?
14. Walk through the five phases of a zero-downtime reshard, and say what the
    one-second write freeze is for.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| `hash(key) % N`, N → N+1 | relocates N/(N+1) of keys (10 → 11 = ~91%) |
| Consistent hashing, adding a node | relocates ~1/N of keys |
| Virtual nodes per physical node (typical) | 128–256 |
| Uber Schemaless logical shards | 4,096 fixed; 1 MySQL master + 2 cross-DC minions per shard |
| Notion logical shards | 480 (chosen for divisibility) on 32 → 96 physical DBs |
| Notion backfill | 3 days on 96 CPUs; 5-minute switchover |
| Notion hot-shard CPU before/after re-shard | ~90% → ~20% |
| Figma first sharded table | Sept 2023; ~10 s partial primary impact, 0 replica impact |
| Figma sharding effort | ~9 months for the first table |
| Stripe DocDB | 5M+ QPS, 2,000+ shards, 99.9995%, traffic switch in ms–2 s |
| Discord Cassandra → ScyllaDB | 177 → 72 nodes; p99 read 40–125 ms → 15 ms |
| GitHub 2018 | 43-second partition → 24 h 11 min degraded service |
| Cassandra default production CL (multi-DC) | `LOCAL_QUORUM` |
| Cassandra lightweight transaction cost | ~4 round trips (Paxos per partition) |
| Speed of light in fibre | ~200,000 km/s (~2/3 c) |
| NY ↔ London theoretical RTT floor | ~56 ms (5,585 km) |
| AWS us-east-1 ↔ eu-west-1 median RTT | ~68 ms |
| AWS us-east-1 ↔ ap-south-1 median RTT | ~196 ms |
| AWS intra-region RTT | 0.1–0.7 ms |
| Fan-out to 32 shards at 1% slow | ~28% of requests hit at least one slow shard |
| Patroni default leader lease (`ttl`) | 30 s (`loop_wait` 10 s) |
| Managed Postgres/MySQL HA failover | typically ~60–120 s end to end |

---

**Next:** [Module 07 — Caching, CDN & Object Storage](./07_Caching_And_CDN.md)