# Module 07 — Caching, CDN & Object Storage

> **What this module makes you able to do:** Add a cache to any design and defend it —
> pick the layer, the pattern, the invalidation strategy and the eviction policy, then
> explain out loud how it fails under a stampede, a hot key or a dual-write race, and
> what you would do about each. Also: stop your API server from ever proxying a 500 MB file.
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** Module 04 — Databases, Module 06 — Replication, Partitioning & Sharding

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 7.1 | Why cache — the latency and cost math | ★★★★★ |
| 7.2 | The cache hierarchy | ★★★★☆ |
| 7.3 | Caching patterns and the cache-aside race | ★★★★★ |
| 7.4 | Invalidation | ★★★★★ |
| 7.5 | Eviction policies | ★★★★☆ |
| 7.6 | Cache stampede / thundering herd | ★★★★★ |
| 7.7 | Hot keys | ★★★★☆ |
| 7.8 | Cache penetration and cache avalanche | ★★★☆☆ |
| 7.9 | Redis in production | ★★★★★ |
| 7.10 | Distributed cache consistency | ★★★★☆ |
| 7.11 | CDN | ★★★★☆ |
| 7.12 | Object / blob storage | ★★★★☆ |

---

## 7.1 Why cache — the latency and cost math

> **One-liner:** A cache buys you latency and origin capacity by trading away freshness,
> and the only number that decides whether it was worth it is the miss rate.

### Say this in the interview

> A cache is a second copy of data placed closer to the reader, and I add one when the
> same data is read many times between writes. The reason it works is a ratio, not a
> speed: a Redis GET on the same VPC is roughly half a millisecond, an indexed
> PostgreSQL query that touches disk is 5 to 50, so the cache is one to two orders of
> magnitude cheaper per read. But the number I actually care about is the miss rate,
> not the hit rate, because the miss rate is what sizes my database. At ten thousand
> reads per second, a 90 percent hit ratio sends a thousand queries per second to
> Postgres and a 99 percent hit ratio sends a hundred — the same workload, a ten times
> smaller database. That is why I treat "we went from 90 to 99 percent" as a capacity
> decision rather than a performance tweak. The cost is that I now have two sources of
> truth and every write has to decide what to do about the stale one, so I would not
> cache at all if reads aren't reused, if writes are as frequent as reads, or if the
> read has to be linearizable. I'd start by measuring reads-per-key-per-TTL, because
> that number caps the hit ratio before I write any code.

### Mental model

Caching is an economic argument with three inputs: how much faster the copy is, how
often you get to use it, and how wrong it is allowed to be.

**The miss-rate lever.** Origin load is `RPS × miss_rate`. Because you multiply by the
miss rate and not the hit rate, improvements at the top end are enormous and
non-linear:

```
 Reads/s   Hit ratio   Miss rate   Queries/s to origin
 -------   ---------   ---------   -------------------
 10,000        0%        100%          10,000
 10,000       50%         50%           5,000     2x  relief
 10,000       90%         10%           1,000    10x  relief
 10,000       99%          1%             100   100x  relief
 10,000     99.9%        0.1%              10  1000x  relief
```

Every "9" you add to the hit ratio divides origin load by ten. The jump from 90 to 99
percent is worth exactly as much as the jump from 0 to 90 percent — this is the single
most useful caching sentence you can say in an interview.

**Effective latency.** Weighted average, not best case:

```
 latency = p_hit x cache_latency + p_miss x origin_latency

 90% hit:  0.90 x 0.5 ms + 0.10 x 30 ms = 3.45 ms
 99% hit:  0.99 x 0.5 ms + 0.01 x 30 ms = 0.80 ms   (4.3x better)
```

Note what this says about p99 latency: at a 90 percent hit ratio, roughly one request in
ten is a full origin round trip, so your p90 *is* your origin latency. A cache improves
the average long before it improves the tail.

**The reuse ceiling — why some things must not be cached.** If a key is read on average
`N` times within one TTL window, the first read is always a miss, so:

```
 max hit ratio = (N - 1) / N

 N =   2  ->  50%    caching is barely worth the hop
 N =  10  ->  90%
 N = 100  ->  99%
```

This is the calculation that tells you when caching is the *wrong* answer:

- **Low reuse.** Unique search queries, per-request LLM prompts with a user's own text,
  one-time signed links. `N ≈ 1`, so the hit ratio is ~0 and you have added a network
  hop, a serialization cost and memory spend for nothing.
- **Write-heavy.** Every write invalidates. If writes and reads arrive at the same rate,
  the effective `N` between invalidations is ~1 regardless of TTL. A live "seats
  remaining" counter behaves this way.
- **Strong consistency required.** Account balance before a transfer, inventory at the
  moment of decrement, an authorization decision after a permission was revoked. Here
  the correct answer is "read the primary, and if that is too slow, fix the primary."
- **Large values with small hit ratios.** A 2 MB JSON blob read twice an hour is
  consuming Redis memory that a million small hot keys would use better.

### Enterprise production example

**Netflix** runs EVCache ("Ephemeral Volatile Cache"), a memcached-based tier-0 service.
As presented at AWS re:Invent 2023 and written up by InfoQ, it spans roughly 200
memcached clusters over 22,000 server instances across four AWS regions, holds about
2 trillion items totalling 14.3 PB, and serves around 400 million operations per second
at a p90 under 2 ms. The design point worth stealing is in the name: *ephemeral* and
*volatile*. Netflix explicitly documents that EVCache "typically operates in contexts
where consistency is not a strong requirement." They did not build a globally consistent
cache; they built a fast one and pushed every use case that needs correctness somewhere
else. That is the trade-off named honestly, and it is why the thing can be that big.

### Code

```python
# The measurement that decides whether to cache at all, before writing cache code.
# Run it against a day of production access logs, per key pattern.
from collections import Counter

def reuse_profile(key_stream, ttl_seconds, now_stream):
    """reads-per-key-per-TTL-window -> the hit-ratio ceiling you can actually buy."""
    windows = Counter()
    for key, ts in zip(key_stream, now_stream):
        windows[(key, int(ts // ttl_seconds))] += 1

    reads = sum(windows.values())
    distinct = len(windows)              # one unavoidable miss per (key, window)
    ceiling = (reads - distinct) / reads if reads else 0.0
    return {
        "reads": reads,
        "avg_reads_per_key_per_ttl": reads / distinct if distinct else 0.0,
        "hit_ratio_ceiling": ceiling,
        # Below ~0.5 the extra hop and the invalidation bugs are not worth it.
        "verdict": "cache it" if ceiling > 0.5 else "do not cache; fix the query",
    }
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Read:write ratio above ~10:1 and the same keys recur | Every read is a unique key (search tails, per-user prompts) | A second source of truth, and an invalidation strategy you must own |
| Origin is the bottleneck and is expensive to scale (Postgres primary, an LLM API, a paid third-party API) | The origin is already cheap and idle | Memory spend plus a new failure mode: what happens when the cache is down or cold |
| Bounded staleness is acceptable and you can say the bound out loud | The read must be linearizable (balances, inventory decrement, authz after revocation) | Stale reads, and reasoning about a race you did not have before |
| The computation is expensive, not just the fetch (aggregations, embeddings, rendered HTML) | Values are large and rarely reused | Cold-start behaviour: a cache flush becomes an origin outage |

### Follow-ups they will ask

**Q: Your cache is at a 99 percent hit ratio and you restart the Redis cluster. What happens?**
A: Origin load jumps 100x instantly — from 100 queries per second to 10,000 in my
example — and the database almost certainly falls over, which then prevents the cache
from refilling. This is why I never treat a cache as purely optional: at high hit ratios
it is load-bearing infrastructure. Mitigations are warming the new cluster before
shifting traffic, a concurrency limiter or semaphore in front of the origin so misses
queue instead of stampeding, and shedding low-priority traffic during the refill.

**Q: Where do you put the cache if the expensive part is an LLM call, not a database query?**
A: Two layers with different keys. An exact-match cache keyed by a hash of the fully
rendered prompt plus model, plus temperature, plus the knowledge-base version, which is
safe and cheap. Then optionally a semantic cache on the embedding of the user question
with a similarity threshold, which is much riskier because near-duplicate questions can
have different correct answers. Both must include the tenant and the permission scope in
the key or you have built a data-leak machine.

**Q: How do you decide the TTL?**
A: TTL is the staleness budget the business will tolerate, converted to seconds — I ask
the product owner "how out of date can this be before someone files a bug?" and use
that. Then I sanity-check it against reuse: the TTL has to be long enough that a key is
read several times within it, or the hit ratio ceiling collapses. If the answers conflict
— must be fresh *and* is rarely reused — that is the signal not to cache.

**Q: Is a 95 percent hit ratio good?**
A: Unanswerable without the absolute miss volume and the segmentation. Five percent of
a million requests per second is 50,000 origin queries per second, which is a lot; five
percent of a thousand is fifty, which is nothing. And a 95 percent global ratio can hide
a 40 percent ratio on one endpoint that is quietly the thing paging you. I alert on
origin queries per second and per-route hit ratio, not on the global number.

### Red flags — do not say this

- ❌ "I'll add Redis to make it fast." → ✅ "Reads outnumber writes about 50 to 1 on this
  endpoint and the same keys recur, so a cache should hold a 95-plus percent hit ratio
  and cut Postgres load about 20x. Staleness budget is 60 seconds."
- ❌ "Cache everything." → ✅ "I'd cache the product catalogue, which is read constantly
  and changes hourly. I would not cache the inventory count, because it changes on every
  purchase and a stale value oversells."
- ❌ "The hit ratio is 90 percent, so we're fine." → ✅ "90 percent means one in ten reads
  still hits Postgres, so my p90 latency is basically the database's latency and the
  database is sized for 10 percent of peak. Getting to 99 percent divides that by ten."
- ❌ "Caching makes the system more reliable." → ✅ "Caching makes the system faster and
  the origin smaller, which makes the *cache* load-bearing. I need a plan for cache
  down and cache cold, or I've added a dependency, not a safety net."

---

## 7.2 The cache hierarchy

> **One-liner:** There are six places to cache a value, they get slower and more shared
> as you go down, and the whole skill is putting each piece of data at the right level.

### Say this in the interview

> I think of caching as a hierarchy rather than a component, because the same request
> passes through up to six caches. The browser cache is free and closest but I cannot
> invalidate it, so I only put immutable, content-hashed assets there. The CDN edge
> serves anonymous users globally and I can purge it, so static assets and public
> read-mostly API responses go there. A reverse proxy in front of my app handles
> micro-caching and request coalescing. Inside the process I keep a small L1 LRU for
> things read on nearly every request — feature flags, tenant config, JWKS keys — which
> is a hundred nanosecond lookup with no network at all. Below that is Redis as a shared
> L2 that survives deploys and is consistent across instances. And at the bottom the
> database's own buffer pool is a cache I get for free, which is why I check whether the
> working set already fits in shared_buffers before I add anything. The rule I use is
> that the further out I push a value, the cheaper the read and the weaker my control
> over invalidation, so immutability earns you distance.

### Mental model

```
        REQUEST PATH                LATENCY      WHO SHARES IT
  ┌───────────────────────┐
  │ 1. Browser / app cache│      ~0 (local)   one user, one device
  └───────────┬───────────┘                   cannot be invalidated
              │ miss
  ┌───────────▼───────────┐
  │ 2. CDN edge PoP       │      5-30 ms      everyone near that PoP
  └───────────┬───────────┘                   purgeable, seconds to global
              │ miss
  ┌───────────▼───────────┐
  │ 3. Reverse proxy      │      1-5 ms       everyone behind that proxy
  │    (nginx / Envoy)    │                   micro-cache + coalescing
  └───────────┬───────────┘
              │ miss
  ┌───────────▼───────────┐
  │ 4. L1 in-process LRU  │      50-500 ns    one process only
  └───────────┬───────────┘                   invalidation is the hard part
              │ miss
  ┌───────────▼───────────┐
  │ 5. L2 Redis / memcache│      0.3-1 ms     whole fleet, survives deploys
  └───────────┬───────────┘                   explicit DEL works
              │ miss
  ┌───────────▼───────────┐
  │ 6. DB buffer pool     │      0.1-1 ms     whole DB, free, automatic
  │    then disk          │      5-50 ms
  └───────────────────────┘
```

**What belongs where:**

| Layer | Put here | Never put here |
|---|---|---|
| Browser | Content-hashed JS/CSS/images with `max-age=31536000, immutable` | Anything you might need to change at a fixed URL |
| CDN | Static assets, public product pages, public API GETs, signed media | Per-user responses without a `Vary`-safe cache key |
| Reverse proxy | 1-5 second micro-cache on hot public endpoints, coalescing | Authenticated responses, unless keyed by identity |
| L1 in-process | Config, feature flags, tenant metadata, JWKS, compiled prompts, tiny hot values with short TTLs | Anything large (it is per-process, so N instances = N copies), anything requiring prompt invalidation |
| L2 Redis | Session data, user profiles, rendered fragments, rate-limit counters, query results, embeddings | Values so big they cause head-of-line blocking on a single-threaded server |
| DB buffer pool | Nothing — you tune it, you don't populate it | — |

**The L1 invalidation problem, stated precisely.** With 40 app pods each holding an L1
copy, a `DEL` in Redis does nothing to those 40 copies. Your options are: very short
L1 TTLs (5-30 seconds) and accept bounded divergence; a pub/sub invalidation channel
that all pods subscribe to (best-effort — a pod that missed the message stays stale);
or Redis client-side caching with tracking (`CLIENT TRACKING`, RESP3), where the server
remembers which clients read which keys and pushes invalidation messages. The pragmatic
default at your scale is short TTL plus pub/sub, and being honest that L1 is
eventually consistent with a bound equal to the L1 TTL.

### Enterprise production example

**Facebook's** memcached deployment (Nishtala et al., NSDI 2013) is explicitly a
hierarchy of pools rather than one flat cache. Within a cluster they run segregated
pools tuned to access pattern — a small "wildcard" pool for the default workload, a
pool for keys that are cheap to fetch but accessed frequently, and a separate pool for
keys that are expensive to fetch and rarely accessed — because mixing a low-churn,
expensive-to-recompute working set with a high-churn cheap one lets the cheap one evict
the expensive one. The lesson is that "add more memory" is often the wrong fix and
"stop letting these two workloads share an eviction policy" is the right one.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Push toward L1/browser for immutable or config-shaped data | Data must be invalidated promptly and correctly | Invalidation control decreases the further out you go |
| Push toward L2 Redis for per-user, per-tenant, invalidatable data | The value is read once (no reuse to amortise the hop) | A network hop and a shared component that can fail |
| Add a reverse-proxy micro-cache when one endpoint is hot and public | Responses are personalised | Up to `micro_ttl` of staleness for everyone |
| Rely on the DB buffer pool when the working set is small | Working set exceeds RAM | Nothing — but check this first, it's free |

### Follow-ups they will ask

**Q: Why bother with L1 if you already have Redis?**
A: Two reasons. Latency: an L1 hit is around 100 nanoseconds versus 300-1000 microseconds
for Redis, so for a value touched five times per request it removes five network round
trips. And hot-key protection: if one key takes 200,000 reads per second, that traffic
lands on a single Redis shard because a single key cannot be split across shards. An L1
with even a 5-second TTL collapses that to one Redis read per pod per 5 seconds.

**Q: How do you keep 40 pods' L1 caches from diverging?**
A: I don't fully — I bound the divergence. Short TTL (5-30 seconds) as the guaranteed
convergence bound, plus a Redis pub/sub invalidation channel for the common case so it
usually converges in milliseconds. Pub/sub is fire-and-forget, so a pod that was
reconnecting misses the message; the TTL is what makes that survivable. I only put data
in L1 when a 30-second stale window is genuinely acceptable.

**Q: Would you cache in the API gateway?**
A: For public unauthenticated GETs, yes, and it is very effective because it also
protects against a stampede in one place. For authenticated traffic I generally don't,
because the cache key has to include identity and the hit ratio per key collapses, and
getting the `Vary` handling wrong at a shared layer means serving one user's data to
another. That risk is not worth the milliseconds.

### Red flags — do not say this

- ❌ "Cache is Redis." → ✅ "There are six cache layers in this request path; Redis is
  the shared L2. The CDN and the in-process L1 do different jobs."
- ❌ "I'll put user sessions in an in-process cache." → ✅ "Sessions go in Redis so any
  instance can serve any request. Only config-shaped data goes in-process."
- ❌ "L1 and L2 both have the data so they're consistent." → ✅ "L1 is eventually
  consistent with L2, bounded by the L1 TTL. I choose that TTL as the staleness budget."

---

## 7.3 Caching patterns and the cache-aside race

> **One-liner:** Five patterns, but you will use cache-aside 90 percent of the time —
> and cache-aside has a race that can pin a stale value in the cache until its TTL,
> which is the detail interviewers use to separate people who have read about caching
> from people who have debugged it.

### Say this in the interview

> I default to cache-aside: the application reads the cache, and on a miss reads the
> database, writes the result back with a TTL, and returns it. I like it because the
> cache is never on the write path, so if Redis is down the system degrades to slow
> instead of broken, and because I only cache what someone actually asked for. The catch
> is a race that most people miss. A reader misses the cache and starts reading the
> database. Before it writes back, a writer updates the row and deletes the cache key —
> which is a no-op because nothing is cached yet. Then the reader writes the value it
> read *before* the update, and now the cache holds a stale value for the entire TTL,
> not for a few milliseconds. The fix that scales is what Facebook's memcached paper
> calls a lease: on a miss the cache hands the reader a token, an invalidation revokes
> outstanding tokens, and the write-back is rejected if the token is stale. On Redis I
> implement that as a short-lived lease key checked inside a Lua script so the check
> and the set are atomic. Write-through and write-behind move the cache onto the write
> path, which buys freshness at the cost of availability and, for write-behind,
> durability — so I only reach for those when the read-after-write requirement is hard.

### Mental model

**Cache-aside (lazy loading)** — the default.

```
 READ                                  WRITE
 ────                                  ─────
 app ──GET──> cache                    app ──UPDATE──> db  (commit)
   hit: return                           then ──DEL───> cache
   miss:                               (delete, do not update — see 7.4)
     app ──SELECT──> db
     app ──SET (ttl)──> cache
     return
