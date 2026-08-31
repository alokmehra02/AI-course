# Module 04 — Scaling, Load Balancing & Stateless Services

> **What this module makes you able to do:** take any single-instance design and scale it
> horizontally on the whiteboard — correctly identifying what state has to move out,
> which load-balancing algorithm to name and why, how health checks should be wired so
> they don't take down the fleet, and where the single points of failure still are after
> you've "added redundancy".
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** Module 02 — Networking & HTTP, Module 03 — API Design

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 4.1 | Vertical vs horizontal scaling | ★★★★☆ |
| 4.2 | Stateless services | ★★★★★ |
| 4.3 | Load balancing algorithms | ★★★★★ |
| 4.4 | L4 vs L7 load balancing | ★★★★☆ |
| 4.5 | Load balancer topology | ★★★★☆ |
| 4.6 | Health checks | ★★★★★ |
| 4.7 | Consistent hashing | ★★★★☆ |
| 4.8 | Autoscaling | ★★★★☆ |
| 4.9 | Single Point of Failure (SPOF) | ★★★★★ |
| 4.10 | Capacity planning & headroom | ★★★★☆ |

---

## 4.1 Vertical vs horizontal scaling

**Interview weight:** ★★★★☆

> **One-liner:** Vertical scaling buys you time and simplicity with a hard ceiling and a
> single failure domain; horizontal scaling buys you unbounded capacity and availability
> at the price of every distributed-systems problem in this document.

### Say this in the interview

> The instinct is to say "scale horizontally," but the senior answer depends on what's
> actually saturated. Vertical scaling — bigger machine — is genuinely the right call more
> often than people admit, because a single cloud VM now goes to hundreds of vCPUs and
> multiple terabytes of RAM, and one big Postgres primary at 96 cores will out-perform a
> badly sharded cluster while costing a fraction of the engineering time. What kills
> vertical scaling isn't performance, it's two other things: it has a ceiling you will
> eventually hit, and one machine is one failure domain, so resizing means a restart and a
> hardware failure means an outage. So the way I frame it is that horizontal scaling is
> what I do for *availability* and vertical scaling is what I do for *capacity*, and I
> almost always need a bit of both. For a stateless API service I go horizontal
> immediately because it's nearly free — the instances share nothing, so N instances
> behind a load balancer is a config change. For the database I go vertical first, then
> read replicas, then caching, and I only shard when I've genuinely exhausted a large
> primary, because sharding costs me cross-shard queries, rebalancing and distributed
> transactions. I'd add one economic point: cloud pricing is roughly linear per vCPU
> through the middle of the range but superlinear at the very top, so the last doubling of
> a machine can cost three or four times the previous one — that price curve, not a
> technical limit, is usually what actually forces the move.

### Mental model

```text
VERTICAL (scale up)                    HORIZONTAL (scale out)

  ┌────────┐      ┌──────────────┐       ┌────┐ ┌────┐ ┌────┐ ┌────┐
  │ 4 vCPU │  ──► │  64 vCPU     │       │ 4  │ │ 4  │ │ 4  │ │ 4  │
  │ 16 GB  │      │  512 GB      │       │vCPU│ │vCPU│ │vCPU│ │vCPU│
  └────────┘      └──────────────┘       └────┘ └────┘ └────┘ └────┘
                                                    ▲
  + no code change                           load balancer
  + no distributed problems                 + no ceiling
  + one thing to reason about               + failure of one ≠ outage
  − ceiling (a real, finite SKU)            + rolling deploys, canaries
  − resize = restart = downtime             − state must move OUT (4.2)
  − ONE failure domain                      − consistency, LB, discovery,
  − superlinear cost at the top               observability, coordination
```

**Where each one actually stops.** This is the part to be concrete about:

```text
Component        Vertical ceiling in practice      What forces horizontal
─────────────────────────────────────────────────────────────────────────
Stateless API    irrelevant — go horizontal        availability, not capacity
                 from instance #1                  (you want ≥2 always)
Postgres primary very high: a 64-96 vCPU box       write throughput, or the
                 handles tens of thousands of      restart/failover window
                 simple TPS comfortably            being unacceptable
Redis            single-threaded for commands, so   memory > one box, or one
                 more vCPUs ≠ more throughput       core saturated → cluster
                 past ~1 core of command work
Kafka / Pub/Sub  n/a — partitioned by design       partition count
Python worker    one process ≈ one core (GIL);     everything; CPU-bound
                 more RAM helps batching only      Python scales by processes
LLM inference    GPU memory is the hard wall       model won't fit, or QPS
```

The Redis row is the one that surprises people: Redis executes commands on a single
thread, so scaling the VM from 8 to 64 vCPUs does almost nothing for command throughput.
You scale Redis by adding memory (vertical, for capacity) or by sharding across a cluster
(horizontal, for throughput) — a good detail to have ready.

### Enterprise production example

**Stripe** ran its core product on a Ruby monolith for over a decade while processing
payments for millions of businesses — a deliberate choice to scale the *deployment*
horizontally (many identical instances of one application) rather than decompose into
services. **Shopify** is the other well-documented version: they scaled a monolith by
running it as many stateless instances and moving the hard problem into the data tier via
"pods" — self-contained shards each with their own database — rather than by breaking the
application apart. The pattern in both cases is the same and it's the one to name: scale
the stateless application layer out early because it's cheap, and defer the expensive,
irreversible decomposition of the data layer as long as you can.

Contrast that with the failure mode: a team that shards Postgres at 500 writes per second
"for scale" and then spends two quarters building cross-shard joins, a routing layer, and
a rebalancing tool — for a workload one 32-core primary would have served for years.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **Vertical:** databases, Redis memory, single-node caches, an early-stage system where engineering time is the scarce resource | You need availability during a single-machine failure, or you're already near the top SKU | A restart to resize; one failure domain; superlinear cost at the top of the range |
| **Horizontal:** stateless services, workers, anything you want ≥2 of for availability | The component holds state you haven't extracted yet | Load balancing, service discovery, distributed state, harder debugging |
| **Both:** vertical for the data tier, horizontal for the app tier | — | The normal answer; you own both sets of concerns |

### Follow-ups they will ask

