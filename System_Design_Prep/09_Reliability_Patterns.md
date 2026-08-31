# Module 09 — Reliability: Retries, Idempotency, Circuit Breakers & Backpressure

> **What this module makes you able to do:** take any design you have just drawn on the
> whiteboard and answer "what happens when this dependency gets slow?" with a specific,
> numbered answer — timeout value, retry policy, idempotency key, breaker threshold,
> queue bound, and what the user sees while it is broken.
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** [Module 05 — Databases, ACID & Indexes](./05_Databases_Relational.md),
> [Module 08 — Messaging, Kafka & Events](./08_Messaging_And_Events.md)

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 9.1 | [Designing for failure](#91-designing-for-failure) | ★★★★☆ |
| 9.2 | [Timeouts](#92-timeouts) | ★★★★★ |
| 9.3 | [Retries and backoff](#93-retries-and-backoff) | ★★★★★ |
| 9.4 | [Idempotency](#94-idempotency) | ★★★★★ |
| 9.5 | [Exactly-once vs at-least-once](#95-exactly-once-vs-at-least-once) | ★★★★☆ |
| 9.6 | [Dead-letter queues](#96-dead-letter-queues) | ★★★★☆ |
| 9.7 | [Circuit breakers](#97-circuit-breakers) | ★★★★★ |
| 9.8 | [Bulkheads](#98-bulkheads) | ★★★☆☆ |
| 9.9 | [Backpressure](#99-backpressure) | ★★★★☆ |
| 9.10 | [Load shedding and graceful degradation](#910-load-shedding-and-graceful-degradation) | ★★★★☆ |
| 9.11 | [Cascading failures](#911-cascading-failures) | ★★★★★ |
| 9.12 | [Distributed locks](#912-distributed-locks) | ★★★★☆ |
| 9.13 | [Leader election](#913-leader-election) | ★★★☆☆ |
| 9.14 | [Saga pattern and compensating transactions](#914-saga-pattern-and-compensating-transactions) | ★★★★☆ |
| 9.15 | [Chaos engineering and game days](#915-chaos-engineering-and-game-days) | ★★★☆☆ |

---

## 9.1 Designing for failure

> **One-liner:** Reliability is not the absence of failure; it is the property that a
> failure in one component produces a bounded, predictable, and recoverable effect.

### Say this in the interview

> I design on the assumption that every remote call can be slow, can fail, or can
> succeed without me finding out — and that third case is the one that actually costs
> money. A timeout is not an answer, it is an unknown: the payment may have gone
> through. So for every dependency in a design I write down four things: what error
> classes it can return, whether each is transient or permanent, whether the operation
> is safe to repeat, and what the user sees when it is down. That gives me my timeout,
> my retry policy, my idempotency key, and my fallback. The habit I care most about is
> asking "what breaks first?" — in almost every service I have worked on the answer is
> a thread or connection pool filling up behind a slow dependency, not the dependency
> itself returning errors. And I try to keep the blast radius small: a failure in the
> embedding provider should degrade search quality, not take down login. I'd usually
> start by naming the single dependency whose slowness would take the whole system with
> it, because that is where the first timeout and breaker go.

### Mental model

There is a standard taxonomy of failure, and knowing it makes you sound like you have
read the literature rather than just the blog posts:

| Failure class | What happens | Example in his stack |
|---|---|---|
| **Crash** | Process stops, cleanly detectable | Pod OOM-killed, node preempted |
| **Omission** | Message or response never arrives | Pub/Sub message dropped by a buggy ack |
| **Timing** | Response arrives, but too late to be useful | Postgres query takes 9 s, client gave up at 2 s |
| **Byzantine** | Component returns *wrong* data confidently | Cache returns another tenant's row after a key-prefix bug |

Cross-cut that with duration:

- **Transient** — will succeed if repeated: connection reset, 503, lock timeout,
  Pub/Sub redelivery, a 429 from OpenAI. **Retry these.**
- **Permanent** — will never succeed if repeated: 400, 401, 404, schema violation,
  a prompt that exceeds the model's context window. **Do not retry these**; retrying a
  permanent error is pure amplification.

The hardest class is **partial failure**: the request half-happened. Charge succeeded,
response lost. Row written, event not published. This is the class that makes
[idempotency](#94-idempotency) and the [saga pattern](#914-saga-pattern-and-compensating-transactions)
necessary, and it is unique to distributed systems — a single-process function call
either returns or throws.

**Blast radius thinking** means drawing the dependency graph and asking, for each edge,
"if this edge becomes infinitely slow, what set of user-visible features stops working?"

```
                     +---------------------+
   login  ---------->|   auth-service      |----> Postgres (users)
                     +---------------------+
                                                  BLAST RADIUS A
   ================================================================
                     +---------------------+
   chat   ---------->|   rag-service       |--+-> Postgres (docs)
                     +---------------------+  |
                                              +-> pgvector  (retrieval)
                                              +-> OpenAI    (generation)
                                                  BLAST RADIUS B
```

If `rag-service` and `auth-service` share one connection pool or one thread pool, you
have merged the two blast radii and an OpenAI incident logs everybody out. Keeping them
separate is [bulkheading](#98-bulkheads).

### Enterprise production example

**Bronson, Aghayev, Charapko and Zhu** formalised the worst version of this in the
HotOS '21 paper *Metastable Failures in Distributed Systems*. Their central observation
is that a system has three states, not two: **stable** (recovers on its own when extra
load is removed), **vulnerable** (healthy, handling load fine, but a positive feedback
loop *can* be ignited), and the **metastable failure state** (goodput is unusably low
and stays low *even after the trigger is removed*). Their point that stings: most
production systems run in the vulnerable state permanently, because it is much more
efficient than the stable state. The trigger gets blamed in the postmortem; the real
root cause is the **sustaining effect**. The follow-up USENIX study *Metastable Failures
in the Wild* examined public incident reports from Google, AWS, Azure, IBM, Spotify and
Cassandra and found the sustaining effect was the **retry policy in more than half** of
them. See [9.11](#911-cascading-failures).

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Any call crosses a process boundary | The call is in-process and cannot partially fail | Every guard (timeout, breaker, dedup store) is code you must own, tune and monitor |
| You have a dependency you do not operate (Stripe, OpenAI, a partner API) | You are prototyping and correctness is not yet the goal | Fallbacks double the number of code paths, and the fallback path is the one that is never tested |

### Follow-ups they will ask

**Q: A payment API call times out. What do you do?**
A: Nothing automatically destructive. A timeout is an unknown outcome, not a failure —
the charge may have succeeded. I retry the *same* request with the *same*
`Idempotency-Key`, so the provider either executes it once or replays the stored
response. If retries are exhausted I leave the payment in a `pending` state and
reconcile against the provider's ledger, rather than telling the user it failed.

**Q: Which failure is worse — a component that is down, or one that is slow?**
A: Slow, by a wide margin. A down dependency fails fast, so my thread returns and my
breaker trips. A dependency at p99 = 30 s with no timeout holds every worker hostage and
converts a partial outage into a total one. That is why I treat latency as an error:
[circuit breakers](#97-circuit-breakers) should trip on slow-call rate, not just error
rate.

**Q: How do you decide where to put reliability effort first?**
A: I rank dependencies by (blast radius × probability of being slow). For a RAG service
that is almost always the LLM provider — highest latency variance, external, and on the
critical path of the main feature — so it gets the tightest timeout, its own bulkhead,
a breaker, and a degraded mode that returns retrieved passages without a generated
answer.

### Red flags — do not say this

- ❌ "We'll add retries so it's reliable." → ✅ "Retries help with transient faults, but
  without a budget and jitter they are the most common sustaining effect in cascading
  failures, so I pair them with a cap of three attempts and a 10% retry budget."
- ❌ "The database is highly available so we don't need to handle failure." → ✅ "HA
  reduces the frequency of failure, not the requirement to handle it — a Postgres
  failover is still 10–30 seconds of connection errors that my app has to survive."
- ❌ "If it times out we show an error." → ✅ "For a read, yes. For a write, a timeout is
  an unknown outcome, so I reconcile rather than guess."

---

## 9.2 Timeouts

> **One-liner:** An unbounded timeout is the single most effective way to convert one
> slow dependency into a full outage, because it lets a slow callee consume the caller's
> entire concurrency budget.

### Say this in the interview

> Every remote call in my services has an explicit timeout, and I derive it from the
> dependency's measured p99 rather than picking a round number. If Postgres serves that
> query at p99 = 120 ms, I set the timeout around 300 to 400 ms — roughly two to three
> times p99 — which is generous enough that normal jitter doesn't cause spurious
> failures but tight enough that a stall frees the worker fast. A 30-second default is
> the dangerous case: with 50 workers and a dependency stuck at 30 seconds, I can only
> serve about 1.7 requests per second before every worker is parked, and my health check
> starts failing even though nothing in my process is broken. I also set three separate
> timeouts, not one: connect, read, and a total deadline for the whole operation,
> because a slow byte-drip response can beat a per-read timeout forever. And I propagate
> the remaining budget down the call chain — gRPC does this natively with deadlines — so
> a downstream service never spends 2 seconds computing an answer for a caller who gave
> up 1.5 seconds ago. I'd size the caller's timeout below its own client's timeout, so
> the failure surfaces at the layer that can actually do something about it.

### Mental model

**Little's Law is why this matters.** Concurrency = throughput × latency. Rearranged:
throughput = concurrency / latency. Your service's capacity is fixed by its worker pool.

```
  Workers = 50,  normal latency = 100 ms  ->  500 req/s capacity
  Workers = 50,  stalled at 30 s          ->  1.7 req/s capacity
                                              (a 300x capacity loss)
```

Nothing crashed. No error was logged by the dependency. You simply have no workers.

**Choose the number from data.** The recipe:

1. Measure the dependency's latency distribution (p50 / p95 / p99 / p99.9).
2. Timeout ≈ **2–3 × p99** for a fast internal call; for a high-variance external call
   like an LLM, use p99 plus a margin, because p99 and p99.9 can be seconds apart.
3. Sanity-check against the user-facing budget: the sum of your timeouts on the critical
   path must be **less** than your own SLO, or your timeout can never fire in time to be
   useful.
4. Re-derive it quarterly. A timeout set against 2023 latency is a config bug in 2026.

**Three timeouts, not one:**

| Timeout | Guards against | Typical internal value |
|---|---|---|
| **Connect** | TCP/TLS handshake hanging, dead host, SYN blackhole | 100–500 ms (same VPC: 50–100 ms) |
| **Read / socket** | Silence *between* bytes after the connection is up | 1–2 × the expected response time |
| **Total / deadline** | The whole operation, including retries and slow streaming | Your remaining request budget |

Only the total deadline is safe on its own. A malicious or sick server that sends one
byte every 900 ms never trips a 1 s read timeout and holds your worker indefinitely —
this is the Slowloris shape, applied to you as a client.

**Deadline propagation (timeout budgets).** The right mental model is a budget that is
*spent*, not a per-hop constant.

```
 client sets deadline = now + 2000 ms
     |
     v  budget 2000
 +--------------+   1900   +---------------+   1400   +-------------+
 | api-gateway  |--------->| order-service |--------->| pay-service |
 | t/o = 1900   |          | t/o = 1400    |          | t/o = 900   |
 +--------------+          +---------------+          +------+------+
                                                             | 900
                                                             v
                                                    +------------------+
                                                    |  Stripe  t/o=800 |
                                                    +------------------+
   Each hop passes down (budget - time already spent - its own margin).
   If budget <= 0 on arrival: fail immediately, do NOT call downstream.
```

gRPC does this for free: a client `deadline` travels in the `grpc-timeout` header and
every hop can read `context.Context.Deadline()` / `ServicerContext.time_remaining()`.
With plain HTTP you must do it yourself — pass an `X-Request-Deadline` header (absolute
Unix millis, not a duration, so clock-relative math is unambiguous) and have each service
clamp its own client timeout to what remains. **Fail fast on arrival if the budget is
already exhausted**: doing the work for a caller who has left is pure waste, and during
an incident it is the waste that keeps you down.

### Enterprise production example

**Shopify** publishes a worked example of deriving timeouts from measurement in *Your
Circuit Breaker is Misconfigured*. For a Rails worker configured with 2 threads talking
to **42 separate Redis instances**, each Redis had its own circuit and a service timeout
of **0.25 s**. From production metrics they knew **99% of Redis requests completed in
under 50 ms** — so in the breaker's half-open state they used a much tighter
`half_open_resource_timeout` of **50 ms** instead of the normal 250 ms, and raised
`error_timeout` to **30 s**. The reasoning is exactly the p99-derived logic above: the
probe only needs to be generous enough to succeed when Redis is healthy, and every
millisecond beyond that is wasted worker utilisation during an outage.

### Code

Python — all three timeouts, plus a propagated deadline:

```python
import time, asyncio, httpx
from fastapi import Header, HTTPException

# connect: TCP+TLS.  read: silence between bytes.  write/pool: send + pool wait.
TIMEOUTS = httpx.Timeout(connect=0.5, read=2.0, write=1.0, pool=0.5)
LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)
client = httpx.AsyncClient(timeout=TIMEOUTS, limits=LIMITS)

MARGIN_MS = 50  # leave time to serialise our own response


async def call_pricing(payload: dict, x_request_deadline: str = Header(None)):
    """x_request_deadline is absolute epoch millis, set by the edge."""
    if x_request_deadline:
        budget = int(x_request_deadline) - int(time.time() * 1000) - MARGIN_MS
        if budget <= 0:
            # Caller has already given up. Doing the work now is pure waste.
            raise HTTPException(504, "deadline exceeded before dispatch")
    else:
        budget = 2000

    hop_timeout = min(budget, 900) / 1000
    try:
        # httpx has no single "total" timeout, so wrap the whole call.
        resp = await asyncio.wait_for(
            client.post(
                "https://pricing.internal/quote",
                json=payload,
                headers={"X-Request-Deadline": str(
                    int(time.time() * 1000) + int(hop_timeout * 1000))},
            ),
            timeout=hop_timeout,
        )
    except (asyncio.TimeoutError, httpx.TimeoutException):
        raise HTTPException(504, "pricing timeout")
    resp.raise_for_status()
    return resp.json()
```

Node — `undici` separates header and body timeouts, and `AbortSignal.timeout` gives you
the total:

```js
import { request } from 'undici';

const TOTAL_MS = 900;

export async function getQuote(payload, deadlineMs) {
  const budget = deadlineMs ? deadlineMs - Date.now() - 50 : TOTAL_MS;
  if (budget <= 0) throw Object.assign(new Error('deadline exceeded'), { status: 504 });

  const hop = Math.min(budget, TOTAL_MS);
  try {
    const { statusCode, body } = await request('https://pricing.internal/quote', {
      method: 'POST',
      body: JSON.stringify(payload),
      headers: { 'content-type': 'application/json',
                 'x-request-deadline': String(Date.now() + hop) },
      connectTimeout: 500,   // TCP + TLS
      headersTimeout: 600,   // time to first byte of the response head
      bodyTimeout: 800,      // max silence between body chunks
      signal: AbortSignal.timeout(hop), // hard ceiling on the whole operation
    });
    if (statusCode >= 500) throw Object.assign(new Error('upstream'), { retryable: true });
    return await body.json();
  } catch (err) {
    if (err.name === 'TimeoutError' || err.name === 'AbortError') {
      throw Object.assign(new Error('pricing timeout'), { status: 504, retryable: true });
    }
    throw err;
  }
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Always, on every remote call | Never — "no timeout" is not a valid design | A too-tight timeout manufactures failures and wastes work the dependency already did |
| Deadline propagation, when the chain is 3+ hops | A single-hop call where the client timeout is enough | Plumbing: every service and client library must read and honour the header |

### Follow-ups they will ask

**Q: Your timeout is 2× p99 and now 1% of requests fail that used to succeed. Is that
wrong?**
A: Not necessarily — that is the trade I chose. A timeout converts unbounded latency
into a bounded, retryable error, and a fast 504 that the client can retry with a fresh
idempotency key is better than a worker parked for 30 s. If the 1% is genuinely
legitimate slow work, the fix is not a longer timeout, it is making that work
asynchronous: accept, return 202, and let the client poll.

**Q: Where does the timeout for an LLM call come from? p99 makes no sense when output
length varies.**
A: Latency there is a function of output tokens, so a single timeout is the wrong shape.
I bound `max_tokens` first, which bounds the work, then set a total deadline from
(measured time-to-first-token p99) + (tokens × measured per-token p99) plus margin. With
streaming I enforce an *inter-token* timeout — say 5 s of silence — rather than a total,
because a legitimately long answer should not be killed while it is still producing
tokens.

**Q: What is the failure mode of setting timeouts per hop instead of propagating a
budget?**
A: Inversion — a downstream hop with a longer timeout than its caller. The caller gives
up at 1 s, the callee keeps working for 3 s, and you burn capacity producing answers
nobody will read. During an incident that orphaned work is what prevents recovery.
Propagating an absolute deadline makes the inversion structurally impossible.

**Q: Should the timeout include retries?**
A: The *total deadline* must, or your worst case is silently attempts × per-attempt
timeout. With 3 attempts at a 2 s timeout plus backoff you have promised the user a 2 s
call and built a 7 s one. I enforce one deadline for the whole operation and stop
retrying when the remaining budget is smaller than the next attempt's timeout.

### Red flags — do not say this

- ❌ "We use a 30 second timeout." → ✅ "I derive it from the dependency's p99 — about
  300 ms for that Postgres query — because at 30 s a single stall consumes my whole
  worker pool."
- ❌ "The HTTP client has a default timeout." → ✅ "Several popular clients default to no
  timeout at all — Python `requests` and Node's `http` both wait forever — so I set it
  explicitly and assert it in a test."
- ❌ "One timeout per call is enough." → ✅ "Connect, read, and total are three different
  failures; a byte-per-second response defeats a read timeout but not a total deadline."

---

## 9.3 Retries and backoff

> **One-liner:** A retry trades extra load for another chance at success — which is a
> good trade when failures are independent and a catastrophic one when they are
> correlated, so retries need backoff, jitter, and a budget.

### Say this in the interview

> Retries are the highest-leverage and most dangerous reliability tool I have. My rules
> are: retry only genuinely retryable errors — 5xx, 429, connection resets, timeouts —
> and never a 4xx, because a 400 will be a 400 forever and retrying it is pure
> amplification. Cap attempts at three. Use exponential backoff, and always add jitter,
> because without it every client that failed at the same instant retries at the same
> instant and you get a synchronised wave that re-kills the dependency the moment it
> comes back. AWS published the canonical analysis of this: with 100 contending clients,
> adding full jitter cut total call count by more than half compared to plain
> exponential backoff. Then two things people forget. First, a retry budget — Google's
> SRE practice is to retry only while retries are under about 10% of your requests,
> which holds worst-case load growth to roughly 1.1x instead of 3x. Second, retries
> multiply across layers: the Google SRE book's own example is a browser, frontend and
> backend each doing 4 attempts, which is 64 attempts on an already-overloaded database
> from one user action. So I pick exactly one layer to own the retry — normally the one
> closest to the failing dependency — and every layer above it fails fast. And every
> retried write carries an idempotency key, because otherwise I am not retrying, I am
> duplicating.

### Mental model

**Retry only what can succeed.** The classification is the whole game:

| Signal | Retry? | Why |
|---|---|---|
| Connection refused / reset, DNS failure | Yes | Never reached the server, or definitely not processed |
| Read timeout on a **read** | Yes | Idempotent by nature |
| Read timeout on a **write** | Yes, **with an idempotency key** | Outcome unknown — this is the dangerous one |
| 500, 502, 503, 504 | Yes | Server-side, plausibly transient |
| 429 | Yes, but honour `Retry-After` | The server is telling you the rate, so obey it |
| 400, 401, 403, 404, 409 (validation), 422 | **No** | Deterministic; a retry cannot change the outcome |
| 409 from an idempotency layer (in-flight) | Yes, after a short delay | Means "the original is still running" |

**Why jitter is mandatory.** Backoff alone does not reduce contention; it just moves
everyone to the same later instant.

```
  Exponential backoff, NO jitter (200/400/800 ms) — 100 clients:

  load |####                ####                ####
       |####                ####                ####
       |####                ####                ####
       +-----|-------------|--------------------|---------> t
            200ms         600ms               1400ms
       Same synchronised spike, three times. Recovery re-kills the dep.

  Full jitter, delay = rand(0, 200 * 2^n):

  load |#  # ## #  #  ## #   # #  ## #  #  # ##  #
       +----------------------------------------------> t
       Same total retries, ~1/4 the peak rate. The dep can drain.
```

The three variants, verbatim from AWS's simulator:

| Name | Formula | Character |
|---|---|---|
| **Full jitter** | `sleep = rand(0, min(cap, base * 2^n))` | Memoryless, best spread, can sleep ~0 |
| **Equal jitter** | `sleep = v/2 + rand(0, v/2)` where `v = min(cap, base*2^n)` | Guarantees a minimum wait |
| **Decorrelated jitter** | `sleep = min(cap, rand(base, prev * 3))` | Walks forward from the last delay |

**Be honest about AWS's own conclusion**, because getting this right is a senior signal:
in their simulation full and equal jitter did approximately the same amount of client
work, and **decorrelated jitter did *more* calls but finished slightly faster**. Equal
jitter was the loser among the jittered options — slightly more work than full jitter and
noticeably slower. All three crushed the no-jitter approaches. So: **full jitter is the
right default**; decorrelated is worth it when time-to-recovery matters more than call
count. Anyone who tells you decorrelated is strictly better has not read the graphs.

**Retry budgets.** Backoff shapes *when* retries land; it does nothing about *how many*.
Google's SRE practice combines two limits:

- **Per-request cap:** ~3 attempts, then bubble the error up.
- **Per-client budget:** each client tracks the ratio of its requests that are retries
  and retries only while that ratio is **below 10%**. The published arithmetic: the
  per-request cap alone lets worst-case traffic grow to just under **3×**; adding the
  10% budget holds it to about **1.1×**.
- **Process-wide ceiling** as a backstop, e.g. *"only 60 retries per minute in a
  process"* — the SRE book's own example.

The related primitive is **adaptive throttling**: reject a retry with probability
`max(0, (requests - K * accepts) / (requests + 1))` over a rolling window, with `K ≈ 2`.
While the dependency is accepting, the numerator stays negative and you never throttle;
as acceptances collapse, rejection probability climbs smoothly toward 1. gRPC ships the
same idea as `retryThrottling` (a token bucket) in its service config.

**Retry amplification.** This is the interview line to have ready. From the Google SRE
book: if the database is overloaded and the JavaScript client, the frontend and the
backend each issue 3 retries (4 attempts), a single user action can produce
**4³ = 64 attempts** on the database.

```
  user action                        1
    -> browser  4 attempts           4
      -> frontend 4 attempts        16
        -> backend 4 attempts       64  requests hit the sick database
```

The fix is architectural, not numeric: **exactly one layer owns the retry.** Normally the
layer immediately above the failing dependency — it has the best error detail and
duplicates the least work. Every layer above it must fail fast and propagate a
non-retryable status.

### Enterprise production example

**AWS** (Marc Brooker, *Exponential Backoff And Jitter*, AWS Architecture Blog, 2015)
simulated optimistic-concurrency writers against a remote store with mean network delay
10 ms and variance 4 ms. Plain capped exponential backoff barely helped: the time-series
plot showed the calls still arriving in tight clusters, just with idle gaps between them.
Adding full jitter **cut the call count by more than half at 100 contending clients** and
also reduced time to completion. AWS's 2023 update to the post notes the pattern is now
built into the AWS SDKs' standard and adaptive retry modes, so you get it without writing
it. Their caveat is worth repeating: jitter does not change the fact that total work
grows as N² under contention — it just makes N² tolerable at realistic N.

### Code

Production-shaped retry wrapper: error classification, a total deadline, decorrelated
jitter, `Retry-After` honouring, and a shared token-bucket budget.

```python
import asyncio, random, time
import httpx

BASE, CAP = 0.1, 10.0        # seconds
MAX_ATTEMPTS = 3
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


class RetryBudget:
    """Token bucket: refill on success, spend on retry. Caps amplification
    at roughly `ratio` of traffic even when everything is failing."""

    def __init__(self, ratio: float = 0.1, capacity: float = 100.0):
        self.ratio, self.capacity, self.tokens = ratio, capacity, capacity

    def on_result(self, ok: bool) -> None:
        if ok:
            self.tokens = min(self.capacity, self.tokens + self.ratio)

    def try_spend(self) -> bool:
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False   # budget exhausted: fail fast, let the dependency breathe


async def request_with_retry(client: httpx.AsyncClient, budget: RetryBudget,
                             deadline: float, **kw) -> httpx.Response:
    sleep = BASE
    last_exc = None
    for attempt in range(MAX_ATTEMPTS):
        if time.monotonic() >= deadline:
            raise TimeoutError("deadline exhausted before attempt")
        try:
            resp = await client.request(timeout=min(2.0, deadline - time.monotonic()), **kw)
            if resp.status_code not in RETRYABLE_STATUS:
                budget.on_result(ok=resp.status_code < 500)
                return resp                       # includes 4xx: never retried
            retry_after = float(resp.headers.get("retry-after", 0) or 0)
            last_exc = httpx.HTTPStatusError("retryable", request=resp.request,
                                             response=resp)
        except (httpx.TransportError, httpx.TimeoutException) as exc:
            retry_after, last_exc = 0.0, exc

        if attempt == MAX_ATTEMPTS - 1 or not budget.try_spend():
            break
        # Decorrelated jitter: rand(base, prev*3). Swap for random.uniform(0, sleep*2)
        # to get AWS "full jitter", which uses less total work.
        sleep = min(CAP, random.uniform(BASE, sleep * 3))
        delay = max(sleep, retry_after)            # server's instruction wins
        if time.monotonic() + delay >= deadline:
            break
        await asyncio.sleep(delay)

    budget.on_result(ok=False)
    raise last_exc
```

The three lines that make it production code rather than a blog snippet: `4xx` returns
instead of retrying, `budget.try_spend()` can refuse, and every branch re-checks the
deadline so the caller's promise is never exceeded.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Transient, independent failures (packet loss, failover, a single sick replica) | The dependency is overloaded — retries are the load | Amplification: the worst case is attempts^layers |
| The operation is idempotent or carries an idempotency key | The write has no dedup key — you will double-charge | Latency: p99 becomes the sum of attempts plus backoff |
| You have a budget and a breaker in front | You have neither | Complexity and one more thing to monitor (retry ratio) |

### Follow-ups they will ask

**Q: Full jitter or decorrelated jitter?**
A: Full jitter by default — `rand(0, min(cap, base * 2^n))` — because AWS's own
simulation showed it used the least client work, and it is memoryless so it is trivial to
reason about. I reach for decorrelated when time-to-recovery matters more than call
count, accepting that it makes slightly more calls. What I would *not* do is equal
jitter: AWS found it does more work than full jitter and takes noticeably longer.

**Q: How do you stop a retry storm that has already started?**
A: Three levers, in order of speed. The circuit breaker stops new retries against a
dependency that is clearly down. The retry budget refuses retries once they exceed ~10%
of traffic. Then server-side load shedding with a distinct "overloaded" status — Google's
guidance is to return a specific code for overload so clients back off rather than
treating it as a generic retryable 503. If it is already metastable, none of those are
enough on their own and you have to drop load hard — shed at the edge or drain the
queue — because the feedback loop will not decay by itself.

**Q: Where in the stack should retries live?**
A: Exactly one layer, and normally the one immediately above the failing dependency,
because it has the most specific error information and re-does the least work. If both
my API gateway and my service retry, I have silently built 9 or 16 attempts. I make this
explicit: gateway retries are off for anything except idempotent GETs, and the service
owns retries for its own dependencies.

**Q: Is it ever right to retry a 4xx?**
A: Three narrow cases. 429 always — it is a rate signal, not a client bug. 408 request
timeout. And 409 from an idempotency layer meaning "the original request is still
in flight", where the correct behaviour is a short backoff and retry with the *same* key.
Everything else in the 4xx range is deterministic and retrying it just adds load.

**Q: Should retries be synchronous in the request path?**
A: Only if the total deadline still fits the user's SLO — realistically one or two fast
retries. Beyond that I make it asynchronous: persist the intent, return 202, and let a
worker retry with long backoff against Pub/Sub or a Kafka retry topic. That way retry
duration is bounded by business need instead of by how long a human will stare at a
spinner.

### Red flags — do not say this

- ❌ "We retry 3 times with exponential backoff." → ✅ "Three attempts, exponential
  backoff with full jitter, only on 5xx/429/network, gated by a 10% retry budget, and
  only at one layer of the stack."
- ❌ "Retries make the system more reliable." → ✅ "Retries improve reliability for
  independent transient faults, and reduce it for correlated ones — which is why the
  metastable-failures study found retry policy was the sustaining effect in over half
  of the public incidents they examined."
- ❌ "We retry everything that fails." → ✅ "Retrying a 400 or a 404 is guaranteed to
  fail again, so it is load with a zero success probability."
- ❌ "Jitter is a micro-optimisation." → ✅ "Jitter is the difference between a
  synchronised wave that re-kills your dependency at recovery and a smooth arrival rate
  it can absorb."

---

## 9.4 Idempotency

> **One-liner:** An operation is idempotent when performing it N times has the same
> observable effect as performing it once — which is the property that makes retrying a
> write safe, and therefore the property that makes every other pattern in this module
> usable.

### Say this in the interview

> Idempotency is what lets me retry a write without double-charging someone. The pattern
> I use is the one Stripe standardised: the client generates a UUIDv4 and sends it in an
> `Idempotency-Key` header on every POST. Server side, I atomically claim that key —
> `INSERT ... ON CONFLICT DO NOTHING`, or a Redis `SET NX` — and only the request that
> wins the claim executes the business logic. When it finishes I store the status code
> and the response body against the key, so any later retry replays byte-identical
> output instead of re-executing. Three details separate a real implementation from a
> toy one. First, the concurrent duplicate: a second request arriving while the first is
> still in flight must not get a cached response, because there isn't one yet — Stripe
> returns 409 Conflict and the client retries with the same key. Second, I hash the
> request body and store the fingerprint, so if someone reuses a key with a different
> payload I reject it rather than silently returning the wrong resource. Third, TTL:
> Stripe keeps keys for at least 24 hours, which is the number I'd default to, because
> the dedup store's cost is proportional to retention and 24 hours covers essentially
> all real client retries. The thing I'd add is that the key must be generated before
> the first attempt and reused across all retries — if the client mints a new UUID per
> attempt, none of this works.

### Mental model

**Naturally idempotent vs not.** HTTP already tells you most of the answer:

| Operation | Idempotent? | Note |
|---|---|---|
| `GET`, `HEAD`, `OPTIONS` | Yes | Safe by definition |
| `PUT /users/42 {name:"A"}` | Yes | Absolute state assignment |
| `DELETE /users/42` | Yes | Second call is a no-op (return 204, not 404) |
| `POST /charges` | **No** | Creates a new resource per call |
| `UPDATE accounts SET balance = 100` | Yes | Assignment |
| `UPDATE accounts SET balance = balance - 10` | **No** | Relative mutation — the classic double-spend |
| Kafka/Pub-Sub consumer that inserts a row | **No**, unless keyed | At-least-once delivery guarantees you *will* see duplicates |

So the first design move is always: **can I make this naturally idempotent?** Replacing
`balance = balance - 10` with a ledger row keyed on `(account_id, transfer_id)` and a
unique constraint eliminates the problem instead of managing it. Prefer that when you
can. When you can't — because the side effect is a call to Stripe or an email send — you
need an explicit idempotency layer.

**The full lifecycle:**

```
 client                      idempotency layer                 business logic
   |                                |                                |
   |  POST /payments                |                                |
   |  Idempotency-Key: 7f3a-...     |                                |
   |------------------------------->|                                |
   |                        (1) claim key atomically                 |
   |                        SET NX / INSERT ON CONFLICT              |
   |                                |                                |
   |          +---------------------+---------------------+          |
   |          | WON claim           | LOST: state=?       |          |
   |          v                     v                     v          |
   |    execute --------------> IN_FLIGHT           DONE (cached)    |
   |          |                     |                     |          |
   |          |                 409 Conflict        replay stored    |
   |          |                 "retry shortly"     status + body    |
   |          v                                     + header         |
   |   (2) store status+body+hash                Idempotent-Replayed |
   |          |                                                      |
   |<---------+ 201 Created                                          |
```

**The concurrent duplicate is the question that separates candidates.** Naive designs
have three states — *absent*, *done* — and break in the gap between them. You need
**three** states: `pending`, `succeeded`, `failed`. A second request that finds `pending`
has no response to replay, so it must not invent one. Options:

1. **Return 409 Conflict** and let the client retry with the same key. Stripe's choice.
   Simple, no held resources, and the client's retry finds the terminal state.
2. **Block and wait** on the pending row (`SELECT ... FOR UPDATE`, or poll Redis) up to a
   short bound. Nicer for the caller, but holds a connection and can chain-stall under
   load. Only do this with a tight cap — say 2 s — then fall back to 409.

Whichever you pick, you need a **stale-pending recovery** path: if the process holding a
`pending` key crashed, the key is stuck and the client can never make progress. The fix
is a staleness check — if `pending` is older than the operation's p99 duration plus
margin (e.g. 30 s for a charge), reclaim the key and allow re-execution. Without this,
one pod OOM permanently bricks that payment.

**Fingerprinting.** Store `SHA-256` of the canonical request body alongside the key. On
a hit, compare. Mismatch means the client reused a key for a different operation — a
client bug, and returning the *first* response would be silently wrong. Stripe returns an
error with the message *"Keys for idempotent requests can only be used with the same
parameters they were first used with."* Reject with 422 (or 409) and say why.

**Replaying the response.** Store the **status code and body of the first attempt,
whether it succeeded or failed** — Stripe explicitly caches 500s too, so a retry sees the
same 500 rather than re-executing a half-done operation. Signal the replay with a
response header (`Idempotent-Replayed: true`) so clients and your own logs can
distinguish a replay from a fresh execution; without it, your "duplicate rate" metric is
unmeasurable.

**TTL and retention.** Retention is a cost/safety dial:

| Retention | Rationale |
|---|---|
| **24 h** | Stripe's v1 default and the sane starting point — covers automated client retries with room to spare |
| **7 d** | Payment or partner APIs where a human might re-submit days later |
| **30 d** | Stripe's own v2 APIs use 30 days per account |

Storage cost is roughly `write_rate × retention × row_size`. At 500 writes/s with 1 KB
records, 24 h is about 43 GB — fine in Postgres, expensive if you keep it all in Redis
memory. Which is why the mature shape is **both**.

**Three implementation levels — know when each is enough:**

```
 LEVEL 1  DB unique constraint          cost: ~0     covers: own-DB writes
   INSERT INTO payments(id, idem_key, ...) -- UNIQUE(idem_key)
   Catch unique violation -> read the existing row, return it.
   Cannot replay an arbitrary response body. Cannot dedupe an
   external side effect (a Stripe call, an email).

 LEVEL 2  Redis SET NX + TTL            cost: 1 RTT  covers: high-volume dedup
   SET idem:{key} pending NX EX 86400
   Sub-millisecond, self-expiring. But Redis is not durable by
   default: a failover can lose the key and permit a duplicate.
   Fine for "don't send the same push twice", not for money.

 LEVEL 3  Idempotency table (+ Redis in front)   covers: money
   Durable Postgres row: key, fingerprint, status, response,
   expires_at. Redis is a read-through cache for the hot path,
   Postgres is the source of truth. This is Stripe's shape.
```

### Enterprise production example

**Stripe** set the industry standard here, and the details are all in their public API
reference. Clients send `Idempotency-Key` on every POST — up to **255 characters**, with
**UUIDv4 recommended** — and Stripe explicitly warns against putting anything sensitive
like an email address in the key. Stripe **saves the resulting status code and body of
the first request for any given key, regardless of whether it succeeded or failed**, so
subsequent requests with the same key return the same result, *including 500s*. Keys are
pruned after **at least 24 hours** for the v1 API (**30 days** per account/sandbox on
v2), and a key reused after pruning generates a genuinely new request. The idempotency
layer **compares incoming parameters against the original** and errors on mismatch. A
key whose original request is still executing concurrently gets **409 Conflict**, which
is retryable. Two deliberate holes in the coverage that are worth quoting: results are
saved **only after endpoint execution begins**, so a request that fails parameter
validation or loses a concurrency race is *not* cached and can be safely retried; and
`GET`/`DELETE` ignore the header because they are already idempotent. Replays are marked
with an `Idempotent-Replayed` response header.

### Code

Postgres schema — the durable source of truth:

```sql
CREATE TABLE idempotency_keys (
    key           TEXT        PRIMARY KEY,
    scope         TEXT        NOT NULL,           -- tenant/account: keys are per-account
    request_hash  TEXT        NOT NULL,           -- sha256 of canonical body
    status        TEXT        NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending','succeeded','failed')),
    response_code INT,
    response_body JSONB,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT now() + INTERVAL '24 hours'
);
CREATE INDEX ON idempotency_keys (expires_at);   -- for the reaper job
```

FastAPI dependency — Redis fast path, Postgres for correctness, all four cases handled:

```python
import hashlib, json
from datetime import timedelta
from fastapi import APIRouter, Header, HTTPException, Request, Response

router = APIRouter()
STALE_PENDING = timedelta(seconds=30)   # ~p99 of a charge, plus margin


def fingerprint(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


@router.post("/payments", status_code=201)
async def create_payment(request: Request, response: Response,
                         idempotency_key: str = Header(..., alias="Idempotency-Key")):
    if len(idempotency_key) > 255:
        raise HTTPException(400, "Idempotency-Key too long")
    raw = await request.body()
    fp = fingerprint(raw)
    scope = request.state.account_id
    rkey = f"idem:{scope}:{idempotency_key}"

    # Fast path: a completed key is replayed from Redis without touching Postgres.
    if cached := await redis.get(rkey):
        rec = json.loads(cached)
        if rec["request_hash"] != fp:
            raise HTTPException(422, "Key reused with different parameters")
        response.headers["Idempotent-Replayed"] = "true"
        response.status_code = rec["response_code"]
        return rec["response_body"]

    async with db.transaction() as tx:
        # Atomic claim. Exactly one concurrent request gets a row back.
        claimed = await tx.fetchrow(
            """INSERT INTO idempotency_keys (key, scope, request_hash)
               VALUES ($1, $2, $3) ON CONFLICT (key) DO NOTHING RETURNING key""",
            idempotency_key, scope, fp)

        if claimed is None:
            row = await tx.fetchrow(
                "SELECT * FROM idempotency_keys WHERE key=$1 FOR UPDATE",
                idempotency_key)
            if row["request_hash"] != fp:
                raise HTTPException(422, "Key reused with different parameters")
            if row["status"] != "pending":
                response.headers["Idempotent-Replayed"] = "true"
                response.status_code = row["response_code"]
                return row["response_body"]
            # Pending. Either genuinely in flight, or its owner died.
            if row["created_at"] > utcnow() - STALE_PENDING:
                raise HTTPException(409, "Request in flight; retry with the same key")
            await tx.execute(
                "UPDATE idempotency_keys SET created_at=now() WHERE key=$1",
                idempotency_key)   # reclaim the orphan and fall through to execute

    try:
        result, code = await charge_customer(json.loads(raw), idempotency_key)
    except BusinessError as exc:
        result, code = {"error": exc.code}, 422          # cache failures too

    # Persist the outcome, then warm Redis. Postgres first: if Redis write
    # fails we lose latency, not correctness.
    await db.execute(
        """UPDATE idempotency_keys SET status=$2, response_code=$3, response_body=$4
           WHERE key=$1""",
        idempotency_key, "succeeded" if code < 400 else "failed", code, result)
    await redis.set(rkey, json.dumps(
        {"request_hash": fp, "response_code": code, "response_body": result}),
        ex=86_400)
    response.status_code = code
    return result
```

Note the ordering: **the idempotency record and the business write must be in the same
transaction** if the business write is in the same database. If it isn't — a Stripe call,
an email — you have a genuine two-phase problem and must accept `pending` as a real state
and reconcile, which is the [saga](#914-saga-pattern-and-compensating-transactions)
territory.

Level 2, when Redis alone is sufficient (deduping a notification, not money):

```python
async def send_once(notification_id: str, payload: dict) -> bool:
    # NX makes this a distributed test-and-set; TTL bounds the dedup window.
    if not await redis.set(f"notif:{notification_id}", "1", nx=True, ex=86_400):
        return False        # someone else already owns this send
    try:
        await provider.send(payload)
        return True
    except Exception:
        await redis.delete(f"notif:{notification_id}")   # release so a retry can win
        raise
```

That `delete` in the exception path is the detail people miss: without it, a failed send
is permanently marked as done and the notification is silently lost.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Any non-idempotent write reachable by a retrying client | The operation is naturally idempotent — use a unique constraint instead | A dedup store: writes, storage proportional to retention, and a reaper job |
| The side effect leaves your system (payment, email, SMS, LLM spend) | Pure reads | One extra round trip on the hot path, and a new failure domain (Redis) |
| At-least-once consumers (Kafka, Pub/Sub) | Single-shot internal jobs with no retry | The dedup window is finite — a duplicate delivered after TTL will re-execute |

### Follow-ups they will ask

**Q: Two requests with the same key arrive at the same millisecond. Walk me through it.**
A: Both hit `INSERT ... ON CONFLICT (key) DO NOTHING`. Postgres serialises them on the
primary key, so exactly one gets a row back and executes; the other gets zero rows,
re-reads with `SELECT ... FOR UPDATE`, sees `pending`, and returns 409 Conflict telling
the client to retry with the same key. The atomicity comes from the unique index, not
from application code — an `if not exists then insert` in Python has a race window and
will double-charge under concurrency.

**Q: Who generates the key, and what happens if the client generates a new one per
retry?**
A: The client, once, before the first attempt — a UUIDv4 held in a variable that survives
the retry loop. If it mints a new key per attempt, the server sees N distinct operations
and charges N times. That is the single most common way this pattern is implemented
wrong, so in my own SDKs I generate the key at the top of the retry loop and assert in a
test that all attempts carry the same value.

**Q: Why not derive the key from a hash of the request body instead?**
A: Because it collides on legitimate repeats. Two genuinely separate $5 coffee purchases
by the same user in the same minute hash identically, and the second one silently
returns the first one's receipt. A body hash makes the operation *unrepeatable*, not
idempotent. The body hash belongs in the *fingerprint* field, to detect key reuse — not
as the key itself.

**Q: Your idempotency store is Redis and it fails over, losing the last second of keys.
What's the consequence?**
A: A duplicate execution window equal to the replication lag. For notifications I accept
that. For payments I don't, which is why Postgres is the source of truth and Redis is a
cache in front of it: the claim happens on the durable store, and if Redis is empty I
fall through to Postgres instead of assuming the key is new. The failure mode I refuse to
build is one where losing the cache changes correctness rather than latency.

**Q: How do you pick the TTL, and what breaks at the boundary?**
A: From the client's real retry behaviour. Automated retries finish in seconds to
minutes, so 24 hours — Stripe's number — has enormous margin. What breaks at the boundary
is that a retry arriving at TTL + 1 s is treated as a brand-new request and executes
again. So the TTL must exceed the longest retry window any client could plausibly use,
including a human clicking "retry" in a dashboard, which is why partner-facing payment
APIs often go to 7 or 30 days.

**Q: Do you need idempotency keys if you already have exactly-once semantics from
Kafka?**
A: Yes, for anything with an external side effect. Kafka's exactly-once is
read-process-write *inside* Kafka via transactions — offsets and output records commit
atomically. The moment the side effect is an HTTP call to Stripe or an email, it is
outside the transaction, so a rebalance and replay repeats it. Idempotency at the effect
boundary is what makes that safe. See [9.5](#95-exactly-once-vs-at-least-once).

### Red flags — do not say this

- ❌ "We check if the record exists before inserting." → ✅ "I claim the key atomically
  with `INSERT ... ON CONFLICT DO NOTHING`, because check-then-insert has a race window
  that double-charges under exactly the concurrency retries create."
- ❌ "We return the cached response for any duplicate." → ✅ "Only for keys in a terminal
  state; a key still `pending` has no response yet, so I return 409 and let the client
  retry."
- ❌ "The idempotency key is a hash of the request." → ✅ "The hash is the fingerprint I
  use to detect key reuse; the key itself is a client-generated UUID, otherwise two
  legitimate identical purchases collide."
- ❌ "We store keys forever to be safe." → ✅ "Retention is a cost dial — 24 hours covers
  real retries; I run a reaper on `expires_at` and only extend to 7–30 days for
  partner-facing payment APIs."
- ❌ "It's idempotent because we use `PUT`." → ✅ "`PUT` is idempotent at the HTTP layer,
  but if the handler emits an event or calls a provider on every invocation, the *system*
  is not."

---

## 9.5 Exactly-once vs at-least-once

> **One-liner:** Exactly-once *delivery* is impossible across an unreliable network;
> exactly-once *effect* is achievable, and the recipe is at-least-once delivery plus
> idempotent processing.

### Say this in the interview

> I treat "exactly-once delivery" as a red flag phrase, because you can't have it: the
> two generals problem means the sender can never know whether the receiver got the
> message or only the ack was lost, so it must choose to resend (at-least-once) or not
> (at-most-once). What I can build is exactly-once *effect* — sometimes called
> effectively-once — which is at-least-once delivery plus an idempotent consumer. In
> practice that means my Pub/Sub or Kafka consumer takes the message's dedup key, does
> an insert with a unique constraint or a Redis `SET NX`, and treats a conflict as "I
> already did this, ack and move on". Kafka does offer exactly-once semantics, but it is
> narrower than the name suggests: it's transactional read-process-write *within* Kafka,
> so the output records and the consumed offsets commit atomically. The moment my side
> effect leaves Kafka — a Stripe charge, an email, a row in Postgres — I am back to
> needing idempotency at that boundary. The honest engineering cost is the dedup window:
> I have to store seen-keys for some retention, and that storage is real. At 10,000
> messages a second with a 24-hour window that's 864 million keys, so I'd size it, put a
> TTL on it, and be explicit that a duplicate arriving after the window will be
> reprocessed.

### Mental model

```
  at-most-once      send, never resend        -> may LOSE messages
  at-least-once     resend until acked        -> may DUPLICATE messages
  exactly-once      impossible as *delivery*
       |
       +-- at-least-once delivery + idempotent processing
                  = exactly-once EFFECT  ("effectively once")
```

Where the duplicates actually come from, in his stack:

| Source | Mechanism |
|---|---|
| **Pub/Sub** | Ack deadline expires while you are still processing → redelivery |
| **Kafka** | Consumer rebalance or crash before offset commit → reprocess from last commit |
| **Client retry** | Timeout with unknown outcome → the same POST twice |
| **Producer retry** | Ack lost after the broker persisted → the same record twice |
| **At-least-once webhooks** | Stripe, GitHub etc. redeliver until they get a 2xx |

**The dedup window and its cost.** Idempotency is only as good as how long you remember.

```
  keys/s x retention = keys stored
  10,000/s x 24 h = 864,000,000 keys
    Redis, 64-byte key + overhead ~ 100 B  ->  ~86 GB of RAM. Not viable.
    Postgres, key + timestamp ~ 60 B/row   ->  ~52 GB + index. Viable, needs
                                               partitioning and a reaper.
  Cheaper shapes:
    - shrink the window to the redelivery window you actually observe (1 h)
    - dedup on the *business* key with a unique constraint you already have
      (order_id), so the dedup store IS the data
    - Bloom filter for a "probably seen" pre-filter, exact store behind it
```

The third option is the one to reach for first: if the consumer's job is "insert a row
per order", then `UNIQUE(order_id)` gives you deduplication with zero extra storage and
infinite retention. **Deduplicating on data you already store is strictly better than a
side table.**

### Enterprise production example

**Kafka's** exactly-once semantics (KIP-98 / KIP-129, GA in 0.11) is the most
misunderstood feature in the ecosystem. It gives you an idempotent producer (sequence
numbers per partition eliminate producer-retry duplicates) and transactions that
atomically commit output records *and* consumer offsets — with `isolation.level=
read_committed` on the downstream consumer. That is genuinely exactly-once for a
Kafka→Kafka topology, and it is what Kafka Streams uses under
`processing.guarantee=exactly_once_v2`. What it is not: a guarantee about anything
outside Kafka. A Kafka consumer that charges a card cannot be made exactly-once by a
Kafka config, because the charge is not in the transaction. **Google Cloud Pub/Sub** is
explicit in the other direction: standard subscriptions are at-least-once and the docs
tell you to build idempotent consumers; the newer exactly-once-delivery subscription
guarantees no redelivery only within the ack deadline for a *successfully acked* message,
and still cannot cover your external side effects.

### Code

Consumer-side dedup on the business key — no side table, unlimited retention:

```python
async def handle_order_event(msg) -> None:
    event = json.loads(msg.data)
    try:
        async with db.transaction() as tx:
            # UNIQUE(order_id) does the dedup. The dedup store IS the data.
            await tx.execute(
                """INSERT INTO orders (order_id, user_id, total_cents, created_at)
                   VALUES ($1,$2,$3,now()) ON CONFLICT (order_id) DO NOTHING""",
                event["order_id"], event["user_id"], event["total_cents"])
            # Outbox: the downstream effect commits atomically with the order.
            await tx.execute(
                """INSERT INTO outbox (id, topic, payload) VALUES ($1,$2,$3)
                   ON CONFLICT (id) DO NOTHING""",
                event["order_id"], "order.confirmed", json.dumps(event))
        msg.ack()
    except Exception:
        msg.nack()        # let Pub/Sub redeliver; the insert is safe to repeat
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| At-least-once + idempotent consumer: virtually always | You genuinely cannot make the effect idempotent (a physical action) | A dedup key on every message and a bounded memory of what you've seen |
| Kafka EOS: Kafka-in, Kafka-out stream processing | The side effect leaves Kafka | Throughput cost of transactions and a much more complex failure model |
| At-most-once: metrics, sampled traces, best-effort telemetry | Anything a user or an auditor will notice | Silent data loss |

### Follow-ups they will ask

**Q: Kafka advertises exactly-once. Why do you still need idempotency?**
A: Because Kafka's guarantee is transactional read-process-write within Kafka — offsets
and output records commit atomically. My consumer's side effect is a Stripe charge, and
that is not in the transaction. If the pod dies between the charge and the offset commit,
the replay charges again. Exactly-once inside Kafka plus an idempotency key at the
external boundary is the complete answer.

**Q: How do you choose the dedup window?**
A: From the measured redelivery behaviour of the transport, not a round number. Pub/Sub
redelivers within the ack deadline and its retry policy, so an hour is usually generous;
webhook providers retry for days, so those need days. I'd rather dedup on a business key
with a unique constraint and get unbounded retention for free than pick a window at all.

**Q: A duplicate arrives after the dedup window expires. What happens?**
A: It is reprocessed — and I say that out loud rather than pretending otherwise. The
mitigation is to make reprocessing harmless where possible: an upsert to the same
terminal state is fine; a second email is annoying; a second charge is unacceptable, so
for money the dedup key lives in the durable ledger with no expiry at all, and the 24-hour
TTL applies only to the response-replay cache.

### Red flags — do not say this

- ❌ "We use exactly-once delivery." → ✅ "At-least-once delivery with idempotent
  processing, which gives exactly-once effect — exactly-once delivery isn't achievable
  across a network that can drop acks."
- ❌ "Kafka gives us exactly-once so duplicates are impossible." → ✅ "Kafka's EOS covers
  Kafka-to-Kafka; my external side effects still need idempotency keys."
- ❌ "We dedupe in memory." → ✅ "In-memory dedup dies with the pod and doesn't cover a
  second replica, so the dedup state has to be shared and durable enough for the
  consequence."

---

## 9.6 Dead-letter queues

> **One-liner:** A DLQ is where a message goes after it has failed enough times that
> continuing to retry it is harming the system — it converts an infinite retry loop into
> a bounded, inspectable backlog.

### Say this in the interview

> A dead-letter queue is the escape hatch for poison messages. Without it, a single
> malformed event blocks a partition or gets redelivered forever, and one bad message
> becomes an outage — that's the classic head-of-line blocking failure in an ordered
> consumer. So I set a max delivery attempt count, usually five with exponential backoff,
> and after that the message goes to a DLQ instead of being retried or dropped. What
> matters more than the mechanism is the metadata: I capture the original payload, the
> full error and stack trace, the attempt count, the original topic and partition and
> offset, the timestamp of first failure, and the trace ID, because without those a DLQ
> is just a folder of mysteries. Then two operational things people skip. First, replay
> tooling — a command that takes a DLQ message, optionally lets me patch it, and
> republishes to the original topic, and that replay path has to be idempotent because
> replaying a payment event twice is worse than not replaying it. Second, alerting: I
> alert on DLQ depth greater than zero, or on rate of arrival, because the real failure
> mode I've seen is the DLQ nobody looks at — messages pile up for weeks, then somebody
> finds 40,000 unprocessed events and there's no longer any way to know which ones still
> matter. I'd treat non-zero DLQ depth as a paging condition, not a dashboard tile.

### Mental model

```
  main topic
     |
     v
  consumer --attempt 1..5 (backoff)--> success? -> ack
     |                                    |
     |                                    no, after N attempts
     v                                    v
  (in-order transports: this consumer  +---------------------+
   is BLOCKED while retrying)          |  dead-letter topic  |
                                       +----------+----------+
                                                  |
                        +-------------------------+------------+
                        v                         v            v
                  ALERT on depth>0        triage / classify   replay
                                                              (idempotent)
```

Common tiering, which reads much better than a single DLQ:

- `orders` → `orders.retry.5s` → `orders.retry.1m` → `orders.retry.10m` → `orders.dlq`

Each retry topic has its own consumer with a delay, which keeps the main partition
unblocked — this is the standard Kafka pattern because Kafka has no per-message delay.
Pub/Sub gives you `minimumBackoff`/`maximumBackoff` and `maxDeliveryAttempts` (5–100)
plus a `deadLetterTopic` natively, and SQS has a redrive policy with `maxReceiveCount`.

**What to capture — the DLQ envelope:**

| Field | Why you will need it at 3 a.m. |
|---|---|
| `original_payload` | To replay at all |
| `original_topic` / `partition` / `offset` / `message_id` | To know where it came from and prove you replayed once |
| `attempt_count` | Distinguishes "transient, unlucky" from "will never work" |
| `error_class` + `message` + stack | To group 40,000 messages into 3 causes |
| `first_failed_at` / `dead_lettered_at` | To know what is still business-relevant |
| `trace_id` | To find the originating request in your traces |
| `consumer_version` | So you can tell whether a since-deployed fix already covers it |

That last one is the pro move: with `consumer_version` you can answer "are these
replayable now?" without guessing.

**Why the DLQ nobody looks at is a real failure mode.** A DLQ with no alert is a silent
data-loss channel with extra steps. It fails in a specific, predictable way: messages
accumulate, retention expires (Pub/Sub defaults to 7 days), and the events are gone — but
because nothing errored, no postmortem is ever written. The controls are unglamorous and
mandatory: alert on depth, alert on age of oldest message, put a named owner on the
queue, and review it in the weekly ops rotation.

### Enterprise production example

**Scenario (labelled as a scenario, not a claim about a company):** a payment webhook
consumer on GCP processes ~2,000 Stripe events/s from a Pub/Sub subscription with
`maxDeliveryAttempts = 5` and backoff from 10 s to 600 s. A schema change ships that adds
a required field; 0.4% of events — about 8/s — fail deserialisation. They exhaust five
attempts in roughly 20 minutes and land in `payments.dlq` at ~8/s, which is 28,000
messages in an hour. Because the alert is on **depth > 1,000 for 5 minutes** it pages in
under 10 minutes; the DLQ envelope groups all of them under one `error_class`, the
consumer is rolled back, and a replay job republishes 28,000 messages to the main topic.
The replay is safe only because the handler dedups on `stripe_event_id` with a unique
constraint. Without that constraint the replay would double-apply 28,000 payment events —
which is why **replay tooling and idempotency are the same project**.

### Code

```python
# GCP Pub/Sub: DLQ is subscription config, not application code.
from google.cloud import pubsub_v1

sub = pubsub_v1.types.Subscription(
    name="projects/p/subscriptions/payments-worker",
    topic="projects/p/topics/payments",
    ack_deadline_seconds=60,
    retry_policy=pubsub_v1.types.RetryPolicy(
        minimum_backoff={"seconds": 10}, maximum_backoff={"seconds": 600}),
    dead_letter_policy=pubsub_v1.types.DeadLetterPolicy(
        dead_letter_topic="projects/p/topics/payments-dlq",
        max_delivery_attempts=5),
)
```

```python
# Replay: idempotent by construction, and it records that it replayed.
async def replay(dlq_messages: list, dry_run: bool = True) -> dict:
    stats = {"replayed": 0, "skipped": 0}
    for m in dlq_messages:
        env = json.loads(m.data)
        if env["consumer_version"] >= CURRENT_VERSION:
            stats["skipped"] += 1      # the bug that killed it is still present
            continue
        if dry_run:
            continue
        await publisher.publish(
            env["original_topic"], json.dumps(env["original_payload"]).encode(),
            # Carried through so the handler's unique constraint dedups the replay.
            dedup_key=env["original_message_id"], replay_of=env["message_id"])
        stats["replayed"] += 1
    return stats
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Any at-least-once consumer that can encounter a poison message | The work is safely droppable (sampled telemetry) | An owned queue, an alert, replay tooling, and a triage habit |
| Ordered consumers where one bad message blocks the partition | Strict global ordering is a hard business requirement — DLQ-ing breaks order | Messages leave the ordered stream, so downstream state can be applied out of order |

### Follow-ups they will ask

**Q: Does DLQ-ing a message break ordering?**
A: Yes, and you have to say so. Message 5 goes to the DLQ, message 6 is applied, and then
you replay 5 — now the state transitions happened out of order. I handle it by making
handlers order-insensitive where I can: version or timestamp each event and ignore stale
ones, or use last-write-wins on the entity. If strict ordering is genuinely required,
DLQ-ing is the wrong answer and the consumer must halt the partition and page a human.

**Q: How many attempts before the DLQ, and why?**
A: Five, with backoff from 10 s to 600 s, which spans roughly 20 minutes of transient
failure. That covers a database failover or a dependency restart. Beyond that the
probability the next attempt succeeds is low enough that continuing costs more in load
than it buys in success, and I would rather have the message parked and visible than
retried invisibly forever.

**Q: What do you alert on for a DLQ?**
A: Two signals. Depth above a threshold sustained over a few minutes catches a burst like
a bad deploy. Age of the oldest message catches the slow leak — one message a day for a
month is invisible on a depth graph and is exactly the case that becomes silent data
loss. I also treat DLQ retention as a deadline: with Pub/Sub's 7-day default, an
unreviewed DLQ *is* a data-loss timer.

### Red flags — do not say this

- ❌ "Failed messages go to a DLQ." → ✅ "After five attempts with backoff they go to a
  DLQ carrying the payload, error, attempt count, source offset and trace ID, with an
  alert on depth and age, and an idempotent replay job."
- ❌ "We retry until it succeeds." → ✅ "Unbounded retry on a poison message is
  head-of-line blocking — one malformed event stalls the partition."
- ❌ "The DLQ is for debugging." → ✅ "The DLQ is unprocessed business data with a
  retention clock on it; it needs an owner and a page, not a dashboard."

---

## 9.7 Circuit breakers

> **One-liner:** A circuit breaker is a local, stateful decision to stop calling a
> dependency that is clearly broken, so that you fail in 1 ms instead of 30 s and stop
> adding load to something that is already down.

### Say this in the interview

> A circuit breaker sits in my client, counts recent outcomes per dependency, and has
> three states. Closed means traffic flows and I'm counting. When the failure rate over
> a rolling window exceeds my threshold — and only once a minimum request volume has
> been seen, so three failures out of three don't trip it — the breaker opens and every
> call fails immediately without touching the network. After a cooldown it goes half-open
> and lets a small number of probe requests through: if they succeed it closes, if any
> fails it re-opens and the cooldown restarts. Hystrix's defaults are a good reference
> point — 20 requests minimum in a 10-second rolling window, 50% error threshold, 5-second
> sleep window. The subtlety I'd emphasise is what you trip on. Error rate alone misses
> the failure that actually kills you, which is a dependency that's slow rather than
> erroring, so I trip on slow-call rate too — resilience4j lets you say "open if more
> than 50% of calls exceed 2 seconds". And breakers must be per dependency, not one
> global breaker, or a sick recommendations service opens the circuit for payments. The
> part candidates skip is what you *do* when it's open: failing fast is only useful if
> there's a fallback — a cached answer, a degraded response, or a queued write. I'd
> rather return stale-but-labelled data than a 500.

### Mental model

```
                  failure rate OR slow-call rate > threshold
                       (and volume >= minimum requests)
        +---------+ ------------------------------------> +--------+
        | CLOSED  |                                       |  OPEN  |
        | count   | <------------------------------------ | fail   |
        | outcomes|      probe succeeded (n times)        | fast   |
        +---------+                                       +--------+
             ^                                                 |
             |                                                 | after
             |          any probe fails -> back to OPEN        | cooldown
             |                (reset cooldown)                 v
             |                                          +--------------+
             +----------------------------------------- |  HALF-OPEN   |
                                                        | allow k reqs |
                                                        +--------------+
```

Exact transition rules worth being able to recite:

| Transition | Condition |
|---|---|
| Closed → Open | `(failure_rate ≥ threshold OR slow_rate ≥ threshold)` **AND** `calls ≥ minimum_volume` within the rolling window |
| Open → Half-open | Cooldown / sleep window elapsed |
| Half-open → Closed | `k` consecutive (or `k` of `n`) probes succeeded |
| Half-open → Open | **Any** probe failed; cooldown restarts (often exponentially) |

**The minimum-volume gate is not optional.** Without it, a service receiving 2 requests
per minute trips its breaker the first time one fails, and a single unlucky packet loss
takes out the dependency for everyone.

**Trip on latency, not just errors.** This is the single highest-value refinement. The
dangerous state is a dependency answering 200 OK at 25 s, because it produces zero errors
while consuming all your workers. resilience4j exposes this directly:
`slowCallRateThreshold` plus `slowCallDurationThreshold`. Rule of thumb: set
`slowCallDurationThreshold` to roughly your timeout, so a call that will time out counts
as a slow call *before* the timeout fires.

**Per-dependency, and often per-instance.** One breaker per (service, operation) pair at
minimum. Shopify goes further and gives each of its Redis instances its own circuit,
because a single sick node should not open the circuit for the other 41.

**What to do when open** — this is where the answer becomes senior:

| Strategy | Example |
|---|---|
| **Fail fast** | Return 503 with `Retry-After`; correct for a write you cannot fake |
| **Cached / stale** | Serve the last good value, labelled `X-Data-Staleness: 45s` |
| **Degraded** | RAG: return retrieved passages with no generated answer |
| **Static default** | Recommendations: return the editorial top-10 |
| **Queue the write** | Accept, return 202, persist intent, drain when the breaker closes |
| **Turn off the feature** | Shopify disables customer sign-in on a storefront when Redis is down, rather than failing the whole page |

**Breaker + retry ordering matters.** The breaker goes *outside* the retry loop, so an
open circuit suppresses the retries too. Inside, and you happily retry three times
against a dependency you already know is dead.

### Enterprise production example

**Netflix Hystrix** popularised the pattern and its defaults are the reference numbers
every interviewer half-remembers: `circuitBreaker.requestVolumeThreshold = 20` (minimum
requests in the rolling window before the breaker will trip at all),
`circuitBreaker.errorThresholdPercentage = 50`,
`circuitBreaker.sleepWindowInMilliseconds = 5000`, over a
`metrics.rollingStats.timeInMilliseconds = 10000` window split into 10 one-second
buckets. Hystrix is in maintenance mode now and **resilience4j** is the modern successor —
same state machine, plus the slow-call thresholds Hystrix lacked.

**Shopify's Semian** is the more interesting production story because it publishes the
tuning arithmetic. Semian combines a circuit breaker *and* a bulkhead, implemented with
SysV semaphores so the limit is shared across all worker processes on a host, and each
protected resource — MySQL, Redis, `Net::HTTP`, gRPC — gets its own named circuit. In
their published example, a Rails worker with **2 threads** talks to **42 Redis
instances**, each with a 0.25 s service timeout; because **99% of Redis calls complete
under 50 ms**, they set `half_open_resource_timeout = 50 ms` (much tighter than the
normal timeout, purely to reduce wasted utilisation on probes) and `error_timeout = 30 s`.
They also describe a real fallback rather than a hypothetical one: customer sessions live
in Redis, so when Redis is unavailable they rescue the exception and **disable customer
sign-in on the storefront** while everything else keeps serving.

### Code

Python with `pybreaker`, wired the way it should be — per dependency, breaker outside
retries, real fallback:

```python
import pybreaker, redis, httpx

# Shared state in Redis so all pods see the same breaker, not one per process.
breaker_store = pybreaker.CircuitRedisStorage(
    pybreaker.STATE_CLOSED, redis.Redis(host="redis", socket_timeout=0.2))

llm_breaker = pybreaker.CircuitBreaker(
    fail_max=20,                 # failures in the window before opening
    reset_timeout=30,            # cooldown before half-open
    state_storage=breaker_store,
    exclude=[lambda e: isinstance(e, httpx.HTTPStatusError)
             and e.response.status_code < 500],   # 4xx is not the dep's fault
)


class SlowCallError(Exception):
    """Raised so a slow-but-successful call still counts against the breaker."""


@llm_breaker
async def _generate(prompt: str) -> str:
    t0 = time.monotonic()
    resp = await client.post("https://api.openai.com/v1/responses",
                             json={"model": "gpt-4o-mini", "input": prompt},
                             timeout=httpx.Timeout(connect=0.5, read=8.0))
    resp.raise_for_status()
    if time.monotonic() - t0 > 6.0:        # slow-call rate, poor man's version
        raise SlowCallError()
    return resp.json()["output_text"]


async def answer(question: str, passages: list[str]) -> dict:
    try:
        return {"answer": await _generate(build_prompt(question, passages)),
                "degraded": False}
    except pybreaker.CircuitBreakerError:
        # Open: do not touch the network. Degrade instead of 500.
        return {"answer": None, "passages": passages, "degraded": True,
                "reason": "generation temporarily unavailable"}
```

resilience4j config (Java/Kotlin services), showing the slow-call thresholds that matter:

```yaml
resilience4j:
  circuitbreaker:
    instances:
      paymentProvider:
        slidingWindowType: TIME_BASED
        slidingWindowSize: 60            # seconds
        minimumNumberOfCalls: 20         # the volume gate
        failureRateThreshold: 50         # percent
        slowCallRateThreshold: 50        # percent of calls...
        slowCallDurationThreshold: 2s    # ...slower than this count as failures
        waitDurationInOpenState: 30s
        permittedNumberOfCallsInHalfOpenState: 5
        automaticTransitionFromOpenToHalfOpenEnabled: true
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Calling a dependency you don't control, or any dependency whose slowness could exhaust your pool | The dependency is in-process, or a single instance of a sharded fleet where the breaker would be per-shard anyway | False opens during a blip, and the fallback path becomes untested code |
| You have a meaningful fallback | Failing fast is no better than failing slow for the user (a payment) | Shared state if you want a fleet-wide view; local state means N independent breakers |

### Follow-ups they will ask

**Q: What do you trip the breaker on?**
A: Error rate **and** slow-call rate, gated on minimum volume. Errors alone miss the
dependency returning 200s at 25 s, which is the case that actually exhausts my workers.
In resilience4j that is `slowCallRateThreshold` with `slowCallDurationThreshold` set near
my timeout, so a doomed call is counted before the timeout even fires.

**Q: Should breaker state be shared across instances or per instance?**
A: Per instance by default. It is local information about local outcomes, it needs no
coordination, and it degrades gracefully. Sharing it via Redis gives you a faster
fleet-wide reaction and consistent behaviour, at the price of making your breaker depend
on Redis — which is a delightful way to have your reliability mechanism become the
outage. If I share it, I fail open on a Redis error.

**Q: The breaker is open. What does the user see?**
A: That depends on the operation, and having an answer per operation is the point. For a
RAG query, retrieved passages with a "generated summary unavailable" banner. For
recommendations, the cached or editorial list. For a payment, an honest 503 with
`Retry-After`, because faking success is worse than failing. I'd also emit a metric on
fallback rate, since a fallback nobody notices becomes a permanent silent degradation.

**Q: How do you avoid a thundering herd when the breaker closes?**
A: Half-open admits a bounded number of probes — five in that config — not the full
traffic. On close I would also ramp rather than switch, and jitter `waitDurationInOpen`
across instances so 200 pods do not all probe on the same second. Without jitter, N pods
with identical cooldowns produce a synchronised probe wave, which is the same failure as
un-jittered retries.

**Q: Isn't a circuit breaker just a retry limiter?**
A: No — they operate on different scopes. Retry policy is per request; the breaker is a
shared verdict about the dependency's health across requests. That is what lets the
1,001st request fail in a microsecond because of what happened to the previous thousand,
which is precisely the property that stops a cascading failure.

### Red flags — do not say this

- ❌ "We open the circuit after 5 failures." → ✅ "Failure rate over a rolling window with
  a minimum-volume gate — Hystrix's defaults are 50% over 20 requests in 10 seconds —
  because a raw count trips on noise for low-traffic endpoints."
- ❌ "One circuit breaker protects the service." → ✅ "One breaker per dependency; a global
  breaker means a sick recommendation service opens the circuit for payments."
- ❌ "When it's open we return an error." → ✅ "Open means fail fast *into a fallback* —
  cached, degraded, or queued — otherwise I've converted a slow failure into a fast
  failure without helping the user."
- ❌ "The breaker replaces timeouts." → ✅ "Timeouts are what generate the signal the
  breaker counts; without timeouts the breaker never sees a failure, it just waits."

---

## 9.8 Bulkheads

> **One-liner:** A bulkhead partitions your finite resources — threads, connections,
> concurrency slots — per dependency, so one slow downstream can exhaust its own share
> and nothing else.

### Say this in the interview

> Bulkhead comes from ship design: watertight compartments so one breach doesn't sink the
> hull. In a service, the resource being compartmentalised is concurrency. If I have 100
> workers and they're a shared pool, then a downstream that goes from 50 ms to 20 seconds
> will progressively occupy all 100 and my healthy endpoints start timing out for a reason
> that has nothing to do with them. So I cap concurrency per dependency: 20 slots for the
> LLM provider, 30 Postgres connections, 10 for the recommendations service. When the LLM
> is sick, calls to it queue or fail fast at 20 in-flight, and the other 80 workers keep
> serving. There are two flavours: a semaphore bulkhead, which just counts in-flight calls
> on the caller's own thread and is nearly free, and a thread-pool bulkhead, which
> dispatches to a dedicated pool and gives true isolation plus the ability to enforce
> timeouts on code that ignores them — at the cost of a context switch and losing thread
> locals. In async Python or Node I use a semaphore, because there are no threads to
> isolate; the concurrency limit *is* the bulkhead. The sizing rule is that the sum of
> your bulkheads should exceed your worker count — you want them binding per dependency,
> not globally — and each one should be at least as big as its dependency's
> throughput × latency, or you've throttled yourself.

### Mental model

```
  SHARED POOL (no bulkhead)          BULKHEADED
  ---------------------              ----------
  100 workers                        100 workers
    LLM slow ->  20 held               LLM: max 20  [########] FULL -> reject
                 60 held                            (other 80 untouched)
                100 held               DB : max 30  [###.....] ok
    everything times out               recs: max 10 [#.......] ok
                                       free:     40
```

Semaphore vs thread-pool:

| | Semaphore | Thread pool |
|---|---|---|
| Isolation | Concurrency count only | True — separate threads |
| Cost | Near zero | Context switch + memory per pool |
| Can enforce timeout on blocking code | No (caller's thread is stuck) | Yes (abandon the task) |
| Thread locals / request context | Preserved | Lost unless propagated |
| Right for | async I/O (FastAPI, Node), high volume | Blocking clients, legacy drivers |

**Sizing.** Little's Law again: a bulkhead of `N` slots supports
`N / latency` requests per second. If the LLM p99 is 2 s and you need 10 req/s, you need
at least 20 slots. Undersize it and you have built a self-inflicted rate limit; oversize
every bulkhead to the worker count and you have not bulkheaded anything.

Also bulkhead your **connection pools**, and size them to the *database's* limit, not your
instance count. 20 pods × a 20-connection pool = 400 connections against a Postgres
`max_connections` of 200 means half your pods cannot connect. Put PgBouncer in front in
transaction-pooling mode and the arithmetic becomes tractable.

### Enterprise production example

**Shopify's Semian** implements the bulkhead with **SysV semaphores**, which is a
deliberate and unusual choice: because the semaphore lives in the kernel rather than the
process, the concurrency limit is shared by every worker process on the host. Their
Redis-client configuration exposes it directly as `tickets: 4` — at most four workers on
that host may be inside a call to that Redis resource at once — alongside the breaker's
`error_threshold`, `success_threshold` and `error_timeout`. Per-resource `name` means
MySQL, Redis and each HTTP dependency get separate compartments, so excessive timeouts in
one cannot consume the workers needed by another.

### Code

```python
import asyncio
from contextlib import asynccontextmanager

# One semaphore per dependency. Sum > worker count, so they bind individually.
LIMITS = {"llm": asyncio.Semaphore(20), "vector": asyncio.Semaphore(30),
          "recs": asyncio.Semaphore(10)}
QUEUE_WAIT = {"llm": 0.5, "vector": 0.2, "recs": 0.05}   # seconds


@asynccontextmanager
async def bulkhead(name: str):
    """Fail fast when the compartment is full — do NOT queue unboundedly."""
    try:
        await asyncio.wait_for(LIMITS[name].acquire(), timeout=QUEUE_WAIT[name])
    except asyncio.TimeoutError:
        BULKHEAD_REJECTED.labels(name).inc()
        raise HTTPException(503, f"{name} at capacity", headers={"Retry-After": "1"})
    try:
        yield
    finally:
        LIMITS[name].release()


async def generate(prompt: str) -> str:
    async with bulkhead("llm"):
        return await llm_breaker.call(prompt)     # bulkhead outside, breaker inside
```

The `QUEUE_WAIT` bound is the part that makes this a bulkhead rather than an unbounded
queue: waiting forever for a slot reintroduces exactly the pile-up you were preventing.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Multiple dependencies share one worker pool and have different latency profiles | Single-dependency service — the worker count already is the bulkhead | Under-utilisation: a compartment can be full while capacity sits idle elsewhere |
| A dependency has high latency variance (LLMs, third-party APIs) | Extremely latency-sensitive paths where the semaphore is measurable overhead | N more numbers to tune, and each one is a potential self-inflicted throttle |

### Follow-ups they will ask

**Q: How do you size a bulkhead?**
A: `slots ≥ target_throughput × p99_latency`, then sanity-check that the sum across
dependencies comfortably exceeds the worker count so each binds independently. For 10
req/s against an LLM at p99 = 2 s that's 20 slots. I monitor rejection rate: steady
rejections while overall CPU is low means the bulkhead is the bottleneck, not the
dependency.

**Q: Bulkhead or circuit breaker — which first?**
A: Both, composed: bulkhead outside, breaker inside. The bulkhead caps the damage of
slowness that has not yet been classified as failure, and the breaker stops the calls
once it has. A breaker alone still lets 100 workers sit in a 20-second call for the
window it takes to trip.

**Q: In async Python there are no threads to isolate. Does the bulkhead still matter?**
A: More, not less — because a single event loop with unbounded concurrency happily
accumulates 10,000 pending coroutines against a stalled dependency, and the failure mode
becomes memory and connection-pool exhaustion rather than thread starvation. The
semaphore is the bulkhead there, and I also cap `httpx.Limits(max_connections=...)` per
client so the socket count is bounded too.

### Red flags — do not say this

- ❌ "We use a thread pool so we're isolated." → ✅ "One shared pool is the opposite of
  isolation; I cap concurrency per dependency so a slow LLM can only occupy its own 20
  slots."
- ❌ "Requests queue until a slot is free." → ✅ "Slots have a bounded acquire timeout,
  then I reject with 503 — an unbounded wait for a slot is the pile-up I'm trying to
  prevent."

---

## 9.9 Backpressure

> **One-liner:** Backpressure is the signal that travels *upstream* telling a producer to
> slow down, and a bounded queue is the mechanism that generates it.

### Say this in the interview

> Backpressure is what happens when a consumer tells a producer "I can't keep up, slow
> down" — and the primary mechanism is simply a bounded queue. The moment a queue has a
> limit, a full queue forces a decision: block the producer, reject the work, or drop
> something. An unbounded queue looks like it's helping, but it's actually converting a
> throughput problem into a latency-and-memory problem: the queue grows without limit,
> latency grows with it until every item is stale by the time it's processed, and
> eventually you OOM. I've seen the numbers on this — if producers push 1,000 items a
> second and consumers handle 800, you accumulate 200 a second, so a 4 GB pod holding
> 2 KB items dies in about three hours, and for the last hour it was serving responses to
> requests the users had already abandoned. The important distinction is between
> backpressure and load shedding: backpressure *slows the producer down* and preserves
> the work, which only works when the producer is something you control and that can wait
> — a Kafka consumer, an internal pipeline, a TCP sender. Load shedding *drops* work,
> which is the only option when the producer is the open internet and cannot be told to
> wait. The control signal I actually alarm on is queue depth and its rate of change,
> plus oldest-item age, because depth alone doesn't tell you whether you're draining. And
> I'd add that if your queue is Kafka, the disk is your buffer and backpressure shows up
> as consumer lag rather than memory — same physics, different failure mode.

### Mental model

```
  NO BACKPRESSURE (unbounded queue)
  producer 1000/s ---> [ ................ growing ] ---> consumer 800/s
                        +200/s forever -> latency -> infinity -> OOM

  BACKPRESSURE (bounded queue, size 5000)
  producer 1000/s ---> [ ############ FULL ] ---> consumer 800/s
        ^                       |
        +-- block / reject <----+   producer learns the real rate
```

**Backpressure vs load shedding** — the distinction interviewers probe:

| | Backpressure | Load shedding |
|---|---|---|
| Direction | Signal travels upstream | Decision made locally |
| Work | Preserved (delayed) | Discarded |
| Requires | A producer that can be slowed | Nothing |
| Fits | Internal pipelines, Kafka consumers, TCP, gRPC streaming | Public HTTP endpoints |
| Failure if absent | Unbounded memory → OOM | Unbounded latency → timeouts everywhere |

You need both: backpressure inside the system, load shedding at the edge where the
producer is the internet and does not take instructions. See
[9.10](#910-load-shedding-and-graceful-degradation).

**Where backpressure already exists for free:**

- **TCP** — the receive window is backpressure at the transport layer. `write()` blocks.
- **Node streams** — `writable.write()` returning `false` plus the `drain` event *is* the
  reactive-streams demand signal; `pipeline()` honours it, a naive `for` loop over
  `write()` does not, and that is the classic Node memory leak.
- **Reactive Streams / gRPC streaming** — the consumer *requests* n items
  (`request(n)`); the producer may not send more than requested. Demand flows upstream,
  data flows downstream.
- **Kafka** — `max.poll.records` and the consumer's own pull model. The consumer asks for
  work; nobody can push it. Lag on disk replaces memory growth, which is why Kafka's
  backpressure failure is "24-hour-old data" instead of "OOMKilled".
- **Pub/Sub** — flow control (`max_outstanding_messages`, `max_outstanding_bytes`) is the
  client-side bound. Leaving it at the default and doing slow work per message is the
  standard way to OOM a Pub/Sub worker.

**Worked example with numbers.** An ingestion pipeline for a RAG system: a Pub/Sub
subscriber pulls documents, chunks and embeds them, writes to pgvector.

```
  Arrival rate            : 1,000 docs/s (bursty; 3,000/s on bulk import)
  Embedding throughput    : 800 docs/s   (bounded by the provider's limit)
  In-flight item size     : ~2 KB (text + metadata)
  Pod memory limit        : 4 GiB, of which ~3 GiB usable for the queue

  Unbounded queue, steady 1,000/s:
    net accumulation  = 200 items/s
    memory growth     = 200 x 2 KB = 400 KB/s = ~1.4 GB/hour
    time to OOM       = 3 GiB / 1.4 GB/h ~= 2.2 hours
    queue depth at OOM= 1.6M items
    latency at OOM    = 1.6M / 800 = 2,000 s = 33 minutes per item
  So for the final ~30 minutes before the crash, every embedding produced is
  for a document whose requester left long ago. That is negative goodput.

  Bounded queue, maxsize = 8,000 (10 s of consumer capacity):
    memory ceiling    = 8,000 x 2 KB = 16 MB   (bounded, predictable)
    worst-case latency= 8,000 / 800  = 10 s    (bounded, predictable)
    on full           = stop acking Pub/Sub -> messages stay in Pub/Sub, a
                        durable disk-backed buffer with a retention clock,
                        instead of in my RAM with a kill signal
```

The insight to say out loud: **the bound converts an unbounded latency and memory problem
into a bounded one, and pushes the buffering to the component designed for buffering.**
Sizing rule: `maxsize ≈ consumer_throughput × acceptable_queue_latency`. Ten seconds is
a good default; if the queue can hold 10 minutes of work, everything in it is stale.

### Enterprise production example

**Shopify** describes the queueing relationship explicitly in *10 Tips for Building
Resilient Payment Systems*: queue size, throughput and latency are linked, so an N+1
query that raises latency lowers throughput, the inbound queue grows, and eventually
clients wait so long they time out — *"at some point you need to put a limit on the amount
of work coming in — your application can't out scale the world."* Their production answer
for checkout is unusually literal backpressure applied to human beings: they use
**scriptable load balancers to throttle how many checkouts happen at once**, and when
demand exceeds capacity, buyers are put in a **waiting queue** before being allowed to
pay. That is a bounded queue with an admission gate, exposed as product behaviour — and
it is a much better user experience than letting everyone in and timing them all out.

### Code

```python
import asyncio
from google.cloud import pubsub_v1

QUEUE_MAX = 8_000          # ~10 s of consumer capacity at 800/s
queue: asyncio.Queue = asyncio.Queue(maxsize=QUEUE_MAX)

# Pub/Sub flow control is the first line of backpressure: the client library
# refuses to hold more than this in memory, and simply stops pulling.
flow = pubsub_v1.types.FlowControl(max_outstanding_messages=QUEUE_MAX,
                                   max_outstanding_bytes=64 * 1024 * 1024)


def on_message(msg) -> None:
    try:
        queue.put_nowait(msg)          # never `await put` from the callback:
    except asyncio.QueueFull:          # that hides the full queue as latency
        msg.nack()                     # back to Pub/Sub: durable, disk-backed
        QUEUE_FULL_NACKS.inc()


async def worker() -> None:
    while True:
        msg = await queue.get()
        try:
            await embed_and_store(msg.data)
            msg.ack()
        except Exception:
            msg.nack()
        finally:
            queue.task_done()
            QUEUE_DEPTH.set(queue.qsize())     # the control signal
```

Node — honouring the demand signal instead of ignoring it:

```js
import { pipeline } from 'node:stream/promises';

// WRONG: ignores the return value of write(); memory grows without limit.
// for (const doc of docs) writable.write(doc);

// RIGHT: pipeline() propagates backpressure from the slow sink to the source.
await pipeline(
  sourceStream,                                    // e.g. GCS object stream
  new Transform({ highWaterMark: 64,               // the bound, in objects
    objectMode: true,
    transform(doc, _enc, cb) { embed(doc).then(r => cb(null, r), cb); } }),
  pgVectorWritable,                                // slow sink sets the pace
);
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Producer and consumer rates can diverge and the producer is yours | The producer is the public internet — shed instead | Rejected or delayed work, and a producer that must handle "slow down" |
| Memory or connection exhaustion is the failure you fear | Work is cheap and droppable | Throughput ceiling by design; bursts are no longer absorbed silently |

### Follow-ups they will ask

**Q: What's the actual difference between backpressure and load shedding?**
A: Backpressure preserves the work and slows the producer, which requires a producer that
can be slowed. Load shedding discards work, which is the only option when the producer is
the open internet. I use backpressure inside the system — bounded queues, Pub/Sub flow
control, Kafka's pull model — and load shedding at the edge. Confusing them leads to the
classic mistake of trying to backpressure a public HTTP endpoint, where "slow down" just
becomes "everyone times out".

**Q: What do you monitor to know backpressure is working?**
A: Queue depth, its first derivative, and the age of the oldest item — depth alone can't
tell you if you're draining. Then the rejection or nack rate, and consumer lag if it's
Kafka. The alert I care about is "depth increasing monotonically for 10 minutes", because
that is the signature of a rate mismatch rather than a burst.

**Q: You bounded the queue and now you're rejecting work you used to accept. Isn't that
worse?**
A: It is the same amount of failed work, made visible and bounded. Before, I accepted
everything and failed it all invisibly 30 minutes later after burning CPU on it — with a
crash at the end. Now I reject 20% immediately with a `Retry-After` and complete 80%
within 10 seconds. Fast rejection is honest and lets the caller decide; slow acceptance
followed by an OOM is neither.

**Q: How does this change if the queue is Kafka rather than in-memory?**
A: The buffer moves to disk, so the memory failure disappears and is replaced by consumer
lag and retention. That is a much better failure mode — a 6-hour lag is recoverable by
scaling consumers, an OOM is not — but it is not unlimited: if lag exceeds retention,
Kafka deletes unread data and you have silent loss. So I alarm on lag as a *time* value,
not a message count, against the retention window.

### Red flags — do not say this

- ❌ "We'll use a queue to handle the spike." → ✅ "A *bounded* queue, sized to about ten
  seconds of consumer capacity, so a sustained rate mismatch shows up as rejection
  instead of unbounded latency and an OOM."
- ❌ "The queue absorbs bursts so we're fine." → ✅ "A queue absorbs *bursts*; it cannot
  absorb a sustained rate mismatch, which just accumulates until memory or retention runs
  out."
- ❌ "We'll autoscale on queue depth." → ✅ "Autoscaling helps when my consumer is the
  bottleneck; if the bottleneck is the embedding provider's rate limit, more consumers
  just produce more 429s."

---

## 9.10 Load shedding and graceful degradation

> **One-liner:** When demand exceeds capacity, you will drop something — load shedding is
> choosing *what* to drop, deliberately and cheaply, instead of letting the system choose
> randomly and expensively.

### Say this in the interview

> Load shedding is admitting that when I'm over capacity I'm going to fail some requests,
> and choosing which ones on purpose. The key insight is that a fast 503 beats a slow
> 200: if I'm at 150% of capacity and I try to serve everything, every request queues,
> everyone waits past their timeout, and I get 0% goodput while burning 100% of my CPU.
> If I shed 40% instantly at admission, the other 60% succeed in normal latency. I shed
> by priority, not randomly — health checks and payment writes are tier zero and never
> shed, authenticated interactive reads are next, then background and analytics work, and
> bulk or batch API traffic is shed first. I get that priority from a header set at the
> edge, and I make sure the shedding decision is cheap: it has to happen before I take a
> database connection or deserialise a large body, or the shed request still costs me
> most of what serving it would have. Alongside shedding I define a degradation ladder per
> feature, so instead of on/off I have full, cached, static, then error. For our RAG
> endpoint that's: full retrieval plus generation, then cached answer, then retrieved
> passages with no generated summary, then a static "search is degraded" response. And
> I'd rather return the third rung with a banner than a 500 — the user still gets
> something useful and my p99 stays flat.

### Mental model

```
  goodput (successful req/s)
     ^
     |          without shedding
     |        .-''-.            with shedding
 cap +-------'      '-.      +------------------------  (flat at capacity)
     |      /          '-.   |
     |     /              '--+--.....
     |    /                        '''----....____  -> 0 at heavy overload
     +---------------------------------------------------> offered load
                cap                    2x cap
  Without shedding, goodput COLLAPSES past capacity: every request queues
  past its timeout, so you spend 100% of CPU producing 0 useful responses.
  With shedding, goodput stays flat at capacity. That's the whole argument.
```

**Why a fast 503 beats a slow 200.** At 150% offered load with a 2 s client timeout and
a 3 s queue wait, 100% of responses arrive after the client has left — you have converted
all of your capacity into waste. Shedding 33% at the door keeps 100% of your capacity
producing responses somebody is still waiting for. The cost of a shed request must be
tiny: reject **before** authentication lookups, body parsing, or acquiring a DB
connection, ideally at the gateway.

**Priority tiers** — the design artefact to bring to the whiteboard:

| Tier | Traffic | Shed at |
|---|---|---|
| 0 | Health checks, liveness, payment writes, auth token refresh | Never |
| 1 | Authenticated interactive reads (a user is watching) | 90% utilisation |
| 2 | Search, recommendations, RAG generation | 80% |
| 3 | Bulk/batch API, exports, backfills, analytics | 70% |
| 4 | Prefetch, speculative work, cache warming | 60% |

**Admission control** is the mechanism. The credible modern version is **adaptive
concurrency**: rather than a hand-tuned request cap, track latency and reduce the
in-flight limit when latency rises above a measured baseline — a TCP-Vegas-style
controller (Netflix's `concurrency-limits` library, Envoy's adaptive concurrency filter).
The reason to prefer it: a static limit is right for exactly one hardware generation and
one traffic mix.

**Brownout** is the finer-grained sibling: instead of rejecting a whole request, drop the
expensive *parts* of it. Render the page without recommendations. Answer without the
re-ranker. Skip the personalisation call. The user gets a complete-looking response with
less value, which is nearly always better than an error.

**A concrete degradation ladder** for a RAG-backed support assistant — this is the kind of
table that makes an interviewer stop and nod:

```
 RUNG 1  FULL         retrieval (pgvector) + rerank + LLM generation
                      p99 2.5 s | cost 1.0x | trigger: normal
 RUNG 2  CACHED       semantic cache hit on normalised question
                      p99 40 ms | cost 0.02x | trigger: LLM p99 > 6 s
                      OR llm breaker half-open
 RUNG 3  NO-RERANK    retrieval + LLM, skip the cross-encoder rerank
                      p99 1.8 s | quality -8% | trigger: CPU > 80%
 RUNG 4  EXTRACTIVE   top-5 passages verbatim, no generation, banner:
                      "showing source excerpts"
                      p99 120 ms | trigger: llm breaker OPEN
 RUNG 5  KEYWORD      Postgres full-text search, no embeddings
                      p99 80 ms | trigger: pgvector breaker OPEN
 RUNG 6  STATIC       link to the help centre + "assistant unavailable"
                      p99 5 ms | trigger: everything else open

 Every rung: emit `degradation_rung` as a metric and an `X-Degraded` header
 so a permanent silent degradation is impossible to miss.
```

That last line is the operational trap to name: a system stuck happily on rung 4 for
three weeks because nothing pages when the fallback works.

### Enterprise production example

**Shopify** does load shedding at the edge with **scriptable load balancers**, throttling
the number of checkouts in flight and placing excess buyers in a **waiting queue** rather
than admitting everyone and timing them out — admission control expressed as product UX,
tested against deliberately scheduled high-volume flash sales. Their **Semian** fallbacks
are graceful degradation in the small: customer sessions live in Redis, so when Redis is
down they **disable customer sign-in on the storefront** and keep serving pages, and for
pages that are worthless without their primary datastore they return an honest HTTP 500
unless a cached copy exists. **Google's SRE book** frames the general principle: return a
*specific* status for overload so clients and upper layers back off rather than treating
it as a generic retryable error, and take degradation conditions seriously — because when
they are ignored, work piles up, tasks run out of memory or thrash, and a subset failure
becomes a cascading one.

### Code

```python
from fastapi import Request, HTTPException
import time

# Tier 0 never sheds. Higher tier number = shed earlier.
TIER_SHED_AT = {0: 1.01, 1: 0.90, 2: 0.80, 3: 0.70, 4: 0.60}

class AdaptiveLimiter:
    """Vegas-style: shrink the in-flight limit when latency exceeds baseline."""
    def __init__(self, initial=200, floor=20, ceiling=2000):
        self.limit, self.floor, self.ceiling = initial, floor, ceiling
        self.inflight, self.baseline = 0, None

    def observe(self, latency: float) -> None:
        self.baseline = latency if self.baseline is None else min(
            self.baseline * 1.05, self.baseline * 0.95 + latency * 0.05)
        queue_est = self.inflight * (1 - self.baseline / max(latency, 1e-6))
        if queue_est > self.limit / 4:
            self.limit = max(self.floor, int(self.limit * 0.9))
        elif queue_est < 1:
            self.limit = min(self.ceiling, self.limit + 1)

    @property
    def utilisation(self) -> float:
        return self.inflight / self.limit


limiter = AdaptiveLimiter()


async def shed_middleware(request: Request, call_next):
    # Cheap first: read the tier from a header the edge already set. No DB,
    # no body parse, no auth lookup before the decision.
    tier = int(request.headers.get("x-priority-tier", 2))
    if request.url.path in ("/healthz", "/readyz"):
        tier = 0
    if limiter.utilisation >= TIER_SHED_AT[tier]:
        SHED.labels(tier=tier).inc()
        return JSONResponse({"error": "overloaded", "tier": tier}, status_code=503,
                            headers={"Retry-After": "2"})
    limiter.inflight += 1
    t0 = time.monotonic()
    try:
        return await call_next(request)
    finally:
        limiter.inflight -= 1
        limiter.observe(time.monotonic() - t0)
```

Note the sequencing: the shed decision reads one header and one integer. If it needed a
Redis lookup or a token decode, shedding itself would become the bottleneck at exactly the
moment you need it.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Public-facing service where offered load can exceed capacity | Internal pipeline where you can apply backpressure instead | Some users get errors while the system reports "healthy" — you must own that explicitly |
| You can classify traffic by priority | All traffic is genuinely equal (rare) | A tier taxonomy that must be maintained and honoured by every caller |
| Degradation ladder exists per feature | The feature is all-or-nothing (a payment) | Every rung is a code path that only runs during incidents — so it must be tested in normal times |

### Follow-ups they will ask

**Q: Why is a fast 503 better than a slow 200?**
A: Because past capacity the slow 200 arrives after the client's timeout, so it is a 100%
CPU cost for 0% goodput — and worse, the client retries, adding load. A 503 with
`Retry-After` costs microseconds, keeps my remaining capacity productive, and gives the
client actionable information. The goodput curve is the argument: without shedding,
goodput collapses toward zero past capacity; with shedding it stays flat.

**Q: How do you know the priority tier without doing expensive work first?**
A: The edge sets it. My API gateway knows the route, the API key's plan and whether the
call is interactive or batch, and stamps `X-Priority-Tier` — which internal callers may
not set themselves. The service trusts that header because it is stripped and rewritten
at the trust boundary. Deriving the tier inside the service would need the auth lookup I
am trying to avoid.

**Q: Doesn't shedding hide the real problem?**
A: It hides it from the *user*, which is the point, and it must not hide it from me. So
shed rate, degradation rung and fallback rate are all first-class metrics with alerts, and
my SLO is measured on served requests *including* shed ones. The specific failure I guard
against is running on rung 4 for weeks because everything looks green.

**Q: How do you test the degradation ladder?**
A: Force it. A config flag pins the rung, so each one runs in staging on every release and
a fraction of production traffic exercises rungs 2 and 4 continuously. Otherwise the
fallback is code that has only ever run during an incident, which is when you least want
to discover that it throws a `KeyError`.

### Red flags — do not say this

- ❌ "We autoscale so we don't need load shedding." → ✅ "Autoscaling takes tens of seconds
  to minutes; shedding protects the 60 seconds before the new pods are ready, and it is
  the only defence when the bottleneck is a downstream I can't scale."
- ❌ "We shed the oldest requests." → ✅ "I shed by *priority tier* at admission — dropping
  a queued request means I already paid for it, so the decision belongs at the door."
- ❌ "Degradation means showing an error page." → ✅ "Degradation is a ladder: full,
  cached, extractive-only, keyword-only, static — and the rung is emitted as a metric so
  we can't sit on a fallback silently."

---

## 9.11 Cascading failures

> **One-liner:** A cascading failure is a positive feedback loop in which the system's own
> response to overload — retries, restarts, health-check-driven node removal — becomes the
> dominant source of load, so the system does not recover when the trigger goes away.

### Say this in the interview

> A cascading failure is a feedback loop, and the anatomy is always roughly the same. One
> dependency gets slow. Because callers have generous or missing timeouts, their threads
> or connections pile up waiting. The caller's pool exhausts, so its own health check
> starts timing out, so the load balancer removes that node — which pushes the same
> traffic onto fewer nodes, which exhausts their pools faster, and now it's spreading
> upstream. Meanwhile retries have doubled or tripled the offered load at exactly the
> moment capacity dropped. The critical property is that this is *metastable*: the
> original trigger can be completely gone and the system stays down, because the
> sustaining effect — usually retries, sometimes cold caches, sometimes GC — is now
> generating the load by itself. The HotOS paper that named this found the sustaining
> effect was retry policy in more than half of the public incidents they studied. That's
> why recovery needs an external push: you shed load hard, disable retries, or, most
> often, take the traffic away completely and let it back in gradually — because if you
> restore full traffic to a cold cache you re-trigger the loop immediately. The
> preventions are the boring stack: tight timeouts derived from p99, retry budgets, jitter,
> circuit breakers, bulkheads, load shedding, and health checks that don't lie. I'd
> single out one thing: your health check must not depend on the sick dependency, or
> your load balancer will amplify the outage for you.

### Mental model

The anatomy, drawn out — memorise the shape, not the words:

```
 (1) dependency D slows        p99: 80 ms -> 8 s
        |
 (2) callers' workers block    no/loose timeout: threads parked in D
        |
 (3) caller pool EXHAUSTS      Little's Law: 50 workers / 8 s = 6 req/s
        |                                    (was 625 req/s)
 (4) health check TIMES OUT    /healthz shares the pool, or probes D
        |
 (5) LB removes the node       "the node is unhealthy" -- it isn't, it's busy
        |
 (6) same load, fewer nodes    per-node load +25% with 4 of 5 remaining
        |
 (7) remaining nodes exhaust   ---> back to (3), now spreading UPSTREAM
        |
 (8) retries multiply load     3 layers x 4 attempts = 64x on D
        |
 (9) METASTABLE                D recovers. System does NOT.
                               Sustaining effect = retries + cold caches
```

**Why it does not self-heal.** In the metastable state the load is generated by the
system's own retry and restart behaviour, so removing the trigger changes nothing.
Bronson et al. define it precisely: goodput is unusably low and a sustaining effect —
work amplification or lost efficiency — keeps it there; **leaving the state requires a
strong corrective push, such as rebooting or dramatically reducing load.** Their
three-state model is the part worth quoting:

```
   STABLE          load low enough to absorb a burst and self-recover
      |  load rises (often permanently -- it's more efficient here)
      v
   VULNERABLE      healthy, but a strong enough trigger can ignite the loop
      |  TRIGGER (deploy, GC pause, network blip, failover, cache flush)
      v
   METASTABLE      goodput ~0, sustained by the feedback loop.
                   Removing the trigger does not help.
```

The line that lands in an interview: *"the postmortem blames the trigger, but the root
cause is the sustaining effect."*

**Common sustaining effects, ranked by how often they are the culprit:**

1. **Retries** — the amplifier. >50% of studied incidents.
2. **Cold caches** — restart empties the cache, so every request hits the database, which
   is now the bottleneck, so you cannot serve enough traffic to warm the cache. This is why
   "just restart everything" often fails.
3. **Queue backlog** — the work in the queue is older than its timeout, so processing it
   produces zero goodput while consuming 100% of capacity.
4. **Health-check flapping** — nodes cycling in and out of the LB, each cycle serving a
   cold-start burst.
5. **GC / memory thrash** — high queue depth raises heap, which raises GC time, which
   raises latency, which raises queue depth.
6. **Leader-election churn** — repeated re-elections, each with a no-progress window.

**The recovery playbook** (say these in order, it sounds like experience):

1. **Stop the amplification first.** Disable retries via a feature flag; the breaker
   should already be doing this.
2. **Drop load hard at the edge.** Shed by tier, or take the traffic to zero. Half
   measures do not exit a metastable state.
3. **Let it back in gradually.** Ramp 1% → 5% → 25% → 100%, watching latency, so caches
   and pools warm under load they can serve. Restoring 100% instantly re-triggers it.
4. **Drain poisoned queues** or fast-fail items older than their deadline — processing
   stale work is negative goodput.
5. **Only then** consider scaling up; capacity added into a live feedback loop is
   consumed by the loop.

**Health checks that lie** deserve their own callout, because it is the step most
candidates miss. If `/healthz` runs on the same exhausted worker pool, or if it checks
the downstream dependency, then a slow dependency makes every node report unhealthy and
your load balancer removes your entire fleet. Rules: serve health checks from a separate
thread/port, make **liveness** shallow (am I alive?) and **readiness** meaningful but
never transitive, and configure your LB so it will not remove *all* backends — Envoy calls
this **panic mode** (below a healthy-host threshold, typically 50%, it routes to all hosts
regardless of health, on the sound theory that half-broken beats zero).

### Enterprise production example

**Bronson, Aghayev, Charapko and Zhu**, *Metastable Failures in Distributed Systems*
(HotOS '21), and the follow-up *Metastable Failures in the Wild* (USENIX), are the best
citations available here because they analysed **public incident reports from Google, AWS,
Azure, IBM, Spotify and Cassandra** and classified trigger vs sustaining effect. Findings
worth quoting: the most common sustaining effect **by far is the retry policy, present in
more than half** of the studied incidents; others included expensive error handling, lock
contention, and performance degradation from leader-election churn. One documented example
they cite is the **Amazon SimpleDB service disruption**, where the trigger was a power
loss that crashed multiple servers and the sustaining effect was **load amplification due
to a timeout** — and the remediation was a change in timeout policy plus additional
capacity, i.e. the fix was to the sustaining effect, not the trigger. The **Google SRE
book** chapter *Addressing Cascading Failures* supplies the mechanics: overload causes
tasks to run out of memory or burn CPU in memory thrashing, latency suffers, traffic is
dropped, and *"the failure in a subset of a system might trigger the failure of other
system components, potentially causing the entire system to fail"* — plus the concrete
countermeasures of ≤3 attempts, per-client retry budgets, server-wide retry ceilings, and
distinct overload status codes.

### Code

The health check that does not lie — the cheapest cascade prevention there is:

```python
from fastapi import APIRouter, Response

router = APIRouter()

@router.get("/healthz")               # LIVENESS: shallow. Never checks a dependency.
async def healthz() -> dict:
    return {"ok": True}               # if the process can answer, it is alive


@router.get("/readyz")                # READINESS: local capacity only.
async def readyz(response: Response) -> dict:
    checks = {
        # My own pool, not the dependency's health. A saturated pool is a real
        # reason to take me out of rotation; a slow downstream is NOT, because
        # every replica shares that downstream and the LB would remove all of us.
        "db_pool": db.pool.freesize > 0,
        "queue": queue.qsize() < QUEUE_MAX * 0.95,
        "inflight": limiter.utilisation < 0.98,
    }
    if not all(checks.values()):
        response.status_code = 503
    return {"ready": all(checks.values()), "checks": checks}
```

```yaml
# Envoy: never remove the whole fleet because a shared dependency is slow.
common_lb_config:
  healthy_panic_threshold: { value: 50 }   # <50% healthy -> ignore health status
outlier_detection:                          # eject the genuinely-bad outlier only
  consecutive_5xx: 5
  max_ejection_percent: 20                  # never eject more than 1 in 5
  base_ejection_time: 30s
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Any multi-service architecture with shared dependencies | Truly independent single-service systems | Every guard (timeouts, budgets, breakers, shedding) is code, config and tuning you own |
| Prevention is cheap; recovery is not | — | Some legitimate requests are rejected during overload, by design |

### Follow-ups they will ask

**Q: Walk me through a cascading failure you would expect in the system we just designed.**
A: The vector database gets slow after an index rebuild. My RAG service has a 30-second
read timeout, so workers park in pgvector calls; at 50 workers and 8-second p99 my
capacity drops from ~600 req/s to about 6. `/readyz` shares the pool, so Kubernetes marks
pods unready and pulls them, concentrating traffic on fewer pods. The client SDK retries
three times, tripling offered load. Within two minutes everything is down including
endpoints that never touch pgvector. The fixes, in order of value: a 500 ms timeout on
pgvector, a bulkhead of 30 slots, a breaker with a keyword-search fallback, and a
`/readyz` that does not probe pgvector.

**Q: Why doesn't the system recover when the original problem is fixed?**
A: Because the load is now self-generated. Retries in flight, queues full of work already
past its deadline, and caches emptied by restarts mean the system is still at 3× offered
load with a fraction of its effective capacity. That is the metastable state, and by
definition it needs an external corrective push — shed to zero and ramp back — rather than
patience.

**Q: What is the single most common mistake that turns a partial outage into a total
one?**
A: A health check that depends on a shared downstream. Everything else degrades one
service; that one makes your load balancer amplify the outage by removing healthy
capacity. Liveness must be shallow, readiness must reflect only local capacity, and the
LB needs a panic threshold so it refuses to eject the entire fleet.

**Q: How would you detect that you are in the vulnerable state before a trigger arrives?**
A: Look for the amplification factor, not the error rate — everything looks green in the
vulnerable state. I track retry-to-request ratio, queue depth trend, utilisation of every
bulkhead, and the gap between p50 and p99. The specific tell is *sustained high
utilisation with no headroom*: a system running at 85% is one GC pause away from igniting
a loop, and load tests that measure goodput past 100% of capacity (not just up to it) are
the only way to see the cliff before a customer does.

### Red flags — do not say this

- ❌ "We'd restart the services." → ✅ "A restart empties the caches, and a cold cache is
  itself a sustaining effect — so I shed load to near zero first, then ramp back in
  stages so caches warm under load they can actually serve."
- ❌ "We'd scale up." → ✅ "Capacity added into a live feedback loop gets consumed by the
  loop; I have to break the amplification first, then scale."
- ❌ "Our health check verifies the database is reachable." → ✅ "That makes every replica
  fail its check simultaneously when the database is slow, so the load balancer removes
  the whole fleet — readiness reflects local capacity only."
- ❌ "It was caused by the network blip." → ✅ "The blip was the trigger; the root cause was
  the sustaining effect — un-budgeted retries — because the system stayed down after the
  network recovered."

---

## 9.12 Distributed locks

> **One-liner:** A distributed lock is a mutual-exclusion primitive across processes, and
> the correct first response to needing one is to check whether a unique constraint,
> `SKIP LOCKED`, or partitioning-by-key would remove the need entirely.

### Say this in the interview

> My honest position is that most requests for a distributed lock are a design smell, so
> I check three cheaper options first. A unique constraint in Postgres gives me mutual
> exclusion for free and it's transactional. `SELECT FOR UPDATE SKIP LOCKED` lets N
> workers claim distinct rows from a queue table with no lock service at all. And
> partitioning by key — Kafka's partition assignment, or consistent hashing — means only
> one consumer ever owns a given key, so exclusion is structural rather than acquired.
> When I genuinely do need a lock, the Redis version is `SET key <random-token> NX PX
> 30000`: NX makes acquisition atomic, PX guarantees it expires if I crash, and the random
> token matters because release must be a compare-and-delete in a Lua script — a plain
> `DEL` can delete a lock that already expired and was acquired by someone else. Then the
> part that shows you've read the literature: Kleppmann's critique of Redlock is that a
> lease-based lock cannot guarantee mutual exclusion in an asynchronous system, because a
> GC pause or a network delay can leave you holding an expired lease while a second client
> legitimately holds it — and Redlock has no facility for generating fencing tokens.
> Antirez pushed back that bounded clock drift is realistic in monitored deployments and
> conceded the monotonic-clock point. Both are right about different things: for an
> efficiency lock, where a rare double-execution costs a duplicate email, Redis SETNX is
> fine. For a correctness lock, where double-execution corrupts data, I want a
> consensus-backed lock service and fencing tokens the resource itself validates. The
> line I'd finish on: the lock service is not the lock — the resource rejecting stale
> tokens is the lock.

### Mental model

**Try these before reaching for a lock:**

| Alternative | Shape | When it fits |
|---|---|---|
| **Unique constraint** | `UNIQUE(idem_key)` + `ON CONFLICT DO NOTHING` | "Only do this once" — most cases |
| **`SELECT ... FOR UPDATE SKIP LOCKED`** ([Module 05](./05_Databases_Relational.md)) | N workers, distinct rows, no contention | Job/queue tables |
| **Partition by key** | Kafka partitions, consistent hashing | One owner per entity, structurally |
| **Optimistic concurrency** | `UPDATE ... WHERE version = $expected` | Low-contention read-modify-write |
| **Postgres advisory lock** | `pg_try_advisory_xact_lock(hashtext(key))` | You already have Postgres and want a real lock that dies with the transaction |
| **Single-writer design** | A leader owns the mutation | Coordinators, schedulers |

`SKIP LOCKED` is the most under-used of these. It turns a queue table into a
lock-free work-claiming mechanism:

```sql
-- N workers can run this concurrently; each gets disjoint rows, no blocking.
WITH claimed AS (
  SELECT id FROM jobs
   WHERE status = 'pending' AND run_after <= now()
   ORDER BY priority DESC, run_after
   FOR UPDATE SKIP LOCKED
   LIMIT 10
)
UPDATE jobs SET status='running', claimed_at=now(), claimed_by=$1
 WHERE id IN (SELECT id FROM claimed)
RETURNING *;
```

**The two failure modes of a lease-based lock:**

```
  (A) The lease expires while you still think you hold it
  client A: acquire(ttl=30s) --[ 25s work ]-- GC PAUSE 20s ----.
                                lease expires at t=30          |
  client B:                     acquire OK at t=31 --[work]----+--> WRITE
  client A: resumes t=45, still believes it holds the lock ----+--> WRITE
                                                both write. corruption.

  (B) Fencing fixes (A) at the RESOURCE, not at the lock service
  client A: token=33 --(paused)------------> write(token=33) REJECTED
  client B: token=34 --> write(token=34) OK  (resource saw 34 already)
```

**Fencing tokens** are the actual fix: the lock service issues a monotonically increasing
number on each grant, the client passes it with every protected write, and **the resource
rejects any write whose token is lower than the highest it has seen.** Kleppmann's key
observation is that this works *even if the client is buggy, paused or partitioned*,
because correctness no longer depends on the holder behaving well. His concrete objection
to Redlock is that it produces no such number — its random value provides uniqueness but
not monotonicity — and a counter on one Redis node is not fault-tolerant while counters on
several nodes drift.

**Present both sides fairly.** Kleppmann: Redlock assumes bounded network delay and
bounded execution time — effectively a synchronous system — and violates safety when those
assumptions break; it is *"neither fish nor fowl"*: too heavyweight for efficiency locks,
not safe enough for correctness locks; if you need correctness, use ZooKeeper (or a
database with real transactional guarantees) **and enforce fencing tokens on all resource
accesses.** Antirez: bounded clock drift is a realistic operational assumption, any
auto-expiring lock shares the pause vulnerability, and tokens can be layered on top of
Redlock; he conceded the point about using a monotonic clock API. The synthesis to offer:

| | Efficiency lock | Correctness lock |
|---|---|---|
| Cost of double execution | Duplicate work, duplicate email, wasted spend | Corrupted data, double charge |
| Acceptable | Redis `SET NX PX` on a single instance | Consensus service (etcd/ZooKeeper) **+ fencing at the resource** |
| Redlock | Unnecessarily heavyweight | Insufficient on its own |

### Enterprise production example

**Kleppmann vs antirez (2016)** is the canonical exchange and naming both sides is a
strong signal. Kleppmann's *How to do distributed locking* argued that Redlock's
correctness depends on timing assumptions, that a GC pause between the final clock check
and the resource access is not caught by any clock check, and that large network delay can
still let a message from a process that no longer holds the lock reach the resource —
therefore **fencing is required regardless**. Antirez's *Is Redlock safe?* accepted the
monotonic-clock recommendation and rejected the broader conclusion. The practically useful
consensus that emerged: keep the critical section short relative to the lease, keep hosts
NTP-synced, prefer a lock service whose correctness does not depend on local clocks
(etcd, ZooKeeper, Spanner) when correctness matters, and **fence at the resource**, because
the safest lock service in the world cannot prevent a stale holder from writing if the
resource does not check tokens.

### Code

Correct Redis lock — random token, TTL, Lua compare-and-delete, and lease extension:

```python
import secrets, redis.asyncio as redis

r = redis.Redis(host="redis", socket_timeout=0.2)

# Release MUST be atomic compare-and-delete. A bare DEL can delete someone
# else's lock if ours already expired -- the classic bug in this code.
_RELEASE = r.register_script("""
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('DEL', KEYS[1])
else
  return 0
end
""")

# Extend only if we still hold it, for work that legitimately runs long.
_EXTEND = r.register_script("""
if redis.call('GET', KEYS[1]) == ARGV[1] then
  return redis.call('PEXPIRE', KEYS[1], ARGV[2])
else
  return 0
end
""")


class LockLost(Exception):
    """We no longer hold the lease. Abort; do not write."""


@asynccontextmanager
async def redis_lock(key: str, ttl_ms: int = 30_000):
    token = secrets.token_urlsafe(24)          # unique per acquisition
    if not await r.set(f"lock:{key}", token, nx=True, px=ttl_ms):
        raise LockUnavailable(key)
    try:
        yield token                             # pass it down: it is the fence
    finally:
        # 0 means the lease had already expired and possibly been re-acquired:
        # anything we wrote after expiry may have raced. Alert on this.
        if await _RELEASE(keys=[f"lock:{key}"], args=[token]) == 0:
            LEASE_EXPIRED_BEFORE_RELEASE.labels(key).inc()
```

Fencing at the resource — the half that actually provides safety:

```sql
-- Monotonic token from the DB, so it survives Redis losing its state.
CREATE TABLE fences (resource TEXT PRIMARY KEY, token BIGINT NOT NULL DEFAULT 0);

-- On acquire: SELECT token+1 ... RETURNING to mint the next token.
-- On every protected write, in one statement:
UPDATE documents
   SET content = $2, fence_token = $3
 WHERE id = $1
   AND fence_token < $3;     -- a paused holder's stale token writes 0 rows
-- rowcount == 0  =>  raise LockLost. Do not retry blindly.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| A genuine singleton section you cannot restructure (a cron that must run once) | A unique constraint, `SKIP LOCKED`, or key partitioning would do | Liveness risk (holder dies → wait for TTL) and safety risk without fencing |
| Efficiency: avoiding duplicate expensive work | Correctness: money, ledgers, inventory — unless you fence | An extra dependency in the critical path; if Redis is down, can you proceed? Decide explicitly |

### Follow-ups they will ask

**Q: Why can't you just `DEL` the key to release the lock?**
A: Because your lease may already have expired and been acquired by another client, so
`DEL` deletes *their* lock and you have created the mutual-exclusion violation you were
preventing. Release has to be a compare-and-delete against a token unique to your
acquisition, which requires atomicity — hence the Lua script. And when the script returns
0, that is a real signal: it means I was operating without the lock, and I want an alert,
not a shrug.

**Q: What TTL do you set, and what if the work takes longer?**
A: TTL a few times the p99 duration of the critical section — 30 s for something that
normally takes 3 s. If work can legitimately exceed it, I run a watchdog that extends the
lease with the compare-and-set `PEXPIRE` script at roughly one third of the TTL, and if an
extension fails I abort rather than continue, because I no longer hold the lock. What I
never do is set a TTL longer than I can tolerate the resource being stuck after a crash —
that is the liveness side of the trade.

**Q: Is Redlock safe?**
A: For efficiency locks, in practice, yes — and for correctness locks, not on its own,
which is where Kleppmann and antirez actually disagree least. Redlock has no fencing-token
facility, so a GC pause or network delay can let an expired holder write. If I need
correctness I use etcd or ZooKeeper for the lease, because their correctness doesn't
depend on local clocks, *and* I fence at the resource. Honestly, if I'm running one Redis
and my critical section is short and idempotent, plain `SET NX PX` is simpler than Redlock
and about as safe.

**Q: I need to make sure a nightly report job runs exactly once across 10 pods. Lock?**
A: I'd use a lock only as a last resort. First choice is a unique constraint on
`(job_name, run_date)` — whoever inserts the row runs the job, everyone else gets a
conflict and exits, and it is durable and auditable. Second choice is a Kubernetes
`CronJob` with `concurrencyPolicy: Forbid`, which makes the scheduler responsible. A
distributed lock is the third choice, and even then the job body should be idempotent so a
double run is survivable.

### Red flags — do not say this

- ❌ "We use Redis SETNX for locking." → ✅ "`SET key <token> NX PX 30000`, released with a
  Lua compare-and-delete — a bare `SETNX` without a TTL deadlocks on crash, and a bare
  `DEL` can release someone else's lock."
- ❌ "Redlock guarantees mutual exclusion." → ✅ "No lease-based lock can, in an
  asynchronous system; a GC pause defeats it. Fencing tokens validated by the resource are
  what actually provide safety."
- ❌ "We take a lock so two workers don't process the same job." → ✅ "`FOR UPDATE SKIP
  LOCKED` gives each worker disjoint rows with no lock service, and it's transactional."

---

## 9.13 Leader election

> **One-liner:** Leader election picks exactly one process to perform a role — scheduler,
> coordinator, singleton writer — and every practical implementation is a renewable lease
> plus a fencing mechanism, because "exactly one" cannot be guaranteed without one.

### Say this in the interview

> I need leader election whenever a job must be a singleton: a scheduler, a rebalancer, a
> change-data-capture reader, anything where two active instances would produce duplicate
> or conflicting work. The mechanism is always a lease — a key with a TTL that one
> instance holds and continuously renews, and if it stops renewing, someone else takes
> over. On GCP or any Kubernetes cluster I'd use the built-in `Lease` object in
> `coordination.k8s.io`, because it's already there, it's backed by etcd's consensus, and
> the client-go leaderelection package handles renewal for me; outside Kubernetes it's
> etcd, ZooKeeper or Consul, or honestly just a Postgres row with an `expires_at` if I
> already have Postgres and can tolerate the failover window. The three numbers that
> matter are lease duration, renew deadline, and retry period — typically 15, 10 and 2
> seconds — and the important consequence is that after a leader dies there's a gap of up
> to the lease duration with no leader at all. That's the availability cost of not having
> split-brain. And split-brain is the real risk: a leader that's partitioned or GC-paused
> still believes it's the leader, so I make the leader step down proactively if it can't
> renew, and I use a fencing token — etcd's revision number or the lease generation — so
> writes from a deposed leader are rejected downstream. Exactly-one-leader is not
> achievable; exactly-one-*writer* is, if the resource fences.

### Mental model

```
  etcd / K8s Lease / ZK ephemeral node
        |
   +----+-----------------------------------------------+
   |  holder: pod-a   generation: 41   renewTime: t=100  |
   +----+-----------------------------------------------+
        |
  pod-a renews every 2s, lease duration 15s     pod-b, pod-c watch and wait
        |
   pod-a network-partitioned at t=104
        |
   t=115  lease expires -> pod-b acquires, generation: 42
        |
   pod-a (still running, still thinks it is leader) writes with generation 41
        |
   resource: 41 < 42  -> REJECTED         <-- fencing is what saves you
```

| Mechanism | How | Failover gap | Notes |
|---|---|---|---|
| **Kubernetes `Lease`** | `coordination.k8s.io/v1`, client-go leaderelection | ~lease duration (15 s default) | Free if you're on GKE; etcd-backed |
| **etcd** | Lease + `Txn` compare-and-swap; `revision` is a fencing token | Configurable, seconds | Strong, and gives you monotonic revisions |
| **ZooKeeper** | Ephemeral sequential znode, lowest sequence wins | Session timeout | Sequence number is a natural fencing token |
| **Consul** | Session + KV acquire | Session TTL | Good if you already run Consul |
| **Postgres row** | `UPDATE leader SET owner=$1, expires_at=now()+15s WHERE expires_at < now()` | Lease TTL | Zero new infra; fine for low-stakes singletons |

**The three timings and what they mean:**

- **Lease duration** (15 s) — how long a lease is valid without renewal. This *is* your
  worst-case leaderless window.
- **Renew deadline** (10 s) — the leader must successfully renew within this or it
  **voluntarily steps down**. Must be < lease duration, so a partitioned leader gives up
  *before* someone else can take over.
- **Retry period** (2 s) — how often to attempt renewal / acquisition.

The invariant: `retry_period < renew_deadline < lease_duration`. Getting this wrong is how
you build a genuine two-active-leaders window.

**Split-brain** is unavoidable in the general case — the leader cannot distinguish "I am
partitioned" from "the world is quiet" fast enough — so you design for it: voluntary step-
down on renewal failure, plus **fencing** so a deposed leader's writes are rejected.

### Enterprise production example

**Kubernetes** itself is the best available example, and it is one he can inspect: both
`kube-controller-manager` and `kube-scheduler` run multiple replicas in active-passive
mode using leader election over a `Lease` object in `coordination.k8s.io`, with defaults of
`leaseDurationSeconds: 15`, `renewDeadlineSeconds: 10`, and `retryPeriodSeconds: 2`. The
consequence is publicly documented behaviour: when a control-plane node dies, scheduling
pauses for up to ~15 seconds while the lease expires and a standby acquires it. That is a
deliberate trade — a bounded availability gap in exchange for never having two schedulers
placing pods simultaneously.

### Code

```python
# Postgres-based lease: no new infrastructure, and the generation is a fence.
LEASE_SECONDS, RENEW_EVERY = 15, 5

async def try_acquire_or_renew(who: str) -> int | None:
    """Returns the fencing generation if we hold the lease, else None."""
    row = await db.fetchrow(
        """INSERT INTO leader (role, owner, expires_at, generation)
           VALUES ('scheduler', $1, now() + $2::interval, 1)
           ON CONFLICT (role) DO UPDATE
             SET owner = $1,
                 expires_at = now() + $2::interval,
                 -- bump the fence only on a genuine takeover, not on renewal
                 generation = leader.generation +
                              CASE WHEN leader.owner = $1 THEN 0 ELSE 1 END
           WHERE leader.owner = $1 OR leader.expires_at < now()
           RETURNING generation""",
        who, f"{LEASE_SECONDS} seconds")
    return row["generation"] if row else None


async def run_as_leader(who: str) -> None:
    gen = None
    while True:
        new_gen = await try_acquire_or_renew(who)
        if new_gen is None:
            gen = None
            await stop_singleton_work()      # step down FAST; do not keep writing
        elif gen != new_gen:
            gen = new_gen
            await start_singleton_work(fence=gen)   # every write carries `gen`
        await asyncio.sleep(RENEW_EVERY)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Genuinely singleton work (scheduler, CDC reader, rebalancer) | The work can be partitioned by key so every instance owns a disjoint slice | A leaderless failover window equal to the lease duration |
| You need a coordinator for a protocol | Idempotency makes duplicate execution harmless — then skip election | A consensus dependency; if etcd is unavailable, nobody leads |

### Follow-ups they will ask

**Q: Two pods both believe they are the leader. How do you prevent damage?**
A: I accept that the belief can happen and stop the *damage* instead: the leader steps down
if it cannot renew within the renew deadline, which is shorter than the lease duration, and
every write from the leader carries a fencing generation that the resource compares
against the highest it has seen. A deposed leader's writes then fail on a `WHERE
generation >= $n` predicate. Preventing the belief needs synchrony; preventing the write
needs one integer.

**Q: Why not just run one replica?**
A: Because then a node failure means the job stops until someone notices. Leader election
buys automatic failover with a bounded gap — Kubernetes' 15-second default — while keeping
the singleton property. The alternative I'd genuinely consider first is partitioning the
work by key so there is no singleton at all, which eliminates the whole problem.

**Q: Postgres row versus etcd for this?**
A: Postgres if I already run it, the singleton is low-stakes, and I can tolerate a lease-
duration gap — it is one table and zero new infrastructure. etcd or the Kubernetes Lease
when I need the consensus guarantees and a monotonic revision I can fence with, or when
the leader coordinates something expensive enough that a split-brain window costs real
money.

### Red flags — do not say this

- ❌ "The leader holds the lock so only one runs." → ✅ "A lease guarantees at most one
  *acquirer*, not at most one *actor* — a GC-paused leader still thinks it leads, so I
  fence the writes."
- ❌ "We use a config flag to designate the leader." → ✅ "A static designation has no
  failover; the point of election is that a standby takes over automatically within the
  lease duration."

---

## 9.14 Saga pattern and compensating transactions

> **One-liner:** A saga replaces a distributed ACID transaction with a sequence of local
> transactions plus explicit compensating actions, trading atomicity for availability and
> accepting that intermediate states are visible.

### Say this in the interview

> A saga is what I use when a business operation spans services and I can't have a single
> ACID transaction — because two-phase commit across HTTP services means a coordinator
> failure can hold locks indefinitely, and it needs every participant available at the same
> instant. So instead of one atomic transaction, I run a sequence of local transactions,
> each of which commits immediately, and I define a compensating action for each step. If
> step four fails, I run the compensations for three, two and one in reverse. Two
> structures: orchestration, where a single coordinator service holds the state machine and
> calls each step, and choreography, where each service listens for the previous step's
> event and emits its own. I default to orchestration for anything with more than about
> three steps, because the workflow is explicit, debuggable and queryable in one place —
> choreography spreads the workflow across N services and nobody can tell you what state
> an order is in without joining logs. Two honest problems. Compensation isn't a rollback:
> the state was visible, so "cancel the order" is a new business fact, not an erasure, and
> if the compensation itself fails — the refund API is down — I need retries with
> idempotency keys and eventually a human queue, because a stuck compensation is real money
> in limbo. And because there's no isolation, I use semantic locks: mark the row
> `PENDING_PAYMENT` so other operations know it's mid-saga rather than settled. Every step
> and every compensation must be idempotent, because the coordinator will retry them.

### Mental model

```
  ORCHESTRATION                          CHOREOGRAPHY
  -------------                          ------------
   +-----------------+                   order-svc --emits--> OrderCreated
   | saga orchestr.  |                                            |
   | (state machine) |                   payment-svc <-listens----+
   +--+---+---+---+--+                     |--emits--> PaymentTaken
      |   |   |   |                                        |
      v   v   v   v                       inventory-svc <--+
    order pay inv ship                       |--emits--> StockReserved
                                                            |
   one place knows the flow             shipping-svc <-------+
   easy to query state, test,           no central state; add a service
   add compensation, retry              without touching others
```

| | Orchestration | Choreography |
|---|---|---|
| Workflow visible | In one service | Spread across N services |
| Coupling | Orchestrator knows all participants | Participants know only events |
| Debugging "where is order 123?" | One query | Join logs across services |
| Adding a step | Change the orchestrator | Add a subscriber |
| Risk | Orchestrator becomes a god service / SPOF | Cyclic event dependencies nobody can see |
| Use for | >3 steps, compensations, money | 2–3 steps, loosely-related side effects |

**Compensation is not rollback.** This is the sentence to say. A rollback erases; a
compensation is a new, visible business fact. `CancelReservation` after
`ReserveInventory` leaves an audit trail, may incur a fee, and may not fully restore the
prior state (the seat someone else took in between is gone). Some steps are
**uncompensatable** — an email is sent, an SMS is delivered, an LLM API call is billed —
so the design rule is: **order the saga so uncompensatable steps come last**, after
everything that can fail has already succeeded.

**When compensation fails.** The failure mode with actual money in it:

```
  step 1 charge card         OK
  step 2 reserve inventory   FAIL (out of stock)
  compensate 1: refund       FAIL (payment provider down)
      -> retry with backoff + the SAME idempotency key
      -> still failing after N attempts
      -> saga state = COMPENSATION_STUCK, row parked, ALERT + human queue
```

You cannot abandon it and you cannot loop forever. The correct design is: compensations
are retried indefinitely with backoff (they are idempotent, so this is safe), the saga row
records `compensation_attempts` and `last_error`, and a stuck compensation pages someone,
because it represents a customer whose money is in limbo.

**Semantic locks** replace the isolation you gave up. Mark the entity with its in-saga
state — `order.status = 'PENDING_PAYMENT'`, `seat.state = 'HELD'` with a `held_until` —
so concurrent operations can see the row is mid-saga and either refuse, queue, or read it
as provisional. Without them you get the classic anomaly: a user sees an order as
confirmed while its payment step is still running, then it disappears.

Cross-links: the transactional outbox that makes each step's event publication atomic with
its local commit is
[Module 08 — Messaging, Kafka & Events](./08_Messaging_And_Events.md); the isolation
properties you are trading away are
[Module 05 — isolation levels](./05_Databases_Relational.md), and the 2PC-vs-saga
comparison sits in [Module 06 — Data Distribution](./06_Data_Distribution.md). Every step
needs [idempotency](#94-idempotency) and a [DLQ](#96-dead-letter-queues).

### Enterprise production example

**Scenario (labelled a scenario, not a company claim):** a booking flow — `reserve seat →
charge card → issue ticket → send confirmation` — implemented as an orchestrated saga in
FastAPI with the state machine in Postgres and steps dispatched over Pub/Sub. The design
decisions that matter: the seat reservation is a semantic lock (`state='HELD'`,
`held_until = now() + 15 min`) so the seat map shows it as unavailable without claiming
it is sold; the card charge carries a client-generated `Idempotency-Key` so the
orchestrator's retries cannot double-charge; ticket issuance comes *before* the
confirmation email because the email is uncompensatable; and a sweeper releases `HELD`
seats whose `held_until` has passed, which is what makes an orchestrator crash recoverable
without a distributed lock. The compensation ladder is `void charge → release seat`, with
`COMPENSATION_STUCK` as an explicit, alertable terminal state.

### Code

```python
# Orchestrated saga: state in Postgres, every step and compensation idempotent.
STEPS = [
    ("reserve_seat",  reserve_seat,  release_seat),
    ("charge_card",   charge_card,   void_charge),
    ("issue_ticket",  issue_ticket,  cancel_ticket),
    ("send_email",    send_email,    None),          # uncompensatable -> LAST
]


async def run_saga(saga_id: str, payload: dict) -> str:
    done: list[str] = []
    for name, forward, _ in STEPS:
        try:
            # saga_id doubles as the idempotency key: a retried step is a no-op.
            await forward(payload, idem_key=f"{saga_id}:{name}")
            await db.execute(
                "UPDATE sagas SET step=$2, updated_at=now() WHERE id=$1",
                saga_id, name)
            done.append(name)
        except PermanentError as exc:
            await compensate(saga_id, payload, done, reason=str(exc))
            return "COMPENSATED"
    await db.execute("UPDATE sagas SET state='COMPLETED' WHERE id=$1", saga_id)
    return "COMPLETED"


async def compensate(saga_id, payload, done, reason) -> None:
    await db.execute(
        "UPDATE sagas SET state='COMPENSATING', failure_reason=$2 WHERE id=$1",
        saga_id, reason)
    for name in reversed(done):
        undo = next(c for n, _, c in STEPS if n == name)
        if undo is None:
            continue                       # already-sent email: nothing to undo
        try:
            await undo(payload, idem_key=f"{saga_id}:undo:{name}")
        except Exception as exc:
            # Never swallow this. Money is in limbo until a human resolves it.
            await db.execute(
                """UPDATE sagas SET state='COMPENSATION_STUCK', stuck_step=$2,
                       last_error=$3 WHERE id=$1""", saga_id, name, str(exc))
            await pager.page("saga_compensation_stuck", saga_id=saga_id, step=name)
            raise
    await db.execute("UPDATE sagas SET state='COMPENSATED' WHERE id=$1", saga_id)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| A business operation spans services or external providers | It all fits in one database — use a real transaction | No isolation: intermediate states are visible, so you need semantic locks |
| You need availability more than atomicity | You need strict serialisability | Roughly 2× the code paths (forward + compensation), and the compensation paths are rarely exercised |
| Steps are individually idempotent and mostly compensatable | Key steps are uncompensatable and cannot be reordered last | A new terminal state, `COMPENSATION_STUCK`, that needs humans |

### Follow-ups they will ask

**Q: Why not two-phase commit?**
A: Because 2PC needs every participant available simultaneously and holds locks for the
duration of the whole protocol, so its availability is the product of the participants'
availabilities and a coordinator crash in the prepared phase can block resources
indefinitely. Across HTTP services with third parties involved — Stripe does not
participate in my 2PC — it is not an option. A saga trades atomicity for availability and
makes the intermediate states explicit instead of pretending they don't exist.

**Q: What if the compensation fails?**
A: Retry it with backoff and the same idempotency key, because compensations are
idempotent by construction and the failure is usually transient. If it stays stuck, the
saga goes to an explicit `COMPENSATION_STUCK` state, the row is parked, and it pages a
human — there is real customer money uncommitted, so the one thing I will not do is log
and continue. I also track the count and age of stuck sagas as an SLO.

**Q: How do you stop a user seeing an order that might get compensated away?**
A: Semantic locks and honest UI states. The order sits in `PENDING_PAYMENT` and the API
reports it as pending, not confirmed; the seat is `HELD` with a `held_until` rather than
sold. Reads therefore never present a provisional state as settled — which is exactly the
isolation guarantee I gave up, reimplemented at the application level where it is visible.

**Q: Orchestration or choreography for a 6-step order flow?**
A: Orchestration. At six steps with compensations, choreography means the workflow exists
only as an emergent property of six subscriptions, and nobody can answer "why is order 123
stuck?" without correlating six services' logs. An orchestrator gives me one state machine
I can query, test, and resume after a crash. I'd use choreography for two or three loosely
coupled reactions where no compensation is needed.

### Red flags — do not say this

- ❌ "The saga rolls back if a step fails." → ✅ "It runs compensating transactions —
  which are new business facts, not erasures, because the intermediate state was already
  visible to other readers."
- ❌ "We use sagas so we get eventual consistency for free." → ✅ "Sagas give me
  availability at the cost of isolation, which I then have to reimplement with semantic
  locks."
- ❌ "Choreography is more scalable so we use it everywhere." → ✅ "Choreography decouples
  deployment but distributes the workflow; past three steps or with compensations
  involved, I want one orchestrator I can query."

---

## 9.15 Chaos engineering and game days

> **One-liner:** Chaos engineering is running controlled failure experiments in production
> to verify that the reliability mechanisms you built actually fire — because a fallback
> that has never executed is a hypothesis, not a control.

### Say this in the interview

> Chaos engineering is the only way I know to find out whether the timeouts, breakers and
> fallbacks I wrote actually work, because all of that code only runs during incidents and
> is therefore the least-tested code in the service. The method is a hypothesis, not
> vandalism: I state what I expect — "if pgvector latency goes to 5 seconds, the RAG
> endpoint degrades to keyword search within 30 seconds and p99 stays under 500 ms" —
> then inject the fault with a controlled blast radius, on a small percentage of traffic,
> with an abort condition and a kill switch. If the hypothesis holds, that's a real
> reliability control; if it doesn't, I've found a bug in a code path that would otherwise
> have surfaced at 3 a.m. Game days are the human version: schedule two hours, pick a
> scenario nobody has prepped for, and test whether the runbook, the dashboards and the
> on-call handoff actually work. Shopify does this deliberately with high-volume flash-sale
> load tests against production. The starting point doesn't need a platform — killing one
> pod, adding 500 ms of latency to one dependency with a proxy, and revoking one IAM
> permission will find more real bugs in an afternoon than a week of reading the code.

### Mental model

The five questions to ask about your own design — and the ones an interviewer may ask
you to answer about a system you just drew:

1. **Kill one instance.** Does in-flight work complete, retry, or vanish? Does the LB
   notice within one health-check interval?
2. **Add 5 s of latency to each dependency, one at a time.** Which timeout fires? Which
   breaker opens? Does anything unrelated break — meaning you have a shared pool that
   needs [bulkheading](#98-bulkheads)?
3. **Make a dependency return 100% errors.** Does the fallback produce something useful,
   and does the error rate stay bounded rather than amplifying via retries?
4. **Fill the queue / kill the consumer.** Does backpressure engage, or does memory grow?
   Does the DLQ receive messages with usable metadata?
5. **Revoke a credential / expire a certificate.** How is it detected, and how fast can it
   be rotated? (This is the one nobody tests and everybody eventually experiences.)

Tools worth naming: `toxiproxy` for latency and connection faults (this is what Shopify
uses to unit-test its Semian fallbacks), Kubernetes `chaos-mesh` or `litmus` for pod and
network faults, and Envoy's fault-injection filter for HTTP-level delays and aborts.

Ground rules that make it engineering rather than gambling: a stated hypothesis, a
bounded blast radius (start at 1% of traffic or one pod), a defined abort condition, a
one-command kill switch, business-hours execution with the owning team present, and a
written outcome — most importantly for the experiments that *fail*.

### Enterprise production example

**Shopify** describes both halves publicly. On the human side they *"regularly test the
resiliency and protection mechanisms of our systems by simulating high-volume flash sales
on specifically set dates"* — a scheduled game day at production scale. On the automated
side, they use **toxiproxy** to design and unit-test the fallbacks around Semian-protected
resources, which is the important detail: their degraded paths, like disabling storefront
sign-in when Redis is down, are covered by tests that inject the failure rather than
assumed to work.

### Follow-ups they will ask

**Q: How do you run chaos experiments without risking real users?**
A: Blast radius and an abort condition. Start in staging to shake out the obvious, then
production at 1% of traffic behind a flag, during business hours, with the owning team
watching, and an automatic abort when the customer-facing SLI degrades past a threshold.
The point is not to cause an incident; it is to verify a control under conditions I chose
rather than conditions chosen for me at 3 a.m. And I'd start with the read path, not the
payment path.

**Q: We have no chaos platform. What's the highest-value experiment you can run this
week?**
A: Put a proxy in front of the single dependency with the largest blast radius and add
500 ms, then 5 s, to a small slice of traffic. That one experiment tests the timeout, the
breaker threshold, the fallback, the bulkhead, and whether the health check lies — which
is most of this module — and it needs no platform, just `toxiproxy` and an afternoon.

---

## Module 09 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Why is an unbounded timeout more dangerous than a dependency that is completely down?
   Use Little's Law with real numbers.
2. Derive a timeout for a Postgres query with p50 = 20 ms, p99 = 120 ms, p99.9 = 900 ms.
   Justify the number, then say what changes if it is an LLM call instead.
3. Explain why jitter is mandatory, then state AWS's actual finding about full versus
   decorrelated jitter — including which one does *more* work.
4. A single user action produces 64 requests against an overloaded database. Explain how,
   and give the two Google SRE controls that fix it and the load multiplier each achieves.
5. Two requests with the same `Idempotency-Key` arrive 1 ms apart. Walk through every
   branch, including what the loser receives and why it is not a cached response.
6. Why is a hash of the request body the wrong choice for an idempotency key, and what is
   it the right choice for?
7. Kafka advertises exactly-once semantics. Explain precisely what it covers and why your
   payment consumer still needs an idempotency key.
8. Give the exact circuit-breaker transition rules, including the minimum-volume gate, and
   explain why you trip on slow-call rate as well as error rate.
9. Distinguish backpressure from load shedding. For a producer at 1,000/s and a consumer
   at 800/s with 2 KB items and 3 GiB of usable memory, compute the time to OOM.
10. Draw the nine-step anatomy of a cascading failure, and explain why the system stays
    down after the trigger is removed.
11. Why can't you release a Redis lock with `DEL`? Write the Lua script and explain what a
    return value of 0 tells you.
12. Summarise Kleppmann's critique of Redlock and antirez's response, then state when each
    of them is right.
13. What is a fencing token, why does Redlock lack one, and why does fencing have to be
    enforced at the resource rather than at the client?
14. Your saga's compensation fails permanently. What state does the saga enter, what
    happens next, and why is "log and continue" unacceptable?
15. Give a five-rung degradation ladder for a RAG endpoint with a trigger and a p99 for
    each rung.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Stripe idempotency key retention (v1 API) | At least **24 hours**; **30 days** on v2 |
| Stripe idempotency key max length | **255 characters**, UUIDv4 recommended |
| Stripe response to a concurrent duplicate key | **409 Conflict** (retryable) |
| Stripe caches the first response | Status **and** body, **including 500s** |
| AWS jitter result, 100 contending clients | Full jitter cut call count by **more than half** |
| AWS full jitter formula | `sleep = rand(0, min(cap, base * 2^n))` |
| AWS decorrelated jitter formula | `sleep = min(cap, rand(base, prev * 3))` |
| AWS finding on decorrelated jitter | **More** calls than full jitter, slightly **less** time |
| Google SRE per-request retry cap | **3 attempts** |
| Google SRE per-client retry budget | Retries **< 10%** of requests |
| Load growth: cap only vs cap + budget | just under **3×** vs about **1.1×** |
| Google SRE server-wide retry ceiling example | **60 retries per minute** per process |
| Google SRE retry amplification example | 3 layers × 4 attempts = **4³ = 64** attempts |
| Adaptive throttling formula | `max(0, (requests − K·accepts) / (requests + 1))`, K ≈ 2 |
| Hystrix `requestVolumeThreshold` | **20** requests |
| Hystrix `errorThresholdPercentage` | **50%** |
| Hystrix `sleepWindowInMilliseconds` | **5,000 ms** |
| Hystrix rolling stats window | **10,000 ms**, 10 × 1 s buckets |
| Shopify Semian example: Redis instances / timeout | **42** instances, **0.25 s** service timeout |
| Shopify: Redis p99 → half-open probe timeout | p99 **< 50 ms** → `half_open_resource_timeout` **50 ms**, `error_timeout` **30 s** |
| Metastable failures: most common sustaining effect | **Retry policy, > 50%** of studied public incidents |
| Typical timeout heuristic | **2–3 × dependency p99** |
| Bounded queue sizing heuristic | `consumer_throughput × ~10 s` |
| Bulkhead sizing heuristic | `slots ≥ target_throughput × p99_latency` |
| Pub/Sub `maxDeliveryAttempts` before DLQ | **5** (range 5–100); Pub/Sub DLQ retention default **7 days** |
| Kubernetes leader election defaults | lease **15 s**, renew deadline **10 s**, retry **2 s** |
| Envoy `healthy_panic_threshold` | **50%** — below this, ignore health status |

---

**Next:** [Module 10 — Security: AuthN/AuthZ, JWT, Encryption & Rate Limiting](./10_Security.md)