```

Consistency: eventually consistent, bounded by TTL plus the race window below.
Failure mode: cache down means every read goes to the database. Guard with a timeout
(50-100 ms) on the cache call and a concurrency limiter on the origin.

**Read-through** — same shape, but the cache library or a sidecar owns the load, so the
application just calls `cache.get(key)` and a loader function runs on miss. Identical
consistency to cache-aside; the advantage is that the loader is defined once, so
single-flight and TTL jitter are enforced everywhere instead of being reimplemented
per call site. This is what the code in 7.6 builds.

**Write-through** — write cache and database synchronously.

```
 app ──SET──> cache ──WRITE──> db ──ack──> cache ──ack──> app
```

Consistency: read-after-write within the cache. Cost: every write pays both latencies,
and if the cache write succeeds and the DB write fails you must roll back or you have
committed a lie. The cache is now on the write path, so cache down means writes down.

**Write-behind (write-back)** — write cache, acknowledge, flush to the database
asynchronously.

```
 app ──SET──> cache ──ack──> app
                 │
                 └── batched flush ──> db      (seconds later)
```

Consistency: fast, and the cache is the source of truth for a window. Cost: **you can
lose acknowledged writes** if the cache dies before flushing. Legitimate for view
counters, "last seen" timestamps and metrics where losing 5 seconds of increments is
fine; disqualifying for anything a user would notice missing.

**Refresh-ahead** — proactively reload a key before its TTL expires, either on a
schedule or triggered by a read close to expiry.

```
 t=0                                        t=TTL
  |──────────────── serve from cache ─────────|
                        ^
                  read at 0.8xTTL triggers async reload;
                  this read is served from the old value
```

Consistency: hides refresh latency entirely from users. Cost: you refresh keys nobody
will ask for again, which wastes origin capacity, and it only helps keys with a steady
request stream. This is the same idea as `stale-while-revalidate` at the CDN and as
XFetch in 7.6.

**The cache-aside race, in full.** This is the part to be able to draw:

```
 time   Reader R                      Writer W                Cache      DB
 ────   ────────                      ────────                ─────      ──
  t1    GET user:42 -> MISS                                    -         A
  t2                                  UPDATE ... SET name=B    -         B
  t3                                  DEL user:42  (no-op!)    -         B
  t4    SELECT -> reads A                                      -         B
        (snapshot taken before t2, or from a lagging replica)
  t5    SET user:42 = A, TTL 3600                              A         B
        ────────────────────────────────────────────────────────────────
        Cache now serves A for one hour. The DELETE at t3 was
        correct and still lost, because it deleted nothing.
```

Note that reordering the writer — delete first, then update — does not fix it; it just
moves the window. Widening it: a read replica with 200 ms of lag makes t4 return stale
data far more often than the millisecond-scale window suggests.

Fixes, weakest to strongest:

1. **TTL as a backstop.** Not a fix; it bounds the damage to one TTL. Always have it.
2. **Delayed double delete.** The writer deletes the key, commits, then deletes again
   after ~500 ms. Cheap, widely used, and probabilistic — it closes the common window
   and not the tail. Fine for a profile name; not for anything that matters.
3. **Leases (the real fix).** The cache hands out a token on miss; an invalidation
   revokes it; a write-back with a revoked token is rejected. Facebook's mechanism,
   and implementable on Redis with a lease key plus Lua.
4. **Versioned CAS.** Store `(value, db_version)` and only accept a write-back whose
   version is newer than what is cached. Requires a monotonic version on the row —
   `xmin`, an `updated_at` with enough resolution, or an explicit `version` column.
5. **CDC-driven invalidation.** Derive invalidations from the committed WAL (7.10), so
   the invalidation is by construction after the commit and carries a version.

### Enterprise production example

**Facebook** hit exactly this in production and documented the fix in *Scaling Memcache
at Facebook* (NSDI 2013). Their lease is a 64-bit token bound to the specific key,
handed to a client on a cache miss and required when the client sets the value back.
memcached verifies the token and rejects the set if the lease was invalidated by an
intervening delete — the paper compares it to load-link/store-conditional. The same
mechanism, with one small change, also solves the thundering herd (see 7.6): the server
returns a token only once every 10 seconds per key. Their measured result on a set of
keys prone to herding: peak database query rate fell from 17,000 per second without
leases to 1,300 per second with them. One mechanism, two bugs, a 13x reduction in peak
provisioned database load.

### Code

```lua
-- fill.lua — cache-aside write-back guarded by a lease. Fixes the t1..t5 race.
-- KEYS[1] = value key            KEYS[2] = lease key
-- ARGV[1] = value  ARGV[2] = ttl_ms  ARGV[3] = the token we were handed on miss
if redis.call('GET', KEYS[2]) ~= ARGV[3] then
  return 0            -- lease revoked by a concurrent invalidation: drop this value
end
redis.call('SET', KEYS[1], ARGV[1], 'PX', ARGV[2])
redis.call('DEL', KEYS[2])
return 1
```

```python
import secrets
from redis.asyncio import Redis

FILL = None  # registered once at startup via r.register_script(open("fill.lua").read())

async def read_through(r: Redis, key: str, loader, ttl_ms: int = 300_000):
    cached = await r.get(key)
    if cached is not None:
        return cached

    token = secrets.token_hex(8)
    lease_key = f"lease:{key}"
    # NX makes this the single-flight gate too; PX bounds a crashed holder.
    got = await r.set(lease_key, token, nx=True, px=5_000)
    value = await loader()
    if got:
        await FILL(keys=[key, lease_key], args=[value, ttl_ms, token])
    # If we did not get the lease another caller is filling; we still return a
    # correct value, we just do not write it back.
    return value

async def invalidate(r: Redis, key: str):
    """Call AFTER the DB transaction commits. Deleting the lease revokes any
    in-flight fill, which is the whole point — a no-op DEL is not enough."""
    await r.delete(key, f"lease:{key}")
```

### Trade-offs

| Pattern | Use it when | Avoid it when | What it costs you |
|---|---|---|---|
| Cache-aside | Default. Read-heavy, tolerant of TTL-bounded staleness | You need read-after-write on the cache | The stale-set race; needs leases or versioning to close |
| Read-through | You want one place to enforce TTL jitter and single-flight | You need per-call-site control of the load path | A layer of indirection; a library or sidecar to own |
| Write-through | Read-after-write matters and write volume is modest | Writes are frequent or cache availability is shaky | Every write pays both latencies; cache down = writes down |
| Write-behind | Counters, metrics, last-seen — high write rate, loss-tolerant | Any write a user would notice missing | You can lose acknowledged writes |
| Refresh-ahead | A small set of expensive, always-hot keys | Long-tail keys with sporadic reads | Wasted origin work refreshing keys nobody reads |

### Follow-ups they will ask

**Q: Walk me through the exact race in naive cache-aside.**
A: Reader misses the cache and issues its `SELECT`. Writer commits an update and deletes
the cache key — a no-op, because the key isn't there yet. Reader's `SELECT` returns the
pre-update value (its snapshot predates the commit, or it hit a lagging replica) and
writes it back with a fresh TTL. The cache now serves the old value for the full TTL and
no further invalidation is coming. The window is much wider than it looks if you read
from replicas.

**Q: Does deleting the cache before the DB write instead of after fix it?**
A: No. Then a reader can miss, read the old value from the database, and write it back
after the writer's delete but before the writer's commit — the same stale value pinned
for a TTL, arrived at from the other direction. Ordering alone cannot fix a race between
two non-atomic operations across two systems; you need a token or a version so the
losing write can be detected and dropped.

**Q: Why is write-behind dangerous even with replicated Redis?**
A: Because Redis replication is asynchronous by default. A primary can acknowledge your
write, fail before replicating, and a replica gets promoted without it — the write is
gone with a success already returned to the user. `WAIT` can block until N replicas ack,
but that removes the latency benefit that motivated write-behind. So I use write-behind
only where losing a few seconds is acceptable by design.

**Q: Redis is down. What does your read path do?**
A: With cache-aside, it falls through to Postgres, which is correct but 100x more load at
a high hit ratio. So the cache client gets a tight timeout, around 50 ms, so a hung Redis
doesn't hold connections; a circuit breaker so I stop paying the timeout on every request
once it's clearly down; and a bounded-concurrency semaphore in front of the database so
misses queue rather than opening 10,000 connections. I would rather serve 2,000 requests
per second slowly than fail all of them.

### Red flags — do not say this

- ❌ "Cache-aside: read cache, on miss read DB and populate. Done." → ✅ "...and the
  populate step needs a lease or a version check, or a concurrent write can leave a
  stale value cached for the whole TTL."
- ❌ "I'll use write-through so the cache is always correct." → ✅ "Write-through gives
  read-after-write on the cache, but it puts the cache on the write path — cache down
  means writes down — and I still have to handle a partial failure between the two writes."
- ❌ "Write-behind is just faster write-through." → ✅ "Write-behind acknowledges before
  durability. It can lose committed-looking writes, so it's for counters, not for orders."

---

## 7.4 Invalidation

> **One-liner:** Delete, don't update; give every key a namespace and a version prefix so
> you can invalidate a million keys with one write; and let a TTL be the backstop for
> every bug you didn't think of.

### Say this in the interview

> I use three invalidation mechanisms and I layer them. TTL always, on every key, because
> it is the only thing that bounds staleness when my explicit invalidation has a bug —
> and it will. Then explicit invalidation on write for anything where a minute of
> staleness is too much. And for cross-service cases, invalidation driven off the
> database's change log via CDC, because that is the only mechanism where the
> invalidation cannot happen before the commit and cannot be forgotten by a new code
> path. Two rules I follow hard. First, delete the key, never update it in place: two
> concurrent writers can apply their updates to the database in one order and to the
> cache in the other order, and then the cache disagrees with the database permanently,
> whereas a delete is idempotent and commutative so the worst case is an extra miss.
> Second, every key gets a structured name with a version prefix — something like
> `v3:profile:tenant:42:user:99` — so when I change the serialization format I bump the
> prefix and every old key becomes unreachable in one config change instead of running
> a `KEYS` scan over a production Redis. I also invalidate after the commit, not inside
> the transaction, because a rolled-back transaction that already deleted the cache just
> causes an unnecessary miss, whereas a committed transaction whose invalidation was
> rolled back leaves a lie in the cache.

### Mental model

**The four mechanisms:**

```
 ┌───────────────────┬──────────────┬───────────────┬─────────────────────┐
 │ Mechanism         │ Staleness    │ Cost          │ Fails how           │
 ├───────────────────┼──────────────┼───────────────┼─────────────────────┤
 │ TTL only          │ up to TTL    │ near zero     │ silently stale;     │
 │                   │              │               │ herd at expiry      │
 │ Explicit DEL      │ ms           │ code on every │ a new write path    │
 │ on write          │              │ write path    │ forgets to call it  │
 │ Versioned key     │ zero for the │ read must     │ old keys linger     │
 │ (v3:, or an id in │ new version  │ know the      │ until eviction      │
 │  the key)         │              │ version       │                     │
 │ CDC / event-driven│ replication  │ Debezium +    │ connector lag or    │
 │ (7.10)            │ lag, 10s ms  │ a consumer    │ death = stale fleet │
 └───────────────────┴──────────────┴───────────────┴─────────────────────┘
```

**Why delete beats update.** Two writers, W1 setting price 100 and W2 setting price 200:

```
       DB order              Cache order (UPDATE)      Cache order (DELETE)
 t1    W1 commits 100        W2 sets cache 200         W2 deletes
 t2    W2 commits 200        W1 sets cache 100         W1 deletes
       DB = 200             cache = 100  WRONG        cache = empty
                            and wrong forever          next read repairs it
```

Two systems, two independent orderings; nothing guarantees they agree. `DELETE` is
idempotent and order-independent, so its failure mode is a cache miss (cheap and
self-healing), while `UPDATE`'s failure mode is permanent divergence. The only extra cost
is one origin read per invalidation, and if that read is expensive enough to matter you
have a hot key (7.7), not an invalidation problem.

**Key naming — a convention worth stating out loud:**

```
   v3  :  profile  :  t42     :  u99   :  fields=name,avatar
   ─┬─    ───┬───     ─┬─       ─┬─      ────────┬──────────
    │        │         │         │               └ what shape of value
    │        │         │         └ entity id
    │        │         └ tenant — never omit this in multi-tenant systems
    │        └ entity type / namespace
    └ schema version — bump to mass-invalidate everything
```

Concretely: `v3:profile:t42:u99`. The version prefix is the escape hatch. When you change
what a cached profile contains, you do not hunt down old keys — you deploy `v4` and every
`v3` key becomes unreferenced and gets evicted by LRU on its own schedule. Two-tier
versioning is even better for entity-scoped mass invalidation: keep a per-tenant version
counter in Redis and include it in the key, so `INCR ver:t42` logically invalidates every
key for tenant 42 in one command.

**Order of operations on write:**

```
  BEGIN                                        ┌ correct: a rollback costs
    UPDATE users SET ... WHERE id = 99;        │ only an extra cache miss
  COMMIT;                                      │
  DEL v3:profile:t42:u99   <── after commit ───┘

  (wrong: DEL inside the transaction — if the tx rolls back you have
   invalidated for nothing; worse, a reader can refill from the
   uncommitted-then-rolled-back state on some isolation levels)
```

The remaining gap: the process can die between `COMMIT` and `DEL`, leaving a stale entry
until TTL. If that gap is unacceptable, the invalidation has to be derived from the commit
itself — either an outbox row written inside the same transaction
(see [Module 08 — Transactional Outbox](./08_Messaging_And_Events.md#811-the-dual-write-problem--transactional-outbox))
or CDC off the WAL.

### Enterprise production example

**Facebook** derives cache invalidations from the database's commit log rather than from
application code. As described in the NSDI 2013 paper, a daemon called `mcsqueal` runs on
each database, reads the SQL statements the database commits (which include the cache keys
to invalidate), batches them, and routes deletes to the memcached instances in each
cluster. The reason they gave is exactly the failure mode above: invalidations issued by
the web server that performed the write are lost when that server dies, and can race with
the commit. Deriving them from the commit log makes invalidation a property of the data
change rather than a thing a code path has to remember. Their gutter pool complements
this — roughly 1 percent of memcached servers held in reserve to absorb requests for a
failed server's keys with short TTLs, so a server failure becomes a small stale window
instead of a database overload.

### Code

```python
# Namespaced, versioned keys + tenant-scoped mass invalidation.
SCHEMA = "v3"                      # bump on serialization change -> global invalidate

async def profile_key(r, tenant_id: int, user_id: int) -> str:
    # A tenant-level counter lets one INCR invalidate every key for that tenant.
    gen = await r.get(f"gen:t{tenant_id}") or b"0"
    return f"{SCHEMA}:profile:t{tenant_id}:g{gen.decode()}:u{user_id}"

async def update_profile(db, r, tenant_id: int, user_id: int, patch: dict):
    async with db.transaction():                     # invalidate AFTER commit
        await db.execute(
            "UPDATE users SET name=:name, updated_at=now() WHERE id=:id",
            {"name": patch["name"], "id": user_id})
    key = await profile_key(r, tenant_id, user_id)
    await r.delete(key, f"lease:{key}")              # delete, never update

async def invalidate_tenant(r, tenant_id: int):
    """Logically drop every cached key for one tenant. O(1), no KEYS scan.
    Old keys are now unreachable and get evicted by allkeys-lru naturally."""
    await r.incr(f"gen:t{tenant_id}")
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| TTL only: data has no clean invalidation hook (aggregates, third-party data, ML features) | Staleness is user-visible and unacceptable | Up to one TTL of staleness, plus synchronised expiry (jitter it — 7.6) |
| Explicit DEL: single service owns all writes to that entity | Many services or batch jobs write the same table | A discipline problem — every new write path must remember |
| Versioned keys: format changes, tenant-scoped mass invalidation | You need to reclaim memory immediately | Old keys occupy memory until evicted |
| CDC-driven: writes come from many places, or from batch jobs and migrations | You can't run Debezium/connector infrastructure | Real operational surface: connector, replication slot, lag monitoring |

### Follow-ups they will ask

**Q: Why delete instead of update the cache?**
A: Because two writers can reach the database in one order and the cache in the other, and
an `UPDATE` then leaves the cache permanently disagreeing with the database. `DELETE` is
idempotent and order-independent, so the worst case is an extra miss that repairs itself.
The only argument for updating is avoiding an origin read on a very hot key, and there
the better tool is a versioned CAS write so an out-of-order update can be detected and
dropped.

**Q: You need to invalidate every cached key for one tenant after a permissions change. How?**
A: A generation counter in the key. I keep `gen:t42` in Redis, include its value in every
key for that tenant, and invalidate the whole tenant with a single `INCR`. That is O(1)
and safe. What I would not do is `KEYS v3:*:t42:*` — it's O(N) over the entire keyspace on
a single-threaded server and will stall every other client (see 7.9). If I truly had to
enumerate, `SCAN` with a cursor and a small `COUNT`.

**Q: The process crashes between COMMIT and DEL. What now?**
A: That key is stale until its TTL, which is exactly why every key has a TTL. If that
window is unacceptable, the invalidation has to be part of the commit: write an outbox row
in the same transaction and have a publisher issue the delete, or drive invalidation from
CDC off the WAL. Both turn "the app remembered" into "the data changed."