**Q: Your API is at 80% CPU. Do you scale up or out?**
A: Out, and immediately — but first I'd check whether CPU is even the real constraint,
because for an I/O-bound FastAPI service at 80% CPU I'd suspect something specific like
JSON serialisation or synchronous crypto blocking the event loop, and one profile might
remove the need to scale at all. Assuming it's real, horizontal, because a stateless API
gets availability from replica count and I want to be running at 50-60% per instance
anyway so a single instance loss doesn't push the rest into the queueing regime (see
[4.10](#410-capacity-planning--headroom)).

**Q: When is vertical scaling the *better* senior answer?**
A: When the component is stateful and the alternative is sharding. A 96-vCPU Postgres
primary with read replicas will serve a workload that most teams believe requires
sharding, and it costs me a maintenance window instead of two quarters of engineering.
I'd also pick vertical for a Redis instance whose problem is dataset size rather than
command throughput, and for an in-process ML model where the constraint is fitting weights
in memory. The rule I'd state: scale vertically until the ceiling or the availability
requirement stops you, because every horizontal step in the data tier is close to
irreversible.

**Q: Doubling instance count doubles throughput. Is that true?**
A: Only until you hit the next shared resource, which is why I'd say it never holds for
long. The usual culprits are the database connection pool — 20 instances × 50 connections
is 1,000 connections against a Postgres `max_connections` of a few hundred, so the app
tier scales and the database falls over — plus a shared cache, a rate limiter, a NAT
gateway, or a downstream third-party quota. Amdahl's law is the general statement: the
serial fraction bounds your speedup. Practically, I size the connection pool to the
database's limit divided by expected instance count, and put a pooler like PgBouncer in
front so instance count and connection count are decoupled.

### Red flags — do not say this

- ❌ "Vertical scaling doesn't scale, so always go horizontal." → ✅ "Horizontal for
  availability and the stateless tier; vertical first for the data tier, because
  sharding is close to irreversible."
- ❌ "We'll shard the database to handle the load." (at modest write volume) → ✅ "A large
  primary plus read replicas plus caching gets me a long way; I'd shard only when I've
  actually saturated writes on a big box."
- ❌ "More instances means more throughput." → ✅ "Until the shared resource — usually the
  database connection pool — becomes the bottleneck, which is why I put a pooler in front
  and size pools to the database's limit."
- ❌ "Give Redis more CPUs." → ✅ "Redis runs commands on one thread; extra vCPUs don't help
  command throughput — I'd add memory, or shard."

---

## 4.2 Stateless services

**Interview weight:** ★★★★★

> **One-liner:** A stateless service is one where any instance can serve any request,
> because nothing a future request depends on lives only in this instance's memory or
> local disk.

### Say this in the interview

> Stateless doesn't mean the system has no state — it means the *service instance* holds
> no state that a subsequent request depends on. That's the property that makes horizontal
> scaling work, because it lets me add and kill instances freely, roll deploys, and route
> any request anywhere. The state hasn't disappeared; it moved to Postgres, Redis, object
> storage, or into the request itself as a signed token. For sessions I have three
> options, and I'd pick between them explicitly. Sticky sessions are the worst of the
> three: they work, but they break scaling, because when an instance dies its users lose
> their sessions, and load ends up unbalanced since the balancer is now honouring affinity
> rather than load. An external session store in Redis is my default — every instance
> reads the session by cookie ID, it survives instance death, and it costs about half a
> millisecond per request on the same VPC. Signed tokens like a JWT are the third option
> and they're genuinely stateless — no lookup at all — but revocation is now hard, because
> a token is valid until it expires, so I keep access tokens short-lived at five to fifteen
> minutes and pair them with a refresh token I *can* revoke. Then there's state that
> legitimately has to be stateful: a WebSocket connection is pinned to one instance by
> definition, and an in-memory cache or a loaded model is deliberately local. For those I
> don't pretend they're stateless — I make them *recoverable*: the client reconnects and
> re-subscribes, a connection registry plus a pub/sub fan-out means any instance can
> deliver a message to a user connected elsewhere, and a cold cache is a latency event
> rather than a correctness one.

### Mental model

**What "state" actually is.** Candidates say "session" and stop. The full list:

```text
Kind of state                       Why it breaks horizontal scaling
──────────────────────────────────────────────────────────────────────────
in-memory session / login           request 2 hits another instance → logged out
in-process cache                    N instances = N inconsistent copies
uploaded file on local disk         only 1 of N instances can serve it back
in-flight background task           instance dies mid-task → work silently lost
in-process scheduler / cron         N instances = the job runs N times
rate-limit counters in memory       real limit becomes N × intended limit
WebSocket / SSE connection          inherently pinned to one instance
loaded ML model / embeddings        fine to be local, but startup is now slow
local SQLite / local queue file     data is invisible to every other instance
sequence generators (i = i + 1)     duplicate IDs across instances
```

The test to say out loud: **"if I kill this instance mid-flight, does anything a future
request needs disappear?"** If yes, it isn't stateless.

```text
STATEFUL (broken)                     STATELESS (works)

  user ──► LB ──► inst A               user ──► LB ──► inst A ─┐
                   └ session in RAM              (any)  inst B ─┼──► Redis
  ✗ next request → inst B                        inst C ─┘     (sessions)
    → "please log in again"                              │
  ✗ inst A dies → those users               ──► Postgres (durable state)
    lose their carts                        ──► GCS/S3   (uploaded files)
  ✗ can't roll a deploy without             ──► Pub/Sub  (in-flight work)
    logging everyone out
                                        ✓ kill any instance, no user impact
                                        ✓ scale 3 → 30 → 3 freely
```

### Session handling — the three options, honestly

| | Sticky sessions | External store (Redis) | Signed token (JWT) |
|---|---|---|---|
| **How** | LB pins client → instance by cookie or source IP | session ID cookie → `GET session:{id}` | claims in the token, verified by signature |
| **Per-request cost** | zero | ~0.3-0.5 ms same-VPC Redis GET | ~10-50 µs signature verify |
| **Instance dies** | those users lose their session | no impact | no impact |
| **Load balance quality** | poor — affinity beats load; long-lived clients create hot instances | good | good |
| **Revocation** | immediate | immediate (`DEL session:{id}`) | **hard** — valid until `exp` |
| **Scale-in** | draining logs users out | free | free |
| **Payload size** | small cookie | small cookie | 300 B-2 kB on *every* request |
| **Extra failure mode** | none new | Redis is now in the auth path | a leaked token is valid until it expires |
| **Use when** | legacy app you can't change; short-lived sessions | default choice for web sessions | service-to-service auth, mobile, cross-domain, or you truly can't afford a lookup |

The JWT revocation problem, since interviewers push on it:

```text
Access token exp = 15 min, refresh token exp = 30 days (revocable, in Postgres)

  login ──► access(15m) + refresh(30d)
  api call ──► verify signature only, NO database read      ← the whole point
  t+15m ──► access expired → POST /token/refresh
                             ├─ refresh token revoked? → 401, force re-login
                             └─ else issue a new access token
  "log out everywhere" ──► DELETE the refresh tokens
                           → worst-case exposure = 15 minutes
```

That's the honest answer: JWTs don't give you revocation, they give you a *bounded window*
of stale authorization, and you choose the window. If a 15-minute window is unacceptable —
say, for an admin who was just fired — you need a denylist of revoked token IDs in Redis,
checked per request, at which point you've reintroduced the lookup you were avoiding.

### What legitimately stays stateful — and how to handle it

```text
1. WebSocket / SSE connections  (inherently pinned)

   user U's socket lives on instance B. An event for U originates on C.

   ┌────────┐   ┌────────┐   ┌────────┐
   │ inst A │   │ inst B │   │ inst C │  ← event for U happens here
   └────────┘   └───┬────┘   └───┬────┘
                    │ U's        │ publish to  ws:user:U
                    │ socket     ▼
                ┌───┴─────────────────────────┐
                │  Redis Pub/Sub  (or Pub/Sub) │  every instance subscribes
                └──────────────────────────────┘   to the channels for the
                    ▲ B receives it, writes         users IT holds
                      to the socket
   + any instance can originate; only the owner writes to the socket
   + connection registry in Redis: user → instance, with a TTL heartbeat
   − a deploy drops every connection: clients MUST reconnect with backoff
     + jitter and re-subscribe, and resume from a cursor (see Module 03 §3.3)


2. In-process cache (L1)  (deliberately local)

   Accept N inconsistent copies and bound the damage with a SHORT TTL
   (5-30 s) plus a Redis L2 behind it. Never try to invalidate N local
   caches synchronously — use a pub/sub invalidation message and treat
   it as best-effort.


3. Singleton work: schedulers, compactions, leader-only jobs

   Do NOT run cron in every replica. Elect a leader:
     · Kubernetes: a Lease object (the same primitive controllers use)
     · Postgres: SELECT pg_try_advisory_lock(job_id) — released on
       disconnect, so a dead pod can't hold it
     · Redis: a lease key with a TTL, renewed; accept that it is not safe
       under adversarial clock skew
   Or better: make the job idempotent and let it run N times harmlessly.


4. Loaded model weights / warm caches  (slow startup)

   The instance is stateless in the correctness sense but expensive to
   replace. Handle it with a startup probe and a generous
   initialDelay/failureThreshold so Kubernetes doesn't kill a pod that is
   legitimately loading 8 GB of weights, plus over-provisioning so a
   scale-out event isn't on the critical path. See 4.6 and 4.8.
```

### Enterprise production example

**Netflix's Zuul 2** is a precise example of the boundary between "stateless" and
"connection-bearing". Netflix's engineering blog explains that the whole point of the
async Netty rewrite was to let devices hold *persistent connections* back to their cloud
infrastructure — "more than 83 million members, each with multiple connected devices" at
the time of writing. Zuul carries no user session state, so any Zuul instance can serve
any request, but each instance owns the TCP connections currently attached to it. That's
the distinction to make: the *service* is stateless, the *connections* are not, and the
design consequence is that a Zuul deploy must drain connections gracefully and clients
must reconnect — which is exactly the recoverability pattern above.

**Scenario (labelled as a scenario, not a company claim):** a multi-tenant RAG API on GKE
loads a 2 GB embedding model per pod. Sessions live in Redis, uploaded documents in GCS,
job state in Postgres, so pods are fully replaceable — but a cold pod needs ~40 seconds
to load weights and warm its tokenizer. The fix isn't to make it stateless; it's a startup
probe with `failureThreshold: 30` at `periodSeconds: 5` (a 150-second budget), a readiness
probe that stays false until the model is resident, and enough headroom that a scale-out
event isn't blocking user traffic on a cold start.

### Code

Graceful shutdown is the part of statelessness people forget: an instance that dies
mid-request throws away work, so "stateless" also means "drains cleanly."

```python
# main.py — FastAPI: readiness flips false BEFORE the server stops accepting,
# so the load balancer removes us while we finish in-flight requests.
import asyncio, contextlib, signal
from fastapi import FastAPI, Response

class State:
    ready = False
    draining = False
    inflight = 0

state = State()

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.pool = await create_pg_pool(min_size=2, max_size=10)
    app.state.redis = await create_redis()
    await warm_caches(app.state)            # load model / prime local caches
    state.ready = True                      # only NOW do we accept traffic
    yield
    state.ready = False                     # readiness → 503 immediately
    state.draining = True
    # Give the LB/kube-proxy time to observe the readiness change and stop
    # routing. Without this window, requests arrive AFTER we start closing.
    await asyncio.sleep(5)
    deadline = asyncio.get_running_loop().time() + 25
    while state.inflight and asyncio.get_running_loop().time() < deadline:
        await asyncio.sleep(0.2)            # finish in-flight work
    await app.state.pool.close()
    await app.state.redis.aclose()

app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def track_inflight(request, call_next):
    if state.draining and not request.url.path.startswith("/healthz"):
        # Belt and braces: if something still routes to us, tell it to retry.
        return Response(status_code=503, headers={"Connection": "close",
                                                  "Retry-After": "1"})
    state.inflight += 1
    try:
        return await call_next(request)
    finally:
        state.inflight -= 1
```

Session in Redis, with the sliding expiry that people forget:

```python
SESSION_TTL = 3600 * 8

async def load_session(redis, sid: str) -> dict | None:
    raw = await redis.get(f"sess:{sid}")
    if raw is None:
        return None
    await redis.expire(f"sess:{sid}", SESSION_TTL)   # sliding window on read
    return json.loads(raw)

async def revoke_all_sessions(redis, user_id: str) -> None:
    # This is why you keep a per-user index: you cannot SCAN in production.
    sids = await redis.smembers(f"user_sessions:{user_id}")
    if sids:
        await redis.delete(*(f"sess:{s}" for s in sids), f"user_sessions:{user_id}")
```

Kubernetes side — `preStop` plus a grace period longer than your drain:

```yaml
spec:
  terminationGracePeriodSeconds: 45          # default is 30 — must exceed drain
  containers:
  - name: api
    lifecycle:
      preStop:
        exec:
          # Runs BEFORE SIGTERM. Buys time for endpoint removal to propagate
          # to every kube-proxy/LB before the process starts shutting down.
          command: ["/bin/sh", "-c", "sleep 10"]
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **Stateless + external store:** default for every HTTP service | Never — this is the baseline | A network hop per request to fetch state; the store is now in your critical path |
| **Sticky sessions:** legacy app you cannot modify | Anything you can change; anything that autoscales | Uneven load, session loss on instance death, painful deploys |
| **Signed tokens:** service-to-service, mobile, cross-domain | You need immediate revocation | No revocation inside the token lifetime; larger request headers |
| **Accepting stateful connections (WS):** real-time features | You can poll or use SSE with reconnect | Connection registry, pub/sub fan-out, reconnect logic, drain-aware deploys |

### Follow-ups they will ask

**Q: You said sticky sessions are bad. Give me the specific failure.**
A: Three. First, an instance dying takes its users' sessions with it — with 10 instances,
losing one logs out 10% of active users, which turns a routine deploy into a visible
incident. Second, affinity beats load: a client with a long-lived connection or a heavy
usage pattern stays pinned, so one instance runs hot while others idle, and the balancer
cannot correct it. Third, it breaks scale-in — draining an instance means either
terminating sessions or waiting for every pinned client to leave, which can be hours. If
I'm forced into stickiness I'd at least make it a *preference* rather than a requirement,
so failover to another instance degrades to a re-login instead of an error.

**Q: A WebSocket connection is inherently stateful. So how do you scale a chat service?**
A: I separate connection ownership from message routing. Each instance owns the sockets
currently attached to it and registers them — `HSET ws:registry {user_id} {instance_id}`
with a heartbeat TTL. When any instance needs to deliver to a user, it publishes to a
channel that user's owning instance is subscribed to, and the owner writes to the socket.
That way message *origination* is stateless and only the final write is pinned. The costs
I'd name: a deploy drops every connection, so clients need reconnect with backoff and
jitter plus a resume cursor; and the registry needs a TTL, because a hard pod kill leaves
a stale entry pointing at a dead instance.

**Q: How do you run a scheduled job without it firing once per replica?**
A: Preferably by making the job idempotent so N executions are harmless — that's more
robust than any election. When it genuinely must be a singleton, I'd use a Kubernetes
Lease, which is the same primitive the built-in controllers use, or
`pg_try_advisory_lock` in Postgres, which I like because the lock releases when the
connection dies, so a hard-killed pod can't hold it. A Redis lease with a TTL works too,
but I'd say out loud that it isn't safe under clock skew and network partitions, so I
wouldn't guard anything financial with it alone.

**Q: Is a JWT stateless if you check a revocation list on every request?**
A: No, and I'd say that plainly — you've reintroduced the lookup and now pay for both a
signature verification and a Redis read. The design question is what window of stale
authorization you can accept. Fifteen-minute access tokens with revocable refresh tokens
means a revoked user keeps access for at most fifteen minutes with zero per-request
lookups. If that's not acceptable, an opaque session ID in Redis is simpler and more
honest than a JWT plus a denylist.

**Q: What about local disk? Kubernetes gives me one.**
A: Treat the container filesystem as scratch only — temp files for the duration of one
request, and nothing a later request will look for. Anything durable goes to object
storage, ideally without passing through my process at all: I issue a signed upload URL so
the client uploads to GCS directly, and a storage event triggers the processing pipeline.
That keeps the API off the large-file path entirely, which also stops one 500 MB upload
from occupying a worker for a minute.

### Red flags — do not say this

- ❌ "Stateless means the app has no state." → ✅ "The *instance* holds no state a later
  request depends on; the state moved to Postgres, Redis and object storage."
- ❌ "Use sticky sessions so we don't need Redis." → ✅ "Sticky sessions lose sessions on
  instance death and unbalance load; a Redis session lookup is ~0.5 ms."
- ❌ "JWTs are stateless so they're better." → ✅ "They remove the lookup and give up
  revocation — I keep access tokens at 15 minutes and revoke the refresh token."
- ❌ "We store uploads on the pod's disk and serve them back." → ✅ "Only one of N
  instances could serve that file; uploads go to GCS via a signed URL."
- ❌ "We run the cron in every replica, it's fine." → ✅ "That's N executions — either the
  job is idempotent or I elect a leader with a Lease or an advisory lock."

---

## 4.3 Load balancing algorithms

**Interview weight:** ★★★★★

> **One-liner:** Round robin assumes every request and every server is identical; least
> connections tracks reality but needs global state; power-of-two-choices gets almost all
> of least connections' benefit by sampling two servers, which is why every sidecar and
> client-side balancer uses it.

### Say this in the interview

> The algorithm choice depends on whether requests are uniform and whether the balancer
> has global state. Round robin is the default and it's fine when requests cost roughly
> the same and servers are identical — but it fails badly with variable request cost,
> because it will happily hand a new request to the instance already grinding through a
> thirty-second export. Least connections fixes that by routing to the fewest in-flight
> requests, which is a good proxy for load, and it's what I'd pick when I have one
> load balancer with full visibility — HAProxy keeps servers in a sorted tree so finding
> the least loaded one is O(1) and it genuinely beats the alternatives. The interesting
> case is when I have *many* independent load balancers — sidecars, or gRPC client-side
> balancing — because then each one has only partial state, and true least-connections
> becomes actively harmful: every balancer independently sees the same instance as idle
> and they all pile onto it, which is a herd. That's where power-of-two-choices wins.
> Sample two backends at random, send the request to the less loaded of the two. It's
> O(1) state, and probabilistically the maximum load goes from growing logarithmically to
> growing double-logarithmically — an exponential improvement over pure random for
> essentially no cost. The reason it beats a greedy "always pick the global minimum" in a
> distributed setting is precisely that it's randomised, so independent balancers don't
> synchronise. And consistent hashing is the fourth option, but it's for a different goal
> — it's for cache affinity and sharding, not for balance, and I'd only reach for it when
> hitting the same backend for the same key actually buys me something.

### Mental model

```text
Round robin                Least connections           Power of two choices
                                                       (P2C / "random two")

A ──► req 1                A: ██ (2 in flight)         pick 2 at random:
B ──► req 2                B: ██████ (6)                 sample {C, A}
C ──► req 3                C: █ (1)      ◄── send        C=1, A=2 → send to C
A ──► req 4                D: ███ (3)
...                                                     O(1) state, no global
ignores actual load        needs GLOBAL in-flight       view needed, and no
                           counts per backend           herd across balancers
```

### The algorithms, and exactly when each fails

| Algorithm | How it picks | Fails when | Cost |
|---|---|---|---|
| **Round robin** | next in rotation | request costs vary; servers differ in size; a slow server keeps getting its share | O(1), no state |
| **Weighted RR** | rotation biased by static weight | weights are static — they don't notice a degraded server | O(1) |
| **Least connections** | fewest in-flight requests | many independent balancers (herding); long-lived connections make counts meaningless | O(1) with a sorted tree, but needs global state |
| **Weighted least conn** | in-flight ÷ capacity weight | same, plus you must maintain weights | O(1) + state |
| **Least response time** | lowest EWMA latency (× in-flight) | a *fast-failing* backend looks fastest — you route more traffic to the server that 500s in 2 ms | O(1) + latency tracking |
| **IP hash / consistent hash** | `hash(key) → backend` | it isn't a balancing algorithm — it optimises affinity and *accepts* imbalance; one hot key = one hot server | O(log V) |
| **Power of two choices** | sample 2 at random, take the less loaded | very small fleets (2-3 backends: sampling 2 ≈ picking all) | O(1), partial state |
| **Random** | uniform random | tail latency: max load grows ~log n / log log n | O(1), no state |

**Why P2C is near-optimal and cheap.** Two claims, both worth stating precisely:

```text
Classic result (Azar/Mitzenmacher, "the power of two choices"):
  n balls into n bins
    · pure random             → max bin ≈ Θ(log n / log log n)
    · sample d=2, take fewer  → max bin ≈ Θ(log log n / log d) + O(1)
  Going from 1 sample to 2 is an EXPONENTIAL improvement in the maximum.
  Going from 2 to 3 buys almost nothing — hence "two".

Distributed-systems result (the reason sidecars use it):
  With M independent load balancers and no shared state, a greedy
  "route to the global minimum" rule makes all M balancers choose the
  SAME idle backend simultaneously → thundering herd → that backend is
  now the most loaded → the herd moves. P2C's randomisation breaks the
  synchronisation, so M balancers spread naturally.
```

The honest counterpoint, which is what makes this a senior answer rather than a recited
fact: **with a single balancer that has full state, proper least-connections beats P2C.**
HAProxy's own benchmark of this found least-connections gave roughly 4% lower peak load,
4% higher request rate and 4% lower response times than power-of-two, because HAProxy
keeps backends in a sorted binary tree and so compares *all* servers, not two. Their
conclusion is worth quoting in an interview: use power-of-two as a better alternative to
round robin when a good least-connections implementation isn't available. So the rule is
about *state*, not fashion:

```text
one decider + full state          →  least connections
many deciders + partial state     →  power of two choices
                                     (Envoy, Linkerd, gRPC, Finagle all
                                      default to P2C for exactly this reason)
```

**Why "least response time" is a trap.** Say this if they ask what you'd avoid:

```text
Backend C's database connection pool is exhausted.
  → it returns 500 in 2 ms.
  → its EWMA latency is now the LOWEST in the fleet.
  → least-response-time routes MORE traffic to the broken backend.

Fix: weight by (latency × in-flight) and, critically, only count SUCCESSFUL
responses — or use outlier detection to eject a backend whose error rate
diverges from the fleet, which is what Envoy's outlier_detection does.
```

### Enterprise production example

**Vimeo** published the clearest production account of picking a load-balancing algorithm
for a real constraint. Their dynamic video packager, Skyfire, serves close to **a billion
DASH and HLS requests per day**, and they needed cache affinity — the same video segment
should reach the same backend so its cache is warm — without letting a popular video
overload one server. Plain consistent hashing gave them affinity but no protection from
hot keys; plain least-connections gave them balance but destroyed the cache hit rate.
They adopted **consistent hashing with bounded loads**: compute the average load, multiply
by a factor `c` to get a target, and if the hashed backend is already at capacity, walk
the ring to the next one. The result is that "no server can exceed its fair share of the
load by more than 1 request," while keys still land on their preferred backend whenever
that backend has room. Vimeo contributed the algorithm to **HAProxy**, where it's available
as a bounded-load option on hash-based balancing.

That example is worth memorising because it demonstrates the actual skill: they didn't
pick an algorithm from a list, they identified two conflicting requirements (affinity and
balance) and chose the algorithm that trades between them with a tunable knob.

### Code

Power-of-two-choices with EWMA latency and success-only accounting — the version you'd
actually ship in a client-side balancer:

```python
import random, time
from dataclasses import dataclass, field

@dataclass
class Backend:
    addr: str
    inflight: int = 0
    ewma_ms: float = 10.0          # optimistic start so new backends get traffic
    consecutive_failures: int = 0
    ejected_until: float = 0.0

class P2CBalancer:
    """Power-of-two-choices with EWMA latency and outlier ejection.
    O(1) per pick, no global coordination — safe to run one per client."""

    ALPHA = 0.2                    # EWMA smoothing
    EJECT_AFTER = 5                # consecutive failures
    EJECT_SECONDS = 30

    def __init__(self, backends: list[str]):
        self.backends = [Backend(a) for a in backends]

    def _live(self) -> list[Backend]:
        now = time.monotonic()
        live = [b for b in self.backends if b.ejected_until <= now]
        return live or self.backends       # fail OPEN: never return zero targets

    def pick(self) -> Backend:
        live = self._live()
        if len(live) == 1:
            return live[0]
        a, b = random.sample(live, 2)      # randomised: no herd across clients
        # Cost = queueing estimate. inflight+1 so an idle backend isn't 0-cost,
        # which would make every client pick the same one.
        cost = lambda x: (x.inflight + 1) * x.ewma_ms
        chosen = a if cost(a) <= cost(b) else b
        chosen.inflight += 1
        return chosen

    def complete(self, b: Backend, latency_ms: float, ok: bool) -> None:
        b.inflight -= 1
        if ok:
            # Only successful responses move the latency estimate. A backend
            # that fails in 2 ms must not look like the fastest one.
            b.ewma_ms += self.ALPHA * (latency_ms - b.ewma_ms)
            b.consecutive_failures = 0
        else:
            b.consecutive_failures += 1
            if b.consecutive_failures >= self.EJECT_AFTER:
                b.ejected_until = time.monotonic() + self.EJECT_SECONDS
```

The config equivalents, since in practice you configure rather than implement:

```nginx
# nginx: round robin is the default; least_conn for variable request cost.
upstream api {
    least_conn;
    server api-1:8000 max_fails=3 fail_timeout=10s;
    server api-2:8000 max_fails=3 fail_timeout=10s;
    server api-3:8000 backup;          # only used if all primaries are down
    keepalive 64;                      # reuse upstream connections
}
```

```yaml
# Envoy / Istio: P2C is the default, and it's the right default for a sidecar.
apiVersion: networking.istio.io/v1
kind: DestinationRule
spec:
  host: search-svc
  trafficPolicy:
    loadBalancer: { simple: LEAST_REQUEST }   # Envoy: P2C over 2 samples
    outlierDetection:                          # eject the fast-failing backend
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50                   # never eject more than half
```

Note `maxEjectionPercent: 50`. Without a cap, a dependency-wide failure ejects every
backend and you have zero targets — the same fail-open concern as health checks in
[4.6](#46-health-checks).

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **Round robin:** uniform request cost, identical servers | Mixed cheap reads and expensive exports on the same pool | Head-of-line: a slow request's server keeps receiving its share |
| **Least connections:** one balancer with full state, variable cost | Many independent balancers; long-lived connections | Global state; herding if replicated naively |
| **P2C:** sidecars, gRPC client-side LB, any distributed decider | Fleets of 2-3 backends | ~4% worse than a good centralised least-conn |
| **Consistent hash:** cache affinity, sharding, sticky routing | You need even load and have no hot-key protection | Accepts imbalance by design; add bounded loads |

### Follow-ups they will ask

**Q: Your fleet is behind round robin and p99 latency is terrible while mean is fine.
What's happening?**
A: Almost certainly heterogeneous request cost. Round robin gives every instance an equal
*count* of requests, not an equal amount of *work*, so an instance that catches two
30-second exports also gets its normal share of cheap reads, and those reads queue behind
the exports — that's pure head-of-line blocking and it shows up only in the tail. Two
fixes, and I'd do both: switch to least-connections or P2C so in-flight work influences
routing, and separate the expensive endpoints onto their own pool so a report can never
queue behind a health check or vice versa. The second matters more; algorithm choice can't
fully rescue a pool serving two workloads with 1000× different cost.

**Q: Why do Envoy, Linkerd and gRPC all default to power-of-two-choices instead of least
connections?**
A: Because in a mesh the decider is the sidecar or the client, so there are hundreds of
independent balancers each with only a local view. A greedy global-minimum rule makes them
all choose the same idle backend at the same moment, which converts an idle instance into
the hottest one and oscillates — a herd. P2C's randomisation is what prevents that
synchronisation, and it needs no shared state. If I had one centralised HAProxy with full
visibility I'd use least-connections instead, and HAProxy's own benchmarks show it's about
4% better in that setting.

**Q: When is `least_time` / least-response-time the wrong choice?**
A: Whenever a backend can fail fast. A pod with an exhausted connection pool returns 500 in
two milliseconds, so its latency average becomes the best in the fleet and the algorithm
sends it *more* traffic — it actively seeks out the broken instance. The mitigations are to
only feed successful responses into the latency estimate, and to run outlier detection so a
backend whose error rate diverges from its peers is ejected regardless of how fast it
answers.

**Q: Does the load-balancing algorithm even matter if you're autoscaling?**
A: They solve different problems on different timescales. Autoscaling changes total
capacity over minutes; load balancing distributes the current second's requests. If
distribution is bad, some instances saturate while the fleet average looks fine, so your
autoscaler — which usually reads the average — doesn't fire, and you get tail latency with
idle capacity sitting right there. So bad balancing actively defeats autoscaling. I'd also
watch per-instance utilisation spread, not just the mean, as a signal that the algorithm is
wrong.

**Q: You have a Redis cluster in front of Postgres and want cache affinity. Which
algorithm?**
A: Consistent hashing on the cache key, so the same key always reaches the node that holds
it — that's [4.7](#47-consistent-hashing). But I'd add bounded loads, because a single
viral key otherwise puts all of its traffic on one node. That's the exact trade Vimeo made
for Skyfire: hash for affinity, cap per-node load at a small multiple of the average, and
spill to the next node on the ring when the preferred one is full.

### Red flags — do not say this

- ❌ "I'll use round robin." (with no qualification) → ✅ "Round robin if request costs are
  uniform; least-connections or P2C once they aren't."
- ❌ "Least connections is always best." → ✅ "Best with one balancer that has full state;
  with many independent balancers it herds, which is why sidecars use P2C."
- ❌ "IP hash balances load." → ✅ "Hashing gives affinity and *accepts* imbalance — it's for
  cache locality or sharding, not for balance."
- ❌ "Route to the fastest server." → ✅ "A fast-failing backend looks fastest; I'd only count
  successful responses and add outlier ejection."
- ❌ "Power of two choices beats least connections." → ✅ "It beats a *distributed* greedy
  choice; a single HAProxy with a sorted tree beats P2C by about 4%."

---

## 4.4 L4 vs L7 load balancing

**Interview weight:** ★★★★☆

> **One-liner:** An L4 balancer forwards TCP connections without reading them — fast,
> cheap, protocol-agnostic; an L7 balancer terminates the connection and reads HTTP, which
> is what lets it route by path, retry, and rewrite, at the cost of CPU and a decrypt.

### Say this in the interview

> The distinction is whether the balancer parses your protocol. An L4 balancer works at
> TCP or UDP — it sees a five-tuple, picks a backend, and forwards packets or splices the
> connection. It can't route by URL path, can't retry a failed request, can't add a header,
> and can't do per-request load balancing, because it makes exactly one decision per
> connection. In exchange it's extremely cheap, it's protocol-agnostic so it handles
> anything TCP-based, and it can preserve the client's source IP. An L7 balancer terminates
> TLS, parses HTTP, and makes a decision per *request*, which is what unlocks
> path-based routing, header-based canaries, retries on 5xx, request buffering,
> compression, and per-request load balancing over HTTP/2 streams. The cost is real: it has
> to decrypt, which means the private key lives on the balancer and you burn CPU on the
> handshake, and it becomes a stateful HTTP participant with its own timeouts and buffers
> to tune. The rule I'd give is that anything HTTP-shaped wants L7, and the exception that
> matters is gRPC — a gRPC service behind an L4 balancer is a classic outage, because L4
> balances connections and gRPC multiplexes everything over one long-lived HTTP/2
> connection, so all your traffic pins to a single backend no matter how many replicas you
> add.

### Mental model

```text
L4 — one decision per CONNECTION                 L7 — one decision per REQUEST

 client                                           client
   │ TCP SYN                                        │ TLS handshake (terminated)
   ▼                                                ▼
┌──────────────┐  picks a backend from            ┌──────────────┐  reads:
│  L4 LB       │  (src_ip, src_port,              │  L7 LB       │  GET /v1/search
│  (Maglev,    │   dst_ip, dst_port, proto)       │  (Envoy,     │  Host: api...
│   NLB, IPVS) │  then forwards packets           │   ALB, GFE)  │  Cookie: ...
└──────┬───────┘  or splices the stream           └──────┬───────┘
       │ opaque bytes — TLS never opened                 │ new connection
       ▼                                                 │ (pooled/keepalive)
   ┌───────┐                                             ▼
   │backend│  TLS terminates HERE                   ┌───────┐
   └───────┘  (LB never sees the plaintext)         │backend│  plaintext or
                                                    └───────┘  re-encrypted
 ⚠ every request on that connection goes             ✓ req 1 → A, req 2 → B
   to the SAME backend, forever                      ✓ retry req on 5xx
                                                     ✓ route /v1/search → svc-a
```

### What each can and cannot do

| | L4 | L7 |
|---|---|---|
| **Sees** | IPs, ports, protocol | method, path, headers, cookies, body |
| **Decision granularity** | per connection | per request (per HTTP/2 stream) |
| **Route by URL path / host** | no | yes |
| **Header/cookie-based canary** | no | yes |
| **Retry a failed request** | no (can only reset the connection) | yes, with per-try timeouts |
| **Inject headers** (`X-Request-Id`, trace context) | no | yes |
| **TLS** | passthrough (backend terminates) | terminates (or re-encrypts to backend) |
| **Sees client source IP** | yes, natively preserved | no — needs `X-Forwarded-For` |
| **Works with non-HTTP** (Postgres, Redis, SMTP, QUIC) | yes | no |
| **gRPC / HTTP/2 balancing** | **no — pins to one backend** | yes, balances streams |
| **WebSocket** | yes (it's just TCP) | yes, with an upgrade-aware config |
| **Relative CPU cost** | very low; kernel/ASIC-level, millions of pps | higher: parse + decrypt + buffer |
| **Latency added** | tens of microseconds | ~0.5-2 ms typical |
| **Cloud examples** | GCP internal/external passthrough NLB, AWS NLB, IPVS | GCP external Application LB (GFE), AWS ALB, Envoy, nginx |

### TLS termination — the three shapes

```text
1. TLS passthrough (L4)
   client ══TLS══════════════════════════► backend
   + LB never holds the key; end-to-end encryption; simplest compliance story
   − LB can't route by path, can't inject headers, can't retry
   − every backend needs the cert and pays the handshake CPU

2. TLS termination (L7)
   client ══TLS══► LB ──plaintext──► backend
   + one place to manage certs and rotate them; handshake CPU centralised
   + full L7 routing, retries, header injection
   − plaintext on the internal network — only acceptable if that hop is
     itself trusted/isolated; a compliance question, not a technical one
   − the private key lives on the LB fleet

3. TLS re-encryption / "bridging" (L7)
   client ══TLS══► LB ══TLS(internal CA)══► backend
   + L7 features AND encryption in transit everywhere  ← usually the answer
   − two handshakes' worth of CPU; internal PKI to run (a mesh does this
     for you with mTLS — see 4.5)