**Q: What TTL for the negative case — a lookup that found nothing?**
A: Much shorter than the positive case, typically 30 to 60 seconds, and stored as an
explicit sentinel rather than an absent key so it's distinguishable from a miss. Long
enough to absorb a scraper hammering non-existent IDs (7.8), short enough that a
newly-created record becomes visible quickly.

### Red flags — do not say this

- ❌ "On update, I update the cache with the new value." → ✅ "On update I delete the key.
  Concurrent writers can order the DB and the cache differently, and a delete's worst case
  is a miss while an update's worst case is permanent divergence."
- ❌ "I'll use `KEYS user:*` to clear those." → ✅ "`KEYS` is O(N) and Redis is
  single-threaded, so that stalls the whole instance. I put a generation counter in the key
  and `INCR` it."
- ❌ "Cache invalidation is hard." (and stopping there) → ✅ "I layer three mechanisms: TTL
  as the backstop, explicit delete-after-commit for the hot path, and CDC when writes come
  from many places."
- ❌ "TTL of 5 minutes on everything." → ✅ "TTL is per-key-class and set from the staleness
  budget: 24 hours for the product catalogue, 60 seconds for a dashboard aggregate, 30
  seconds for negative lookups, and jittered so they don't all expire together."

---

## 7.5 Eviction policies

> **One-liner:** Eviction is what the cache does when it is full, Redis's default is to
> return errors rather than evict, and knowing that one fact is worth more than reciting
> all ten policy names.

### Say this in the interview

> Eviction is the policy for what to drop when memory is full, and the first thing I check
> in production is `maxmemory-policy`, because Redis defaults to `noeviction` — which
> means when you hit the limit, writes start failing with an OOM error while reads keep
> working. That surprises people who assume a cache silently makes room. For a pure cache
> I set `allkeys-lru`, which is a good default because most access patterns are Pareto
> shaped. I switch to `allkeys-lfu` when there's a stable popular set being polluted by
> scans or crawlers, because LRU only remembers that a key was touched once recently while
> LFU remembers that it has been touched rarely overall. And I avoid `volatile-*` policies
> unless I'm certain every key has a TTL, because if nothing is eligible they behave
> exactly like `noeviction` and you get write failures with plenty of "free" memory. The
> detail worth knowing is that Redis's LRU is approximate: rather than maintaining a global
> ordering, it samples five keys per eviction and evicts the oldest of the sample, keeping
> a pool of good candidates across samplings. Raising `maxmemory-samples` to 10 gets very
> close to true LRU at more CPU. That approximation is the right engineering call —
> maintaining exact LRU for a hundred million keys would cost more memory than it saves.

### Mental model

```
       memory used
            │
  maxmemory ├─────────────────── policy decides here ────────────
            │                            │
            │        ┌───────────────────┴────────────────────┐
            │        │                                        │
            │   noeviction                              allkeys-* / volatile-*
            │   writes -> OOM error                     pick a victim, free,
            │   reads   -> still fine                   retry the write
            │
```

**The ten `maxmemory-policy` values:**

| Policy | Victim | Note |
|---|---|---|
| `noeviction` | none — writes error | **The Redis OSS default.** Right for a datastore, wrong for a cache |
| `allkeys-lru` | least recently used, any key | Best general-purpose cache default |
| `allkeys-lfu` | least frequently used, any key | Better when a stable hot set is polluted by scans |
| `allkeys-random` | any key | Only when every key is equally likely; cheapest |
| `volatile-lru` | LRU among keys with a TTL | Redis Enterprise default. Degenerates to `noeviction` if no key has a TTL |
| `volatile-lfu` | LFU among keys with a TTL | Same caveat |
| `volatile-random` | random among keys with a TTL | Same caveat |
| `volatile-ttl` | shortest remaining TTL | Approximate, not exact ordering |
| `allkeys-lrm` / `volatile-lrm` | least recently *modified* | Redis 8.6+; only writes refresh the timestamp |

**LRU vs LFU, the case that decides it.** A crawler walks your entire product catalogue
once — a million cold keys, each read exactly once.

```
 LRU: those million reads are all "recent", so they sit at the top of the
      recency order and evict your genuinely hot 10,000 keys. Hit ratio
      collapses right after the crawl and stays down until the hot set refills.

 LFU: each crawled key has a frequency counter of 1. Your hot keys have
      counters in the hundreds. The crawler's keys are the first victims.
      Hit ratio barely moves.
```

The general rule: **LRU optimises for recency, LFU for popularity.** Choose LFU when
popularity is stable over hours or days and you have scan-shaped traffic (crawlers,
analytics jobs, batch exports, a full-catalogue reindex). Choose LRU when the hot set
genuinely moves — a news feed, a live event, a session store.

Redis LFU has two knobs that matter. `lfu-log-factor` (default 10) controls how quickly
the counter saturates, because the counter is logarithmic and 8 bits wide rather than a
raw count. `lfu-decay-time` (default 1 minute) is how long before a counter loses a point,
which is what stops a key that was popular last Tuesday from being immortal. Setting decay
to 0 means never decay, which is almost always a mistake.

**Approximated LRU.** Redis does not keep a global LRU list. On each eviction it samples
`maxmemory-samples` keys (default 5), keeps the best candidates in a small pool carried
across successive samplings, and evicts from there. From `redis.conf`: the default of 5
"produces good enough results," 10 "approximates very closely true LRU but costs more
CPU," 3 is faster and less accurate, and the maximum is 64. Say this in an interview and
you sound like you have read the config file, because you have.

**TTL expiry is not eviction.** Two separate mechanisms, and they get conflated:

```
 Expiry:   key had a TTL and it elapsed. Removed lazily on access, plus an
           active cycle that samples keys with TTLs ~10x/second. Happens
           whether or not memory is under pressure.
 Eviction: memory hit maxmemory. maxmemory-policy picks a victim, possibly
           one with no TTL at all and plenty of life left.
```

### Enterprise production example

The **Redis** project's own configuration documentation makes the eviction trade-off
explicit and is worth quoting because it justifies the default: `allkeys-lru` is
recommended "when you expect that a subset of elements will be accessed far more often
than the rest… a very common case according to the Pareto principle." Redis Enterprise
diverges deliberately — `volatile-lru` is the default there, and for Active-Active
databases the default is `noeviction`, with eviction beginning at 80 percent of the memory
limit rather than 100 percent because evictions must be propagated to every participating
cluster and that needs headroom. Two products, same engine, different defaults, each
justified by its consistency model. If asked "what's the right eviction policy," that is
the answer: it depends on whether the thing is a cache or a database, and Redis ships
different defaults for exactly that reason.

### Code

```bash
# What to actually check on a Redis you inherited.
redis-cli CONFIG GET maxmemory maxmemory-policy maxmemory-samples
redis-cli INFO memory   | grep -E 'used_memory_human|maxmemory_human|mem_fragmentation'
redis-cli INFO stats    | grep -E 'evicted_keys|expired_keys|keyspace_(hits|misses)'
```

```conf
# redis.conf for a pure cache (not a datastore).
maxmemory 24gb                 # leave ~25% of the box: COW on fork, buffers, fragmentation
maxmemory-policy allkeys-lru   # NOT the default; the default (noeviction) fails writes
maxmemory-samples 5            # 10 ~= true LRU at more CPU; max 64

# If a crawler or a nightly reindex is wrecking your hit ratio, switch to:
# maxmemory-policy allkeys-lfu
# lfu-log-factor 10            # counter saturation
# lfu-decay-time 1             # minutes before a counter loses a point; 0 = never (bad)
```

```python
# The alert that matters: evictions plus a falling hit ratio means undersized memory.
# Evictions alone are normal and healthy for a cache.
hits, misses = info["keyspace_hits"], info["keyspace_misses"]
hit_ratio = hits / (hits + misses)
if info["evicted_keys_rate"] > 0 and hit_ratio < 0.90:
    page("cache undersized: evicting the working set, not the tail")
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `allkeys-lru` — general cache, moving hot set | Scan traffic regularly floods the keyspace | Cold scans evict your hot set |
| `allkeys-lfu` — stable popularity, crawler/batch traffic present | Popularity genuinely shifts hourly | Slower to adapt; a newly hot key can be evicted before its counter grows |
| `volatile-*` — mixed cache and persistent data in one instance | Not every key has a TTL | Behaves like `noeviction` when nothing is eligible: writes fail with memory to spare |
| `noeviction` — Redis is the datastore, not a cache | It is a cache | Writes fail at the limit; you must monitor and scale ahead of it |
| `allkeys-random` | Uniform access | Cheapest; evicts hot keys as readily as cold |

### Follow-ups they will ask

**Q: When does LFU beat LRU?**
A: When popularity is stable and something periodically scans the keyspace. A nightly
full-catalogue reindex reads a million keys once; under LRU all of those are "recent" and
they evict the ten thousand keys real users are hitting, so the hit ratio drops right after
the job and stays down. Under LFU each scanned key has a frequency of 1 and is the first
victim, so the hot set survives. The cost is adaptation speed — a genuinely newly popular
key has a low counter and can be evicted before it earns its place.

**Q: You set `maxmemory` and `volatile-lru`, and writes start failing at the limit. Why?**
A: Because `volatile-lru` only considers keys that have a TTL, and some of my keys have
none. With no eligible victim, Redis cannot free memory and behaves exactly like
`noeviction` — OOM errors on writes while `INFO` shows memory full of ineligible keys.
Fix is either `allkeys-lru`, or guarantee a TTL on every key, and don't mix cache data and
persistent data in one instance.

**Q: Are evictions in `INFO` a problem?**
A: Not by themselves — a cache at its memory limit evicting the cold tail is working as
designed. It becomes a problem when evictions rise *and* the hit ratio falls, which means
you're evicting the working set rather than the tail. That pair is the alert; `evicted_keys`
alone is noise.

**Q: Why is Redis's LRU approximate, and does it matter?**
A: Exact LRU needs a global doubly-linked list plus per-key back-pointers, which is
significant memory and pointer-chasing per access at a hundred million keys. Redis instead
samples five candidates per eviction and keeps a pool of good ones across samplings. It
matters only at the margin: you occasionally evict the sixth-oldest instead of the oldest,
which changes the hit ratio by a fraction of a percent. If you care, `maxmemory-samples 10`
gets very close to true LRU for more CPU.

### Red flags — do not say this

- ❌ "Redis evicts old keys when it's full." → ✅ "Only if you configure it to. The OSS
  default is `noeviction`, which fails writes at the limit. For a cache I set
  `allkeys-lru` explicitly."
- ❌ "LRU is the best eviction policy." → ✅ "LRU is the best default. LFU wins when a
  stable hot set is being polluted by scan traffic, because LRU treats a one-time crawl as
  recency."
- ❌ "TTL and eviction are the same thing." → ✅ "Expiry removes keys whose TTL elapsed,
  under memory pressure or not. Eviction removes keys because memory is full, and can take
  keys with no TTL at all."

---

## 7.6 Cache stampede / thundering herd

> **One-liner:** One popular key expires, every concurrent request misses at the same
> instant, and they all recompute the same value against an origin sized for one percent
> of that load — the classic way a cache turns a traffic spike into an outage.

### Say this in the interview

> A stampede is what happens when a hot key expires under concurrency. Say a key is read
> five thousand times a second and takes 300 milliseconds to rebuild. At the moment it
> expires, every request in that 300 millisecond window misses — about fifteen hundred
> requests — and all fifteen hundred run the same expensive query. The database saturates,
> the queries get slower, which widens the window, which lets more requests in, and you
> have congestion collapse on a database that was comfortable a second earlier. The
> nastiest part is that it is self-inflicted by the cache: without a cache the load would
> have been steady. I mitigate it in layers. Jittered TTLs first, because it costs one
> line and stops synchronised expiry across many keys. Then single-flight, so within one
> process only one caller rebuilds and the rest await the same future. Then a distributed
> lease — a Redis SET NX with a short expiry — so only one process in the fleet rebuilds,
> and everyone else serves the previous value while it's in flight. That last bit is
> stale-while-revalidate and it is the one that actually saves you, because it means no
> user is ever waiting on a rebuild. The most elegant version is probabilistic early
> expiration, XFetch from the 2015 VLDB paper, where each reader independently decides to
> refresh early with a probability that rises as expiry approaches, so the refresh happens
> before there is ever a herd. Facebook's memcached paper reports the same idea via leases
> taking peak database query rate on herd-prone keys from seventeen thousand a second down
> to thirteen hundred.

### Mental model

**The failure timeline.** Key `home:feed` at 5,000 req/s, rebuild takes 300 ms, TTL 60 s.

```
 t=0.000  TTL expires. Cache: MISS.
 t=0.000  Request #1 misses, starts SELECT (300 ms).
 t=0.001  Requests #2..#6 miss (5 more, none of them know about #1).
   ...
 t=0.300  ~1,500 requests have each started the same 300 ms query.
          Postgres now has 1,500 concurrent expensive queries against a
          pool of 100 connections. 1,400 are queued.
 t=0.300  Queries that should take 300 ms now take 3 s (CPU + lock + IO
          contention). The rebuild window widened 10x.
 t=3.000  ~15,000 requests are in flight. Connection pool exhausted.
          Unrelated endpoints start failing: the pool is a shared resource.
 t=3.x    Client timeouts fire. Clients retry. Retries add load.
          -> congestion collapse. The cache never refills because no
             query completes fast enough to win.
```

Two properties make this vicious: the load is **synchronised** (everyone at once) and
**self-amplifying** (slower origin means a wider window means more requests).

**The five mitigations, and what each actually fixes:**

```
 ┌─────────────────────────┬───────────────────────────────────────────┐
 │ Jittered TTL            │ Fixes: many keys expiring in the same     │
 │ ttl x (1 +- 10%)         │ second (avalanche, 7.8). Does NOT fix a  │
 │                         │ single hot key. One line. Always do it.   │
 ├─────────────────────────┼───────────────────────────────────────────┤
 │ Single-flight            │ Fixes: N concurrent callers in ONE        │
 │ (in-process coalescing) │ process. With 40 pods you still get 40    │
 │                         │ origin queries, not 1,500. Big win, cheap.│
 ├─────────────────────────┼───────────────────────────────────────────┤
 │ Distributed lease/lock  │ Fixes: fleet-wide. SET lease NX PX 5000.  │
 │                         │ Question becomes: what do the losers do?  │
 ├─────────────────────────┼───────────────────────────────────────────┤
 │ stale-while-revalidate  │ Answers it: losers serve the previous     │
 │ (physical TTL > logical)│ value. NOBODY waits. This is the one that │
 │                         │ turns an outage into a stale-data blip.   │
 ├─────────────────────────┼───────────────────────────────────────────┤
 │ XFetch (probabilistic   │ Prevents the herd from forming at all by  │
 │ early expiration)       │ refreshing before expiry. No locks, no    │
 │                         │ coordination, no extra round trip.        │
 └─────────────────────────┴───────────────────────────────────────────┘
```

**XFetch, precisely.** From *Optimal Probabilistic Cache Stampede Prevention* (Vattani,
Chierichetti, Lowenstein, VLDB 2015). Store two extra fields with the value: `delta`, how
long the last recomputation took, and `expiry`, the logical expiry time. On every read:

```
        recompute if:   now - delta x beta x ln(rand())  >=  expiry
                             └──────────┬───────────┘
                          always positive, because ln of a number
                          in (0,1) is negative. This is a random
                          "lead time" that grows with how expensive
                          the key is to rebuild.
```

`beta` defaults to 1.0; above 1.0 refreshes earlier, below 1.0 later. Far from expiry the
gap is large and the random lead time rarely exceeds it, so essentially every reader
serves the cached value. As `now` approaches `expiry` the probability rises smoothly
toward one, and a single early reader trips it, rebuilds, and resets the clock before a
herd can form. The paper's key result is that the tuning parameter does **not** need to
depend on request rate, which is why it works with no tuning. Expensive keys (large
`delta`) volunteer earlier, which is exactly the behaviour you want.

**Physical vs logical TTL** is the enabling trick for both stale-while-revalidate and
XFetch: set the Redis TTL (physical) longer than the freshness deadline (logical, stored
in the value). Between the two there is a value you can still serve while someone
rebuilds.

```
 |<────────── logical TTL: 60 s ──────────>|<─ grace: 60 s ─>|
 |            serve as fresh               | serve as stale  |  hard miss
 0                                         60               120
                                            ^
                                    refresh triggers here; readers
                                    keep getting the old value until
                                    the rebuild lands
```

### Enterprise production example

**Facebook**, in *Scaling Memcache at Facebook* (NSDI 2013), solved the herd with lease
throttling: a memcached server returns a lease token for a given key only once every 10
seconds, and requests arriving inside that window get a special notification telling the
client to wait briefly and retry — by which time the leaseholder has usually set the value.
Their measurement on a set of herd-prone keys over a week: peak database query rate of
17,000 per second without leases, versus 1,300 per second with them. Since they provision
databases for peak load, that is roughly a 13x reduction in provisioned database capacity
from one mechanism.

**Cloudflare** solves the same problem at the CDN layer from two directions. Tiered Cache
funnels misses from many edge PoPs through an upper tier, and Cloudflare reports customers
achieving "a 60% or greater reduction in their cache miss rate" compared with their
traditional CDN service. And their `stale-while-revalidate` is now fully asynchronous:
previously the first request after expiry blocked on the origin, whereas now that request
triggers a background revalidation and immediately receives the stale content with an
`UPDATING` status. Same principle as the code below, implemented at 300-plus PoPs.

**Discord** built request coalescing directly into the data layer. Their Rust data services
sit between the API and ScyllaDB with roughly one gRPC endpoint per database query and no
business logic, and their stated headline feature is coalescing: if multiple users request
the same row at the same time, the first spins up a worker task and subsequent requests
subscribe to it, so the database is queried once and the row is returned to all
subscribers. That is single-flight promoted from a library utility to an architectural
tier, specifically to protect the database from hot partitions.

### Code

```python
"""Read-through cache with jittered TTL, in-process single-flight, a
fleet-wide lease, XFetch early refresh, and stale-while-revalidate.
This is the shape a production cache helper actually has."""
import asyncio, math, random, secrets, time
from typing import Awaitable, Callable

class StampedeSafeCache:
    def __init__(self, redis, ttl: float, jitter: float = 0.10, beta: float = 1.0,
                 grace: float = 60.0, lease_ms: int = 5_000):
        self.r, self.ttl, self.jitter = redis, ttl, jitter
        self.beta, self.grace, self.lease_ms = beta, grace, lease_ms
        self._inflight: dict[str, asyncio.Future] = {}

    async def get(self, key: str, loader: Callable[[], Awaitable[bytes]]) -> bytes:
        m = await self.r.hgetall(key)          # v, delta, expiry in one round trip
        stale = m.get(b"v")
        if stale is not None:
            expiry, delta = float(m[b"expiry"]), float(m[b"delta"])
            # XFetch: lead time grows with rebuild cost; P(refresh) -> 1 near expiry.
            lead = -delta * self.beta * math.log(random.random())
            if time.time() + lead < expiry:
                return stale                   # fresh enough, the common path
        return await self._rebuild(key, loader, stale)

    async def _rebuild(self, key, loader, stale):
        fut = self._inflight.get(key)
        if fut is not None:                    # coalesce within this process
            return await asyncio.shield(fut)
        fut = asyncio.get_running_loop().create_future()
        self._inflight[key] = fut
        try:
            token = secrets.token_hex(8)
            lease = await self.r.set(f"lease:{key}", token, nx=True, px=self.lease_ms)
            if not lease and stale is not None:
                fut.set_result(stale)          # another pod is rebuilding: serve stale
                return stale
            t0 = time.perf_counter()
            value = await loader()             # the only call that reaches the origin
            delta = time.perf_counter() - t0
            ttl = self.ttl * (1 + random.uniform(-self.jitter, self.jitter))
            await self.r.hset(key, mapping={"v": value, "delta": delta,
                                            "expiry": time.time() + ttl})
            # Physical TTL exceeds logical expiry: that gap is the stale-serving window.
            await self.r.pexpire(key, int((ttl + self.grace) * 1000))
            await self.r.delete(f"lease:{key}")
            fut.set_result(value)
            return value
        except Exception as exc:
            if stale is not None:
                fut.set_result(stale)          # stale-if-error: origin down != user 500
                return stale
            fut.set_exception(exc)
            raise
        finally:
            self._inflight.pop(key, None)
```

```javascript
// Node equivalent of the single-flight core. The whole idea is one map.
const inflight = new Map();

async function singleFlight(key, fn) {
  const existing = inflight.get(key);
  if (existing) return existing;                 // every concurrent caller awaits one promise
  const p = fn().finally(() => inflight.delete(key));
  inflight.set(key, p);
  return p;
}

const jitter = (ttlMs, pct = 0.1) =>
  Math.round(ttlMs * (1 + (Math.random() * 2 - 1) * pct));
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Jittered TTL — always, on every key | Never a reason to skip | Expiry times become non-deterministic (fine) |
| Single-flight — always, in every process | Never a reason to skip | A map and some care around exceptions |
| Distributed lease — a rebuild is expensive enough that 40 concurrent ones hurt | Rebuild is cheap; the lease round trip costs more than it saves | One extra Redis round trip on miss; a crashed holder blocks until `PX` elapses |
| stale-while-revalidate — staleness is acceptable for the rebuild duration | The read must never be stale (auth, balances) | Users see data up to `grace` seconds old |
| XFetch — hot keys with a steady request stream | Sporadically-read keys (no reader arrives in the early window) | Slightly more origin work than strictly necessary; `delta` estimated from last rebuild |

### Follow-ups they will ask

**Q: Does jittering TTLs prevent a stampede?**
A: It prevents *avalanche* — many different keys expiring in the same second, typically
because they were all populated by the same deploy or warm-up job. It does nothing for a
single hot key: that key still expires at one instant and every concurrent reader still
misses. Jitter is necessary and not sufficient; the single-key case needs coalescing or
early refresh.

**Q: You have single-flight in the process. Do you still need a distributed lock?**
A: Depends on the fan-out and the rebuild cost. With 40 pods, single-flight alone turns
1,500 concurrent origin queries into 40, which is usually survivable. If the rebuild is a
30-second analytical query or a paid LLM call, 40 is still 40 times too many, and a Redis
`SET NX PX` lease gets it to 1. I add the lease when `cost_of_rebuild × pod_count` is
actually a problem, not reflexively.

**Q: Who holds the lock while it rebuilds, and what if that process dies?**
A: The lease is a Redis key with a `PX` expiry — typically a couple of times the p99
rebuild time — so a dead holder self-releases. I store a random token as the value and
delete only if the token matches, via Lua, so a slow holder that already expired cannot
release someone else's lease. And critically: the losers do not block on the lock, they
serve stale. A lock where the losers wait just converts a database stampede into a
latency stampede.

**Q: How is XFetch better than just refreshing at 80 percent of the TTL?**
A: A fixed 80 percent threshold is a synchronised trigger — every reader crosses it at the
same moment, so you have moved the herd earlier, not removed it. XFetch is randomised per
request, so exactly one reader typically trips it. And the lead time scales with `delta`,
so keys that are expensive to rebuild refresh earlier automatically. The VLDB paper's
central result is that the parameter doesn't need to track the request rate, which is why
it works untuned.

**Q: Where does this bite in an LLM application specifically?**
A: A shared prompt template or a retrieval result cached for a popular question. The
rebuild isn't a 300 ms query, it's a 3-second generation that costs real money, so the
herd window is ten times wider and every duplicate has a dollar cost. I would run
single-flight plus a lease on the semantic cache key, and serve the previous answer with
`stale-while-revalidate` while one caller regenerates.

### Red flags — do not say this

- ❌ "I'll add a lock so only one request rebuilds." → ✅ "One rebuilds behind a leased
  lock, and the others serve the previous value rather than waiting. A lock alone turns a
  database stampede into a latency stampede."
- ❌ "Jittered TTLs solve the thundering herd." → ✅ "Jitter solves synchronised expiry
  across many keys. A single hot key still needs coalescing or probabilistic early
  refresh."
- ❌ "The cache protects the database." → ✅ "The cache protects the database until a hot
  key expires, at which point the cache is the thing that synchronises the load. That's
  why single-flight and stale-while-revalidate aren't optional at a high hit ratio."
- ❌ "We'd just add read replicas." → ✅ "Replicas raise the ceiling but don't change the
  shape — 1,500 simultaneous identical queries is a coordination bug, not a capacity
  problem, and it should be fixed with one query instead of more capacity."

---

## 7.7 Hot keys

> **One-liner:** A single key cannot be split across shards, so one celebrity, one
> flash-sale SKU or one bad client can saturate one Redis node while the other nineteen
> sit idle.

### Say this in the interview

> A hot key is the case where sharding stops helping, because consistent hashing places a
> key on exactly one node and no amount of adding nodes moves that key's traffic. If a
> single product page takes two hundred thousand reads a second during a flash sale, that
> lands on one Redis shard, and that shard is single-threaded, so you saturate one CPU
> core while the rest of the cluster is idle. I detect it before it hurts: `redis-cli
> --hotkeys` sampling in staging, `MONITOR` briefly and never under load, per-key metrics
> on the client side for the top keys, and the honest signal in production which is one
> shard's CPU and network at ninety percent while the cluster average is fifteen. There
> are three fixes and I usually apply the first. Client-side L1 caching with a one to five
> second TTL: forty pods each reading that key once per second is forty reads a second
> instead of two hundred thousand, a five-thousand-fold reduction, at the cost of up to a
> second of staleness. Second, key splitting — write the same value to N suffixed copies
> and have readers pick one at random, which spreads a hot key across N shards but makes
> invalidation N deletes. Third, read replicas of the cache for read-only traffic. I reach
> for L1 first because it's the only one that removes the network hop entirely.

### Mental model

```
 WITHOUT mitigation                     WITH L1 + key splitting
 ─────────────────                      ───────────────────────
  200k rps for "sku:9"                   200k rps for "sku:9"
        │                                       │
        │ hash("sku:9") -> slot 4821            │ 40 pods x L1 (2 s TTL)
        ▼                                       ▼  = 20 rps to Redis
 ┌────────────┐ ┌───────┐ ┌───────┐      ┌────────────┐ ┌────────────┐
 │  shard 2   │ │shard 3│ │shard 4│      │  shard 2   │ │  shard 3   │
 │ CPU 100%   │ │ 8%    │ │ 6%    │      │ sku:9#0..3 │ │ sku:9#4..7 │
 │ THE PROBLEM│ │ idle  │ │ idle  │      │ ~5 rps ea. │ │ ~5 rps ea. │
 └────────────┘ └───────┘ └───────┘      └────────────┘ └────────────┘
```

**Detection, in order of how much you should trust it:**

1. **Client-side per-key counters.** Sample 1 percent of reads, count by key prefix and
   by full key for the top offenders, export as a metric. The only method that works
   continuously under production load.
2. **Per-shard resource metrics.** One node's CPU or network far above the cluster average
   is the unambiguous production signal.
3. **`redis-cli --hotkeys`.** Uses `OBJECT FREQ`, so it needs an LFU policy. Fine in
   staging or on a replica; it walks the keyspace.
4. **`MONITOR`.** Shows every command. Costs significant throughput. Seconds only, and
   preferably against a replica. Never leave it running.

**Fix 1 — client-side L1 (usually the right answer).** A short-TTL in-process cache turns
`N_requests` into `N_pods / L1_TTL` reads:

```
 200,000 rps  x  40 pods sharing the load  x  2 s L1 TTL
   -> each pod reads Redis once per 2 s -> 20 rps total
   -> 10,000x reduction, cost: up to 2 s staleness
```

**Fix 2 — key splitting.** Write to N copies, read one at random:

```
 write: for i in 0..N-1:  SET sku:9#{i} <value> EX 60      (N writes)
 read:  GET sku:9#{randrange(N)}                            (1 read)

 N=8 spreads across up to 8 slots -> up to 8 different shards.
 Cost: writes are 8x, invalidation is 8 DELs, and the N copies can
 briefly disagree, so the effective staleness is the write fan-out
 duration. Use only for read-mostly hot keys.
```

**Fix 3 — consistent hashing with bounded loads.** Instead of always placing a key on its
hashed node, cap any node's load at `(1 + ε)` times the average and spill to the next node
in the ring when it is full. Keeps the rebalance-friendliness of consistent hashing while
removing the guarantee that one key ruins one node. Good to name; rarely something you
implement yourself, since it lives in load balancers and proxies.

**The concrete scenario — a flash sale.** 09:59:55, and a marketing push lands on one SKU:

```
 09:59:55  Normal: 500 rps across 50k SKUs. Every shard ~10 rps.
 10:00:00  Push lands. sku:9 goes to 200k rps. All of it -> shard 2.
 10:00:01  Shard 2 CPU 100%. It is single-threaded, so latency for EVERY
           key on shard 2 (thousands of unrelated keys) goes 0.4 ms -> 40 ms.
 10:00:03  App connection pools fill waiting on shard 2. Endpoints that
           have nothing to do with sku:9 start timing out.
 10:00:05  Adding Redis nodes does not help: rebalancing moves other
           slots, and sku:9 still hashes to exactly one node.
```

The lesson to state out loud: a hot key degrades every tenant of that shard, not just the
hot entity — which is why it is an availability problem, not a performance problem.

### Enterprise production example

**Shopify** faced the write-side version of this on flash sales and solved it at the edge.
Their engineering blog describes an edge tier built on nginx plus OpenResty's Lua module,
where they implemented a leaky-bucket throttle with a 5-second period in front of checkout.
The forcing constraint was in their data model: every checkout session created a new MySQL
record and every step in the flow modified that same record, so a flash sale was a
write-hotspot the cache layer could not absorb. Requests over the limit were redirected to
a queue page which was itself rendered by Shopify but **cached in nginx**, with an injected
JavaScript snippet polling `/checkout`; once through, the user got a securely signed cookie
that let them skip the throttle for the rest of the session. A follow-up post describes
adding stateless fair queueing — a threshold computed independently on each load balancer,
with the user's arrival timestamp in a signed cookie, chosen specifically because a shared
datastore would be a new point of failure and cross-datacentre Redis replication was
"nontrivial." Two details worth stealing: the overflow page is cached so the degraded path
is cheaper than the happy path, and fairness was achieved with a cookie instead of shared
state.

For scale context on what they design for: Shopify's 2025 BFCM readiness post reports scale
tests reaching 146 million requests per minute and over 80,000 checkouts per minute at
their p90 projections, and 200 million requests per minute at p99.

**Discord's** fan-out numbers show why hot entities need architectural answers rather than
tuning. Their post on scaling large servers spells out the quadratic: a guild with 1,000
people online where everyone sends one message is a million notifications; 10,000 online is
100 million; 100,000 online is 10 billion. Their fix was to introduce "relays" between the
guild process and user sessions, handling up to 15,000 connected sessions per relay — key
splitting applied to a fan-out process rather than a cache key.

### Code

```python
"""Hot-key handling: detection by sampling, then L1 + optional key splitting."""
import random, time
from collections import Counter
from cachetools import TTLCache

_SAMPLE_RATE = 0.01
_key_counts: Counter[str] = Counter()

def record(key: str) -> None:
    if random.random() < _SAMPLE_RATE:
        _key_counts[key] += 1          # scrape and reset this on a 60 s timer

# L1: 5,000 keys, 2 s TTL. Bounds staleness AND removes the network hop.
_l1 = TTLCache(maxsize=5_000, ttl=2.0)

async def get_hot(r, key: str, loader, splits: int = 1):
    record(key)
    if (v := _l1.get(key)) is not None:
        return v
    # Splitting only helps if the read picks a random replica of the key.
    physical = key if splits == 1 else f"{key}#{random.randrange(splits)}"
    v = await r.get(physical)
    if v is None:
        v = await loader()
        # Write every split so any reader can be served; pipeline it.
        async with r.pipeline(transaction=False) as pipe:
            for i in range(splits):
                pipe.set(key if splits == 1 else f"{key}#{i}", v, ex=60)
            await pipe.execute()
    _l1[key] = v
    return v

async def invalidate_hot(r, key: str, splits: int = 1):
    await r.delete(*([key] if splits == 1 else [f"{key}#{i}" for i in range(splits)]))
    _l1.pop(key, None)                 # local only: other pods clear on their own TTL
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Client-side L1, 1-5 s TTL | The value must be fresher than the L1 TTL | Up to `ttl` staleness, per-pod and unsynchronised |
| Key splitting into N copies | The key is write-heavy | N writes, N deletes, and a window where copies disagree |
| Cache read replicas | Writes are the hot path | Replication lag; a replica read can be older than the primary |
| Bounded-load consistent hashing | You'd have to build it yourself | Some keys are no longer where the plain hash says they are |
| Edge throttle + cached overflow page (Shopify's answer) | The traffic is legitimate and must all be served | Some users get a queue page instead of the product |

### Follow-ups they will ask

**Q: A single Redis shard is at 100 percent CPU and the rest are idle. What do you do, and what won't work?**
A: What won't work is adding nodes — the key hashes to one slot and one node no matter how
many I add. First I confirm it's a single key with client-side sampling rather than a hot
slot range. Then, in order: an L1 cache with a 1-5 second TTL, which usually ends the
incident in a deploy; key splitting into N suffixed copies if the value is read-mostly; and
if this is a recurring pattern, a dedicated cache tier for hot entities so they can't
degrade unrelated keys. I'd also check for a pathological command on that shard — a big
`HGETALL` or an `SMEMBERS` on a large set will pin one core just as effectively as a hot
key.

**Q: Why does a hot key hurt other keys?**
A: Because Redis executes commands on a single thread per instance. A saturated node
processes its queue serially, so every key on that shard — thousands of unrelated ones,
possibly other tenants — inherits the queueing delay. That's what makes hot keys an
availability problem: the blast radius is the shard, not the entity.

**Q: You split a hot key into 8 copies. What breaks?**
A: Invalidation and coherence. Every write becomes 8 writes and every delete 8 deletes,
which is fine if pipelined, but the fan-out is not atomic — for a few milliseconds
different readers see different values, so effective staleness equals the write fan-out
duration. And if one `SET` of the eight fails, one shard serves a stale value until TTL
with nothing to detect it. So splitting is for read-mostly values, and I put a TTL on every
copy as the repair mechanism.

**Q: How do you find hot keys without hurting production?**
A: Client-side sampling — count 1 percent of reads by key and export the top N as a metric.
It's continuous, cheap, and gives history so I can see a key heating up before it saturates.
`redis-cli --hotkeys` needs an LFU policy and walks the keyspace, so it goes on a replica or
in staging. `MONITOR` is a last resort for seconds at a time; it costs real throughput and
has caused incidents of its own.

### Red flags — do not say this

- ❌ "Add more Redis nodes to spread the load." → ✅ "Sharding can't split a single key.
  I need client-side caching or key splitting; adding nodes leaves that key on one node."
- ❌ "Use `MONITOR` to find hot keys." → ✅ "Client-side sampled counters in production;
  `--hotkeys` or `MONITOR` on a replica, briefly, because `MONITOR` costs real throughput."
- ❌ "Redis is fast, one key can't be a bottleneck." → ✅ "One instance is single-threaded,
  so one key can saturate one core at a few hundred thousand ops per second, and every
  other key on that shard queues behind it."
- ❌ "We'd shard by user ID so it's even." → ✅ "Even in aggregate, but a celebrity user or
  a flash-sale SKU is one key on one shard. Hash-based sharding gives you uniform *key*
  distribution, not uniform *traffic* distribution."

---

## 7.8 Cache penetration and cache avalanche

> **One-liner:** Penetration is traffic for keys that will never be cacheable because they
> don't exist; avalanche is many keys expiring at once — both look like a stampede in a
> graph and need completely different fixes.

### Say this in the interview

> These three get lumped together and they have different causes. A stampede is one hot key
> expiring with many concurrent readers, and the fix is coalescing. Penetration is requests
> for keys that don't exist — a scraper walking sequential IDs, or an enumeration attack —
> so every request is a guaranteed miss and the cache provides zero protection no matter how
> big it is. I fix that by caching the negative result with a short TTL, thirty to sixty
> seconds, stored as an explicit sentinel so I can tell "known absent" from "not cached,"
> and by validating the ID format before touching any datastore. If the key space is huge
> and mostly absent, a Bloom filter in front is worth it: it answers "definitely not
> present" or "maybe present," with false positives but never false negatives, so a negative
> answer is safe to trust and a positive one just means you do the real lookup. At one
> percent false positives it costs about 9.6 bits per element, so a hundred million IDs fit
> in roughly 120 megabytes versus 1.6 gigabytes to store the keys themselves. Avalanche is
> the third one: many different keys expiring in the same second, which almost always means
> a deploy or a warm-up script populated them together with identical TTLs. Jitter the TTLs
> and that whole failure class disappears.

### Mental model

```
 ┌──────────────┬────────────────────────┬────────────────────────────────┐
 │ Failure      │ Cause                  │ Fix                            │
 ├──────────────┼────────────────────────┼────────────────────────────────┤
 │ Stampede     │ ONE hot key expires,   │ single-flight, lease,          │
 │ (7.6)        │ many concurrent readers│ stale-while-revalidate, XFetch │
 ├──────────────┼────────────────────────┼────────────────────────────────┤
 │ Penetration  │ Keys that DO NOT EXIST │ negative caching, input        │
 │              │ (scraper, enumeration, │ validation, Bloom filter,      │
 │              │  bad client, bad ID)   │ per-client rate limit          │
 ├──────────────┼────────────────────────┼────────────────────────────────┤
 │ Avalanche    │ MANY keys expire in    │ TTL jitter, staggered warm-up, │
 │              │ the same second        │ per-key-class TTLs             │
 └──────────────┴────────────────────────┴────────────────────────────────┘