```

**Cost difference, concretely.** A TLS 1.3 handshake is one round trip (TLS 1.2 is two)
plus an asymmetric operation that costs far more CPU than the symmetric encryption of the
rest of the session. That's why session resumption and connection keepalive matter more
than the cipher choice, and why an L7 balancer terminating millions of *new* connections
per second is a genuinely different cost profile from one serving long-lived keepalive
connections. In cloud pricing terms, L7 balancers generally bill on processed data plus
rule/route evaluations while L4 balancers bill closer to raw throughput — so a
high-bandwidth, low-logic path (video, bulk transfer) is materially cheaper at L4.

### Enterprise production example

**Google Cloud's** load-balancing stack is the cleanest illustration of the two layers
having different jobs. The global external Application Load Balancer is L7: it terminates
TLS at Google Front Ends distributed across the edge, so the handshake completes close to
the user and the long-haul leg to your backend rides Google's network. Behind it,
Google's L4 balancing uses **Maglev**, a software network load balancer whose defining
property is *consistent hashing over the backend set* — so when a Maglev instance is added
or removed, existing connections mostly keep landing on the same backend rather than being
reset. That's consistent hashing ([4.7](#47-consistent-hashing)) solving an L4 problem:
without it, scaling the balancer fleet would break in-flight connections.

**AWS's** equivalent split is worth knowing for contrast: NLB is L4, gives you a static IP
per availability zone, and preserves the client source IP; ALB is L7, is reached through a
DNS name whose records change as it scales, and requires you to read `X-Forwarded-For` for
the client IP. That DNS detail has caused real incidents — a client that caches DNS beyond
the record TTL keeps hammering ALB nodes that have been scaled away, so long-lived clients
must honour the TTL or re-resolve.

### Code

```yaml
# GKE: two Services for the same Deployment, one L7 and one L4, because they
# answer different questions.

# L7: path routing, TLS termination, per-request retries, canary by header.
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: api
  annotations:
    kubernetes.io/ingress.class: "gce"
    networking.gke.io/managed-certificates: "api-cert"
spec:
  rules:
  - host: api.acme.com
    http:
      paths:
      - path: /v1/search
        pathType: Prefix
        backend: { service: { name: search-svc, port: { number: 80 } } }
      - path: /v1/documents
        pathType: Prefix
        backend: { service: { name: doc-svc, port: { number: 80 } } }
---
# L4: a raw TCP path for a Postgres pooler — no HTTP semantics exist here,
# so an L7 balancer is not just unnecessary, it's impossible.
apiVersion: v1
kind: Service
metadata:
  name: pgbouncer
  annotations:
    networking.gke.io/load-balancer-type: "Internal"
spec:
  type: LoadBalancer
  externalTrafficPolicy: Local     # preserves client source IP; note this
  ports: [{ port: 6432, targetPort: 6432, protocol: TCP }]   # skips pods on
  selector: { app: pgbouncer }                                # nodes with none
```

The gRPC trap and its fix, in one place:

```yaml
# WRONG: gRPC behind an L4 Service. One HTTP/2 connection per client means
# every RPC from that client hits ONE pod. Add 10 replicas, 9 stay idle.
apiVersion: v1
kind: Service
metadata: { name: search-grpc }
spec:
  type: ClusterIP
  ports: [{ port: 50051, protocol: TCP }]
---
# RIGHT (option A): headless Service + gRPC client-side LB over all endpoints.
apiVersion: v1
kind: Service
metadata: { name: search-grpc-headless }
spec:
  clusterIP: None                 # DNS returns ALL pod IPs, not one VIP
  ports: [{ port: 50051, protocol: TCP }]
  selector: { app: search }
# client: grpc.insecure_channel("dns:///search-grpc-headless:50051",
#            options=[("grpc.lb_policy_name", "round_robin")])
#
# RIGHT (option B): a sidecar/mesh (Envoy) that balances HTTP/2 STREAMS,
# or GCP Traffic Director for proxyless gRPC xDS-based balancing.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **L4:** non-HTTP protocols, extreme throughput, source-IP preservation, TLS passthrough for compliance | HTTP traffic that needs path routing or retries; gRPC | No per-request decisions, no retries, no header injection |
| **L7:** any HTTP/gRPC API, canaries, retries, WAF, one place for certs | Raw TCP/UDP; ultra-high-bandwidth bulk transfer | ~0.5-2 ms, TLS CPU, key custody, more knobs to misconfigure |
| **L4 in front of L7:** the standard production shape | A single small service | Two tiers to operate (usually both managed, so: little) |

### Follow-ups they will ask

**Q: Why does gRPC break behind an L4 load balancer?**
A: Because L4 makes one routing decision per connection and gRPC deliberately multiplexes
every call over a single long-lived HTTP/2 connection. So the connection is assigned once,
and every RPC for the lifetime of that connection lands on the same pod — you can scale to
fifty replicas and one of them takes all the traffic. There are three fixes: gRPC's own
client-side load balancing against a headless service so the client sees every endpoint, an
L7 proxy like Envoy that balances individual HTTP/2 streams, or a control plane like
Traffic Director doing xDS-based balancing for proxyless gRPC.

**Q: You terminate TLS at the L7 balancer. Is plaintext to the backend acceptable?**
A: It depends entirely on the trust boundary, and I'd say that rather than picking a side.
Inside a single VPC with private subnets and no third-party tenancy, many organisations
accept it. For anything regulated, or a multi-tenant cluster, I'd re-encrypt to the
backend — which is exactly what a service mesh gives you for free via mTLS, and it also
gets you workload identity rather than just encryption. The middle option is TLS
passthrough, but that costs me all the L7 features I terminated for in the first place.

**Q: How does the backend know the real client IP behind an L7 balancer?**
A: `X-Forwarded-For`, and the important part is trusting it correctly. The header is
client-writable, so I must count from the *rightmost* entry inward and only trust as many
hops as I actually operate — otherwise a client sends a forged `X-Forwarded-For` and
spoofs their IP past my rate limiter and my audit log. In nginx that's `set_real_ip_from`
with the balancer's CIDR; in FastAPI it's `ProxyHeadersMiddleware` with `trusted_hosts`
set to the balancer, not `"*"`.

**Q: Which layer should terminate a WebSocket?**
A: Either works, but I'd terminate at L7 with an upgrade-aware config, because I still want
path routing and authentication on the initial HTTP upgrade request. The thing that
actually bites is timeouts: a WebSocket is a long-lived connection with potentially long
idle periods, and every default idle timeout in the path — balancer, proxy, ingress — will
kill it. So I set generous idle timeouts and send application-level pings well inside the
shortest one.

### Red flags — do not say this

- ❌ "L7 is better than L4." → ✅ "Different jobs: L4 for raw TCP throughput and source-IP
  preservation, L7 for anything needing path routing or retries."
- ❌ "We put the gRPC service behind the internal TCP load balancer." → ✅ "L4 pins one
  HTTP/2 connection to one pod — I need client-side LB or an L7 proxy that balances
  streams."
- ❌ "The load balancer retries failed requests." (of an L4 LB) → ✅ "L4 can only reset the
  connection; request-level retries need L7."
- ❌ "We read `X-Forwarded-For` for the client IP." → ✅ "I parse it right-to-left and only
  trust the hops I operate — otherwise it's spoofable."

---

## 4.5 Load balancer topology

**Interview weight:** ★★★★☆

> **One-liner:** Real systems have four or five layers of balancing — DNS, anycast global,
> regional, service-level, and client-side — each solving a different problem at a
> different timescale.

### Say this in the interview

> Load balancing in production isn't one box, it's a chain, and each layer exists because
> the layer above it can't solve that layer's problem. At the top, DNS decides which
> *region* or which entry point you reach, and it's a blunt instrument because clients and
> resolvers cache records — so DNS-based failover is measured in minutes, not seconds, and
> I'd never rely on it for fast failover. The modern fix is anycast: one IP address
> announced from many locations, so BGP routes the user to the nearest edge and failover
> happens in the network rather than in a DNS TTL. That's how GCP's global load balancer
> works — a single anycast IP, TLS terminated at the closest Google front end. Below that,
> a regional balancer spreads across zones, and then a service-level balancer or the
> Kubernetes Service picks a pod. Finally there's client-side balancing, which is where
> gRPC and service meshes live: the client itself knows every endpoint and picks one, so
> there's no proxy hop at all. The reason I'd walk through it this way in an interview is
> that it maps directly onto blast radius — anycast handles a region failing, regional
> handles a zone failing, service-level handles a pod failing — and it explains why "add a
> load balancer" is never a complete answer to "what if it goes down".

### Mental model