```

**Negative caching.** Store a sentinel, not nothing:

```
 GET product:99999999
   -> b"\x00NULL"     : known absent. Return 404 without touching Postgres.
   -> None            : not cached. Do the lookup.
```

Two rules. The negative TTL is much shorter than the positive one (30-60 s), so a
newly-created record appears quickly. And the sentinel is invalidated on create — when
`product:99999999` is actually inserted, delete the negative entry in the same
post-commit invalidation path, or the creator's own read-after-write shows a 404.

**Bloom filters.** A bit array plus `k` hash functions. Insert sets `k` bits; query checks
`k` bits. If any is 0 the element is **definitely absent**; if all are 1 it is **probably
present**.

```
 bits:  0 1 1 0 0 1 0 0 1 0 1 0
              ^     ^       ^
  query "x": all k bits set  -> MAYBE present  -> do the real lookup
  query "y": one bit is 0    -> DEFINITELY absent -> return 404, free
```

The asymmetry is the whole value: **no false negatives.** You can act on "absent" without
verification, which is exactly the direction that saves the database. Sizing:

```
   m/n = -ln(p) / (ln 2)^2        bits per element
   k   = (m/n) x ln 2             optimal number of hash functions

   p = 1%     ->  9.6 bits/elt,  7 hashes
   p = 0.1%   -> 14.4 bits/elt, 10 hashes

   100M product IDs at p=1%:  100e6 x 9.6 bits  =  ~120 MB
   the same IDs stored as 16-byte keys in a set:  ~1.6 GB  (13x more)
```

When it's actually worth it: the key space is large, misses dominate, and you can tolerate
that a plain Bloom filter cannot delete (removing an element would clear bits shared with
others — use a counting or cuckoo filter if you need deletion, or rebuild periodically). If
you have 100,000 possible IDs, skip the filter and cache the whole ID set in a Redis `SET`;
the Bloom filter is complexity you're not being paid for. Redis offers this natively via
`BF.ADD` / `BF.EXISTS` in the Bloom module.

**Avalanche.** The cause is nearly always operational rather than organic:

```
 A deploy runs a warm-up script:  for k in top_10000: SET k v EX 3600
 3,600 seconds later, 10,000 keys expire within the same millisecond.
 Origin load: 0 -> 10,000 concurrent queries. Instantly.

 Fix (one line):  EX int(3600 * (1 + uniform(-0.1, 0.1)))
 -> expiry spread over 720 seconds, ~14 queries/s instead of 10,000 at once.
```

### Enterprise production example

Rather than attribute a penetration incident to a company that hasn't published one, here
is a **realistic enterprise scenario**, clearly labelled as a scenario: a B2B SaaS exposes
`GET /api/v1/documents/{uuid}` behind a per-tenant cache. A customer's integration has a
bug and retries with a UUID that was deleted, at 400 requests per second per worker across
50 workers. Every request is a guaranteed cache miss on a UUID that will never exist, so
20,000 requests per second reach Postgres, each doing an index lookup that returns nothing.
The cache hit ratio dashboard looks fine — the denominator is dominated by legitimate
traffic — while `pg_stat_statements` shows one query at the top with a near-zero row count.
The fix is three lines: a negative cache entry with a 60-second TTL, UUID format validation
before the database call, and a per-tenant rate limit so one broken integration cannot
consume shared capacity. This shape of incident is common enough that negative caching
should be a default, not a reaction.

For the real-world use of the underlying technique: **Google's Bigtable** and **Apache
Cassandra** both maintain Bloom filters per SSTable so a read can skip files that
definitely do not contain the row key, which is the same "trust the negative" property
applied to disk seeks rather than database queries.

### Code

```python
NEG = b"\x00NULL"          # sentinel: distinguishes "known absent" from "not cached"
NEG_TTL, POS_TTL = 60, 3600

async def get_product(r, db, product_id: str):
    if not _UUID_RE.fullmatch(product_id):     # never let a malformed ID reach the DB
        raise HTTPException(400, "invalid product id")

    key = f"v1:product:{product_id}"
    cached = await r.get(key)
    if cached == NEG:
        raise HTTPException(404, "not found")  # free: no DB, no filter
    if cached is not None:
        return orjson.loads(cached)

    # Bloom filter: a negative answer here is trustworthy (no false negatives).
    if not await r.execute_command("BF.EXISTS", "bf:product_ids", product_id):
        await r.set(key, NEG, ex=NEG_TTL)
        raise HTTPException(404, "not found")

    row = await db.fetch_one("SELECT * FROM products WHERE id = :id", {"id": product_id})
    if row is None:                            # Bloom false positive, or a race
        await r.set(key, NEG, ex=NEG_TTL)
        raise HTTPException(404, "not found")

    await r.set(key, orjson.dumps(dict(row)),
                ex=int(POS_TTL * (1 + random.uniform(-0.1, 0.1))))   # jitter: no avalanche
    return dict(row)

async def create_product(db, r, row: dict):
    async with db.transaction():
        await db.execute("INSERT INTO products ...", row)
    await r.execute_command("BF.ADD", "bf:product_ids", row["id"])
    await r.delete(f"v1:product:{row['id']}")  # clear the negative entry, or the
                                               # creator's own read returns 404
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Negative caching — any public lookup by client-supplied ID | Absent-then-created must be visible instantly | Up to `NEG_TTL` of a stale 404 after a create, unless you invalidate on create |
| Bloom filter — key space is huge, misses dominate | Key space is small (just cache the ID set) | Memory, a false-positive rate, and no deletion without a counting/cuckoo variant |
| TTL jitter — always | Never | Nothing |
| Per-client rate limit — shared multi-tenant capacity | Single-tenant internal service | A limit to tune, and 429s a client must handle |

### Follow-ups they will ask

**Q: Explain the false-positive property and why it's safe.**
A: A Bloom filter can say "probably present" for something absent, but never "absent" for
something present, because insertion only ever sets bits. So the negative answer is
authoritative and I can return 404 on it without touching the database — which is the
direction that protects me. A false positive costs one wasted database lookup that returns
nothing, which is the behaviour I had anyway. The tunable is memory: 9.6 bits per element
buys 1 percent, 14.4 buys 0.1 percent.

**Q: When is a Bloom filter not worth it?**
A: When the key space is small enough to enumerate — under a few million IDs I'd just keep
a Redis `SET` and use `SISMEMBER`, which is exact, deletable, and simpler. Also when the
set churns heavily, since a plain Bloom filter can't delete and needs periodic rebuilds.
And if misses are rare, the filter adds a hop to every request to optimise a case that
doesn't happen. It earns its place at hundreds of millions of mostly-absent keys.

**Q: Distinguish avalanche from stampede.**
A: Stampede is one key, many concurrent readers, at one expiry instant — fixed by
coalescing so only one rebuild happens. Avalanche is many *different* keys expiring in the
same instant, usually because a deploy or warm-up populated them together with identical
TTLs — fixed by jittering TTLs so expiry spreads over a window. Coalescing does nothing for
avalanche because the requests are for different keys, and jitter does nothing for a single
hot key. Different bugs, similar-looking graphs.

**Q: You cached a 404 for 60 seconds and then the record is created. Now what?**
A: The creator's own read-after-write returns 404, which is a real bug and the reason the
create path must delete the negative entry in the same post-commit invalidation as any
other write. Belt and braces: keep the negative TTL short so an unrelated write path that
forgets self-heals in under a minute.

### Red flags — do not say this

- ❌ "The cache handles that." → ✅ "A cache can't help with requests for keys that don't
  exist — every one is a guaranteed miss. That needs negative caching and input validation."
- ❌ "Bloom filters can give wrong answers." → ✅ "Bloom filters have false positives but
  never false negatives, so 'absent' is trustworthy and that's the answer I act on."
- ❌ "Use a Bloom filter" (for a small key set) → ✅ "With only a few hundred thousand IDs
  I'd keep the set in Redis and use `SISMEMBER`, which is exact. A Bloom filter is for
  hundreds of millions of keys where memory is the constraint."

---

## 7.9 Redis in production

> **One-liner:** Redis is a single-threaded in-memory data structure server, which means
> one slow command blocks every other client, and almost every Redis incident traces back
> to somebody forgetting that.

### Say this in the interview

> The one fact that drives everything is that Redis executes commands on a single thread
> per instance. That's why it's fast — no locks, no context switching, atomic operations for
> free — and it's also why a single O(N) command is an availability incident. `KEYS *` on
> ten million keys, or `SMEMBERS` on a million-element set, blocks every other client for
> the duration. So I treat command complexity as a production concern: `SCAN` instead of
> `KEYS`, `HSCAN` instead of `HGETALL` on big hashes, and the slow log configured at ten
> milliseconds so I find out before customers do. On data structures, the ones that change
> designs are hashes for partial object reads, sorted sets for leaderboards and sliding
> window rate limiters, streams for a lightweight consumer-group queue, and HyperLogLog for
> unique counts at twelve kilobytes per counter with about 0.81 percent error, which is a
> genuinely different order of magnitude from a set. For persistence I need to know what I'm
> losing: RDB is a point-in-time fork-and-snapshot, so a crash loses everything since the
> last save, while AOF with `everysec` loses about a second. For high availability, Sentinel
> gives me automatic failover on a single dataset and Cluster gives me sharding across
> sixteen thousand three hundred and eighty-four hash slots — and Cluster is where multi-key
> operations break, unless I use hash tags in braces to force related keys into the same
> slot. Then pipelining to amortise round trips and Lua when I need read-modify-write to be
> atomic.

### Mental model

**Single-threaded, and what follows from it:**

```
      clients                    ONE event loop thread
   ┌──────────┐
   │ client A │──GET──┐        ┌──────────────────────────┐
   │ client B │──SET──┼───────>│ command 1 ─ command 2 ─ …│──> replies
   │ client C │──KEYS─┘        │  strictly serial          │
   └──────────┘                └──────────────────────────┘
                                      ▲
                        client C's KEYS * on 10M keys takes 3 s.
                        A and B wait 3 s. So does every health check.
                        p99 for the entire instance = 3 s.
```

Consequences to state out loud: every single command is atomic for free (no `WATCH`
needed for one command); a transaction (`MULTI`/`EXEC`) or a Lua script runs with nothing
interleaved; and command Big-O is a latency budget, not trivia.

**Command complexity that matters:**

| Safe | Dangerous | Instead |
|---|---|---|
| `GET`/`SET` O(1) | `KEYS pattern` O(N) over the whole keyspace | `SCAN` with a cursor and small `COUNT` |
| `HGET` O(1) | `HGETALL` O(N) on a large hash | `HMGET` for known fields, or `HSCAN` |
| `ZADD`/`ZSCORE` O(log N) | `SMEMBERS` O(N) on a big set | `SSCAN`, or `SRANDMEMBER` with a count |
| `ZRANGE k 0 99` O(log N + 100) | `ZRANGE k 0 -1` O(N) | Always bound the range |
| `EXPIRE`, `TTL` O(1) | `DEL` on a huge collection O(N) | `UNLINK` (frees on a background thread) |
| `SETRANGE`, `INCR` O(1) | `FLUSHALL` on a big keyspace | `FLUSHALL ASYNC` |

**Data structures that change a design:**

```
 STRING      GET/SET/INCR. Serialized blobs, counters, locks (SET NX PX).
 HASH        Partial reads of an object: HGET user:42 email. Small hashes are
             ziplist-encoded, so they are also very memory-efficient.
 SORTED SET  Score-ordered. Leaderboards (ZREVRANGE), sliding-window rate
             limiters (score = timestamp, ZREMRANGEBYSCORE to trim),
             delay queues (score = run_at, ZRANGEBYSCORE 0 now).
 LIST        LPUSH/BRPOP as a simple work queue. No consumer groups, no
             replay, no ack. Fine for fire-and-forget, not for reliability.
 SET         Membership, SINTER for "mutual followers". SISMEMBER is O(1).
 STREAM      Append-only log with consumer groups, XACK, XPENDING, XAUTOCLAIM.
             A real at-least-once queue inside Redis. See Module 08.
 HYPERLOGLOG PFADD/PFCOUNT. Cardinality in ~12 KB per counter at ~0.81%
             standard error, regardless of whether you count 1k or 1e9 items.
             PFMERGE unions them, so daily counters roll up into monthly.
 GEO         GEOADD/GEOSEARCH — a sorted set with geohash scores underneath.
 BITMAP      SETBIT/BITCOUNT. Daily-active flags: 1 bit per user per day.
```

The HyperLogLog trade is the memorable one: exact unique visitors for 100 million users
needs a set of roughly 100 million entries (gigabytes); HyperLogLog needs 12 KB and is
within about 1 percent. If the product question is "roughly how many unique viewers," you
were never being paid for exactness.

**Persistence — what each option loses:**

```
 RDB (snapshot)          fork() + write a compact point-in-time file.
                         LOSES: everything since the last save (e.g. up to 5 min).
                         COSTS: fork copy-on-write can transiently double memory.
                         GOOD FOR: backups, fast restarts (loads much faster than AOF).

 AOF (append-only file)  Append every write command; rewrite periodically to compact.
                         appendfsync always   -> loses ~0, very slow
                         appendfsync everysec -> loses ~1 s   (the sane default)
                         appendfsync no       -> loses up to ~30 s (OS flush)
                         COSTS: larger files, slower restart.

 Both                    Recommended for a datastore. For a pure cache, consider
                         neither: persistence buys nothing if you can refill from
                         the origin, and it costs fork pauses and disk IO.
```

Also worth saying: Redis replication is **asynchronous**. A primary can acknowledge a write
and fail before replicating it, and the promoted replica will not have it. `WAIT numreplicas
timeout` blocks until N replicas ack, which trades away the latency that made you choose
Redis. This is why "Redis as the source of truth for money" is a wrong answer.

**Sentinel vs Cluster:**

```
 SENTINEL                              CLUSTER
 ─────────                             ───────
 One dataset, one primary,             16,384 hash slots spread over N primaries,
 N replicas.                           each with replicas.
 Sentinels monitor + elect;            Nodes gossip; automatic failover per shard.
 clients ask Sentinel for the primary. Client is slot-aware and redirects on MOVED.
 Scales READS (replicas), not memory.  Scales memory and writes.
 Multi-key ops: all fine.              Multi-key ops: only within one slot.
 Use when: dataset fits one node.      Use when: it does not.
```

**Hash tags** are the escape hatch for Cluster's multi-key restriction. Redis hashes only
the substring inside `{}` when computing the slot:

```
  user:42:profile        -> slot A     ┐ different slots:
  user:42:sessions       -> slot B     ┘ MGET / MULTI / Lua across them = CROSSSLOT error

  {user:42}:profile      -> ┐
  {user:42}:sessions     -> ┴ same slot: multi-key ops and Lua work

  Cost: you have deliberately created a hot slot. Only group keys that must be
  operated on atomically, and never group by something coarse like {tenant:1}.
```

### Enterprise production example

**Netflix's EVCache** is the reference for what a cache tier looks like at the top end, and
it is instructive that they run memcached rather than Redis: per InfoQ's 2024 write-up of
their re:Invent session, roughly 200 clusters over 22,000 instances, about 2 trillion items,
14.3 PB, 400 million operations per second, p90 under 2 ms. The architectural detail worth
stealing is how they replicate across regions — not by Redis-style replication, but by
publishing mutations to Kafka and having a reader service per region apply them, with a
single Kafka cluster serving all 200-plus EVCache clusters and each cluster mapped to a
topic partitioned by event volume. They also report an interesting cost optimisation:
batching and compressing replication payloads to cut cross-region network spend. When
someone asks "how would you keep caches consistent across regions," "publish invalidations
to a log and let each region apply them" is a better answer than "replicate the cache," and
Netflix is the citation.