```text
  user
    │  1. DNS: api.acme.com → ?
    ▼                                        timescale: minutes (TTL-bound)
 ┌───────────────────────────────────────┐    decides: which region / entry IP
 │ DNS  (Cloud DNS / Route 53)           │    ⚠ clients cache past TTL; NOT a
 │  · geo / latency / weighted routing   │      fast failover mechanism
 │  · health-checked failover records    │
 └──────────────────┬────────────────────┘
                    │  2. one anycast IP announced from many PoPs
                    ▼                        timescale: seconds (BGP)
 ┌───────────────────────────────────────┐    decides: which edge PoP
 │ GLOBAL LB (anycast)                   │    does: TLS termination at the
 │  GCP global external ALB / GFE        │          edge, WAF, DDoS scrubbing,
 │  AWS Global Accelerator / CloudFront  │          caching, HTTP/3
 └──────────────────┬────────────────────┘
                    │  3. cross-zone, in-region
                    ▼                        timescale: sub-second
 ┌───────────────────────────────────────┐    decides: which zone / node group
 │ REGIONAL LB                           │    does: zone-aware routing, health
 │  regional ALB/NLB, GKE Ingress        │          checks, connection draining
 └──────────────────┬────────────────────┘
        ┌───────────┼───────────┐
        ▼           ▼           ▼          4. which pod
   ┌─────────┐ ┌─────────┐ ┌─────────┐        timescale: per request
   │ zone a  │ │ zone b  │ │ zone c  │        Service / kube-proxy / NEG
   └────┬────┘ └────┬────┘ └────┬────┘
        │           │           │
        ▼           ▼           ▼          5. east-west: client-side LB
   ┌──────────────────────────────────┐        no proxy hop at all
   │  pods, each with a mesh sidecar  │        gRPC round_robin / P2C,
   │  (Envoy) doing P2C + mTLS        │        Envoy sidecar, Traffic Director
   └──────────────────────────────────┘
```

**Client-side load balancing**, because it's the one candidates never bring up:

```text
Proxy LB (server-side)              Client-side LB (gRPC, mesh)

 client ──► LB ──► backend           client ──┬──► backend A
                                              ├──► backend B
 + client is dumb                             └──► backend C
 + one place for policy
 − extra network hop (+0.5-2 ms)     + no proxy hop: lowest latency
 − LB is a scaling unit and a SPOF   + per-request choice over HTTP/2 streams
 − LB must be HTTP/2-aware for gRPC  + no LB fleet to scale
                                     − every client needs endpoint discovery
                                       (DNS, xDS, Eureka, Consul)
                                     − policy is now deployed with the CLIENT,
                                       so a bad policy needs a client rollout
                                     − N clients × M backends connections
```

A sidecar is the hybrid: the client talks to `localhost`, and the sidecar does discovery,
P2C, mTLS and retries. You get client-side latency with centrally-managed policy, and you
pay ~50-100 MB of memory and a little latency per pod, plus a whole control plane to run.

### Enterprise production example

**Google Cloud's** global external Application Load Balancer is the reference anycast
design: you get a *single* global IP address, announced from Google's edge locations, and
TLS is terminated at the nearest Google Front End. Two consequences worth naming. First,
there's no DNS-based scaling problem — the IP never changes, so a client that caches DNS
forever is still correct, which is precisely the failure mode AWS ALB users hit when they
ignore the record TTL. Second, the long-haul hop from edge to your backend region runs
over Google's private backbone rather than the public internet, so the user's TLS
handshake completes in a few milliseconds at the edge even if your backend is a continent
away.

Underneath, Google's L4 layer is **Maglev**, which uses consistent hashing over backends
specifically so that adding or removing a balancer instance doesn't reset existing
connections. **AWS's** comparable pieces are Global Accelerator (anycast IPs) in front of
regional ALBs or NLBs, and CloudFront for cached edge delivery.

### Code

```yaml
# GKE + GCP: container-native load balancing. The NEG annotation is the
# detail that matters — without it, traffic goes LB → node → kube-proxy → pod
# (a double hop with a second, invisible round of balancing). With it, the
# Google LB targets pod IPs directly and its health checks see real pods.
apiVersion: v1
kind: Service
metadata:
  name: search-svc
  annotations:
    cloud.google.com/neg: '{"ingress": true}'          # container-native LB
    cloud.google.com/backend-config: '{"default": "search-backendconfig"}'
spec:
  type: ClusterIP
  ports: [{ port: 80, targetPort: 8000 }]
  selector: { app: search }
---
apiVersion: cloud.google.com/v1
kind: BackendConfig
metadata: { name: search-backendconfig }
spec:
  timeoutSec: 30
  connectionDraining: { drainingTimeoutSec: 60 }   # must exceed your longest
  healthCheck:                                     # in-flight request
    type: HTTP
    requestPath: /healthz/ready
    checkIntervalSec: 5
    unhealthyThreshold: 3        # 15 s to eject: fast enough, not twitchy
    healthyThreshold: 2
  logging: { enable: true, sampleRate: 0.1 }
```

gRPC client-side balancing with health-aware picking:

```python
import grpc

# dns:/// makes gRPC resolve ALL A records of a headless Service and keep a
# subchannel to each. round_robin then picks per-RPC across live subchannels.
channel = grpc.aio.insecure_channel(
    "dns:///search-grpc-headless.default.svc.cluster.local:50051",
    options=[
        ("grpc.lb_policy_name", "round_robin"),
        ("grpc.enable_retries", 1),
        # Health checking: gRPC drops a subchannel whose health service says
        # NOT_SERVING, instead of discovering it via failed RPCs.
        ("grpc.service_config", json.dumps({
            "healthCheckConfig": {"serviceName": ""},
            "methodConfig": [{
                "name": [{"service": "search.v1.SearchService"}],
                "retryPolicy": {
                    "maxAttempts": 3,
                    "initialBackoff": "0.1s", "maxBackoff": "1s",
                    "backoffMultiplier": 2,
                    "retryableStatusCodes": ["UNAVAILABLE", "RESOURCE_EXHAUSTED"],
                },
            }],
        })),
        ("grpc.keepalive_time_ms", 30_000),
        ("grpc.keepalive_timeout_ms", 10_000),
    ],
)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **DNS routing:** region selection, coarse geo, weighted migration | Fast failover (TTLs are advisory; clients over-cache) | Minutes of stale routing after a failure |
| **Anycast global LB:** any multi-region user-facing product | Single-region internal service | Managed-service cost; less control over edge behaviour |
| **Client-side LB:** gRPC east-west, latency-critical internal calls | Polyglot clients you don't control | Every client needs discovery; policy ships with clients |
| **Sidecar mesh:** many services, zero-trust mTLS, uniform retries | Fewer than ~10 services | ~50-100 MB and a little latency per pod, plus a control plane |

### Follow-ups they will ask

**Q: Why isn't DNS enough for failover?**
A: Because you don't control caching. Resolvers, operating systems, browsers and JVMs all
cache, and plenty of them ignore a short TTL — some JVM configurations historically cached
forever. So a 60-second TTL means "some clients recover in 60 seconds and some in an
hour," which isn't a failover mechanism, it's a hope. DNS is the right tool for coarse
region selection and for weighted migrations where minutes are fine. For real failover I
want anycast, where withdrawing a BGP announcement moves traffic in seconds, or a global
balancer that health-checks backends behind a stable IP.

**Q: What does anycast actually give you over DNS-based geo routing?**
A: The routing decision moves from the client's resolver into the network, so it's neither
cached nor client-dependent. One IP is announced from many locations and BGP delivers each
user to the topologically nearest one; if a location withdraws its announcement, traffic
shifts without any client doing anything. The trade-off is that anycast is only
comfortable for connectionless or short-lived connections at the edge — a mid-connection
BGP reconvergence can move packets to a different PoP that has no state for that TCP
connection, which is one reason edge TLS termination plus a stable backend leg is the usual
shape.

**Q: Should I add a service mesh?**
A: Not for fewer than about ten services. What a mesh buys is uniform mTLS with workload
identity, retries, timeouts, circuit breaking and per-call telemetry without touching
application code — that's genuinely valuable when twenty teams would otherwise implement
retries twenty different ways. What it costs is a control plane on your critical path, a
sidecar per pod, a new class of failure that looks like an application bug, and an upgrade
treadmill. For a handful of services, gRPC's built-in client-side balancing plus a
retry-and-timeout library gets me most of it.

**Q: What's the difference between GKE's default Service load balancing and
container-native load balancing?**
A: Without the NEG annotation, the Google load balancer targets *nodes*, and `kube-proxy`
on that node then picks a pod — a second, invisible balancing decision, an extra hop, and
health checks that report on the node rather than on the pod. With container-native load
balancing the LB targets pod IPs directly, so there's one hop, one balancing decision, and
health checks that reflect actual pod readiness. It also makes connection draining work
properly, because the LB knows about the specific pod being removed.

### Red flags — do not say this

- ❌ "DNS failover handles region outages." → ✅ "TTLs are advisory and clients over-cache;
  DNS is minutes. Anycast or a global LB with health checks is seconds."
- ❌ "One load balancer is enough." → ✅ "Global LB for region selection, regional for zone
  spread, service-level for pods — each handles a different blast radius."
- ❌ "Client-side load balancing means no load balancer." → ✅ "It means no proxy hop; you
  still need endpoint discovery and you've moved policy into the client."
- ❌ "We'll add a service mesh for observability." (with 4 services) → ✅ "Below ~10 services
  the control plane and sidecars cost more than they return; OpenTelemetry in the app is
  cheaper."

---

## 4.6 Health checks

**Interview weight:** ★★★★★

> **One-liner:** Liveness asks "should this process be killed?", readiness asks "should
> this instance receive traffic?", and conflating them — or letting either one check a
> shared dependency — is how a thirty-second database blip becomes a full outage.

### Say this in the interview

> Health checks are the most dangerous thing on this list, because a bad one turns a small
> problem into a total one. There are three probes and they have genuinely different
> semantics. Liveness asks whether the process should be killed and restarted — so it must
> check only local, in-process state, like "is the event loop responsive". Readiness asks
> whether this instance should receive traffic right now, and failing it removes the
> instance from the load balancer without killing it. A startup probe covers slow
> initialisation — loading model weights, warming a cache — and its whole purpose is to
> keep the liveness probe from killing a pod that is legitimately still booting. The
> failure mode people walk into is putting a dependency check in the wrong probe. If my
> liveness probe does a `SELECT 1` against Postgres and Postgres has a thirty-second blip,
> every pod fails liveness simultaneously, Kubernetes kills the entire fleet, and when the
> database recovers it's hit by a thundering herd of cold pods all opening connections at
> once — I turned a thirty-second degradation into a fifteen-minute outage and made the
> recovery harder. Same shape with a deep readiness check: every instance drains at once
> and the load balancer has zero healthy targets. So the rule is that shared-dependency
> checks belong in *monitoring*, not in the routing or restart path. AWS says this
> explicitly in their own guidance — don't attach deep load balancer health checks to your
> auto scaling group, because it causes mass termination of the fleet during a dependency
> failure. What I do instead is keep the probes shallow, run deep checks in a background
> thread that feeds dashboards and alerts, and let individual endpoints fail per request:
> the endpoint that needs Postgres returns 503, and the endpoints that don't keep serving.

### Mental model

```text
                    THE THREE PROBES

startupProbe   "is initialisation finished?"
  · runs FIRST; liveness and readiness are SUSPENDED until it passes
  · exists so a slow boot (8 GB of model weights) isn't mistaken for a hang
  · fail → the container is killed and restarted
  · budget = periodSeconds × failureThreshold  (make it generous)

livenessProbe  "should I kill this process?"
  · check ONLY local, in-process state
  · fail → kubelet kills the container.  THIS IS CAPITAL PUNISHMENT.
  · ⚠ never touch a database, cache, or any network dependency here

readinessProbe "should this instance get traffic?"
  · fail → removed from the Service endpoints / LB target group.
           The process KEEPS RUNNING and can recover.
  · check local readiness (pool initialised, caches warm, not draining)
  · ⚠ a SHARED dependency here fails every replica at once
```

**The cascade, drawn.** This is the diagram to reproduce on a whiteboard:

```text
BAD: dependency check in the probe

  t=0   Postgres has a 30 s blip (failover, or a lock storm)
          │
          ▼
  every pod's probe runs SELECT 1  ──► fails  ──► on ALL 20 pods at once
          │                                  (they are not independent!)
          ├── if it was LIVENESS  ──► kubelet kills all 20 containers
          │        │
          │        ▼
          │   20 cold pods restart, all open connection pools at t=30 s
          │        │
          │        ▼
          │   Postgres, just recovering, is hit by a connection herd
          │   → fails again → probes fail again → CrashLoopBackOff
          │   → 30-second blip becomes a 15-minute outage
          │
          └── if it was READINESS ──► all 20 removed from the LB
                   │
                   ▼
              zero healthy targets → LB returns 503 to 100% of traffic
              (even for endpoints that never touch Postgres)


GOOD: probes are shallow; the dependency is handled per request

  liveness   GET /healthz/live   → 200 if the event loop responds. Nothing else.
  readiness  GET /healthz/ready  → 200 if local init done AND not draining.
                                   (optionally: a CACHED dep status, fail-open)
  business   GET /v1/search      → 503 if THIS request needs the vector DB
                                   and it's down
             GET /v1/config      → 200, still served from local memory

  Result: the blip degrades only the endpoints that needed the broken thing.
          Nothing is killed. Nothing drains. Recovery is automatic.
```

**Deep vs shallow — where each belongs:**

```text
Layer                 Depth      Consequence of failure      Correct?
────────────────────────────────────────────────────────────────────────
liveness probe        shallow    container killed            ✅ shallow only
readiness probe       shallow    removed from LB             ✅ shallow only
LB / target group     shallow    removed from rotation       ✅ shallow
autoscaler health     shallow    instance TERMINATED         ✅ shallow ONLY
background monitor    DEEP       a page fires                ✅ deep belongs here
/healthz/deep (debug) DEEP       a human reads it            ✅ manual only
```

If you *must* have a dependency check in the routing path, it needs **fail-open**: when
every target is unhealthy, send traffic to all of them anyway rather than to none. AWS ALB
does this by design — if a target group contains only unhealthy targets, the load balancer
routes to all of them regardless of health — which converts "total outage" into "degraded".

**Graceful shutdown and connection draining** — the other half of health checks, because
the sequence is genuinely counter-intuitive:

```text
Kubernetes pod deletion, in order:

  1. pod marked Terminating; removed from EndpointSlice
     ⚠ this is EVENTUALLY consistent — every kube-proxy and every cloud LB
       has to observe it. That takes hundreds of milliseconds to seconds.
  2. preStop hook runs (if defined)         ← put your sleep HERE
  3. SIGTERM to PID 1
  4. terminationGracePeriodSeconds countdown (default 30 s)
  5. SIGKILL

  The bug: steps 1 and 3 race. If the process exits promptly on SIGTERM,
  requests routed just before step 1 propagated arrive at a closed socket
  → connection resets → 502s during EVERY deploy.

  The fix: preStop { sleep 10 } so endpoint removal propagates BEFORE the
  process starts shutting down, plus a grace period longer than
  (sleep + longest in-flight request), plus flipping readiness to false
  first so anything that re-resolves also stops sending.
```

### Enterprise production example

**AWS** publishes this as explicit guidance rather than folklore, which makes it citable.
Their Networking blog on choosing health checks with Elastic Load Balancing and EC2 Auto
Scaling defines *shallow* checks as on-box only — critical processes running, software
behaving, filesystem healthy — and *deep* checks as including off-box interactions like
resolving DNS, querying a database, or calling a downstream service. Their conclusion is
direct: **"As a best practice, don't add 'deep' ELB health checks to your ASG. This will
prevent the mass termination of your EC2 instance fleet during a dependency failure."**
They also name the trade-off honestly — deep checks at the load balancer let you route
around a single instance's transient dependency problem quickly, but then Auto Scaling
can't use that signal to replace genuinely broken instances. That's the shape of the whole
topic: fast ejection and safe replacement pull in opposite directions, and the resolution
is to use different checks for the two jobs.

**Scenario (labelled as a scenario):** a FastAPI RAG service on GKE had its readiness probe
call the vector database. A routine index rebuild made the vector DB slow for 40 seconds.
All 12 pods failed readiness simultaneously, the EndpointSlice emptied, and the Ingress
returned 503 for every request — including `/v1/config` and `/healthz`, which never touch
the vector DB. Moving the vector-DB check out of readiness and into a per-request
dependency, with a cached background status feeding alerts, turned the next occurrence into
a 40-second partial degradation of one endpoint.

### Code

```python
# health.py — three endpoints, three different questions.
import asyncio, time
from fastapi import APIRouter, Response

router = APIRouter(prefix="/healthz")

class Health:
    started = False          # startup finished (model loaded, pools open)
    draining = False         # SIGTERM received: stop taking new traffic
    dep_status: dict = {}    # background DEEP check results — NOT for routing

health = Health()

@router.get("/live")
async def live() -> Response:
    """LIVENESS. Local only. Failing this KILLS the container, so it must
    never depend on anything off-box."""
    return Response(status_code=200)          # reachable ⇒ the loop is alive

@router.get("/ready")
async def ready() -> Response:
    """READINESS. Local readiness + draining state. No shared dependencies:
    a shared dep here fails every replica in lockstep."""
    if health.draining or not health.started:
        return Response(status_code=503)
    return Response(status_code=200)

@router.get("/deep")
async def deep() -> Response:
    """DEEP. For humans, dashboards and alerts. NEVER wired to a probe,
    a target group, or an autoscaler."""
    ok = all(d["ok"] for d in health.dep_status.values())
    return JSONResponse(health.dep_status, status_code=200 if ok else 503)

async def dependency_monitor(app) -> None:
    """Runs in the background. Feeds alerting, not routing. Memoised so 20
    pods polling every 10 s don't themselves become load on the database."""
    while True:
        for name, check in (("postgres", check_pg), ("redis", check_redis),
                            ("vector_db", check_vector)):
            t0 = time.monotonic()
            try:
                await asyncio.wait_for(check(app), timeout=2.0)
                health.dep_status[name] = {"ok": True,
                                           "ms": round((time.monotonic()-t0)*1000)}
            except Exception as e:
                health.dep_status[name] = {"ok": False, "error": str(e)[:200]}
                DEP_DOWN.labels(name).inc()      # Prometheus → alert → human
        await asyncio.sleep(10)
```

And the per-request degradation that replaces the deep probe:

```python
@app.get("/v1/search")
async def search(q: str):
    try:
        return await vector_db.search(q, timeout=0.5)
    except (TimeoutError, ConnectionError):
        # This endpoint degrades. Others keep serving. The pod stays in the LB.
        raise HTTPException(503, "search temporarily unavailable",
                            headers={"Retry-After": "5"})

@app.get("/v1/config")                     # never touches the vector DB
async def config():                        # → keeps returning 200 throughout
    return CACHED_CONFIG
```

The Kubernetes manifest — every number here is a decision:

```yaml
spec:
  terminationGracePeriodSeconds: 45        # > preStop sleep + longest request
  containers:
  - name: api
    startupProbe:
      httpGet: { path: /healthz/live, port: 8000 }
      periodSeconds: 5
      failureThreshold: 30                 # 150 s budget to load 8 GB of weights
    livenessProbe:
      httpGet: { path: /healthz/live, port: 8000 }
      periodSeconds: 10
      timeoutSeconds: 2
      failureThreshold: 3                  # 30 s of failure before a kill
    readinessProbe:
      httpGet: { path: /healthz/ready, port: 8000 }
      periodSeconds: 5
      timeoutSeconds: 2
      failureThreshold: 2                  # 10 s to drain: quicker than liveness
      successThreshold: 1
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 10"]   # let endpoint removal
                                                    # propagate before SIGTERM
```

Two relationships to state out loud: readiness must fail *faster* than liveness (10 s vs
30 s), so a struggling pod is drained before it's killed and gets a chance to recover; and
the startup probe budget must exceed worst-case initialisation, or a slow boot becomes a
`CrashLoopBackOff` that looks like a code bug.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **Shallow liveness + shallow readiness** | Never deviate for shared dependencies | A pod with a broken dependency stays in rotation and fails requests — which is the *correct*, smaller blast radius |
| **Deep checks in background monitoring** | Wiring them to probes, target groups or autoscalers | You detect dependency failure by alert, not by automatic ejection |
| **Deep check at a fail-open LB (ALB/NLB)** | Any LB that fails closed | Fail-open is hard to test; verify the behaviour before relying on it |
| **Startup probe with a generous budget** | Fast-starting services (it's just noise) | A genuinely hung boot takes the full budget to be detected |

### Follow-ups they will ask

**Q: Why shouldn't the liveness probe check the database?**
A: Because liveness failure means the container gets killed, and the database is shared, so
all replicas fail the probe at the same instant. Kubernetes then kills the whole fleet, and
when the database recovers it's hit by every pod cold-starting and opening a connection
pool simultaneously — which can push it back over and produce a `CrashLoopBackOff` cycle. A
process that can't reach its database isn't broken; it's *blocked*, and restarting it
doesn't fix the database. Restarting only helps for genuinely local, unrecoverable states:
a deadlock, a wedged event loop, unrecoverable heap exhaustion.

**Q: Then how do you detect that a pod's database connection is genuinely broken while its
neighbours are fine?**
A: That's a *local* condition, so it belongs in readiness — but the check has to be on the
pod's own connection pool, not on the database. "Can I acquire a connection from my pool
within 100 ms" is local state: it fails on the pod with the wedged pool and passes on the
healthy ones, so exactly one pod drains. Contrast that with `SELECT 1` against the shared
database, which fails identically everywhere. The distinction is whether a failure is
correlated across replicas.

**Q: You deploy and see a burst of 502s every time. Why?**
A: Endpoint removal and process shutdown are racing. Kubernetes marks the pod
`Terminating` and sends SIGTERM at effectively the same time, but the endpoint removal has
to propagate to every `kube-proxy` and every cloud load balancer, which takes hundreds of
milliseconds to seconds. If the process exits promptly on SIGTERM, requests routed in that
window hit a closed socket. The fix is a `preStop` sleep of about ten seconds so
propagation completes first, flipping readiness to false at the top of shutdown, a
`terminationGracePeriodSeconds` longer than the sleep plus the longest in-flight request,
and a connection-draining timeout on the load balancer that matches.

**Q: What is a "deep" health check good for, then?**
A: Alerting and diagnosis. A background task that checks each dependency every ten seconds
and exports a metric per dependency tells me *which* thing is broken within seconds, which
is exactly what I want at 3 a.m. — and it costs nothing dangerous, because no routing or
restart decision reads it. I'd memoise the result so twenty pods checking every ten seconds
don't themselves become meaningful load on the database, which is a real failure I've seen
turn a health check into the cause of the incident.

**Q: A pod is up and passing probes but returning 500s for real traffic. What's missing?**
A: The probes are measuring the wrong thing, and this is why probes are a floor rather than
the whole story. The real signal is the service-level indicator — error rate and latency on
actual requests — so I'd have an alert on 5xx rate per deployment, and for the routing
decision I'd add outlier detection at the balancer or mesh, which ejects a backend whose
error rate diverges from the fleet regardless of what its health endpoint claims. That
catches "healthy but wrong", which no self-reported probe ever will.

### Red flags — do not say this

- ❌ "The health check verifies the database connection." → ✅ "Shallow probes only; a shared
  dependency in a probe fails every replica at once. Deep checks feed alerts."
- ❌ "Liveness and readiness can be the same endpoint." → ✅ "Failing liveness kills the
  container; failing readiness just drains it. Conflating them turns a drainable blip into
  a fleet restart."
- ❌ "We restart the pod if it can't reach Redis." → ✅ "Restarting doesn't fix Redis, and
  restarting everything makes recovery worse — the pod should degrade, not die."
- ❌ "Health checks are `GET /health` returning 200." → ✅ "Three probes with three
  semantics, plus a deep background monitor that never touches routing."
- ❌ "We set a 30-second grace period, that's plenty." → ✅ "The grace period must exceed the
  preStop sleep plus the longest in-flight request, or deploys emit 502s."

---

## 4.7 Consistent hashing

**Interview weight:** ★★★★☆

> **One-liner:** Modulo hashing remaps almost every key when the node count changes;
> consistent hashing maps keys and nodes onto the same ring so adding a node moves only
> about `1/(N+1)` of the keys.

### Say this in the interview

> The problem consistent hashing solves is resizing. If I shard by `hash(key) % N`, then
> going from four nodes to five doesn't move a fifth of the keys — it moves about eighty
> percent of them, and the math is clean: for a random key, the probability that
> `h mod N` equals `h mod (N+1)` is one over `N+1`, so the fraction that *moves* is
> `N/(N+1)`. At a hundred nodes that's ninety-nine percent. For a cache that means a
> near-total cold start the moment you add capacity, and every one of those misses hits the
> database at the same time — so scaling out the cache causes the outage you were scaling
> to prevent. Consistent hashing fixes it by hashing both keys and nodes into the same
> circular space and assigning each key to the first node clockwise from it. Now adding a
> node only steals the arc between it and its predecessor, so only about `1/(N+1)` of keys
> move and everything else stays put. The catch is that N random points on a ring are not
> evenly spaced — the largest arc is roughly `ln N` times the average, so with ten nodes one
> node can own more than double its fair share. That's what virtual nodes fix: each
> physical node gets a hundred to two hundred and fifty-six positions on the ring instead
> of one, and the imbalance falls off as one over the square root of the number of virtual
> nodes, which gets you within a few percent. Cassandra and DynamoDB both do exactly this.
> And the remaining problem is that consistent hashing balances *keys*, not *traffic*, so a
> single viral key still lands on one node — which is why the production refinement is
> bounded loads: cap each node at a small multiple of the average and spill to the next
> node on the ring when it's full.

### Mental model

**Step 1 — why modulo is catastrophic. Show the math:**

```text
Sharding by  node = hash(key) % N

Going from N nodes to N+1, a key stays put only if
    h mod N  ==  h mod (N+1)

N and N+1 are always coprime, so by the Chinese Remainder Theorem
h mod N and h mod (N+1) are independent and uniform. They agree only when
both equal some common value j < N:

    P(stay) = Σ_{j=0}^{N-1} (1/N)·(1/(N+1)) = N · 1/(N(N+1)) = 1/(N+1)

    ⇒  fraction REMAPPED = N/(N+1)

    N = 4  →  5  :  80% of keys move
    N = 10 → 11  :  91% of keys move
    N = 100→101  :  99% of keys move

Worked example, N = 4 → 5:
  key    h      h%4    h%5    moved?
  a      17      1      2      yes
  b      20      0      0      no
  c      33      1      3      yes
  d      41      1      1      no
  e      50      2      0      yes
  ⇒ 3 of 5 moved in this tiny sample; asymptotically 4/5.
```

For a 100-node Memcached tier holding a 90% hit rate, adding one node takes the hit rate to
roughly 1% instantaneously. Every miss becomes a database query. That's the outage.

**Step 2 — the ring.** Drawn as a wrapping line, which is easier to read than a circle:

```text
  hash space 0 .. 2^32-1, wrapping at the right edge back to 0
  0                                                              2^32
  ├────┬──────┬───┬────────┬──┬───┬───────────┬──────┬───────┬─────┤
       A1     B3  C2       A4 B1  C3          A2     B2      C1
       ▲
       └─ each mark is a node's position (a "token")

  A key hashes to a point and walks CLOCKWISE (rightward, wrapping) to
  the first node mark it meets.

  hash("user:42") lands here ───┐
  0                            ▼                                 2^32
  ├────┬──────┬───┬────────┬──┬┼──┬───────────┬──────┬───────┬─────┤
       A1     B3  C2       A4  B1  C3          A2     B2      C1
                                └─► owner: B1   ⇒ physical node B
```

The same thing as a circle, since interviewers sometimes want to see it:

```text
                        0 / 2^32
                            │
                 C1 ●───────┼───────● A1
                   ╱        │        ╲
            B2 ●            │            ● B3
              │      hash("doc:7") ──┐    │
            A2 ●                     ▼    ● C2
               ╲          walk clockwise ╱
            C3 ●───────● B1 ●───────● A4
                                 ▲
                                 └─ first node clockwise = owner
```

**Step 3 — adding a node moves only one arc:**

```text
BEFORE                              AFTER adding node D (token D1)
  ├──┬─────────┬──────┬──────┤        ├──┬────┬────┬──────┬──────┤
     A1        B1     C1                 A1   D1   B1     C1
     └── B1 owns this arc ──┘            └─A1─┘└D1┘└─B1───┘
                                              ▲
  keys in [A1, B1) → B1              only keys in [A1, D1) move: A1→D1
                                     everything else is UNTOUCHED
  ⇒ ~1/(N+1) of keys move, and they move to exactly one new node.
```

**Step 4 — why virtual nodes are mandatory:**

```text
Without vnodes: N random points on a ring are NOT evenly spaced.
  The expected largest gap is ≈ ln(N)/N of the ring, i.e. ~ln(N)× the mean.
    N = 10  → the unluckiest node can own > 2× its fair share
    N = 100 → still ~4-5× the mean for the worst arc

  ├────────────────────────┬──┬──────────────────┬─┬──────────────┤
       A (huge arc)         B  C   (big arc)      D E
  ▲ A and C are hot; B, D, E are idle. Also: if A dies, its ENTIRE
    arc lands on B — one node absorbs 100% of a failed node's load.

With V vnodes per physical node: each node has V small arcs scattered
around the ring. Load imbalance shrinks as ≈ 1/√V.
    V = 1    → tens of percent of imbalance
    V = 100  → roughly ±10%
    V = 256  → roughly a few percent

  ├─┬──┬─┬───┬──┬─┬──┬───┬─┬──┬──┬─┬───┬──┬─┬──┬───┬─┬──┬──┬─┬──┤
   A B  C A   B  C A  B   C A  B  C A   B  C A  B   C A  B  C A
  ▲ Now if A dies, its many small arcs are absorbed by B and C roughly
    EVENLY — no single neighbour eats the whole failed node's load.
    Weighted capacity is free too: a 2× bigger node just gets 2× the vnodes.
```

Two properties for the price of one: better balance, *and* graceful failure spreading.
That second one is the answer to "why not just use fewer, better-placed tokens."

**Step 5 — bounded loads, for hot keys:**

```text
Consistent hashing balances KEYS, not TRAFFIC. One viral key = one hot node.

Consistent hashing with bounded loads:
  1. average load m/n  (m = outstanding requests incl. this one, n = nodes)
  2. target t = c × average,  c typically 1.25-1.5
  3. hash the key → walk clockwise to the preferred node
  4. if that node's load ≥ ⌈t⌉, keep walking to the next node with room
     (one must exist: not every node can be above average)

  ⇒ affinity whenever the preferred node has capacity, and a hard cap of
    "no more than c× the average, plus at most 1 request" when it doesn't.
  ⇒ the knob: c → 1 means perfect balance and poor affinity; large c means
    perfect affinity and no protection.
```

### Enterprise production example

**Vimeo** deployed exactly this. Their video packager Skyfire serves close to a billion
DASH and HLS requests per day, and they needed the same video segment to reach the same
backend for cache warmth, without a popular video melting one server. Plain consistent
hashing gave affinity but no hot-key protection; least-connections gave balance but
destroyed the cache hit rate. They implemented **consistent hashing with bounded loads** —
computing a target load as `c ×` the average and walking the ring past any node already at
capacity — and describe the guarantee as: no server can exceed its fair share of the load
by more than one request. They contributed the algorithm to **HAProxy**, where bounded-load
consistent hashing is now a supported balancing option.

**Apache Cassandra** and **Amazon DynamoDB** both partition with consistent hashing plus
virtual nodes; the original Dynamo paper is where the technique entered mainstream
infrastructure. Cassandra exposes the virtual-node count as `num_tokens` — historically
256 per node in the 3.x line, lowered to 16 by default in 4.0 alongside a smarter token
allocation algorithm that achieves comparable balance with far fewer tokens. That
progression is a good detail: more virtual nodes buy balance, but they also increase
gossip and repair overhead, so the industry moved toward fewer, better-placed tokens.
**Memcached** clients have shipped consistent hashing for years (the Ketama scheme), which
is why a Memcached tier can be resized without a total cache flush.

**Google's Maglev** L4 load balancer uses consistent hashing over backends so that adding
or removing a Maglev instance doesn't reset existing TCP connections — the same primitive
solving a connection-affinity problem instead of a data-placement one.

### Code

A compact, production-shaped ring. The interesting parts are the sorted token array with
`bisect` for O(log VN) lookup, and the bounded-load variant.

```python
import bisect, hashlib
from collections import Counter