**Facebook's** memcached paper is the other essential citation, and the operational detail
most worth repeating is that they moved from TCP to UDP for `get` requests, accepting
dropped packets as cache misses, precisely because at their request volume the memory cost
of per-connection TCP buffers on the server was itself the scaling limit.

### Code

```lua
-- sliding_window.lua — atomic sliding-window rate limiter.
-- Demonstrates why Lua matters: check-then-act across 4 commands with zero
-- interleaving, on a single-threaded server, in one round trip.
-- KEYS[1] = "rl:{user:42}"   (braces = hash tag, so Cluster keeps it in one slot)
-- ARGV    = now_ms, window_ms, limit, unique_member
local now, window, limit = tonumber(ARGV[1]), tonumber(ARGV[2]), tonumber(ARGV[3])

redis.call('ZREMRANGEBYSCORE', KEYS[1], 0, now - window)   -- drop what aged out
local used = redis.call('ZCARD', KEYS[1])

if used >= limit then
  local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
  return {0, 0, math.ceil(tonumber(oldest[2]) + window - now)}   -- retry_after_ms
end

redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('PEXPIRE', KEYS[1], window)                     -- self-cleaning key
return {1, limit - used - 1, 0}
```

```python
import time, uuid
from redis.asyncio import Redis

class RateLimiter:
    def __init__(self, r: Redis, limit: int = 100, window_ms: int = 60_000):
        self.r, self.limit, self.window_ms = r, limit, window_ms
        self._script = None

    async def setup(self):
        with open("sliding_window.lua") as f:      # register once; EVALSHA thereafter
            self._script = self.r.register_script(f.read())

    async def check(self, user_id: int) -> tuple[bool, int, int]:
        allowed, remaining, retry_ms = await self._script(
            keys=[f"rl:{{user:{user_id}}}"],
            args=[int(time.time() * 1000), self.window_ms, self.limit, uuid.uuid4().hex],
        )
        return bool(allowed), remaining, retry_ms

async def batch_fetch(r: Redis, user_ids: list[int]) -> list[dict]:
    """Pipelining: 100 round trips at 0.5 ms each = 50 ms; pipelined = ~1 ms."""
    async with r.pipeline(transaction=False) as pipe:
        for uid in user_ids:
            pipe.hmget(f"v1:user:{uid}", "name", "email", "plan")   # not HGETALL
        return await pipe.execute()
```

```conf
# Production Redis config for a cache. The lines that prevent incidents.
maxmemory 24gb
maxmemory-policy allkeys-lru        # NOT the default; see 7.5
slowlog-log-slower-than 10000       # microseconds: log anything over 10 ms
slowlog-max-len 512
timeout 300                         # reap idle clients
tcp-keepalive 60
appendonly no                       # a pure cache: refill from origin, skip fork pauses
save ""                             # disable RDB too, for the same reason
lazyfree-lazy-eviction yes          # free big objects off the main thread
lazyfree-lazy-expire yes
rename-command KEYS ""              # remove the footgun entirely
rename-command FLUSHALL ""
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Redis for cache, counters, rate limits, leaderboards, locks, ephemeral queues | As the durable source of truth for money or orders | Async replication can lose acknowledged writes |
| Sentinel | You need more memory or write throughput than one node gives | Scales reads only; failover takes seconds and needs client support |
| Cluster | Dataset fits one node comfortably | Multi-key ops restricted to one slot; resharding is an operation, not a config change |
| Lua for atomic read-modify-write | The script is long or slow | It blocks the single thread for its whole duration — Lua is a critical section |
| Pipelining | You need each reply before deciding the next command | Loses request-per-response semantics; batch errors need per-command handling |
| Streams as a queue | You need Kafka-scale retention or replay across weeks | Memory-bound; see [Module 08](./08_Messaging_And_Events.md#84-message-brokers-compared) |

### Follow-ups they will ask

**Q: Why is `KEYS` dangerous, and what do you use instead?**
A: Redis is single-threaded, so `KEYS pattern` scans the entire keyspace on the one thread
that serves everybody. On ten million keys that's seconds during which every other client —
including health checks — is blocked, so the whole instance's p99 becomes the duration of
that one command. I use `SCAN` with a cursor and a small `COUNT`, which is incremental and
interleaves with other commands. In production I `rename-command KEYS ""` so nobody can do
it by accident.

**Q: RDB or AOF, and what do you lose?**
A: RDB forks and writes a point-in-time snapshot, so a crash loses everything since the
last save — up to five minutes with the default schedule — and the fork can transiently
double memory via copy-on-write. AOF appends every write; with `appendsync everysec` you
lose about a second, at the cost of larger files and slower restarts. For a datastore I run
both. For a pure cache I often run neither, because I can refill from the origin and
persistence just buys me fork pauses and disk IO.

**Q: How do you do a multi-key operation in Redis Cluster?**
A: Only if the keys are in the same hash slot, otherwise you get `CROSSSLOT`. I force that
with a hash tag — Redis hashes only what's inside `{}`, so `{user:42}:profile` and
`{user:42}:sessions` land in the same slot and `MGET`, `MULTI` and Lua work across them.
The cost is that I've deliberately created a hot slot, so I only group keys that genuinely
need atomicity together and never group by something coarse like tenant.

**Q: `MULTI`/`EXEC` or Lua?**
A: Lua, when the logic depends on what it reads. `MULTI`/`EXEC` queues commands and runs
them atomically but cannot branch on an intermediate result — you'd need `WATCH` and an
optimistic-retry loop. A Lua script runs atomically *and* can compute, so read-modify-write
is one round trip with no retry. The caveat is that the script is a critical section on the
single thread, so it must be short.

**Q: Redis Sentinel promotes a replica. What can you lose?**
A: Any write the old primary acknowledged but hadn't replicated, because replication is
asynchronous. There's also a split-brain window where the old primary is still accepting
writes before it learns it's been demoted — bounded with `min-replicas-to-write` and
`min-replicas-max-lag`, which make the primary refuse writes when it can't see enough
replicas. It's a real trade-off, and it's the reason Redis isn't the ledger.

**Q: What do you monitor?**
A: Hit ratio from `keyspace_hits`/`keyspace_misses`, evicted keys, `used_memory` against
`maxmemory`, `mem_fragmentation_ratio`, `connected_clients` against `maxclients`, blocked
clients, replication lag in bytes, and the slow log. The composite alert that matters is
evictions rising while the hit ratio falls, which means I'm evicting the working set rather
than the tail.

### Red flags — do not say this

- ❌ "Redis is fast so command choice doesn't matter." → ✅ "It's single-threaded, so one
  O(N) command blocks every client. Command complexity is a latency budget."
- ❌ "Redis is multi-threaded now so this is fine." → ✅ "Redis 6+ threads I/O reads and
  writes, but command *execution* is still one thread. `KEYS` still blocks everything."
- ❌ "Redis persists to disk so it won't lose data." → ✅ "With AOF `everysec` I lose about
  a second on a crash; with RDB I lose up to the snapshot interval. And replication is
  async, so a failover can lose acknowledged writes."
- ❌ "I'll store the session and use `HGETALL`." → ✅ "`HMGET` for the fields I need.
  `HGETALL` is O(N) and I'd be paying for the whole object on every request."
- ❌ "Use Redis Cluster for high availability." → ✅ "Cluster is for sharding memory and
  writes. If one node holds the dataset, Sentinel gives me HA with far less operational
  complexity."

---

## 7.10 Distributed cache consistency

> **One-liner:** The cache and the database are two systems with no shared transaction,
> so every write is a dual write — and the pragmatic answer is cache-aside with
> delete-after-commit plus a TTL, not a distributed transaction.

### Say this in the interview

> Writing to the database and updating the cache is a dual write across two systems with
> no shared transaction, so there is no ordering I can choose that is correct in every
> interleaving. What I can do is choose the failure mode. I use cache-aside with
> delete-after-commit: commit the transaction, then delete the key. If the delete fails or
> the process dies in between, the cache is stale until its TTL, which is a bounded,
> self-healing, read-only error. Compare that with the alternatives: updating the cache
> instead of deleting can leave it permanently wrong if two writers interleave, and
> invalidating inside the transaction means a rollback has already destroyed cache state
> and, worse, a reader can refill from data that never committed. When that TTL window is
> too wide, I stop making it the application's job and derive invalidation from the
> database's write-ahead log with CDC — Debezium reading the Postgres replication slot and
> publishing to Kafka, with a consumer that deletes cache keys. That's strictly better in
> three ways: it cannot fire before the commit because it reads committed changes, it
> cannot be forgotten by a new write path or a batch migration, and the events carry an
> LSN so I can version keys and reject out-of-order writes. The cost is real operational
> surface — a connector, a replication slot that will fill your disk if the consumer stalls,
> and lag to monitor. And the read-modify-write race stays regardless: if I read a counter
> from cache, add one, and write it back, two concurrent requests lose an increment, so
> counters belong in Redis with `INCR` or in the database with an atomic update, never in a
> read-modify-write cycle through a cache.

### Mental model

**All four orderings are wrong somewhere.** This is the honest framing:

```
 (a) update DB, then DEL cache      <- the pragmatic default
     fails if: process dies between the two -> stale until TTL (bounded, read-only)
     also: the 7.3 stale-set race, unless leases/versioning

 (b) DEL cache, then update DB
     fails if: a reader refills with the OLD value after the DEL but before
     the commit -> stale until TTL, same cost, and now also a window where
     the cache is empty for no reason

 (c) update DB, then SET cache to the new value
     fails if: two writers reach the DB in one order and the cache in the
     other -> cache PERMANENTLY disagrees with the DB. Strictly worse.

 (d) DEL cache inside the transaction
     fails if: the tx rolls back -> you invalidated for nothing (cheap), but
     a reader can also refill from uncommitted state on some isolation
     levels -> a value that never existed, cached. Strictly worse.
```

Ranking: (a) is best, (b) is acceptable, (c) and (d) are bugs. And (a)'s failure mode has
the properties you want in an error — bounded in time, read-only, self-healing.

**CDC-driven invalidation.**

```
   FastAPI ──BEGIN; UPDATE; COMMIT──> Postgres
                                        │ WAL (committed changes only)
                                        ▼
                                    Debezium  (logical replication slot,
                                        │      plugin=pgoutput)
                                        ▼
                                     Kafka  topic: pg.public.users
                                        │  key = pk, value = before/after + LSN
                                        ▼
                            invalidation consumer
                                        │  DEL v3:profile:t{t}:u{id}
                                        ▼
                                      Redis
```

Why it is genuinely better, not just different:

1. **Cannot precede the commit.** The WAL contains committed changes, so the invalidation
   is causally after the write by construction.
2. **Cannot be forgotten.** A new service, an ad-hoc `UPDATE`, a data migration, a
   backfill script — all of them go through the WAL. Application-level invalidation only
   covers the code paths someone remembered.
3. **Carries a version.** Each event has an LSN, so you can store `(value, lsn)` and reject
   a write-back whose LSN is older than what's cached — which closes the 7.3 stale-set race
   without leases.

What it costs: Debezium plus Kafka Connect to run; a Postgres replication slot that
**retains WAL until consumed**, so a stalled consumer fills your primary's disk (this is the
outage everyone who runs CDC has had once); typically tens to hundreds of milliseconds of
lag, so it is not a read-after-write mechanism; and a mapping from table rows to cache keys
that must be kept in sync as the cache schema evolves.

**The read-modify-write race** — separate bug, commonly conflated:

```
 Request A                    Request B                  Cache
 GET views:9 -> 100                                      100
                              GET views:9 -> 100         100
 SET views:9 = 101                                       101
                              SET views:9 = 101          101   <- lost an increment
```

No TTL, invalidation strategy or CDC pipeline fixes this, because the bug is
non-atomic read-modify-write. Fixes: `INCR` in Redis (atomic, single-threaded); a Lua
script for anything more complex than an increment; `UPDATE ... SET n = n + 1` in the
database; or optimistic concurrency with a version column and a retry. The general
principle: never route a read-modify-write cycle through two systems.

### Enterprise production example

**Facebook** chose exactly the CDC approach for their primary invalidation path.
*Scaling Memcache at Facebook* describes `mcsqueal`, a daemon on each database that reads
committed SQL statements, extracts the cache keys to invalidate, batches them, and routes
deletes to memcached instances across clusters. Their stated reason maps precisely onto the
argument above: invalidations issued by the web server that performed the write are lost if
that server dies, and can race with the commit. Deriving invalidation from the commit log
makes it a property of the data change rather than something a code path has to remember.

**Netflix** solved the same problem for cross-region cache coherence with a log as well:
EVCache mutations are published to Kafka and applied per-region by a reader service, with
one Kafka cluster serving 200-plus EVCache clusters. The pattern is identical — put
invalidation on a durable, ordered log and let consumers apply it — and it is worth naming
both examples because it shows the pattern is not Postgres-specific.

### Code

```sql
-- Debezium-friendly: an explicit monotonic version makes cache writes CAS-able.
ALTER TABLE users ADD COLUMN version bigint NOT NULL DEFAULT 0;

CREATE OR REPLACE FUNCTION bump_version() RETURNS trigger AS $$
BEGIN
  NEW.version := OLD.version + 1;
  RETURN NEW;
END $$ LANGUAGE plpgsql;

CREATE TRIGGER users_version BEFORE UPDATE ON users
  FOR EACH ROW EXECUTE FUNCTION bump_version();
```

```python
# CDC invalidation consumer: the only component allowed to delete cache keys.
# Idempotent (DEL is), and ordered per key because Kafka partitions by the PK.
from confluent_kafka import Consumer

TABLE_TO_KEYS = {
    "public.users":    lambda r: [f"v3:profile:t{r['tenant_id']}:u{r['id']}",
                                  f"v3:usercard:t{r['tenant_id']}:u{r['id']}"],
    "public.products": lambda r: [f"v1:product:{r['id']}"],
}

async def run(consumer: Consumer, redis):
    while True:
        msg = consumer.poll(1.0)
        if msg is None or msg.error():
            continue
        ev = orjson.loads(msg.value())
        source, after = ev["source"], ev.get("after") or ev.get("before")
        keys = TABLE_TO_KEYS[f"{source['schema']}.{source['table']}"](after)
        # Delete the lease too: revokes any in-flight fill (see 7.3).
        await redis.delete(*keys, *[f"lease:{k}" for k in keys])
        consumer.commit(msg, asynchronous=False)   # at-least-once; DEL is idempotent
```

```python
# Never do read-modify-write through the cache.
await r.incr(f"views:{post_id}")                             # atomic, correct
await r.hincrby(f"stats:{post_id}", "views", 1)              # atomic, correct

# views = int(await r.get(k)); await r.set(k, views + 1)     # loses increments
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Cache-aside + delete-after-commit + TTL | You need read-after-write on the cache | A stale window if the process dies mid-way; the 7.3 stale-set race |
| CDC-driven invalidation | You can't operate Debezium/Connect, or you need sub-10 ms invalidation | Replication slot disk risk, connector ops, tens-to-hundreds of ms lag |
| Versioned CAS writes (store `(value, version)`) | The row has no monotonic version | A schema column or trigger; slightly more complex writes |
| Write-through | Read-after-write on the cache is a hard requirement | Cache on the write path: cache down = writes down |
| `INCR` / atomic DB update for counters | — always | Nothing; this is simply the correct primitive |

### Follow-ups they will ask

**Q: Why delete after the commit rather than before?**
A: Because the two failure modes are not symmetric. Deleting after means a crash in between
leaves a stale entry until TTL — bounded, read-only, self-healing. Deleting before means a
reader can refill from the pre-commit value in the window between the delete and the
commit, which produces the same staleness *plus* a pointless empty-cache window. Neither is
race-free, so I pick the one whose worst case is cheaper.

**Q: CDC gives you eventual consistency with tens of milliseconds of lag. When is that not good enough?**
A: Read-after-write for the user who just made the change. If someone edits their profile
and immediately reloads, CDC lag means they might see the old value, which reads as a bug
even though the system is behaving as designed. The standard fix is to bypass the cache for
the writer specifically — a short-lived "I just wrote this" marker keyed by session that
routes their reads to the primary for a few seconds — while everyone else gets the cached
path.

**Q: What's the operational risk of Debezium on Postgres?**
A: The replication slot. Postgres retains WAL until the slot's consumer confirms it, so if
Debezium or Kafka is down, WAL accumulates on the **primary's** disk and eventually fills
it, taking down the database that the cache was supposed to protect. So I alert on
`pg_replication_slots.confirmed_flush_lsn` lag in bytes, set `max_slot_wal_keep_size` so
Postgres will drop a hopelessly lagging slot rather than die, and treat resnapshotting as
a documented, rehearsed procedure.

**Q: Two requests increment a counter through the cache. What happens?**
A: Both read the same value, both add one, both write the same result, and one increment is
silently lost. This is a read-modify-write race and no invalidation strategy touches it. The
fix is to use an atomic primitive: `INCR` in Redis, a Lua script for anything conditional,
or `UPDATE ... SET n = n + 1` in Postgres. If the value must be both durable and hot, I
increment in Redis and flush aggregates to Postgres periodically, accepting bounded loss on
the counter but never on the record.

**Q: How would you keep caches consistent across two regions?**
A: Not by replicating the cache. I publish invalidation events to a log — Kafka or Pub/Sub
— and have a consumer in each region apply deletes locally, which is what Netflix does for
EVCache across four AWS regions. Each region's cache is independently correct-eventually,
there's no cross-region read on the hot path, and the log gives me ordering and replay. The
cost is cross-region lag, so I still keep TTLs as the backstop.

### Red flags — do not say this

- ❌ "I'll wrap the DB write and the cache update in a transaction." → ✅ "Redis isn't in
  the Postgres transaction. It's a dual write, so I pick the failure mode: delete after
  commit, TTL as the backstop, and CDC when the window is too wide."
- ❌ "Use a distributed transaction / two-phase commit between Redis and Postgres." → ✅
  "2PC across a cache and a database is the wrong tool — it takes a latency and
  availability hit to solve a problem a TTL already bounds."