class ConsistentHashRing:
    """Consistent hash ring with virtual nodes and optional bounded loads."""

    def __init__(self, nodes: list[str] | None = None, vnodes: int = 150):
        self.vnodes = vnodes
        self._ring: dict[int, str] = {}     # token -> physical node
        self._tokens: list[int] = []        # sorted tokens, for bisect
        for n in nodes or []:
            self.add(n)

    @staticmethod
    def _hash(key: str) -> int:
        # md5 is fine here: we need uniformity and speed, not collision
        # resistance. Never use it for anything security-bearing.
        return int.from_bytes(hashlib.md5(key.encode()).digest()[:8], "big")

    def add(self, node: str, weight: int = 1) -> None:
        for i in range(self.vnodes * weight):   # weight => proportional share
            t = self._hash(f"{node}#{i}")
            self._ring[t] = node
            bisect.insort(self._tokens, t)

    def remove(self, node: str) -> None:
        for t in [t for t, n in self._ring.items() if n == node]:
            del self._ring[t]
            self._tokens.remove(t)

    def get(self, key: str) -> str:
        if not self._tokens:
            raise RuntimeError("empty ring")
        i = bisect.bisect(self._tokens, self._hash(key))    # first token > h
        return self._ring[self._tokens[i % len(self._tokens)]]   # wrap at 2^64

    def get_n(self, key: str, n: int) -> list[str]:
        """N distinct physical nodes clockwise — this is how replication
        factor works in Cassandra/Dynamo."""
        out: list[str] = []
        i = bisect.bisect(self._tokens, self._hash(key))
        for step in range(len(self._tokens)):
            node = self._ring[self._tokens[(i + step) % len(self._tokens)]]
            if node not in out:
                out.append(node)
                if len(out) == n:
                    break
        return out

    def get_bounded(self, key: str, load: Counter[str], c: float = 1.25) -> str:
        """Consistent hashing with bounded loads (the Vimeo/HAProxy variant).
        Walk past any node already at c x the average."""
        nodes = {n for n in self._ring.values()}
        cap = -(-(int(c * (sum(load.values()) + 1)) ) // len(nodes))   # ceil
        i = bisect.bisect(self._tokens, self._hash(key))
        for step in range(len(self._tokens)):
            node = self._ring[self._tokens[(i + step) % len(self._tokens)]]
            if load[node] < max(cap, 1):
                return node
        return self._ring[self._tokens[i % len(self._tokens)]]   # all full
```

Proving the two properties — worth running once so the numbers are yours:

```python
ring = ConsistentHashRing([f"node-{i}" for i in range(10)], vnodes=150)
keys = [f"user:{i}" for i in range(100_000)]
before = {k: ring.get(k) for k in keys}

dist = Counter(before.values())
spread = (max(dist.values()) - min(dist.values())) / (len(keys) / 10)
print(f"imbalance with 150 vnodes: {spread:.1%}")        # ≈ 5-10%

ring.add("node-10")
moved = sum(1 for k in keys if ring.get(k) != before[k])
print(f"moved on 10 -> 11 nodes: {moved / len(keys):.1%}")   # ≈ 9% ≈ 1/11
# modulo hashing on the same change would move 10/11 ≈ 91%.
```

Same ring at `vnodes=1` gives an imbalance in the tens of percent — run both and the
argument for virtual nodes stops being theoretical.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Distributed cache tiers, sharded stores, sticky routing for cache warmth, session affinity to a partition | You need *even traffic* and have hot keys (add bounded loads) | Ring state to distribute; rebalancing still moves `1/(N+1)` of data |
| Virtual nodes at 100-256 per physical node | Very large clusters where token metadata and repair cost matters (Cassandra 4.0 moved to 16 + smart allocation) | Memory for tokens; more gossip/repair surface |
| Bounded loads when one key can go viral | Pure data placement where load isn't the issue | Some cache misses when spilling; a `c` factor to tune |

### Follow-ups they will ask

**Q: Give me the number. How many keys move when you go from 100 nodes to 101?**
A: With modulo, about 99% — a key stays only when `h mod 100` equals `h mod 101`, which
has probability `1/101`. With consistent hashing, about `1/101`, roughly 1%, and they all
move to the one new node. That two-orders-of-magnitude difference is the entire reason the
technique exists, and it's the difference between "we added a cache node" being a
non-event and being an outage.

**Q: Why do you need virtual nodes at all? Just place the tokens evenly.**
A: You can, and Cassandra 4.0's allocation algorithm effectively does — that's why it
dropped the default from 256 tokens to 16. But hand-placed tokens have to be recomputed
whenever the cluster changes, which reintroduces coordination. The other reason for
virtual nodes is failure spreading: with one token per node, a dead node's entire arc lands
on its single clockwise neighbour, which then carries double load and often falls over
too. With 150 scattered vnodes, the dead node's arcs are absorbed roughly evenly by
everyone. Virtual nodes also make heterogeneous capacity trivial — a machine twice the
size just gets twice the tokens.

**Q: Consistent hashing balances keys. What about a single viral key?**
A: It doesn't help at all, and I'd say that plainly — one key is one point on the ring and
therefore one node, no matter how many nodes you have. Three fixes, in increasing order of
effort: bounded loads, so the node caps out and requests spill clockwise; key splitting,
where a known-hot key becomes `key:0..key:9` across ten nodes with the reader picking at
random; and a small local L1 cache in the client so the hottest keys never leave the
process. For a read-heavy hot key the L1 cache is usually the cheapest and most effective.

**Q: How does the ring stay consistent across many clients?**
A: Either every client computes the ring from a shared membership list — which is the
Memcached/Ketama model, and it's fine because the hash function is deterministic so all
clients agree given the same list — or membership comes from a coordination service or
gossip protocol, which is what Cassandra does. The failure mode to watch is a *split view*:
during a membership change, two clients briefly disagree about the node set and write the
same key to different nodes. For a cache that's a tolerable extra miss; for a data store
it's a correctness bug, which is why real stores route through a quorum rather than
trusting one client's view.

**Q: Where does this show up in load balancing rather than data placement?**
A: Google's Maglev uses consistent hashing over backends so that scaling the balancer fleet
doesn't reset existing TCP connections — without it, adding a Maglev instance would remap
connections and break them mid-flight. HAProxy and nginx both offer consistent hashing on a
request key for cache affinity, and HAProxy additionally supports the bounded-load variant
Vimeo contributed. It's the same primitive: minimise disruption when the target set
changes.

### Red flags — do not say this

- ❌ "`hash(key) % N` is fine, we rarely add nodes." → ✅ "Adding one node to a hundred
  remaps 99% of keys — the cache goes cold exactly when I'm scaling to handle load."
- ❌ "Consistent hashing distributes load evenly." → ✅ "It distributes *keys* and only
  roughly — N random points leave gaps of ~ln N × the mean, which is why virtual nodes
  exist. And it does nothing about hot keys without bounded loads."
- ❌ "Virtual nodes are an optimisation." → ✅ "They're required for balance and for
  spreading a failed node's load; without them one neighbour absorbs the whole arc."
- ❌ "Consistent hashing solves hot keys." → ✅ "One key is one ring position is one node —
  hot keys need bounded loads, key splitting, or a client-local cache."

---

## 4.8 Autoscaling

**Interview weight:** ★★★★☆

> **One-liner:** Autoscaling is a control loop, so the whole game is picking a signal that
> actually leads demand — queue depth or concurrency, not CPU — and making scale-up fast
> while scale-down is slow.

### Say this in the interview

> Autoscaling is a feedback loop and the two things that decide whether it helps or hurts
> are the signal and the asymmetry. On the signal: CPU is the default and it's usually the
> wrong one. For an async Python worker pulling from a queue, CPU tells me nothing — the
> worker is I/O-bound waiting on an LLM API, so it sits at 15% CPU while the backlog grows
> to a hundred thousand messages. The signal that leads demand is queue depth, or better,
> queue depth divided by throughput, which gives me the *age* of the backlog in seconds
> and is directly comparable to my latency SLO. For a synchronous API the right signal is
> concurrency — in-flight requests per instance — because by Little's Law concurrency
> equals request rate times latency, so it captures both a traffic spike and a slowdown in
> a dependency. On the asymmetry: scale up aggressively and scale down slowly, because the
> costs are wildly different. Scaling up too late means dropped requests and a violated
> SLO; scaling down too early means you scale back in and immediately have to scale out
> again, and if instances are slow to start you're permanently behind. So I'd use no
> stabilisation window on scale-up and something like five to ten minutes on scale-down,
> and I'd add headroom on top so the autoscaler isn't in the critical path of every spike.
> The thing I'd flag unprompted is cold start: if a pod takes forty seconds to load model
> weights, my autoscaler cannot respond to a thirty-second spike, so the honest answer for
> spiky traffic is a warm pool plus predictive or schedule-based scaling, not a faster
> reactive loop.

### Mental model

```text
             the control loop, and where each thing goes wrong

  demand ──►┌──────────┐──► signal ──►┌──────────┐──► desired replicas
            │  system  │              │autoscaler│
            └──────────┘◄─ capacity ──└──────────┘
                  ▲                          │
                  └──── provisioning delay ◄─┘
                        (image pull, boot, warm-up: 10 s .. 3 min)

  ⚠ if provisioning delay > the duration of your spike, reactive
    autoscaling CANNOT help. That's a headroom problem, not a tuning problem.
```

**Pick the signal that leads demand:**

```text
Workload                     WRONG signal      RIGHT signal
──────────────────────────────────────────────────────────────────────────
Async queue worker           CPU               queue depth, or better:
(I/O-bound: LLM, HTTP)       (sits at 15%)     backlog_age = depth / throughput
                                               → directly comparable to SLO
Sync HTTP API                CPU alone         in-flight concurrency per pod
                                               (Little's Law: L = λ × W, so
                                               it catches BOTH a traffic
                                               spike and a slow dependency)
CPU-bound service            CPU               CPU (genuinely correct here)
(transcode, embedding on CPU)
GPU inference                CPU               GPU utilisation + queue wait,
                                               or requests-in-flight
Cron-shaped batch            anything reactive schedule / predictive
                                               (you KNOW it's coming)

Why backlog_age beats raw depth: "100,000 messages" means nothing on its own.
At 5,000 msg/s that's 20 s of work — fine. At 50 msg/s it's 33 minutes — page
someone. Scaling on depth/throughput makes the target an SLO, not a guess.
```

**Scale-up vs scale-down asymmetry:**

```text
            cost of being wrong

  too slow to scale UP        →  429s, timeouts, SLO breach, revenue
  too fast to scale DOWN      →  thrash: out → in → out, and with a 60 s
                                 cold start you are permanently behind
  too slow to scale DOWN      →  you pay for idle instances  ← cheapest error

  ⇒ scale up: react in seconds, no stabilisation window, allow big steps
    scale down: 5-10 min stabilisation window, small steps (e.g. ≤10%/min)
```

**Thundering herd on scale-out** — the failure people don't anticipate:

```text
  t=0    traffic spike → HPA adds 20 pods
  t=20s  20 pods boot SIMULTANEOUSLY and each:
           · opens a DB connection pool  (20 × 20 = 400 new connections)
           · fetches config / secrets    (400 requests to the config service)
           · warms its cache             (400 identical cache-miss queries)
           · registers with discovery
         ⇒ the dependency you scaled out to protect gets hit hardest at the
           exact moment it is already saturated

  Mitigations:
    · jittered startup: sleep(random(0, 5s)) before opening pools
    · small pool min_size (2), grow lazily — not min_size = max_size
    · request coalescing / single-flight on cache warm-up
    · PgBouncer so pod count and DB connection count are decoupled
    · maxSurge limits and scale-up step caps so 20 pods arrive as 4 × 5
```

### Enterprise production example

**Scenario (labelled as a scenario, not a company claim):** a document-ingestion pipeline
on GKE — Pub/Sub → parse → chunk → embed → pgvector. The workers were HPA-scaled on CPU at
a 70% target. Because each worker spent most of its time awaiting the embedding API, CPU
never exceeded 25%, so the HPA never scaled beyond the minimum of three replicas while the
subscription backlog grew past 400,000 messages and the oldest unacknowledged message aged
past two hours. Nothing was "unhealthy": CPU was green, error rates were zero, and the SLO
was being missed badly.

Switching to KEDA scaling on Pub/Sub `num_undelivered_messages` with a target of 500
messages per replica made the loop track the actual work, and adding a second trigger on
`oldest_unacked_message_age` gave a direct SLO-shaped signal. The other necessary change
was the herd fix: with `min_size` equal to `max_size` on the Postgres pool, scaling from 3
to 60 replicas opened 1,200 connections at once against a `max_connections` of 500. Adding
PgBouncer and a lazy pool were what made the scale-out survivable.

The reusable lesson: **the autoscaler was working perfectly and reading a signal that had
nothing to do with the work.** That's the most common autoscaling incident, and it's a
design error rather than a tuning error.

### Code

KEDA scaling on queue depth *and* backlog age — the two triggers together:

```yaml
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata: { name: embedding-worker }
spec:
  scaleTargetRef: { name: embedding-worker }
  minReplicaCount: 2            # never 0 for latency-sensitive work: cold start
  maxReplicaCount: 60           # a real ceiling — protects the DB and your bill
  pollingInterval: 15
  cooldownPeriod: 300           # scale-DOWN stabilisation: 5 min
  advanced:
    horizontalPodAutoscalerConfig:
      behavior:
        scaleUp:
          stabilizationWindowSeconds: 0        # react immediately
          policies:
          - { type: Percent, value: 100, periodSeconds: 30 }   # up to 2x/30s
          - { type: Pods,    value: 10, periodSeconds: 30 }    # step cap:
          selectPolicy: Min                                     # avoid a herd
        scaleDown:
          stabilizationWindowSeconds: 600      # 10 min: expensive to be wrong
          policies:
          - { type: Percent, value: 10, periodSeconds: 60 }    # ≤10%/min
  triggers:
  - type: gcp-pubsub                # capacity signal
    metadata:
      subscriptionName: doc-embeddings
      mode: SubscriptionSize
      value: "500"                  # target ~500 undelivered msgs per replica
  - type: gcp-pubsub                # SLO signal: age, not depth
    metadata:
      subscriptionName: doc-embeddings
      mode: OldestUnackedMessageAge
      value: "120"                  # keep the oldest message under 2 minutes
```

For a synchronous API, scale on concurrency rather than CPU:

```yaml
# HPA on a custom metric: in-flight requests per pod (Prometheus Adapter).
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: search-api }
spec:
  scaleTargetRef: { apiVersion: apps/v1, kind: Deployment, name: search-api }
  minReplicas: 4                   # ≥ 1 per zone + 1: survives a zone loss
  maxReplicas: 100
  metrics:
  - type: Pods
    pods:
      metric: { name: http_requests_inflight }
      target: { type: AverageValue, averageValue: "20" }
      # 20 concurrent per pod. By Little's Law (L = λW), at 50 ms latency
      # that is ~400 RPS/pod; if latency degrades to 200 ms, the SAME 400 RPS
      # produces 80 in flight and the HPA scales out. CPU would not have moved.
  - type: Resource                 # CPU as a safety net, not the primary
    resource: { name: cpu, target: { type: Utilization, averageUtilization: 75 } }
  behavior:
    scaleUp:   { stabilizationWindowSeconds: 0 }
    scaleDown: { stabilizationWindowSeconds: 300 }
```

The application side of the herd fix:

```python
# Jittered, lazy pool init so 40 pods starting together don't open 800
# connections in the same second against a saturated database.
import asyncio, random

async def create_pg_pool():
    await asyncio.sleep(random.uniform(0, 3.0))     # de-synchronise the herd
    return await asyncpg.create_pool(
        dsn=settings.pg_dsn,
        min_size=2,                # NOT max_size: grow only under real load
        max_size=10,               # per-pod cap. 10 × max_replicas ≤ pgbouncer
        max_inactive_connection_lifetime=300,
        command_timeout=5,
    )
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **Reactive (HPA/KEDA):** gradual traffic changes, provisioning faster than the spike | Spikes shorter than your cold start | Always lagging by the provisioning delay; needs headroom anyway |
| **Predictive / scheduled:** known daily or weekly shape, marketing events | Genuinely unpredictable traffic | You pay for capacity you predicted; wrong predictions cost both ways |
| **Queue depth / backlog age:** async workers | Sync request-response paths | Needs a metric adapter (KEDA/Prometheus) — CPU is built in |
| **Concurrency:** sync APIs | CPU-bound compute where CPU *is* the truth | A custom metric to export and maintain |
| **Warm pool / over-provision:** slow cold start, spiky traffic | Cheap, fast-starting stateless services | You pay for idle capacity — often the correct trade |

### Follow-ups they will ask

**Q: Why is CPU the wrong autoscaling signal for a worker pulling from a queue?**
A: Because the worker is I/O-bound. It spends its time awaiting an LLM API or a database,
so CPU stays at 15% while the backlog grows without bound — the autoscaler is green and
the SLO is being violated. CPU only correlates with load for CPU-bound work. For a queue
worker, the signal is queue depth divided by throughput, which is the *age* of the backlog
in seconds and is directly comparable to a latency objective. That reframing is the whole
answer: scale on the thing your SLO is written against.

**Q: Your pods take 90 seconds to become ready. How do you handle a traffic spike?**
A: I stop trying to solve it with the autoscaler, because a reactive loop cannot respond
faster than provisioning. Four moves instead. Attack the cold start — bake model weights
into the image or load them from a local SSD instead of pulling from GCS, and use a startup
probe so Kubernetes doesn't kill a legitimately slow boot. Keep a warm pool: `minReplicas`
sized for peak-minus-headroom rather than for the average. Scale on a leading indicator —
upstream queue depth or connection count — so I begin provisioning before the spike lands
on the service. And shed load gracefully at the edge with a 429 and `Retry-After` so the
overload degrades instead of collapsing.

**Q: What's the danger of scaling down aggressively?**
A: Thrash, and the way it compounds. If I scale in as soon as the metric dips, the reduced
capacity pushes the metric back up, so I scale out again — and with a 60-second cold start
I'm permanently one step behind while paying for constant churn. Scale-in is also
disruptive in itself: every terminated pod drops connections and drains in-flight requests,
so aggressive scale-down produces user-visible errors during quiet periods, which is
absurd. The asymmetry is deliberate: the cost of over-provisioning for ten extra minutes is
a few dollars, and the cost of under-provisioning is an SLO breach.

**Q: How do you stop autoscaling from taking down your database?**
A: A hard `maxReplicas` derived from the database's connection budget, not from what
Kubernetes will allow — `maxReplicas × pool.max_size` must stay under
`max_connections` minus headroom for migrations and admin. Then PgBouncer in transaction
mode, so pod count and backend connection count are decoupled entirely and I can scale the
app tier without touching the database's limits. Plus jittered, lazy pool initialisation so
a scale-out event doesn't arrive as one synchronised connection storm. The general
principle: every autoscaler needs a ceiling set by its most fragile downstream dependency.

**Q: Should `minReplicas` ever be zero?**
A: For genuinely batch work with no latency requirement — a nightly report, a
backfill — yes, and scale-to-zero is real money. For anything user-facing, no: the first
request after idle pays the full cold start, and if the workload is bursty you're paying
that repeatedly. I'd also never run `minReplicas: 1` for something that matters, because
one replica is a single point of failure and gives you nowhere to roll a deploy. For
multi-zone availability I'd start at one per zone plus one, so losing a zone doesn't drop
me below capacity.

### Red flags — do not say this

- ❌ "We autoscale on CPU at 70%." (for I/O-bound workers) → ✅ "CPU doesn't move for
  I/O-bound work; I scale on backlog age, which is comparable to the SLO."
- ❌ "Autoscaling handles traffic spikes." → ✅ "Only spikes longer than provisioning time;
  for shorter ones I need headroom or a warm pool."
- ❌ "Scale up and down with the same thresholds." → ✅ "Asymmetric: react immediately on the
  way up, 5-10 minute stabilisation on the way down, or it thrashes."
- ❌ "Set `maxReplicas` high so we never run out." → ✅ "`maxReplicas × pool size` must stay
  under the database connection budget — otherwise autoscaling *causes* the outage."
- ❌ "Scale to zero to save money." (for a user-facing API) → ✅ "Fine for batch; for
  user-facing traffic the first request pays the full cold start."

---

## 4.9 Single Point of Failure (SPOF)

**Interview weight:** ★★★★★

> **One-liner:** A SPOF is any component whose failure takes down the system, and the ones
> that actually cause outages are never the application servers — they're the load
> balancer, DNS, the config service, the shared cache, and the deploy pipeline you need in
> order to fix things.

### Say this in the interview

> The way I hunt SPOFs is mechanical: I go through my own diagram box by box and arrow by
> arrow and ask "if this dies right now, what still works?" — and crucially I include the
> things I drew as a single box because they're managed, and the things I didn't draw at
> all. Candidates always find the database and the app servers. The ones that actually
> cause outages are elsewhere. The load balancer itself, if it's a single instance rather
> than a replicated managed service. DNS — if my registrar or my zone is unavailable,
> nobody reaches me no matter how healthy my fleet is. The config or feature-flag service,
> because if the app can't start without fetching config, that service is now in the
> critical path of every deploy and every pod restart. The shared cache, because if the
> system can't survive a cold cache, Redis isn't a cache, it's a database with no
> durability. Certificate expiry, which is a scheduled outage you've already booked. And
> the deploy pipeline, which is the meta-SPOF: if the thing you need to push a fix is down,
> your recovery time is unbounded. Then for each real SPOF I pick a redundancy pattern —
> active-active if the component is stateless or can accept concurrent writes,
> active-passive with a promotion path if it can't, which is what a Postgres primary with a
> standby is. And I'd finish with the honest part: redundancy without *tested* failover is
> theatre. A standby you have never promoted is a standby that will not promote, so I'd
> want game days and regular failover drills, not just an architecture diagram with two
> boxes.

### Mental model

**The systematic hunt.** Walk the request path outside-in, then walk the *control* path:

```text
DATA PATH — trace one request and kill each thing in turn
  registrar / domain    → domain expires or is hijacked: total outage
  DNS zone (authoritative) → nobody resolves you; healthy fleet, zero traffic
  anycast / global LB    → managed, but check: single region config?
  TLS certificate        → expiry is a SCHEDULED outage you already booked
  regional LB            → single instance? single zone? single AZ subnet?
  API gateway            → replicated? is its CONFIG a SPOF? control plane?
  app instances          → the one everyone finds. Usually already fine.
  DB primary             → active-passive + tested promotion
  DB connection pooler   → PgBouncer is a SPOF in front of an HA database
  cache                  → can you serve at all with a cold cache?
  queue / broker         → replication factor ≥ 3, min.insync.replicas = 2
  object storage         → managed and multi-zone; but is the BUCKET regional?
  third-party API        → LLM provider, payment provider: circuit break +
                           fallback model / degraded mode
  NAT gateway / egress    → one NAT per region = one egress SPOF
  shared file mount       → an NFS/Filestore mount every pod needs

CONTROL PATH — the SPOFs nobody draws
  config / feature flags → app won't boot without it ⇒ in the critical path
  secrets manager        → same: pod restart needs it, so an outage blocks
                           every scale-out and every deploy
  service discovery      → stale endpoints are often better than none:
                           cache last-known-good and fail open
  identity provider      → if every login needs the IdP, an IdP outage is
                           your outage; cache validated sessions
  container registry     → can't pull the image ⇒ can't scale out or restart
  CI/CD pipeline         → ★ the META-SPOF: you cannot ship the fix
  observability          → not a SPOF for users, but you're now blind
  the on-call runbook    → in a wiki hosted on the system that's down
```

**The redundancy patterns:**

```text
ACTIVE-ACTIVE                        ACTIVE-PASSIVE

  ┌────┐   ┌────┐                      ┌────────┐      ┌────────┐
  │ A  │   │ B  │  both serving        │ PRIMARY│─repl─►│ STANDBY│
  └──┬─┘   └─┬──┘                      └────┬───┘      └────┬───┘
     └───┬───┘                              │ serving       │ idle
      traffic                             traffic     (warm, catching up)

  + no failover step: capacity        + only one writer: no conflicts
    just reduces                      + simple consistency story
  + failover is instant               − failover takes seconds to minutes
  − needs conflict resolution for     − the standby is paid-for idle capacity
    concurrent writes                 − ★ untested promotion = no standby
  − must run ≤50% loaded each, or     − split-brain if both think they're
    losing one overloads the other      primary → needs fencing/STONITH
  Use for: stateless services, LBs,   Use for: SQL primaries, leader-elected
  read replicas, caches, gateways     singletons, schedulers, stateful stores
```

**Capacity math that people get wrong.** Redundancy is only real if the survivors can
carry the load:

```text
3 zones, active-active, must survive losing ONE zone:
   normal: each zone carries 1/3 = 33% of traffic
   after:  each survivor carries 1/2 = 50% of traffic  → +50% per zone

   ⇒ steady-state per-zone utilisation must be ≤ 66% just to SURVIVE,
     and ≤ ~50% to survive without entering the queueing regime (4.10).

2 zones (a very common "HA" setup):
   after losing one, the survivor carries 100% → it must run at ≤50%.
   ⇒ "two zones" means you pay for 2× capacity to get 1× of headroom.
     Three zones only needs 1.5×. This is why 3 AZs is the standard.
```

### Enterprise production example

**Netflix's Zuul** illustrates the useful inversion: because *every* request already
traverses the gateway, Netflix's own engineering blog lists among Zuul's responsibilities
that it "channels traffic to other cloud regions when an AWS region is in trouble." The
component that looks like the biggest SPOF is deliberately built into the mechanism for
surviving the largest failure. That's the framing to bring to an interview — a chokepoint
you must make redundant anyway is also the best place to implement failover.

The broader industry pattern worth naming, without attributing specifics: several of the
largest publicly-analysed internet outages of recent years were not server failures. They
were control-plane failures — a bad configuration change propagating globally, a BGP or
DNS misconfiguration making healthy infrastructure unreachable, or an expired certificate.
The lesson generalises cleanly: your servers are probably redundant; your *configuration
change process* is probably not, because a single bad config reaches every replica in
seconds, and redundant replicas all fail identically. Which is why staged rollout,
automatic rollback on error rate, and a config path that survives its own control plane
matter more than another replica.

### Code

Fail-open dependency handling, which is the most common concrete SPOF fix:

```python
# The rate limiter must not be able to take down the API it protects.
async def check_rate_limit(redis, key: str, limit: int, window_s: int) -> bool:
    try:
        async with asyncio.timeout(0.05):          # 50 ms: never block a request
            count = await redis.incr(f"rl:{key}")
            if count == 1:
                await redis.expire(f"rl:{key}", window_s)
            return count <= limit
    except (TimeoutError, ConnectionError):
        RATE_LIMITER_DEGRADED.inc()                 # alert on this
        return True     # FAIL OPEN: better to serve unlimited than to serve
                        # nothing. For abuse protection I'd fail CLOSED instead,
                        # and that choice must be explicit per limiter.
```

Config with a last-known-good fallback, so the config service leaves the boot path:

```python
LKG_PATH = "/var/cache/app/config.json"      # emptyDir or the image itself

async def load_config() -> dict:
    try:
        async with asyncio.timeout(3):
            cfg = await http.get_json(settings.config_url)
        Path(LKG_PATH).write_text(json.dumps(cfg))   # persist last-known-good
        return cfg
    except Exception:
        CONFIG_FETCH_FAILED.inc()
        if Path(LKG_PATH).exists():
            logger.warning("config service unreachable; using last-known-good")
            return json.loads(Path(LKG_PATH).read_text())
        # Baked into the image at build time: the pod can ALWAYS boot.
        logger.error("no cached config; using compiled-in defaults")
        return DEFAULT_CONFIG
```

Spreading replicas so "3 replicas" isn't 3 pods on one node:

```yaml
spec:
  replicas: 6
  template:
    spec:
      topologySpreadConstraints:
      - maxSkew: 1
        topologyKey: topology.kubernetes.io/zone     # even across zones
        whenUnsatisfiable: DoNotSchedule
        labelSelector: { matchLabels: { app: api } }
      - maxSkew: 1
        topologyKey: kubernetes.io/hostname          # and across nodes
        whenUnsatisfiable: ScheduleAnyway
        labelSelector: { matchLabels: { app: api } }
---
apiVersion: policy/v1
kind: PodDisruptionBudget            # stops a node drain from taking the fleet
metadata: { name: api-pdb }
spec:
  minAvailable: 4                    # of 6: a cluster upgrade can't drop below
  selector: { matchLabels: { app: api } }
```

Without `topologySpreadConstraints`, the scheduler is free to place all six pods in one
zone, and "6 replicas across 3 zones" is a claim on a diagram rather than a fact about the
cluster. Without a `PodDisruptionBudget`, a routine node-pool upgrade can drain them all.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **Active-active:** stateless services, gateways, LBs, read replicas | Single-writer stores; anything needing global ordering | You must run ≤50-66% loaded, so you pay for the headroom |
| **Active-passive:** SQL primary, leader-elected singletons | Where seconds of failover are unacceptable | Idle standby cost; failover latency; untested promotion is worthless |
| **Fail-open on a non-critical dependency** | Security controls and abuse protection | Degraded correctness during the outage — must be an explicit choice |
| **Multi-region active-active** | Anything short of a genuine regional-outage requirement | 2× infrastructure, cross-region data consistency, a large complexity step |

### Follow-ups they will ask

**Q: Walk me through the SPOFs in a diagram with a load balancer, three app servers, and
one Postgres.**
A: Postgres is the obvious one — single primary, so a standby with streaming replication
and a *tested* promotion path, plus PgBouncer for connections, noting that PgBouncer then
becomes its own SPOF and needs two instances. The load balancer next: if it's a managed
cloud LB it's already replicated, but if it's a single nginx VM it's the biggest SPOF in
the picture. Then the ones not in the diagram: DNS, the TLS certificate and its renewal
automation, the container registry the pods pull from, the config and secrets services the
app needs to boot, and the CI/CD pipeline I'd need to ship a fix. And finally the zone
layout — three app servers is meaningless if all three are in one availability zone.

**Q: You have two of everything. Are you highly available?**
A: Not necessarily, for three reasons I'd check. Capacity: with two, losing one means the
survivor takes 100%, so it must have been running at 50% or less — otherwise "HA" just
means both fail instead of one. Correlation: two instances in the same zone, on the same
node, or behind the same NAT gateway share a failure mode, so I'd verify actual placement
with topology spread constraints rather than trusting replica count. And failover
mechanics: an untested promotion path, a health check that doesn't detect the failure mode,
or a DNS TTL of an hour all mean the redundancy exists but never activates.

**Q: What's the SPOF candidates never mention?**
A: The deploy pipeline, and I'd call it the meta-SPOF. Every other failure has a bounded
recovery time only if I can ship a change; if CI, the container registry, or the artifact
store is down, my recovery time is unbounded and I'm reduced to whatever I can do by hand.
The related one is the configuration *change process*: a single bad config propagates to
every replica in seconds, and redundant replicas fail identically — which is why config
needs staged rollout and automatic rollback on error rate, exactly like code. Runbooks
hosted on the system that's down belong in the same category.

**Q: How do you handle a third-party API being a SPOF — say your LLM provider?**
A: Timeout, circuit breaker, and a fallback that produces a degraded but useful answer
rather than an error. Concretely: a hard per-request deadline, a breaker that opens after a
threshold of failures so I stop queueing doomed requests, a secondary provider or a smaller
self-hosted model behind the same interface, and a cache — including a semantic cache — so
repeated questions are served without the provider at all. And I'd decide the degraded
behaviour with the product owner in advance: for a RAG product, returning retrieved source
passages without a generated summary is a far better outage than a 500.

**Q: How do you actually verify a SPOF is fixed?**
A: You break it on purpose. A failover drill on the database in a staging environment with
production-shaped data, a zone-evacuation exercise, killing the Redis instance during a
game day to confirm the fail-open path works and the alert fires. The reason this matters
is that every untested failover I've seen has had at least one thing wrong with it — a
missing IAM permission, a hardcoded hostname, a DNS TTL nobody lowered, a replica that had
silently fallen behind. Redundancy you haven't exercised is a hypothesis.

### Red flags — do not say this

- ❌ "We have a load balancer, so there's no SPOF." → ✅ "The load balancer is itself a SPOF
  unless it's a replicated managed service — and DNS in front of it is another."
- ❌ "Redis is just a cache, its failure isn't critical." → ✅ "Only if the system survives a
  cold cache. If a cache miss storm takes down Postgres, Redis is a hard dependency."
- ❌ "We have a standby database." → ✅ "And we drill promotion, because an untested failover
  is an untested assumption."
- ❌ "Two replicas is high availability." → ✅ "Only if each runs at ≤50% and they're in
  different zones — otherwise losing one overloads the other."
- ❌ "Config is loaded at startup from the config service." → ✅ "Then the config service is
  in the critical path of every restart; I cache last-known-good and bake defaults into the
  image."

---

## 4.10 Capacity planning & headroom

**Interview weight:** ★★★★☆

> **One-liner:** You never run above about 60-70% utilization because queueing delay grows
> as `ρ/(1-ρ)` — the last 20% of capacity costs you multiples of your latency — and because
> the headroom is what absorbs an instance or zone failure.

### Say this in the interview

> Capacity planning has two constraints and people usually only know one. The first is
> redundancy: with three zones and a requirement to survive losing one, each zone must run
> at no more than about two-thirds, because the survivors pick up half the traffic each
> instead of a third. With only two zones the survivor takes everything, so you're capped
> at fifty percent — which is why three availability zones is the standard shape, since it
> needs one-and-a-half times capacity rather than two. The second constraint is queueing
> theory, and it's the one that surprises people. Mean waiting time in a queue scales as
> rho over one minus rho, where rho is utilization. At fifty percent that multiplier is
> one. At seventy percent it's about two point three. At ninety percent it's nine, and at
> ninety-five percent it's nineteen. So pushing utilization from seventy to ninety percent
> doesn't buy you twenty percent more capacity — it multiplies your queueing delay by
> roughly four, and it shows up in p99 first while your averages still look fine. Those two
> constraints compose: I'd target roughly fifty percent steady-state per instance, so that
> losing a zone puts me at seventy-five percent, which is uncomfortable but serving. And
> I'd validate it rather than assume it — a load test that ramps until latency knees over
> tells me the real per-instance capacity, and then I plan against that number instead of
> against a CPU percentage.

### Mental model

**Constraint 1 — N+1 and N+2 redundancy:**

```text
N   = the capacity you need to serve peak
N+1 = one spare unit: survives ONE failure
N+2 = two spares: survives one failure WHILE one unit is in maintenance
      (this is why "N+1" is often not enough — deploys and patching are
       planned unavailability that coincides with unplanned failures)

Zones:  survive 1 loss    max steady-state utilisation per zone
  2 zones                 50%   → you buy 2.0× capacity for 1× of headroom
  3 zones                 66%   → you buy 1.5×          ← the standard
  4 zones                 75%   → you buy 1.33×
  5 zones                 80%   → diminishing; more zones = more cross-AZ
                                   traffic cost and latency
```

**Constraint 2 — the queueing wall.** This is the number to memorise:

```text
For an M/M/1-ish queue, mean wait = service_time × ρ/(1-ρ)

   ρ (utilisation)   wait multiplier   what it feels like
   ───────────────────────────────────────────────────────────────
        50%              1.0×          smooth
        60%              1.5×          fine
        70%              2.3×          ← practical ceiling
        80%              4.0×          p99 starts hurting
        90%              9.0×          p99 is 4× worse than at 70%
        95%             19.0×          effectively an outage in the tail
        99%             99.0×          gone

   ├──────────────────────────────────────┤ wait
   │                                   ╱
   │                                 ╱
   │                             ╱
   │                        ╱
   │                 ╱
   │        ╱───────
   └──┴────┴────┴────┴────┴────┴────┴─────► ρ
     0.3  0.5  0.6  0.7  0.8  0.9  0.95

   ▲ The knee is real and it is around 0.7. Capacity "left on the table"
     above that point is not capacity — it is latency you have already spent.
```

**Compose them:** target ~50% per instance in steady state, so that a zone loss lands you
at ~75% (a 4× wait multiplier — degraded but serving) instead of at 100% (gone).

**Sizing from first principles, with Little's Law:**

```text
Little's Law:  L = λ × W     (concurrency = arrival rate × latency)

Worked example — a RAG search API:
  peak traffic          2,000 RPS
  p50 latency           120 ms   (mostly waiting on the vector DB + LLM)
  ⇒ required concurrency = 2,000 × 0.12 = 240 in-flight requests

  measured per-pod safe concurrency (from a load test, not a guess): 40
  ⇒ pods needed at 100% utilisation      = 240 / 40  = 6
  ⇒ at a 50% utilisation target          = 12
  ⇒ N+1 for a zone loss across 3 zones   = 12 × 1.5 = 18
  ⇒ round to a multiple of 3 zones       = 18 pods, 6 per zone

  Sanity-check the dependencies, because this is where plans break:
    · DB connections: 18 pods × 10 = 180. Postgres max_connections = 200?
      → PgBouncer, or lower the per-pod pool.
    · LLM provider quota: 2,000 RPS × tokens — is the account limit above it?
    · If latency DOUBLES (a slow dependency), required concurrency doubles to
      480 → I need 36 pods for the SAME traffic. This is why concurrency,
      not RPS, is the right autoscaling signal (4.8).
```

**Load testing that produces a usable number:**

```text
Ramp until it breaks, and record where the KNEE is — not where it errors.

  1. Ramp arrival rate slowly (e.g. +10% per minute), open-loop:
     a fixed arrival rate, NOT a fixed number of looping virtual users.
     Closed-loop tests self-throttle when the system slows and hide the cliff.
  2. Plot p50/p95/p99 latency AND throughput against offered load.
  3. The knee = the load where p99 starts rising faster than linearly.
     THAT is your per-instance capacity. Not the point where it 500s.
  4. Test with production-shaped data: cache hit rates, payload sizes and
     key distributions dominate the result. An empty-cache test is a
     different system.
  5. Then test the failure modes, which is where the surprises are:
     · kill one instance mid-test — does the rest hold?
     · cold cache — what is capacity at a 0% hit rate?
     · one dependency at +500 ms — does concurrency explode and OOM you?
```

### Enterprise production example

**Google's SRE practice** is the widely-cited public reference for this discipline, and two
of its ideas are worth naming precisely. The first is the **error budget**: if the SLO is
99.9% availability, the 0.1% is a budget you're allowed to spend, which turns "how much
headroom do we need" from an argument into arithmetic. The second is that they explicitly
plan capacity against *both* organic growth and inorganic demand spikes (launches,
migrations), and they insist that load testing be done against the real system rather than
inferred from resource metrics — because a CPU percentage doesn't tell you where the
latency knee is.

**AWS's** operational guidance points at the same 60-70% number from the redundancy
direction rather than the queueing one: their recommended practice for a
three-availability-zone deployment is to have enough capacity that losing one zone still
serves peak, which caps steady-state per-zone utilisation at roughly two-thirds. The
useful observation is that the two independent lines of reasoning — queueing theory and
zone redundancy — converge on the same operating point, which is why "don't run above about
70%" is such a durable rule of thumb.

### Code

Capacity arithmetic worth writing down rather than doing in your head:

```python
from dataclasses import dataclass

@dataclass
class CapacityPlan:
    peak_rps: float
    p50_latency_s: float
    per_pod_safe_concurrency: int      # from a LOAD TEST, not a guess
    zones: int = 3
    utilisation_target: float = 0.5    # steady-state per pod
    pod_db_connections: int = 10

    @property
    def required_concurrency(self) -> float:
        return self.peak_rps * self.p50_latency_s          # Little's Law

    @property
    def pods(self) -> int:
        raw = self.required_concurrency / self.per_pod_safe_concurrency
        with_headroom = raw / self.utilisation_target
        # Survive losing one zone: survivors must carry the whole load.
        survivable = with_headroom * self.zones / (self.zones - 1)
        per_zone = -(-int(survivable) // self.zones)        # ceil
        return per_zone * self.zones                        # even across zones

    def report(self) -> str:
        pods = self.pods
        return (
            f"concurrency needed : {self.required_concurrency:.0f}\n"
            f"pods               : {pods}  ({pods // self.zones}/zone)\n"
            f"steady-state util  : "
            f"{self.required_concurrency / (pods * self.per_pod_safe_concurrency):.0%}\n"
            f"util after 1 zone  : "
            f"{self.required_concurrency / (pods * (self.zones-1)/self.zones * self.per_pod_safe_concurrency):.0%}\n"
            f"DB connections     : {pods * self.pod_db_connections}"
            f"  ← check against max_connections\n"
            f"queue wait mult.   : see the rho/(1-rho) table"
        )

print(CapacityPlan(peak_rps=2000, p50_latency_s=0.12,
                   per_pod_safe_concurrency=40).report())
```

An open-loop load test — a fixed *arrival rate*, which is what exposes the knee:

```javascript
// k6: ramping-arrival-rate holds the ARRIVAL RATE, so the system cannot
// self-throttle by slowing down. A ramping-vus test would hide the cliff.
import http from 'k6/http';
import { Trend } from 'k6/metrics';

const searchLatency = new Trend('search_latency', true);

export const options = {
  scenarios: {
    ramp: {
      executor: 'ramping-arrival-rate',
      startRate: 100, timeUnit: '1s',
      preAllocatedVUs: 200, maxVUs: 3000,   // must exceed λ × W at the worst
      stages: [                              // latency, or k6 becomes the limit
        { target: 500,  duration: '3m' },
        { target: 1000, duration: '3m' },
        { target: 1500, duration: '3m' },
        { target: 2000, duration: '3m' },
        { target: 3000, duration: '3m' },    // past expected peak: find the knee
      ],
    },
  },
  thresholds: {
    // Record the offered load at which this first fails: that is capacity.
    'search_latency{expected_response:true}': ['p(99)<800'],
    http_req_failed: ['rate<0.01'],
  },
};

export default function () {
  const res = http.post(`${__ENV.BASE_URL}/v1/search`,
    JSON.stringify({ q: pickRealisticQuery() }),   // real key distribution:
    { headers: { 'Content-Type': 'application/json' } });  // cache hit rate
  searchLatency.add(res.timings.duration);                 // dominates results
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **~50% steady-state target** | Batch/async work with no latency SLO (run those hot — 90%+ is fine) | Roughly 2× the instances of a naive plan |
| **N+2 (spare for failure *and* maintenance)** | Non-critical internal services | One more unit of capacity per failure domain |
| **3 zones** | A single-zone dev environment | Cross-zone network cost and a little latency |
| **Regular open-loop load testing** | Never — but do it in a production-shaped environment | Engineering time, and a realistic test environment to maintain |

### Follow-ups they will ask

**Q: Why can't you run at 90% utilization? You're wasting money.**
A: Because that last 20% isn't capacity, it's latency I've already spent. Queueing delay
scales as `ρ/(1-ρ)`, so moving from 70% to 90% multiplies mean wait by about four, and the
tail moves much more than the mean — p99 degrades badly while the average still looks
acceptable, which is exactly the failure that surprises teams. On top of that, 90%
utilization leaves no room to absorb an instance or zone failure, so a single pod loss
pushes the survivors past 100% and the system doesn't degrade, it collapses. The extra
instances are buying tail latency and failure tolerance, and both are cheaper than the
incident.

**Q: How do you find real per-instance capacity?**
A: An open-loop load test — a fixed arrival rate that ramps — against a
production-shaped environment, and I record the *knee*: the offered load at which p99 starts
rising faster than linearly. That's capacity. Two things I'd insist on. It has to be
open-loop, because a closed-loop test with a fixed number of looping virtual users
self-throttles when the system slows down and completely hides the cliff. And the data has
to be realistic, because cache hit rate and key distribution dominate the result — a test
against a warm cache and a uniform key distribution measures a system I don't operate.

**Q: What if traffic grows 10× in a month?**
A: I'd separate the tiers, because they scale differently. The stateless tier is mostly a
budget and quota question — autoscaling handles it if `maxReplicas` and the connection
budget are raised. The data tier is where the real work is, and 10× is the point where a
vertical bump plus read replicas plus caching stops being enough, so I'd want to know the
read/write split first. If it's read-heavy, replicas and caching go a long way. If it's
write-heavy, that's a sharding conversation and it needs lead time measured in quarters,
not a scaling policy. I'd also check the third-party quotas — an LLM provider's rate limit
does not autoscale because I asked it to.

**Q: You're at 55% CPU but p99 latency is bad. What now?**
A: CPU isn't the constraint, so I stop looking at it. The usual suspects are a connection
pool where requests queue for a connection while CPU idles, a saturated thread or event
loop blocked on synchronous work, lock contention, or a slow downstream dependency inflating
concurrency. The measurement that answers it is a latency breakdown: how much of p99 is
spent waiting to *start* versus executing. If it's queueing, the fix is pool sizing or
concurrency limits, not more CPU. This is also the argument for autoscaling on concurrency
rather than CPU — concurrency would have caught it and CPU never will.

**Q: How does capacity planning change for an LLM-backed service?**
A: The bottleneck moves off my infrastructure, so the units change. Concurrency is still
the right frame via Little's Law, but `W` is dominated by time-to-first-token plus
generation time — often two to four seconds — so required concurrency for the same RPS is
twenty to forty times higher than for a normal API. That means my own pods are cheap and
mostly idle, and the real constraints are the provider's rate limit and my token budget. So
I plan in tokens per minute rather than requests per second, add a semantic cache to cut
the request count directly, and treat a smaller fallback model as capacity rather than
purely as a reliability feature.

### Red flags — do not say this

- ❌ "We run at 85% CPU, we're efficient." → ✅ "Queueing delay is ~5.7× at 85% versus 2.3×
  at 70%, and there's no room to absorb a failure — that's tail latency, not efficiency."
- ❌ "Autoscaling means we don't need capacity planning." → ✅ "Autoscaling can't beat
  provisioning delay, and it needs a `maxReplicas` derived from the database's connection
  budget — both come out of a capacity plan."
- ❌ "We load tested and it handled 5,000 RPS." → ✅ "It handled 5,000 RPS at what p99, with
  what cache hit rate, and where was the knee? The number alone isn't a capacity."
- ❌ "N+1 is enough." → ✅ "N+1 covers one failure; it doesn't cover a failure during a
  deploy or a node upgrade, which is why critical tiers get N+2."
- ❌ "Two availability zones gives us HA." → ✅ "Two zones caps you at 50% utilisation to
  survive one loss; three zones only needs 66%, so three is cheaper for the same
  guarantee."

---

## Module 04 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. When is vertical scaling the *better* senior answer than horizontal? Give two concrete
   components and say what stops each one.
2. Why does giving Redis more vCPUs not increase command throughput?
3. Name six kinds of state that break horizontal scaling, beyond "the session".
4. Compare sticky sessions, an external session store, and signed tokens on three axes:
   per-request cost, behaviour when an instance dies, and revocation.
5. A WebSocket connection is inherently pinned to one instance. Describe the full design
   that lets any instance deliver a message to a user connected elsewhere.
6. Why do Envoy, Linkerd and gRPC default to power-of-two-choices rather than least
   connections? And when does least connections win?
7. Why is "least response time" dangerous, and what two changes make it safe?
8. Why does a gRPC service behind an L4 load balancer send all its traffic to one pod?
   Give two different fixes.
9. Draw the cascade that happens when a liveness probe checks the database and the
   database has a 30-second blip.
10. What are the exact semantics of startup, liveness and readiness probes? Why must
    readiness fail *faster* than liveness?
11. You see a burst of 502s on every deploy. Explain the race and the four-part fix.
12. Do the modulo-hashing math: going from 100 nodes to 101, what fraction of keys move,
    and why is the answer `N/(N+1)`? What is it with consistent hashing?
13. Why are virtual nodes required rather than optional? Give both reasons.
14. Consistent hashing doesn't help with a single viral key. Name three things that do.
15. Why is CPU the wrong autoscaling signal for a queue worker, and what is `backlog_age`?
16. Explain the scale-up / scale-down asymmetry and give the two stabilisation windows
    you'd configure.
17. What is the thundering herd on scale-out, and what four things do you do about it?
18. List eight SPOFs that are not the database or the application servers.
19. Why does surviving the loss of one zone out of three cap per-zone utilization at 66%?
    What does it cap it at with two zones?
20. Recite the `ρ/(1-ρ)` table at 50, 70, 90 and 95 percent. Why can't you run at 90%?
21. Size a service from scratch: 2,000 RPS, 120 ms p50, 40 safe concurrent requests per
    pod, 3 zones, surviving one zone loss. Show the arithmetic.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Queueing wait multiplier `ρ/(1-ρ)` | 50%→1.0×, 70%→2.3×, 80%→4×, 90%→9×, 95%→19× |
| Practical utilization ceiling | ~70%; target ~50% steady-state per instance |
| Max per-zone utilization to survive losing 1 zone | 2 zones → 50%; 3 zones → 66%; 4 → 75% |
| Capacity multiple bought | 2 zones = 2.0×; 3 zones = 1.5× ← why 3 AZs is standard |
| Little's Law | concurrency = RPS × latency (`L = λW`) |
| Modulo hashing, N → N+1 | `N/(N+1)` of keys remap: 80% at N=4, 99% at N=100 |
| Consistent hashing, N → N+1 | ~`1/(N+1)` of keys move (~1% at N=100) |
| Virtual nodes per physical node | 100-256; imbalance shrinks as ~`1/√V` |
| Imbalance without vnodes | largest arc ≈ `ln N` × the mean |
| Cassandra `num_tokens` default | 256 in 3.x → 16 in 4.0 (smarter allocation) |
| Bounded-load consistent hashing | cap = `⌈c·m/n⌉`, `c` ≈ 1.25-1.5 |
| Vimeo Skyfire scale (bounded-load CH in production) | ~1 billion DASH/HLS requests/day |
| HAProxy: least-conn vs power-of-two | least-conn ≈ 4% better peak load, RPS and latency |
| Power of two choices, max load | `Θ(log n / log log n)` → `Θ(log log n)` |
| Netflix Zuul 2 (async Netty) | ~25% more throughput, ~25% less CPU on the push cluster |
| Redis session lookup, same VPC | ~0.3-0.5 ms |
| L7 load balancer added latency | ~0.5-2 ms (vs tens of µs for L4) |
| TLS handshake round trips | 1 RTT (TLS 1.3), 2 RTT (TLS 1.2) |
| Kubernetes `terminationGracePeriodSeconds` default | 30 s — usually too short; set 45 s+ |
| `preStop` sleep to cover endpoint propagation | ~10 s |
| Readiness vs liveness failure budget | readiness ~10 s, liveness ~30 s (readiness first) |
| Startup probe budget for a slow model load | `periodSeconds 5 × failureThreshold 30` = 150 s |
| HPA scale-down stabilization window default | 300 s (scale-up default: 0 s) |
| JWT access token lifetime to propose | 5-15 min, with a revocable refresh token |
| AWS ALB fail-open behaviour | all targets unhealthy → routes to all of them anyway |

---

**Next:** [Module 05 — Relational Databases](./05_Databases_Relational.md)