- ❌ "CDC gives strong consistency." → ✅ "CDC gives *reliable* eventual consistency: the
  invalidation can't be forgotten or fire early, but there's still tens to hundreds of
  milliseconds of lag."
- ❌ "The cache and DB are eventually consistent, so it's fine." → ✅ "Eventually consistent
  bounded by the TTL, which is the number I'd tell the product owner. And read-modify-write
  through the cache is still wrong regardless — counters use `INCR`."

---

## 7.11 CDN

> **One-liner:** A CDN is a globally distributed reverse-proxy cache that terminates
> connections near the user, so it cuts round-trip time and origin load at the same time —
> and its hardest problem is the cache key, not the caching.

### Say this in the interview

> A CDN is a cache at the network edge. Anycast routing sends a user to the nearest point
> of presence, TLS terminates there instead of at my origin, and a hit is served from that
> PoP — so someone in Singapore gets 10 milliseconds instead of a 250 millisecond round
> trip to us-central1. Two effects, not one: lower latency and less origin traffic. What I
> spend the most care on is the cache key, because the default is the URL and that's usually
> wrong. Query parameters like UTM tags fragment one object into thousands of variants, and
> a careless `Vary: Cookie` makes every response unique per user, which means a zero
> percent hit ratio and a CDN bill for nothing. So I normalise the key: strip marketing
> parameters, whitelist the ones that actually change the response, and never vary on
> anything high-cardinality. On headers, I separate browser policy from edge policy —
> `Cache-Control` for the browser, `CDN-Cache-Control` (that's RFC 9213) or `Surrogate-
> Control` for the edge — so I can tell the edge to cache for a day while telling the
> browser to revalidate every minute, which gives me a high hit ratio and still lets me
> purge. That combination plus `stale-while-revalidate` and `stale-if-error` is the
> configuration I reach for on HTML and JSON, because the edge then serves stale during a
> refresh and during an origin outage, so no user ever waits on my origin and no user sees a
> 502 for content that's already in cache. Add an origin shield so misses from hundreds of
> PoPs collapse to one origin request — Cloudflare publishes a 60 percent or greater
> reduction in cache miss rate from their tiered cache. For private content, signed URLs
> with a short expiry and a path scope rather than putting auth logic at the edge.

### Mental model

```
   Singapore user                        Frankfurt user
        │ anycast: same IP, nearest PoP        │
        ▼                                      ▼
  ┌───────────────┐                     ┌───────────────┐
  │ PoP: SIN      │  HIT: 10 ms         │ PoP: FRA      │
  │ edge cache    │                     │ edge cache    │
  └───────┬───────┘                     └───────┬───────┘
          │ MISS                                 │ MISS
          └──────────────┬──────────────────────┘
                         ▼
              ┌────────────────────────┐
              │ ORIGIN SHIELD (1 PoP)  │  collapses misses from all PoPs
              │ upper-tier cache       │  + request coalescing
              └───────────┬────────────┘
                          │ MISS (one request, not 300)
                          ▼
              ┌────────────────────────┐
              │ ORIGIN (us-central1)   │
              │ Cloud Run / GKE / LB   │
              └────────────────────────┘
```

Without a shield, 300 PoPs each missing the same object means 300 origin requests for one
object. With a shield, one. This is why tiered caching moves the hit ratio so much: the
edge tier's hit ratio is limited by per-PoP traffic, while the shield sees the sum.

**What to cache and what not to:**

| Cache aggressively | Cache carefully | Never cache |
|---|---|---|
| Content-hashed JS/CSS/images (`immutable`, 1 year) | HTML with a short TTL plus `stale-while-revalidate` | Anything with a `Set-Cookie` you didn't intend to share |
| Fonts, video segments, downloads | Public JSON APIs, keyed on a normalised URL | Authenticated responses without identity in the key |
| Public product pages, docs, blog | Personalised pages via edge-side includes or a `Vary` on a *low-cardinality* segment | `POST`/`PUT`/`DELETE` responses |
| Signed media (short expiry) | Search results for popular queries | Anything where a stale read is a security issue (post-revocation authz) |

**The cache key and the `Vary` problem.** Default key is method plus host plus path plus
query string. Two ways that goes wrong:

```
 /product/9?utm_source=twitter&utm_campaign=spring
 /product/9?utm_campaign=spring&utm_source=twitter
 /product/9?fbclid=xyz
 /product/9
   -> four cache entries for one object. Hit ratio collapses, origin sees
      four times the misses. FIX: normalise — strip utm_*/fbclid/gclid,
      sort remaining params, whitelist only params that change the response.

 Vary: Cookie
   -> every distinct cookie value is a distinct cache entry. With a session
      cookie that is one entry per user: a 0% hit ratio, and you are paying
      the CDN to store garbage. FIX: never vary on Cookie. Vary on a
      low-cardinality derived header you set yourself, e.g.
      Vary: X-Device-Class   (values: mobile | desktop)
```

**Headers, with the separation of concerns that matters:**

```http
# Immutable, content-hashed asset. Never revalidated; that's the point.
Cache-Control: public, max-age=31536000, immutable

# HTML / JSON API. Browser revalidates often; edge holds it long and purges.
Cache-Control: public, max-age=60, stale-while-revalidate=300, stale-if-error=86400
CDN-Cache-Control: max-age=86400, stale-while-revalidate=600, stale-if-error=86400
Surrogate-Key: product-9 tenant-42            # tag-based purge (Fastly)

# Private, per-user. Browser may cache; shared caches must not.
Cache-Control: private, no-cache, must-revalidate

# Truly uncacheable.
Cache-Control: no-store
```

Directive meanings people get wrong: `no-cache` means "you may store it, but revalidate
before use" — it is *not* "don't cache"; `no-store` is "don't write it down at all";
`must-revalidate` forbids serving stale after expiry; `private` means "browser yes, shared
caches no." And `s-maxage` applies to shared caches but is honoured by browsers' notion of
shared caching too, which is why `CDN-Cache-Control` (RFC 9213, June 2022) exists — it
targets the CDN tier unambiguously and is supported by Cloudflare, Vercel and others, with
vendor prefixes like `Cloudflare-CDN-Cache-Control` available when you need per-CDN control.

**Purging: soft vs hard.**

```
 HARD purge   evict the object. Next request is a MISS -> origin.
              If the object is hot, you have created a stampede at every PoP.

 SOFT purge   mark stale. Next request is served STALE while the edge
              revalidates in the background. No origin spike, no user waits.
              Prefer this for hot objects; it is what stale-while-revalidate
              gives you on a schedule instead of on demand.

 Tag/surrogate-key purge   "purge everything tagged product-9" — one API call
              invalidates the product page, the listing pages it appears on,
              and the API response. This is the versioned-key idea (7.4) at
              the CDN layer, and it is why you should emit tags from day one.
```

**Signed URLs for private content.** Generate a URL with an expiry and a signature; the
edge validates the signature without calling your origin.

```
 https://cdn.example.com/docs/t42/report.pdf
     ?Expires=1735689600
     &Signature=<HMAC over path + expiry + optional client IP>
     &Key-Pair-Id=...

 Keep expiry short (minutes). The URL IS the credential: it will end up in
 browser history, in a Slack message and in an access log, so scope the
 signature to the exact path and never to a prefix you'd regret.
```

**A CDN in front of an API** is legitimate and underused, with conditions: only `GET` and
`HEAD`; a normalised cache key; short TTLs (5-60 s) with `stale-while-revalidate`; `Vary`
only on low-cardinality dimensions; and an explicit `no-store` on every authenticated
route, enforced by default rather than per-route, so a new endpoint is uncacheable until
someone deliberately opts it in. Even a 10-second TTL on a hot public endpoint collapses
10,000 requests per second to 0.1 origin requests per second per PoP, and the edge does
the request coalescing for you.

### Enterprise production example

**Cloudflare** publishes the number that justifies an origin shield: customers enabling
Tiered Cache "can achieve a 60% or greater reduction in their cache miss rate as compared
to Cloudflare's traditional CDN service." The mechanism is exactly the shield above — edge
data centres check an upper tier, and only the upper tier may talk to the origin. They also
made `stale-while-revalidate` fully asynchronous: previously the first request after expiry
blocked on the origin and that unlucky visitor got the revalidation latency, whereas now
that request triggers a background refresh and immediately receives the stale object with
an `UPDATING` status, with all subsequent requests also served from cache until the origin
responds. Three consequences they call out are worth repeating verbatim in an interview
because they are the reasons to configure it: no visitor waits on the origin when the asset
is already cached; every visitor gets the same response during revalidation; and the first
request is no longer exposed to origin timeouts or errors.

Request coalescing at the edge is worth naming per-vendor because it is on by default in
some and not others: Fastly coalesces by default, CloudFront coalesces concurrent requests
for the same key natively, and on Cloudflare upper-tier collapsing comes with Tiered Cache.
"Is coalescing on?" is a good question to ask about any CDN you inherit.

### Code

```nginx
# nginx as origin: emit browser policy and edge policy separately.
map $uri $cache_policy {
    ~^/static/.*\.[0-9a-f]{8,}\.(js|css|woff2|png|svg)$  "immutable";
    ~^/api/v1/public/                                     "shortlived";
    default                                               "private";
}

location / {
    # Normalise the cache key: drop marketing params before they fragment it.
    if ($args ~ (.*)(^|&)(utm_[^&]*|fbclid=[^&]*|gclid=[^&]*)(&|$)(.*)) {
        set $args $1$5;
    }

    add_header Vary "Accept-Encoding, X-Device-Class" always;   # NOT Cookie

    set $cc "private, no-cache, must-revalidate";
    set $cdn_cc "no-store";
    if ($cache_policy = "immutable") {
        set $cc "public, max-age=31536000, immutable";
        set $cdn_cc "max-age=31536000";
    }
    if ($cache_policy = "shortlived") {
        set $cc "public, max-age=60, stale-while-revalidate=300, stale-if-error=86400";
        set $cdn_cc "max-age=86400, stale-while-revalidate=600, stale-if-error=86400";
    }
    add_header Cache-Control     $cc     always;
    add_header CDN-Cache-Control $cdn_cc always;   # RFC 9213: targets the edge

    proxy_pass http://app;
}
```

```python
# FastAPI: cacheable by exception, never by default. One decorator, one policy.
from fastapi import Response

def public_cache(resp: Response, max_age: int, tags: list[str],
                 edge_max_age: int | None = None):
    edge = edge_max_age or max_age * 60
    resp.headers["Cache-Control"] = (
        f"public, max-age={max_age}, stale-while-revalidate={max_age * 5}, "
        f"stale-if-error=86400")
    resp.headers["CDN-Cache-Control"] = (
        f"max-age={edge}, stale-while-revalidate={edge // 10}, stale-if-error=86400")
    resp.headers["Surrogate-Key"] = " ".join(tags)   # enables soft, tag-scoped purge

@app.get("/api/v1/public/products/{pid}")
async def get_product(pid: str, response: Response):
    product = await load_product(pid)
    public_cache(response, max_age=60, tags=[f"product-{pid}",
                                             f"cat-{product['category_id']}"])
    return product

@app.middleware("http")
async def default_uncacheable(request, call_next):
    resp = await call_next(request)
    resp.headers.setdefault("Cache-Control", "private, no-store")   # safe default
    return resp
```

```python
# Soft purge on write: mark stale, don't evict. No origin spike on a hot object.
async def on_product_updated(pid: str, category_id: str):
    await fastly.purge_tag(f"product-{pid}", soft=True)   # serves stale + revalidates
    await fastly.purge_tag(f"cat-{category_id}", soft=True)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Static assets, public pages, media | Everything is per-user and uncacheable | Egress and request pricing; a purge pipeline to build |
| CDN in front of a public API (short TTL + SWR) | Responses are authenticated or personalised | Up to `max_age + swr` staleness; risk of a cache-key mistake leaking data |
| Origin shield / tiered cache | Traffic is concentrated in one region already | An extra hop on a miss; the shield PoP is a new dependency |
| Signed URLs for private content | Access rules are complex or change mid-session | The URL is a bearer credential and leaks into logs and history |
| Soft purge | You must guarantee the old bytes are gone (legal takedown, leaked secret) | Stale served during revalidation |

### Follow-ups they will ask

**Q: Your CDN hit ratio is 40 percent on an endpoint you expected to be 95. Where do you look first?**
A: The cache key. Almost always either query-parameter fragmentation — `utm_*`, `fbclid`,
random cache-busters, or the same parameters in different orders creating separate entries —
or a `Vary` on something high-cardinality like `Cookie` or a full `User-Agent`, which makes
nearly every response unique. I'd check the response headers next: an unintended
`Set-Cookie` makes most CDNs refuse to cache, and so does a missing or `private`
`Cache-Control`. Then TTLs: if `max-age` is 10 seconds and per-PoP traffic is thin, the
object expires before the second request arrives, which is what an origin shield fixes.

**Q: Soft purge or hard purge, and why?**
A: Soft by default. Hard purge evicts, so the next request at every PoP is a miss and a hot
object becomes a stampede at the origin — you deployed a fix and caused an outage. Soft
purge marks the object stale, so the edge serves stale immediately and revalidates in the
background: no origin spike and no user waits. I use hard purge only when the old bytes must
not be served at all, like a legal takedown or a leaked secret.

**Q: Can you put a CDN in front of an authenticated API?**
A: Only with the identity in the cache key, and I usually don't. The hit ratio per key
collapses because there's no sharing, so the benefit is small, while the downside is
catastrophic — one `Vary` mistake and you serve one user's data to another. What I do
instead is cache the public parts at the edge with a short TTL and compose the personalised
parts at the client or in the app, so the shared cache only ever holds shared data.

**Q: How do you handle a deploy so users don't get a mix of old and new assets?**
A: Content-hashed filenames with `immutable, max-age=31536000` on the assets, and a short
TTL on the HTML that references them. New HTML points at new hashed URLs, so old and new
assets coexist and a user mid-session keeps working from the old set. Nothing needs purging
— the asset URLs are immutable by construction — which also means a rollback is just
serving the old HTML again.

**Q: What does `stale-if-error` buy you that a retry doesn't?**
A: It converts an origin outage into stale content instead of a 502. If the origin returns
an error or times out and I have a cached copy within the `stale-if-error` window, the edge
serves the old bytes. Combined with a long window — I often use 24 hours — my site stays up
and readable through a full origin outage, degraded rather than down. A retry just means the
user waits longer for the same failure.

### Red flags — do not say this

- ❌ "A CDN caches static files." → ✅ "It's a distributed reverse-proxy cache. Static
  assets are the easy case; short-TTL public API responses with `stale-while-revalidate`
  are often the bigger win because they also protect the origin."
- ❌ "I'll set `Vary: Cookie` to keep users separate." → ✅ "That makes every response a
  unique cache entry and drives the hit ratio to zero. I keep authenticated responses out of
  the shared cache entirely and vary only on low-cardinality headers I set myself."
- ❌ "`no-cache` means don't cache it." → ✅ "`no-cache` means store it but revalidate
  before use. `no-store` means don't write it down."
- ❌ "We'll purge on every deploy." → ✅ "Content-hashed asset URLs mean nothing needs
  purging. For content changes I soft-purge by surrogate key, so the edge serves stale while
  it revalidates instead of stampeding my origin."

---

## 7.12 Object / blob storage

> **One-liner:** Object storage is a flat key-value store for bytes with HTTP semantics and
> eleven nines of durability, and the single most important thing to know is that your API
> server must never be in the data path for a large file.

### Say this in the interview

> Object storage — S3, GCS, Azure Blob — is a flat namespace of immutable-ish objects
> addressed by a key, not a filesystem. There are no directories; a slash is just a
> character in the key, and what looks like a folder is a prefix filter on a list
> operation. That matters because listing a prefix with millions of keys is a paginated
> scan, not an O(1) directory read, so I keep hot metadata in Postgres and treat the bucket
> as bytes. On consistency, S3 has provided strong read-after-write consistency for all
> GET, PUT and LIST operations since December 2020, in every region at no extra cost, so
> the old workarounds like S3Guard and EMRFS consistent view are gone — but cross-region
> replication is still asynchronous, which is a distinction interviewers like. The pattern
> I always reach for is the pre-signed URL upload: the client asks my API for permission,
> the API authorises, generates a signed PUT URL scoped to one exact object key with a
> fifteen minute expiry, and the client uploads straight to the bucket. My API never sees
> the bytes. If I proxied a 500 megabyte upload through FastAPI I'd hold a worker for
> minutes, burn egress twice, cap concurrency at a handful of uploads per pod, and turn a
> pod restart into a failed upload — for a request that does no business logic. Then the
> bucket write emits an event to Pub/Sub, a worker picks it up and does the slow work, and
> the client polls a status endpoint. Files over about a hundred megabytes go via multipart
> upload so parts retry independently and upload in parallel, and I set a lifecycle rule to
> abort incomplete multipart uploads after seven days because otherwise I pay for orphaned
> parts forever. That is exactly the shape of the document ingestion pipeline in Module 14.

### Mental model

```
 THE PATTERN — API never touches the bytes

  ┌────────┐  1. POST /uploads {filename, type, size}   ┌──────────────┐
  │ Client │ ─────────────────────────────────────────> │ FastAPI      │
  │        │ <───────────────────────────────────────── │ authorise,   │
  │        │  2. {signed PUT url, document_id}          │ insert row   │
  │        │                                            │ status=      │
  │        │                                            │ AWAITING     │
  │        │  3. PUT bytes (direct, may be 500 MB)      └──────┬───────┘
  │        │ ────────────────────────────┐                     │
  └───┬────┘                             ▼                     │ Postgres
      │                        ┌──────────────────┐            │
      │ 6. GET /documents/{id} │ GCS / S3 bucket  │            │
      │    -> status           └────────┬─────────┘            │
      │                                 │ 4. object.finalize   │
      │                                 ▼                      │
      │                         ┌───────────────┐              │
      │                         │ Pub/Sub / SQS │              │
      │                         └───────┬───────┘              │
      │                                 │ 5. pull              │
      │                                 ▼                      │
      │                         ┌───────────────┐              │
      └──────── status ─────────│ Worker: parse,│──────────────┘
                                │ chunk, embed  │  updates status
                                └───────────────┘
```

**Why the API must not proxy the bytes** — the arithmetic that ends the argument:

```
 Proxying a 500 MB upload through FastAPI:
   - one worker held for the entire upload: 500 MB at 10 Mbps = ~7 minutes
   - a pod with 4 workers supports 4 concurrent uploads. Not 400. Four.
   - egress paid twice: client -> pod, pod -> bucket
   - memory or disk spooling on the pod, plus a body-size limit to tune
   - a deploy or an OOM mid-upload fails the upload entirely
   - the load balancer's request timeout (often 60 s) kills it anyway

 Pre-signed PUT:
   - API request is ~5 ms of authorisation and one INSERT
   - concurrency is bounded by the bucket, which is effectively unbounded
   - resumable/multipart retries are the client's and the SDK's problem
   - the pod can be restarted mid-upload with no effect
```

**The model, precisely:**

```
 bucket:  globally unique namespace, a region, a storage class, a policy
 key:     "tenant/42/incoming/uuid/report.pdf" — one flat string.
          "/" is NOT a path separator to the store. There are no directories.
          Listing "tenant/42/" is a prefix scan, paginated, O(keys matched).
 object:  bytes + metadata + optional version. Overwrite = a new version
          (or a full replace if versioning is off). No partial in-place edits.
```

**Consistency today.** S3 has offered strong read-after-write consistency since 1 December
2020 for all GET, PUT and LIST operations, plus operations that change tags, ACLs or
metadata — all objects, all regions, no extra charge, no performance penalty. GCS has always
been strongly consistent for object reads and listings. What is still eventual: cross-region
replication, and some bucket-level configuration propagation. Know the date; it is a
credible detail, and "S3 is eventually consistent" is now simply out of date.

**Storage classes and lifecycle.** The cost lever people forget:

```
 GCS                   S3                        Use for
 ───                   ──                        ───────
 Standard              Standard                  active reads
 Nearline (~30d min)   Standard-IA               monthly access
 Coldline (~90d min)   Glacier Instant Retrieval  quarterly
 Archive  (~365d min)  Glacier Deep Archive      compliance, near-never

 Lifecycle policy — set this on day one, not after the first bill:
   30d  -> Nearline        90d -> Coldline        365d -> Archive
   abort incomplete multipart uploads after 7d   <- pure waste otherwise
   delete noncurrent versions after 90d          <- versioning is not free
```

The trap: minimum storage durations. Deleting a Coldline object after 10 days still bills
90 days, so a lifecycle rule that transitions objects you rewrite frequently can cost more
than Standard.

**Multipart upload.** Above roughly 100 MB, split into parts (5 MB minimum, except the
last), upload in parallel, retry parts independently, then complete with the list of ETags.
Benefits: parallelism, per-part retry instead of restarting a 5 GB upload after a network
blip, and no need to know the total size upfront. The cost is a state machine — an
initiated upload that is never completed or aborted keeps its parts and keeps billing,
which is why the abort-incomplete lifecycle rule is not optional.

**Event notifications.** The bucket is the trigger, which is what makes this pattern
reliable:

```
 GCS:  object.finalize -> Pub/Sub topic -> subscription -> worker (or Cloud Run)
 S3:   s3:ObjectCreated:* -> SQS / SNS / EventBridge / Lambda

 Properties to state:
  - at-least-once. The same event can arrive twice, so the worker must be
    idempotent — key the work on the object generation/version, not the name.
    See Module 09 - Idempotency.
  - never trust the notification payload for size or type; HEAD the object.
  - always route through a queue, not straight to a function, so you get
    retries, a DLQ and backpressure.
```

### Enterprise production example

**Amazon S3's** move to strong consistency, announced 1 December 2020, is the cleanest
real-world illustration of a consistency/performance trade-off being engineered away rather
than accepted. The AWS announcement is worth quoting because of what it rules out: all GET,
PUT and LIST operations became strongly consistent, applying "to all existing and new S3
objects," working "in all regions," "at no extra charge," with "no impact on performance"
and "no global dependencies." Werner Vogels' follow-up explains how: rather than bypassing
the metadata cache — which would have cost latency — they built a cache coherence protocol
using an in-memory "witness" component that acts as a read barrier, letting a read detect
whether its cached metadata is stale before serving it. The consequence for practitioners
was that Amazon EMR's `EMRFS Consistent View` and the open-source `S3Guard` layers, both of
which existed purely to paper over eventual consistency, became unnecessary. If an
interviewer asks about eventual consistency in object storage, this is the answer that shows
you have kept up.

**DoorDash's** Iguazu pipeline shows the downstream half of the pattern at scale: events land
in Kafka, Flink transforms them, and results are written to S3 for the data warehouse and
data lake alongside Redis for real-time features — with hundreds of billions of events per
day at a 99.99 percent delivery rate, and end-to-end latency to Snowflake reduced from about
a day to a few minutes. Object storage as the durable landing zone with a stream as the
transport is the standard shape, not an exotic one.

### Code

```python
"""Pre-signed upload. The API authorises and records; it never sees the bytes."""
import re
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from google.cloud import storage
from pydantic import BaseModel, Field

router = APIRouter()
_bucket = storage.Client().bucket("acme-uploads")

ALLOWED_TYPES = {"application/pdf", "text/csv", "image/png", "image/jpeg"}
MAX_BYTES = 200 * 1024 * 1024
_SAFE = re.compile(r"[^A-Za-z0-9._-]")

class UploadRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    content_type: str
    size_bytes: int = Field(gt=0, le=MAX_BYTES)

@router.post("/uploads", status_code=202)
async def create_upload(req: UploadRequest, user=Depends(current_user), db=Depends(get_db)):
    if req.content_type not in ALLOWED_TYPES:
        raise HTTPException(415, "unsupported content type")

    document_id = uuid4()
    # The tenant prefix IS the security boundary: the signature is bound to this
    # exact key, so a client cannot redirect the upload elsewhere.
    key = (f"tenant/{user.tenant_id}/incoming/{document_id}/"
           f"{_SAFE.sub('_', req.filename)}")

    url = _bucket.blob(key).generate_signed_url(
        version="v4",
        expiration=timedelta(minutes=15),
        method="PUT",
        content_type=req.content_type,           # client MUST match or the sig fails
        headers={"x-goog-content-length-range": f"1,{MAX_BYTES}"},   # enforced by GCS
    )

    await db.execute(
        """INSERT INTO documents (id, tenant_id, object_key, content_type,
                                  declared_size, status)
           VALUES (:id, :t, :k, :ct, :sz, 'AWAITING_UPLOAD')""",
        {"id": document_id, "t": user.tenant_id, "k": key,
         "ct": req.content_type, "sz": req.size_bytes})

    return {"document_id": document_id, "upload_url": url,
            "method": "PUT", "expires_in": 900,
            "required_headers": {"Content-Type": req.content_type}}
```

```python
"""Worker: triggered by the bucket event, idempotent on object generation."""
async def handle_object_finalize(event: dict, db, storage_client):
    key, generation = event["name"], int(event["generation"])

    blob = storage_client.bucket(event["bucket"]).get_blob(key)
    if blob is None or blob.generation != generation:
        return                                  # superseded by a newer write; drop it
    if blob.size > MAX_BYTES:                   # verify server-side, never trust the client
        await mark_rejected(db, key, "too large")
        return

    # Idempotency key = (object_key, generation). At-least-once delivery means this
    # handler WILL be called twice for the same object. See Module 09.
    claimed = await db.execute(
        """UPDATE documents SET status = 'PROCESSING', generation = :g
            WHERE object_key = :k
              AND (generation IS NULL OR generation < :g)
              AND status <> 'PROCESSING'
         RETURNING id""",
        {"k": key, "g": generation})
    if claimed is None:
        return                                  # a duplicate delivery: already handled

    await enqueue_parse_and_embed(document_id=claimed["id"], object_key=key)
```

```json
// GCS lifecycle policy. Set this on day one; it is the difference between a
// storage bill that grows linearly and one that grows quadratically.
{
  "lifecycle": {
    "rule": [
      {"action": {"type": "SetStorageClass", "storageClass": "NEARLINE"},
       "condition": {"age": 30, "matchesPrefix": ["tenant/"]}},
      {"action": {"type": "SetStorageClass", "storageClass": "COLDLINE"},
       "condition": {"age": 90, "matchesPrefix": ["tenant/"]}},
      {"action": {"type": "AbortIncompleteMultipartUpload"},
       "condition": {"age": 7}},
      {"action": {"type": "Delete"},
       "condition": {"age": 30, "matchesPrefix": ["tenant/*/tmp/"]}},
      {"action": {"type": "Delete"},
       "condition": {"daysSinceNoncurrentTime": 90}}
    ]
  }
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Files, media, backups, model artifacts, data-lake landing zone | You need partial in-place updates or POSIX semantics | No random writes; overwrite is a whole new object |
| Pre-signed URLs for upload and download | The client cannot be trusted with a direct URL at all | The URL is a bearer credential; keep expiry short and the scope exact |
| Multipart upload above ~100 MB | Small files (the overhead dominates) | State to manage; orphaned parts bill until aborted |
| Event notification to a queue | You need ordered or exactly-once processing | At-least-once delivery: the worker must be idempotent |
| Lifecycle transitions to colder classes | Objects are rewritten or read often | Minimum storage durations and retrieval fees can exceed the savings |

### Follow-ups they will ask

**Q: Why not just upload through your API?**
A: Because it puts a worker in the data path for minutes. A 500 MB upload at 10 Mbps holds
one worker for about seven minutes, so a 4-worker pod supports four concurrent uploads, and
that request does no business logic — it's pure byte shuffling. On top of that I pay egress
twice, need spooling and body-size limits, my load balancer's 60-second timeout kills it
anyway, and a deploy mid-upload fails the user's upload. A pre-signed PUT makes it a 5 ms
authorisation call and moves the bytes to infrastructure built for bytes.

**Q: How do you stop a client abusing a pre-signed URL?**
A: Scope it narrowly and expire it fast. The signature is bound to one exact object key,
one HTTP method, and one `Content-Type`, with a 15-minute expiry, and I enforce a size
range server-side via `x-goog-content-length-range` (or a POST policy on S3) so a client
can't upload 50 GB against a URL I issued for 10 MB. The key includes the tenant prefix, so
even a leaked URL can only write to one object inside one tenant's namespace. I still verify
size and type server-side after the fact, because the only limits I trust are the ones the
storage service enforced.

**Q: Is S3 eventually consistent?**
A: Not since 1 December 2020. All GET, PUT and LIST operations, plus tag, ACL and metadata
changes, are strongly consistent — all objects, all regions, no extra cost, and Amazon
explicitly states no performance impact. That's why `S3Guard` and EMRFS consistent view
became unnecessary. What remains asynchronous is cross-region replication, so a read in the
replica region can lag.

**Q: The same event fires twice and your worker runs twice. What happens?**
A: With object-storage notifications that's expected, not exceptional — delivery is
at-least-once. So the worker keys its work on the object's generation or version ID and
claims it with a conditional `UPDATE ... WHERE generation < :g AND status <> 'PROCESSING'`.
A duplicate delivery updates zero rows and returns. Without that, a duplicate re-parses a
PDF and writes a second set of embeddings, and now the retrieval quality is quietly wrong.
See [Module 09 — Idempotency](./09_Reliability_Patterns.md#94-idempotency).

**Q: How do you list all files for a tenant?**
A: I don't list the bucket — I query Postgres, which holds one row per object with the
tenant, key, size, status and content type. Prefix listing is a paginated scan whose cost
grows with the number of matching keys, has no secondary indexes and no joins, and at a
million objects per tenant that's a slow, expensive, rate-limited operation. The bucket
stores bytes; the database stores what I need to search, sort and filter.

**Q: Where does this connect to your RAG pipeline?**
A: It is the front of it. Signed upload lands the document in the bucket, the
`object.finalize` event goes to Pub/Sub, a worker parses and chunks and embeds, and the
vectors go to the vector store while the status transitions on the Postgres row that the
client polls. The upload API returns 202 immediately, because parsing a 200-page PDF and
generating embeddings takes tens of seconds and no user should hold an HTTP connection for
that. Detail is in Module 14 — Document Ingestion.

### Red flags — do not say this

- ❌ "The client uploads to my API and my API writes it to S3." → ✅ "The client gets a
  pre-signed URL and uploads directly. My API never touches the bytes — otherwise one
  upload occupies one worker for minutes."
- ❌ "I'll create a folder per tenant in the bucket." → ✅ "There are no folders. It's a
  flat keyspace and the slash is just a character, so `tenant/42/...` is a key prefix. I
  keep the searchable metadata in Postgres."
- ❌ "S3 is eventually consistent, so I'll add a retry loop after upload." → ✅ "S3 has been
  strongly consistent for GET, PUT and LIST since December 2020. The retry loop is dead code
  now; cross-region replication is still async."
- ❌ "I'll store the uploaded file in Postgres as a `bytea`." → ✅ "Blobs go in object
  storage and the row holds the key. Large objects in Postgres bloat backups, WAL and the
  buffer pool, and you lose CDN offload."
- ❌ "Object storage is cheap so we don't need lifecycle rules." → ✅ "Standard-class storage
  for cold data plus orphaned multipart parts plus retained noncurrent versions is how a
  storage bill triples. Lifecycle rules go in with the bucket."

---

## Module 07 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Your endpoint does 10,000 reads per second at a 90 percent hit ratio. Quantify the
   effect on the database of getting to 99 percent, and explain why that number is
   non-linear.
2. Name a case where adding a cache is the wrong engineering decision, and give the
   arithmetic that proves it.
3. Draw the exact interleaving by which a concurrent read and write in naive cache-aside
   leaves a stale value cached for a full TTL. Then give two different fixes and say which
   one Facebook shipped.
4. Why delete the cache key instead of updating it with the new value? Give the two-writer
   scenario.
5. What is Redis's default `maxmemory-policy`, what happens when you hit `maxmemory` with
   it, and what would you set for a pure cache?
6. Describe a case where `allkeys-lfu` beats `allkeys-lru`, and the cost of choosing LFU.
7. A single key is expiring at 5,000 requests per second with a 300 ms rebuild. Walk the
   failure timeline, then list every mitigation and say which one means no user ever waits.
8. One Redis shard is at 100 percent CPU and the other nineteen are idle. What is
   happening, why does adding nodes not help, and what do you do first?
9. Distinguish cache stampede, cache penetration and cache avalanche by cause and by fix.
10. Explain the Bloom filter false-positive property and why it makes the negative answer
    safe to act on. How many bits per element for 1 percent?
11. Why is `KEYS *` an availability incident rather than a slow query? What do you use
    instead, and how do you prevent someone running it?
12. Your CDN hit ratio is 40 percent when you expected 95. List the four things you check,
    in order.
13. Why must the API server never proxy a 500 MB upload? Give the concurrency arithmetic.
14. A bucket event fires twice for the same object. What must the worker do, and what is the
    idempotency key?

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Redis GET, same VPC | ~0.3-1 ms; sub-millisecond p99 |
| In-process L1 cache hit | ~50-500 ns (no network) |
| Indexed Postgres query, warm buffer pool | ~1-5 ms; 5-50 ms if it touches disk |
| CDN edge hit vs cross-continent origin | ~10-30 ms vs ~150-250 ms |
| Origin load reduction: 90% → 99% hit ratio | 10x (miss rate 10% → 1%) |
| Origin load reduction: 99% → 99.9% | another 10x |
| Hit-ratio ceiling at N reads per key per TTL | (N−1)/N — N=10 gives 90% max |
| Facebook memcached lease token rate | one per key per 10 seconds |
| Facebook: peak DB QPS on herd-prone keys, without vs with leases | 17,000/s → 1,300/s |
| Facebook gutter pool size | ~1% of memcached servers |
| Netflix EVCache scale | ~200 clusters, 22,000 instances, 400M ops/s, ~2T items, 14.3 PB |
| Netflix EVCache p90 latency / cross-region replication | <2 ms / 30M events per second |
| Redis `maxmemory-samples` default (and near-exact LRU) | 5 (10 approximates true LRU; max 64) |
| Redis `lfu-log-factor` / `lfu-decay-time` defaults | 10 / 1 minute |
| Redis OSS default `maxmemory-policy` | `noeviction` — writes fail at the limit |
| Redis Cluster hash slots | 16,384 |
| HyperLogLog memory and error | ~12 KB per counter, ~0.81% standard error |
| AOF `appendfsync everysec` data loss on crash | ~1 second |
| Bloom filter bits per element | 9.6 at 1% FPR (7 hashes); 14.4 at 0.1% (10 hashes) |
| Bloom filter for 100M IDs at 1% | ~120 MB vs ~1.6 GB to store the keys |
| Cloudflare Tiered Cache cache-miss reduction | 60% or greater |
| XFetch refresh condition | `now − delta × beta × ln(rand()) ≥ expiry`, beta default 1.0 |
| S3 strong read-after-write consistency since | 1 December 2020, all regions, no extra cost |
| Multipart upload minimum part size | 5 MB (except the final part) |
| Abort-incomplete-multipart lifecycle rule | 7 days |
| Suggested pre-signed URL expiry | 15 minutes |
| Shopify BFCM scale-test peak | 146M requests/min at p90; 200M requests/min at p99 |
| Discord fan-out at 100k online users, one message each | ~10 billion notifications |

---

**Next:** [Module 08 — Messaging, Kafka & Event-Driven Architecture](./08_Messaging_And_Events.md)
