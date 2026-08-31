# Module 11 — Observability, SLOs & Disaster Recovery

> **What this module makes you able to do:** instrument a service so you can debug a
> production incident you have never seen before, define an SLO with an error budget
> that actually changes release decisions, and pick a disaster-recovery strategy by
> naming its RTO, RPO and cost instead of saying "we'd have a backup".
>
> **Interview weight:** ★★★★☆
>
> **Prerequisites:** Module 09 — Reliability Patterns, Module 06 — Scaling, Replication
> & Sharding

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 11.1 | Monitoring vs observability | ★★★☆☆ |
| 11.2 | Logs | ★★★★☆ |
| 11.3 | Metrics | ★★★★★ |
| 11.4 | Four Golden Signals, RED and USE | ★★★★★ |
| 11.5 | Distributed tracing | ★★★★☆ |
| 11.6 | Health checks & graceful shutdown | ★★★★☆ |
| 11.7 | SLI, SLO, SLA & error budgets | ★★★★★ |
| 11.8 | Alerting | ★★★★☆ |
| 11.9 | Incident response & postmortems | ★★★☆☆ |
| 11.10 | Disaster recovery strategies | ★★★★★ |
| 11.11 | RPO & RTO | ★★★★★ |
| 11.12 | Multi-region architecture | ★★★★☆ |
| 11.13 | Deployment safety as reliability | ★★★★☆ |

---

## 11.1 Monitoring vs observability

> **One-liner:** Monitoring answers questions you thought of in advance; observability
> lets you ask a question you have never asked before without shipping new code.

### Say this in the interview

> Monitoring and observability are not the same thing, and the difference is what you
> can do at 3 a.m. Monitoring is the dashboards and alerts I built for the failure
> modes I predicted — CPU is high, the error rate crossed 1%, the queue is backing up.
> Those are known unknowns: I knew the question, I just didn't know the answer yet.
> Observability is the property that my telemetry is rich enough to answer a question I
> never anticipated — "why is p99 bad only for tenant 4417, only on the PDF ingest
> path, only since the 14:05 deploy?" — without adding new instrumentation and waiting
> for a release. The practical dividing line is cardinality. Metrics are cheap because
> they are pre-aggregated over a small set of labels, so they can tell me *that*
> something is wrong but almost never *which* thing. The moment I need to slice by
> user ID, tenant ID, or request ID, I need high-cardinality data — traces and wide
> structured events — and that is where the cost lives. So in practice I run low-
> cardinality metrics for alerting and SLOs, and high-cardinality traces and events for
> debugging, and I decide up front which dimensions are worth paying for.

### Mental model

The three pillars framing (logs, metrics, traces) is how vendors sell it. The more
useful framing is: what is the *cardinality* of the question you need to answer?

```
QUESTION                                DATA THAT ANSWERS IT      COST
--------------------------------------  ------------------------  --------
"Is the service up?"                    metric, 1 series          ~free
"Which endpoint is slow?"               metric, ~50 series        cheap
"Which tenant is slow?"                 metric, ~10k series       expensive
"Which request was slow and why?"       trace / wide event        very high
"What did this one user see at 14:05?"  log with request_id       very high

    low cardinality  ──────────────────────────────►  high cardinality
    cheap, aggregatable, alertable        expensive, must be sampled
```

Cardinality is the number of distinct label-value combinations. A Prometheus metric
with labels `{endpoint, method, status}` at 20 × 5 × 8 is 800 time series — fine. Add
`user_id` with a million values and you have created a million series, each costing
memory in the scrape target and in Prometheus itself. That is not a "tuning issue";
it is the reason metrics and traces are different tools.

### Enterprise production example

**Google's** SRE practice codified the monitoring half of this in the Four Golden
Signals (2016 SRE book): latency, traffic, errors, saturation — four low-cardinality
signals sufficient to page on. Everything Google says about debugging *beyond* those
four signals involves per-request data. That split — a tiny alerting surface plus a
deep, sampled debugging surface — is the pattern to copy, and it is the opposite of
what most teams do, which is alert on fifty metrics and keep no request-level data.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Metrics for alerting, SLOs, capacity | Metrics to find *which* customer broke | Cardinality limits your questions |
| Traces/wide events for debugging | Tracing 100% of traffic at high RPS | Storage and ingest bill; sampling bias |
| Logs for the exact sequence of events | Logs as a metrics substitute | Log-derived metrics are slow and costly |

### Follow-ups they will ask

**Q: Your Prometheus fell over after a deploy. What did the deploy probably do?**
A: Someone added a high-cardinality label — usually `user_id`, `order_id`, a raw URL
path with IDs in it, or an unbounded error message string. Each unique combination
creates a new time series, memory grows linearly, and Prometheus OOMs. The fix is to
template the path (`/orders/{id}` not `/orders/8813`), move the identifier into a trace
attribute or log field, and add a series-count alert on `count({__name__=~".+"})` per
job so the next one is caught before it pages.

**Q: If you could only keep one of logs, metrics or traces, which would you keep?**
A: Metrics, because SLOs and paging depend on them and they are the only one cheap
enough to keep unsampled at 100% forever. But I'd immediately argue the question is
wrong for a distributed system: without traces you cannot answer "which of the eleven
services in this request path spent the time", and that is the majority of real
incidents in a microservice architecture.

### Red flags — do not say this

- ❌ "We have observability, we use Datadog." → ✅ "We have observability for the
  dimensions we chose to instrument — tenant, endpoint, model version. Anything else
  needs a code change, so we picked those deliberately."
- ❌ "The three pillars are logs, metrics and traces." (stopping there) → ✅ "Logs,
  metrics and traces differ mainly in cardinality and cost, which is what decides
  which one answers a given question."

---

## 11.2 Logs

> **One-liner:** Structured JSON with a request ID on every line, correct levels,
> nothing sensitive, and sampling on the happy path — otherwise logs are just an
> expensive way to not find things.

### Say this in the interview

> I log structured JSON, one object per line, never free-text string concatenation,
> because the whole value of a log line is being able to filter on
> `tenant_id = X AND status >= 500` without a regex. Every line carries a
> `request_id` that I generate at the edge if the client didn't send one, store in a
> context variable so I never have to thread it through function signatures, and
> forward on every outbound call so the same ID appears in the logs of every downstream
> service. On levels: ERROR means a human needs to look; anything I handled and
> recovered from is WARN or INFO, otherwise ERROR becomes noise and people stop
> reading it. I never log request bodies, Authorization headers, tokens, or anything
> that could be PII — I log the shape, not the content, and I keep a deny-list in the
> log formatter itself so it's not a code-review responsibility. Volume matters: at
> 10,000 requests per second, one 1 KB log line per request is 864 GB a day, which at
> typical managed-platform ingest pricing is real money, so I log 100% of errors and
> sample successes at something like 1%, keeping the trace ID so I can still find the
> full story for anything interesting.

### Mental model

```
   client                edge / gateway            service A          service B
     │                        │                        │                  │
     │  (no X-Request-ID)     │ generate               │                  │
     ├───────────────────────►│ req_id=7f3a...         │                  │
     │                        ├───────────────────────►│  header:         │
     │                        │  X-Request-ID: 7f3a    │  X-Request-ID    │
     │                        │                        ├─────────────────►│
     │                        │                        │                  │
     └── every log line in all three processes carries req_id=7f3a ───────┘

   Query: request_id:"7f3a..."  →  the full cross-service story of one request
```

Three rules that separate usable logs from log spam:

1. **One event, one line, structured.** `{"ts":..., "level":"error", "msg":"...",
   "request_id":..., "tenant_id":..., "duration_ms":...}`. Never log an object by
   interpolating it into a message string.
2. **Levels mean severity to a human, not verbosity to a developer.** ERROR = someone
   is paged or ticketed. WARN = degraded but handled (a retry succeeded, a cache miss
   storm). INFO = business events worth keeping (payment captured). DEBUG = off in
   production, on per-request via a header or a flag.
3. **The log is not the metric.** Counting errors by grepping logs is 100× more
   expensive than a counter and arrives minutes later. Emit a metric *and* a log.

**What never goes in a log:** passwords, tokens, API keys, `Authorization` headers,
full card numbers (log the last 4 and the BIN if you must), national IDs, email
addresses in a regulated context, LLM prompt contents when the prompt contains user
data, and full request/response bodies. The last one is the common one: someone adds
"log the body for debugging", it ships, and now the log store is a PII store with a
different retention policy and different access controls than your database.

### Enterprise production example

**Scenario (labelled as a scenario, not a claim about a named company):** a mid-size
SaaS running 40 pods at 6,000 rps emits an average of 4 log lines per request at
~700 bytes each. That is 6,000 × 4 × 700 B ≈ 16.8 MB/s ≈ 1.45 TB/day. Managed log
platforms commonly price ingest plus indexed retention in the range of $0.50–$2.50 per
GB, so this is on the order of $25k–$100k a month before anyone has read a single line.
Dropping to 100% of errors plus 1% of successes typically cuts volume by 90–95% while
keeping every line you'd actually open during an incident — because the interesting
requests are the failing and slow ones, and tail-based trace sampling keeps those.

### Code

```python
# logging_setup.py — structured JSON logging + request-ID propagation for FastAPI
import json, logging, time, uuid
from contextvars import ContextVar
from fastapi import FastAPI, Request

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")
_REDACT = {"password", "token", "authorization", "api_key", "secret", "card_number"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": request_id_ctx.get(),
        }
        for key, value in getattr(record, "extra_fields", {}).items():
            payload[key] = "[REDACTED]" if key.lower() in _REDACT else value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"))


app = FastAPI()
log = logging.getLogger("api")


@app.middleware("http")
async def request_context(request: Request, call_next):
    rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
    token = request_id_ctx.set(rid)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("unhandled_error", extra={"extra_fields": {
            "path": request.url.path, "method": request.method}})
        raise
    finally:
        request_id_ctx.reset(token)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    # Sample the happy path; keep every error.
    if response.status_code >= 400 or elapsed_ms > 1000 or hash(rid) % 100 == 0:
        log.info("request", extra={"extra_fields": {
            "path": request.url.path, "method": request.method,
            "status": response.status_code, "duration_ms": elapsed_ms}})
    response.headers["X-Request-ID"] = rid
    return response
```

Propagate it outbound too — otherwise the chain breaks at the first hop:

```python
import httpx

async def call_downstream(path: str) -> httpx.Response:
    headers = {"X-Request-ID": request_id_ctx.get()}
    async with httpx.AsyncClient(timeout=httpx.Timeout(2.0, connect=0.5)) as client:
        return await client.get(f"https://billing.internal{path}", headers=headers)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Reconstructing one request's exact sequence | Computing rates and percentiles | $0.50–$2.50/GB ingested and indexed |
| Post-hoc forensics and audit trails | Alerting (too slow, too expensive) | PII/retention risk in a second data store |
| Debug-level detail behind a per-request flag | Always-on DEBUG in production | Disk, network, and the noise that hides signal |

### Follow-ups they will ask

**Q: How do you keep a request ID available deep in the call stack without passing it everywhere?**
A: In Python, a `ContextVar` — it is asyncio-task-local, so concurrent requests in the
same event loop don't see each other's value, unlike a module global. In Node.js, the
equivalent is `AsyncLocalStorage` from `node:async_hooks`. Both survive `await`
boundaries; thread-locals do not in async code.

**Q: A customer reports an error but has no request ID. How do you find it?**
A: Return the request ID to the client in a response header and in the error body, and
tell support to ask for it. Failing that, I search on the dimensions I *did* index —
`tenant_id`, `user_id`, time window, and status — which is exactly why those need to be
structured fields rather than buried in a message string.

**Q: Should logs go to stdout or to a file?**
A: stdout, as an unbuffered stream, per the 12-factor rule. The process should not know
about log shipping, rotation, or destinations; the platform collects stdout. Writing to
files inside a container means log loss on crash and a disk-full failure mode.

### Red flags — do not say this

- ❌ "We log everything so we can debug anything." → ✅ "We log 100% of errors and
  sample the happy path, because full-fidelity logging at our volume costs more than
  the service it monitors."
- ❌ "We log the request body for debugging." → ✅ "We log field names and sizes, never
  values, and the formatter has a deny-list so it can't leak by accident."

---

## 11.3 Metrics

> **One-liner:** Counters and histograms are additive across instances, which is why
> you can compute a real p99 from them — averaging per-instance percentiles is
> arithmetic that means nothing.

### Say this in the interview

> I use four metric types and pick them deliberately. A counter only goes up — requests
> served, errors, bytes — and I always graph its rate, never its raw value. A gauge is
> a point-in-time level that can go both ways: queue depth, pool connections in use,
> memory. A histogram puts each observation into pre-defined latency buckets and
> exposes cumulative bucket counts, and that is the one that matters for latency,
> because bucket counts are additive: I can sum them across every pod and then
> interpolate a true p99 for the whole service. A summary computes quantiles inside the
> process, and those are mathematically not aggregatable — if pod A reports a p99 of
> 100 ms and pod B reports 200 ms, the average, 150 ms, is not the p99 of anything. The
> real p99 could be 200 ms if pod B took most of the traffic. That is why every
> production latency SLI I've built is a histogram with buckets chosen around the SLO
> threshold, not a summary and definitely not an average. The other thing I watch is
> cardinality: total series is the product of every label's distinct values, so I never
> put user IDs or raw URL paths in a label, and I template paths to `/orders/{id}`.

### Mental model

**The four types**

```
counter     ▁▂▃▄▅▆▇█   monotonically increasing; use rate() / increase()
gauge       ▃▇▂▆▁▅▃▇   goes up and down; use the raw value, min, max, avg
histogram   buckets    counts per bucket + _sum + _count; aggregatable
summary     quantiles  computed in-process; NOT aggregatable across instances
```

**Why you cannot average percentiles** — this is the detail that reads as senior:

```
Pod A: 1,000 requests, p99 = 100 ms
Pod B: 9,000 requests, p99 = 200 ms

"Average of the p99s" = 150 ms.        ← meaningless
True p99 of 10,000 requests: the slowest 100 requests. 90% of traffic is
on Pod B, so almost all of those 100 slowest requests come from Pod B.
The real answer is ≈ 200 ms.
```

Percentiles are order statistics; they are not linear, so no weighted average of them
is correct either. The only correct way to combine them is to combine the underlying
distributions. That is exactly what a histogram does: each bucket is a counter, counters
sum, and `histogram_quantile(0.99, sum by (le) (rate(bucket[5m])))` reconstructs the
quantile from the merged distribution.

**Bucket choice matters more than people expect.** A histogram's accuracy is bounded by
its bucket edges. If your SLO is "p99 < 300 ms" and your buckets are
`[0.1, 0.5, 1, 5]`, you can only say the p99 is somewhere between 100 ms and 500 ms.
Put bucket boundaries around the threshold you care about: `[0.05, 0.1, 0.2, 0.3, 0.5,
1, 2, 5]`. Better still, for an availability SLO, don't interpolate at all — count
requests faster than the threshold and divide, which is exact.

**Cardinality**

```
series = |endpoint| × |method| × |status| × |le buckets| × |instances|
       =    20      ×    4     ×    6     ×     10      ×    30
       = 144,000 series      ← fine

add label tenant_id (5,000 tenants)  →  720,000,000 series  ← Prometheus dies
```

**Pull vs push**

| | Pull (Prometheus scrapes `/metrics`) | Push (OTLP, StatsD, Pushgateway) |
|---|---|---|
| Target discovery | Prometheus needs to find you | You need to know the collector |
| Liveness | Scrape failure *is* a signal (`up == 0`) | Silence is ambiguous |
| Short-lived jobs | Bad — job exits before scrape | Good — the natural fit |
| Serverless / Lambda | Bad | The only option |
| Firewalls / NAT | Needs inbound reachability | Outbound only |

Default to pull for long-running services, push for batch jobs, cron, and serverless.

### Enterprise production example

**Prometheus** itself is the case study for the cardinality constraint: it holds an
in-memory index of every active series, so operators typically plan on the order of a
few KB of RAM per active series and treat a few million active series as the practical
ceiling for a single server before they shard or move to a remote-write backend like
Thanos, Mimir or Google Cloud Managed Service for Prometheus. That number is why "just
add a user_id label" is not a small decision — it is a request to multiply your
monitoring bill by the size of your user base.

### Code

```python
# metrics.py — Prometheus instrumentation for a FastAPI service
from fastapi import FastAPI, Request, Response
from prometheus_client import (
    CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest,
)
import time

# Buckets straddle the 300 ms SLO threshold so the p99 is accurate where it matters.
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "Request latency by route and method",
    labelnames=("route", "method", "status_class"),
    buckets=(0.01, 0.05, 0.1, 0.2, 0.3, 0.5, 1.0, 2.0, 5.0),
)
REQUESTS = Counter(
    "http_requests_total", "Requests", ("route", "method", "status"))
INFLIGHT = Gauge("http_requests_inflight", "In-flight requests", ("route",))

app = FastAPI()


@app.middleware("http")
async def observe(request: Request, call_next):
    # route template, NOT request.url.path — /orders/{id}, never /orders/8813
    route = request.scope.get("route").path if request.scope.get("route") else "unmatched"
    INFLIGHT.labels(route).inc()
    started = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        return response
    finally:
        elapsed = time.perf_counter() - started
        INFLIGHT.labels(route).dec()
        REQUESTS.labels(route, request.method, str(status)).inc()
        REQUEST_LATENCY.labels(route, request.method, f"{status // 100}xx").observe(elapsed)


@app.get("/metrics")
def metrics() -> Response:
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
```

Under Gunicorn/Uvicorn with multiple workers, each worker has its own registry and
Prometheus scrapes only one of them. Set `PROMETHEUS_MULTIPROC_DIR` and use
`prometheus_client.multiprocess.MultiProcessCollector`, or scrape each worker on its
own port. Getting this wrong silently under-reports your traffic by the worker count.

The query that turns those buckets into a real service-wide p99:

```promql
histogram_quantile(
  0.99,
  sum by (le, route) (rate(http_request_duration_seconds_bucket[5m]))
)
```

Note the `sum by (le)` — that is the aggregation across pods that a summary could
never give you.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Histogram for any latency SLI | Summary for anything multi-instance | ~10 extra series per label set |
| Counter + `rate()` for throughput/errors | Gauges for things that only increase | Nothing; this is the cheap one |
| Labels for bounded, low-cardinality sets | Labels for IDs, emails, URLs, messages | Series count multiplies; OOM risk |

### Follow-ups they will ask

**Q: Why is p99 latency the wrong SLI for a service where 90% of traffic is health checks?**
A: Because the health checks dominate the distribution and push the real user requests
past the 99th percentile boundary, so the p99 looks great while users suffer. I'd
exclude infrastructure traffic from the SLI entirely, or split the histogram by a
`traffic_class` label and compute the SLO only over user-facing requests.

**Q: Your p50 is 40 ms and your p99 is 4 seconds. What does that shape tell you?**
A: A 100× spread almost always means two populations, not one slow path — typically
cache hit versus cache miss, or a fast path plus a retry/timeout path. I'd split the
histogram by that dimension rather than trying to optimise "the p99", because the
average of two distributions has no bottleneck to fix.

**Q: What is the difference between `rate()` and `increase()` and when does it bite you?**
A: `rate()` is per-second, `increase()` is the total over the window; `increase()` is
literally `rate() × window`. Both extrapolate and both need a window of at least 4×
the scrape interval, otherwise you get gaps and jitter. The classic bite is using a
1-minute window with a 30-second scrape interval and seeing your graph flicker to zero.

**Q: How do you alert on a counter that stops moving?**
A: `rate()` going to zero is only meaningful if you know traffic should be non-zero, so
I compare against the same time last week (`offset 7d`) rather than a fixed threshold,
or I alert on the *absence* of the series with `absent()`, which catches "the exporter
died" rather than "the traffic stopped".

### Red flags — do not say this

- ❌ "We average the p95 across instances." → ✅ "We sum histogram buckets across
  instances and compute the quantile from the merged distribution — percentiles don't
  average."
- ❌ "We alert when average latency exceeds 500 ms." → ✅ "Averages hide the tail; we
  alert on the fraction of requests slower than the SLO threshold."

---

## 11.4 The Four Golden Signals, RED and USE

> **One-liner:** RED describes your services, USE describes the resources under them,
> and the Four Golden Signals are the umbrella that spans both.

### Say this in the interview

> I use three frameworks and they are not competitors, they are scoped differently.
> The Four Golden Signals, from Google's SRE book, are latency, traffic, errors and
> saturation — the minimum set for any user-facing service, and the set I'd page on.
> RED, from Tom Wilkie, is rate, errors and duration: it is the Golden Signals minus
> saturation, deliberately, because Wilkie wanted one identical dashboard he could
> stamp out for every request-driven microservice. USE, from Brendan Gregg, goes the
> other direction — for every resource, check utilisation, saturation and errors. USE
> is a checklist for CPUs, disks, network links, connection pools and thread pools;
> it says nothing about user experience, and RED says nothing about capacity. So in
> practice: RED per service, USE per resource underneath it, Golden Signals as the
> paging contract. One detail I always add — I measure latency of successful and failed
> requests separately, because a fast 500 makes your latency graph look better during
> an outage, which is precisely backwards.

### Mental model

```
        USERS
          │
          ▼
   ┌─────────────────────────────────────────────┐
   │  SERVICES — the request path                │
   │  RED:  rate · errors · duration             │  ← "are users having
   └─────────────────────────────────────────────┘     a bad time?"
          │
          ▼
   ┌─────────────────────────────────────────────┐
   │  RESOURCES — CPU, disk, pools, queues       │
   │  USE:  utilisation · saturation · errors    │  ← "which resource is
   └─────────────────────────────────────────────┘     the bottleneck?"

   FOUR GOLDEN SIGNALS  =  latency · traffic · errors  (service side)
                        +  saturation                  (resource side)
```

| Framework | Signals | Origin | Unit of analysis | Blind spot |
|---|---|---|---|---|
| Golden Signals | latency, traffic, errors, saturation | Google SRE book, 2016 | A user-facing service | Doesn't tell you how to drill into a resource |
| RED | rate, errors, duration | Tom Wilkie, 2015 | Each request-driven service | No saturation — you find capacity limits by hitting them |
| USE | utilisation, saturation, errors | Brendan Gregg, 2012 | Each resource | Says nothing about user experience |

**Utilisation vs saturation** is the pair people conflate. Utilisation is the fraction
of time the resource was busy (CPU at 70%). Saturation is the work that is queued
because the resource couldn't take it yet (run-queue length, pool wait time, queue
depth). Saturation is the leading indicator: a CPU at 100% utilisation with zero
saturation is a perfectly efficient system; a CPU at 60% with a growing run queue is
about to fall over. That is why "alert on CPU > 80%" is usually the wrong alert (see
[11.8](#118-alerting)).

### The exact dashboard I'd build for a new service

Four rows, top to bottom, in this order — the order matters because it is the order you
read them during an incident.

```
ROW 1  SLO & BUDGET   ┌──────────────┬──────────────┬──────────────────┐
                      │ SLO attain-  │ Error budget │ Burn rate 1h/6h  │
                      │ ment 30d     │ remaining %  │ (see 11.7)       │
                      └──────────────┴──────────────┴──────────────────┘
ROW 2  RED (service)  ┌──────────────┬──────────────┬──────────────────┐
                      │ rate by route│ error % by   │ p50/p95/p99 by   │
                      │ (req/s)      │ status class │ route, 2xx only  │
                      └──────────────┴──────────────┴──────────────────┘
ROW 3  DEPENDENCIES   ┌──────────────┬──────────────┬──────────────────┐
                      │ per-dep call │ per-dep      │ per-dep p99 +    │
                      │ rate         │ error/timeout│ circuit state    │
                      └──────────────┴──────────────┴──────────────────┘
ROW 4  USE (resource) ┌──────────────┬──────────────┬──────────────────┐
                      │ CPU / mem    │ DB pool: in- │ queue depth &    │
                      │ per pod      │ use + wait ms│ consumer lag     │
                      └──────────────┴──────────────┴──────────────────┘
```

Row 1 tells you whether to page. Row 2 tells you whether it's you. Row 3 tells you
whether it's someone you call. Row 4 tells you which resource ran out. If you can't
answer "is it us or a dependency?" in fifteen seconds, the dashboard is wrong.

### Enterprise production example

**Brendan Gregg** (then at Netflix, now Intel) designed USE explicitly as a fast
checklist and claims it "solves about 80% of server issues with 5% of the effort" —
the value is that you enumerate *every* resource and ask the same three questions
instead of starting from whatever metric happens to be on a dashboard. **Tom Wilkie**
built RED at Weaveworks in 2015 for the opposite reason: with hundreds of
microservices, you cannot hand-design a dashboard per service, so you need three
metrics that every service emits identically and one dashboard template that works for
all of them. Both frameworks exist because of scale problems in opposite directions —
too many resources to check, and too many services to dashboard.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| RED for every HTTP/gRPC service | RED as your only capacity signal | Misses saturation until it's an outage |
| USE for pools, disks, CPUs, queues | USE as a user-experience proxy | You can be at 20% CPU and totally down |
| Golden Signals as the page-worthy set | Paging on all three frameworks | Alert fatigue; see 11.8 |

### Follow-ups they will ask

**Q: You have one alert budget. RED or USE?**
A: RED, because it is closest to the user. USE metrics are diagnostic — I want them on
a dashboard and in a runbook, not on a pager. The exception is saturation signals with
no user-visible symptom until they're catastrophic: disk filling, certificate expiry,
and consumer lag on a queue with a retention limit. Those get a ticket-level alert
because by the time they show up in RED it is too late.

**Q: How do you apply RED to something that isn't request-driven, like a Kafka consumer?**
A: Rate becomes messages processed per second, errors become processing failures and
DLQ deposits, duration becomes per-message handling time — and I add consumer lag as
the saturation signal, because for a queue-driven system lag *is* the user-facing
latency. That is the case where RED alone is genuinely insufficient.

**Q: Which of the golden signals is hardest to measure and why?**
A: Saturation, because it's resource-specific and rarely exposed directly. CPU
saturation is run-queue length, not utilisation; memory saturation is swap and page
scan rate, not used bytes; connection-pool saturation is time spent waiting for a
connection, which most ORMs don't emit by default. You usually have to instrument it
yourself, which is why most teams skip it and then get surprised.

### Red flags — do not say this

- ❌ "RED and the golden signals are the same thing." → ✅ "RED is the golden signals
  minus saturation, scoped to request-driven services."
- ❌ "We measure average latency across all responses." → ✅ "We measure latency for
  successful responses separately, because failing fast makes the average look better
  during an outage."

---

## 11.5 Distributed tracing

> **One-liner:** A trace is the causal tree of one request across every service it
> touched, and it answers the one question metrics structurally cannot: where did the
> time actually go?

### Say this in the interview

> A trace is one request; a span is one unit of work inside it, with a start time, a
> duration, a parent, and attributes. The context that stitches them together travels
> in the W3C `traceparent` header — version, a 32-hex-character trace ID, the caller's
> 16-hex span ID, and flags including the sampled bit — and OpenTelemetry propagates it
> automatically on every instrumented client. What tracing gives me that metrics cannot
> is causality within a single request: metrics tell me p99 is 3 seconds, a trace tells
> me 2.4 of those seconds were the third retry to the embedding service because the
> first two timed out at 800 ms. On sampling, head-based means you decide at the first
> span, so it's cheap and stateless but you throw away errors and slow requests at the
> same rate as everything else. Tail-based decides after the trace completes, so you can
> keep 100% of errors and everything over your latency threshold and drop most of the
> healthy traffic — Datadog reports customers dropping around 98% of ingest that way.
> The cost is that it's stateful: every span of a trace must reach the same collector,
> so you need a load-balancing exporter keyed on trace ID and enough memory to buffer
> every in-flight trace for the decision window. That's the trade — tail-based is
> strictly better data for strictly more infrastructure.

### Mental model

```
trace_id = 4bf92f3577b34da6a3ce929d0e0e4736        total 1,240 ms
│
├─ POST /chat                       api-gateway      ├────────────┤ 1240
│  ├─ auth.verify                   auth-svc          ├─┤            18
│  ├─ retrieve                      rag-svc            ├─────────┤  920
│  │   ├─ embed                     embedding-svc       ├───┤       310
│  │   ├─ embed  (retry 1)          embedding-svc          ├───┤    300  ◄─ here
│  │   └─ vector.search             pgvector                  ├─┤   190
│  └─ llm.generate                  openai                     ├──┤  290
```

Metrics would have told you p99 = 1.24 s. Only the trace tells you a retried embedding
call is 610 ms of it, and only the span attributes tell you it retried because of a
`ReadTimeout` at 300 ms.

**Header on the wire:**

```
traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
             ▲  ▲                                ▲                ▲
             │  trace-id (16 bytes, 32 hex)      │                sampled=01
             version (00)                        parent span-id (8 bytes)
```

`tracestate` carries vendor-specific key-value pairs alongside it. All-zero trace IDs
and span IDs are invalid, and version `ff` is reserved.

**Head vs tail sampling:**

```
HEAD-BASED (decide at span 0)
  request ──► [dice roll: keep 1%] ──► all downstream spans honour the bit
  + stateless, zero buffering, predictable cost
  − you keep 1% of errors too; the interesting traces are mostly gone

TAIL-BASED (decide after the trace finishes)
  all spans ──► collector buffers by trace_id for `decision_wait` (e.g. 10s)
            ──► policy: keep if (error) OR (duration > 1s) OR (1% random)
  + you keep 100% of what you'd actually look at
  − stateful: needs load-balancing exporter so one trace lands on one
    collector; memory ≈ in-flight traces × spans × span size
```

### Enterprise production example

**Datadog** documents the standard production topology for OpenTelemetry tail sampling:
a two-tier collector deployment where agent-tier collectors forward spans through the
**load-balancing exporter** (which routes by trace ID) to a gateway tier that buffers,
evaluates policies and exports. They also make the point that matters most: compute
span metrics *before* sampling, otherwise your RED dashboards silently reflect only the
sampled traffic and your error rate becomes a lie. Real deployments report cutting
ingest by roughly 98% with error-plus-latency policies while keeping every trace worth
opening.

### Code

```python
# tracing.py — OpenTelemetry for FastAPI + httpx + psycopg, exporting OTLP
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

resource = Resource.create({
    "service.name": "rag-api",
    "service.version": "2026.3.1",
    "deployment.environment": "prod",
})

provider = TracerProvider(
    resource=resource,
    # Head sampling at the edge; the collector does tail sampling downstream.
    # ParentBased means we honour an upstream service's decision instead of
    # re-rolling the dice and producing broken, half-sampled traces.
    sampler=ParentBased(root=TraceIdRatioBased(1.0)),
)
provider.add_span_processor(
    BatchSpanProcessor(
        OTLPSpanExporter(endpoint="http://otel-collector:4317", insecure=True),
        max_queue_size=8192,
        max_export_batch_size=512,
        schedule_delay_millis=2000,
    )
)
trace.set_tracer_provider(provider)
tracer = trace.get_tracer(__name__)


def instrument(app) -> None:
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/healthz,/readyz,/metrics")
    HTTPXClientInstrumentor().instrument()
    PsycopgInstrumentor().instrument()


async def retrieve(query: str, tenant_id: str) -> list[str]:
    with tracer.start_as_current_span("rag.retrieve") as span:
        # Attributes are the high-cardinality dimensions you cannot afford as
        # metric labels — this is the whole point of traces.
        span.set_attribute("tenant.id", tenant_id)
        span.set_attribute("rag.query_chars", len(query))
        chunks = await _vector_search(query, tenant_id)
        span.set_attribute("rag.chunks_returned", len(chunks))
        if not chunks:
            span.add_event("retrieval.empty")
        return chunks
```

The collector side, where the expensive decision happens:

```yaml
# otel-collector-gateway.yaml
processors:
  tail_sampling:
    decision_wait: 10s          # buffer window; memory scales with this
    num_traces: 100000          # in-flight traces held in memory
    policies:
      - name: all-errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow-requests
        type: latency
        latency: {threshold_ms: 1000}
      - name: baseline-sample
        type: probabilistic
        probabilistic: {sampling_percentage: 1}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Multi-service request paths | A single-process monolith (profile instead) | ~1–5% CPU for instrumentation |
| Finding *where* latency lives | Computing rates/SLOs (use metrics) | Ingest cost; sampling bias in analysis |
| Tail sampling for error/slow retention | Low-traffic services (just keep 100%) | Stateful collectors, memory, LB exporter |

### Follow-ups they will ask

**Q: You added tracing and your p99 got worse. What happened?**
A: Almost always the exporter is synchronous or the batch queue is full and applying
backpressure into the request path. `BatchSpanProcessor` should be async with a bounded
queue that *drops* spans when full rather than blocking. Losing spans is acceptable;
adding latency to user requests to record that latency is not.

**Q: How do you connect a trace to a log line?**
A: Inject `trace_id` and `span_id` into every log record from the active span context —
OpenTelemetry's logging instrumentation does this automatically. Then one click goes
from a slow span to the exact log lines emitted inside it, which is the single highest-
value integration in the whole stack.

**Q: A request crosses a Pub/Sub topic. Does the trace survive?**
A: Only if you propagate context through the message. HTTP propagation is automatic,
messaging is not — you inject `traceparent` into the message attributes on publish and
extract it on consume, then start the consumer span as a *link* rather than a child if
the consumer is batching, because one batch may span many traces.

**Q: What's the sampling bias problem with tail-based sampling?**
A: If you keep 100% of errors and 1% of successes, any ratio you compute from traces is
wrong — your traced error rate looks like 50% when reality is 0.5%. That's why span
metrics must be computed before the sampling processor, and why you never compute an
SLI from sampled traces.

### Red flags — do not say this

- ❌ "We trace 100% of requests." (at high RPS, without qualification) → ✅ "We sample
  head-based at 100% into the collector and tail-sample there, keeping all errors and
  everything over 1 second, which lands around 2% of spans in storage."
- ❌ "Tracing replaces logging." → ✅ "Traces tell me where the time went; logs tell me
  what the code decided. I need both, joined on trace ID."

---

## 11.6 Health checks & graceful shutdown

> **One-liner:** Liveness asks "is this process wedged?", readiness asks "should I get
> traffic right now?", and putting a database check in liveness is how you turn a
> database blip into a full outage.

### Say this in the interview

> I run three probes and they answer three different questions. Liveness answers "is
> this process irrecoverably stuck?" — if it fails, Kubernetes kills and restarts the
> container, so it must only check things a restart can fix, meaning it checks nothing
> but the process itself. Readiness answers "can I serve traffic right now?" — if it
> fails, the pod is pulled out of the Service endpoints but not restarted, so it's the
> right place for "still warming caches" or "connection pool is exhausted". Startup
> handles slow boots, like loading a model, so the liveness probe doesn't kill the pod
> before it has finished starting. The dangerous mistake is a deep liveness check that
> pings Postgres: if the database has a five-second blip, every pod fails liveness
> simultaneously, Kubernetes restarts all of them, they all reconnect at once, and you
> have converted a five-second degradation into a ten-minute cold-start outage with a
> connection stampede. So liveness is shallow and self-only; readiness can be deeper
> but must degrade rather than all-fail-at-once. And on shutdown, the sequence matters:
> the endpoint removal and the SIGTERM happen in parallel and are not synchronised, so
> I put a five-to-fifteen-second sleep in the preStop hook to let the endpoint removal
> propagate to kube-proxy before the app starts refusing connections.

### Mental model

```
                  fails  →  what happens                use it for
  ┌────────────┐
  │ startup    │  kill & restart (after failureThreshold)  slow boot: model
  │            │  liveness/readiness suspended until pass  load, migrations
  ├────────────┤
  │ liveness   │  kill & RESTART the container             deadlock, event-loop
  │            │  ← restart must be able to fix it         wedge, OOM spiral
  ├────────────┤
  │ readiness  │  REMOVE from Service endpoints            warming up, pool
  │            │  ← no restart; comes back when it passes  exhausted, draining
  └────────────┘
```

**Why deep liveness checks cause cascading failure:**

```
   t=0    Postgres primary failover, 8 s of refused connections
   t=1    every pod's liveness probe (which pings the DB) fails
   t=11   failureThreshold=3 × periodSeconds=5 reached → kubelet kills ALL pods
   t=12   Postgres recovers — but there are now zero pods
   t=12   40 pods start simultaneously, each opening a 20-connection pool
   t=40   800 new connections hit a database with max_connections=200
   t=40   Postgres refuses connections → probes fail again → restart loop
   ─────────────────────────────────────────────────────────────────────
   An 8-second database blip became a 10-minute outage. The probe caused it.
```

The rule: **a liveness probe should only fail for conditions a restart will fix.** A
dependency being down is not one of those conditions.

Readiness has a subtler version of the same trap. If readiness checks the database and
the database goes down, *every* pod goes unready at once and the Service has zero
endpoints — clients get connection failures instead of a `503` with a useful body, and
you lose the ability to serve cached or degraded responses. My default: readiness
checks only what this pod needs to serve *any* request (pool initialised, caches warm,
not draining), and dependency health is surfaced on a separate `/health/deps` endpoint
that dashboards and humans read, not the orchestrator.

**Graceful shutdown — the sequence that actually prevents 502s:**

```
  kubectl delete / rolling update
        │
        ├──► PATH A (control plane)   ├──► PATH B (kubelet, same instant)
        │    Pod → Terminating         │    run preStop hook
        │    EndpointSlice: ready=false│    then send SIGTERM to PID 1
        │    kube-proxy updates iptables│   then wait terminationGracePeriod
        │    ingress/LB updates        │    then SIGKILL
        │                              │
        └─── THESE ARE NOT SYNCHRONISED ──┘
             Path B usually wins → app stops accepting while traffic
             is still being routed to it → 502s

  FIX:  preStop: sleep 10   ← holds SIGTERM until Path A has propagated
        then app: stop accepting new conns → finish in-flight →
                  close DB pool → flush telemetry → exit 0
        terminationGracePeriodSeconds ≥ preStop sleep + max request time + margin
```

### Enterprise production example

**Kubernetes** exposes three flags on a terminating pod's EndpointSlice —
`ready: false`, `serving: true`, `terminating: true` — precisely because of this race.
`serving: true` tells a smart load balancer "don't send me *new* requests, but I can
still complete the ones you already gave me", which is what allows graceful connection
draining instead of cold connection resets. The community's standard mitigation, in the
Kubernetes issue tracker since 2018 and recommended in *Kubernetes in Action*, is a
5–15 second `preStop` sleep. It is a workaround for an inherent distributed-systems race
condition, not a bug you can configure away.

### Code

```python
# health.py — liveness / readiness / startup for FastAPI, done correctly
import asyncio, contextlib, signal
from fastapi import FastAPI, Response

app = FastAPI()
state = {"ready": False, "draining": False, "pool": None}


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    state["pool"] = await create_pool(min_size=2, max_size=10)
    await warm_caches()
    state["ready"] = True
    yield
    state["ready"] = False           # readiness fails immediately on shutdown
    await state["pool"].close()

app.router.lifespan_context = lifespan


@app.get("/healthz", status_code=200)          # LIVENESS — shallow, self only
async def liveness() -> dict:
    # If this handler runs at all, the event loop is not wedged. That is the
    # entire question. No database, no Redis, no downstream service.
    return {"status": "alive"}


@app.get("/readyz")                            # READINESS — can I serve traffic?
async def readiness(response: Response) -> dict:
    if state["draining"] or not state["ready"]:
        response.status_code = 503
        return {"status": "draining" if state["draining"] else "starting"}
    # Only check what this pod owns. A pool with zero free connections means
    # THIS pod should stop taking traffic; it does not mean restart it.
    if state["pool"].get_idle_size() == 0 and state["pool"].get_queue_size() > 50:
        response.status_code = 503
        return {"status": "pool_saturated"}
    return {"status": "ready"}


@app.get("/health/deps")     # NOT wired to any probe — for humans and dashboards
async def dependency_health() -> dict:
    checks = await asyncio.gather(
        _ping(state["pool"], "postgres"), _ping_redis(), _ping_vector_db(),
        return_exceptions=True,
    )
    return {"dependencies": {c["name"]: c["ok"] for c in checks if isinstance(c, dict)}}


def _handle_sigterm(*_):
    state["draining"] = True     # readiness starts failing; LB drains us

signal.signal(signal.SIGTERM, _handle_sigterm)
```

```yaml
# deployment.yaml — the probe and shutdown configuration that goes with it
spec:
  terminationGracePeriodSeconds: 45      # ≥ preStop(10) + max request(30) + margin
  containers:
    - name: api
      lifecycle:
        preStop:
          exec:
            command: ["sh", "-c", "sleep 10"]   # let endpoint removal propagate
      startupProbe:                              # 30 × 5s = 150s to boot
        httpGet: {path: /readyz, port: 8000}
        periodSeconds: 5
        failureThreshold: 30
      livenessProbe:
        httpGet: {path: /healthz, port: 8000}
        periodSeconds: 10
        timeoutSeconds: 2
        failureThreshold: 3                      # 30s of wedge before restart
      readinessProbe:
        httpGet: {path: /readyz, port: 8000}
        periodSeconds: 5
        timeoutSeconds: 2
        failureThreshold: 2                      # pull from LB fast
        successThreshold: 1
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Shallow liveness (`/healthz` returns 200) | Liveness that touches a dependency | Slightly slower detection of "hung on DB" |
| Readiness gating on self-owned resources | Readiness that all pods fail together | You must handle degraded mode in code |
| `preStop: sleep 10` + SIGTERM handling | Relying on SIGTERM alone | 10 s longer rollouts per pod |

### Follow-ups they will ask

**Q: Your liveness probe is shallow, so how do you detect a process that's alive but not doing useful work?**
A: With metrics and alerts, not with a probe. Zero throughput, event-loop lag over a
threshold (see [Module 13 — Node.js concurrency](./13_Concurrency_And_Performance.md#132-the-nodejs-concurrency-model)),
or consumer lag growing while the process reports healthy. Then a human or an automated
runbook restarts it. Restarting is a dangerous action; the orchestrator should only do
it for unambiguous local failure.

**Q: What's the right `failureThreshold` for liveness?**
A: High enough that a GC pause, a slow disk, or a brief CPU spike doesn't restart you.
`periodSeconds: 10, timeoutSeconds: 2, failureThreshold: 3` gives ~30 seconds of
tolerance, which is my default. Aggressive liveness settings cause far more outages than
they prevent.

**Q: Why does a rolling update still drop requests even with readiness probes?**
A: Because readiness controls whether the pod is *added* to endpoints, and the removal
path on termination is a separate, unsynchronised code path. Readiness probes do nothing
for you on the way out — the `preStop` sleep does.

**Q: Long-lived connections — WebSockets, gRPC streams — during a rollout?**
A: Endpoint removal doesn't affect established connections, so you need the application
to actively close them. Send a GOAWAY (gRPC/HTTP2) or a close frame with a reconnect
hint (WebSocket) on SIGTERM, and size `terminationGracePeriodSeconds` for the drain, or
clients will get hard resets at SIGKILL.

### Red flags — do not say this

- ❌ "Our health check verifies the database is reachable." (as liveness) → ✅ "Liveness
  is shallow; a database check there converts a dependency blip into a restart storm."
- ❌ "We use the same endpoint for liveness and readiness." → ✅ "They cause different
  actions — restart versus de-register — so they must answer different questions."

---

## 11.7 SLI, SLO, SLA & error budgets

> **One-liner:** The SLI is what you measure, the SLO is the target you commit to
> internally, the SLA is the contract with money attached — and the error budget is the
> difference between the SLO and 100%, which is the amount of unreliability you are
> allowed to *spend*.

### Say this in the interview

> An SLI is a measurement — the proportion of requests that were both successful and
> under 300 milliseconds. An SLO is the target for that measurement over a window —
> 99.9% over 30 rolling days. An SLA is a contract with a customer that includes a
> financial consequence, and it is always looser than the SLO, because I want to be
> paged and fix things well before I owe anyone a refund. The part that changes how a
> team behaves is the error budget: 99.9% over a 30-day month means 0.1% of 43,200
> minutes, which is 43.2 minutes of allowed badness a month. That is a budget, not a
> failure — if we haven't spent it, we are being too conservative and should ship
> faster; if we've burned it in the first week, we freeze feature releases and spend
> the rest of the month on reliability work. For alerting I don't page on "error rate
> above 1%", I page on burn rate: the multiple of the budget-consumption rate that
> would exhaust the whole month. Google's recommendation is multi-window, multi-burn-
> rate — page at 14.4× sustained over both one hour and five minutes, which means 2% of
> the monthly budget is gone; page at 6× over six hours and thirty minutes; and open a
> ticket at 1× over three days. The short window is there so the alert clears quickly
> when the incident ends, instead of firing for another hour.

### Mental model

**Choosing the SLI.** Two shapes, and the choice matters:

```
REQUEST-BASED                          WINDOW-BASED
  good events / valid events             good minutes / total minutes
  "99.9% of requests succeed"            "99.9% of minutes are good minutes"

  + natural for HTTP APIs                + natural for batch, pipelines,
  + one bad request = one bad event        anything without a request count
  − a 1-minute outage at 3 a.m. with     + a low-traffic outage still counts
    10 requests costs almost nothing     − you must define "a good minute"
```

For a request-driven API, use request-based. For a data pipeline or anything where
traffic volume varies wildly, window-based avoids the "outage during low traffic is
free" pathology.

**Setting the SLO.** Set it from what users need, not from what you currently do. If
your service is currently at 99.97%, setting the SLO to 99.97% means you have zero
budget and every deploy is a crisis. If users would not notice 99.5%, setting 99.99%
means you spend engineering years buying reliability nobody values. The honest process:
find the point where users start complaining or churning, set the SLO slightly tighter
than that, and check it's achievable given your dependencies — you cannot promise 99.99%
on top of a cloud database with a 99.95% SLA without multi-region failover.

**The error budget table** — memorise the 99.9% and 99.99% rows:

| SLO | Budget | Per 30-day month | Per week | Per year |
|---|---|---|---|---|
| 99% | 1% | 7 h 12 min | 1 h 41 min | 3 d 15 h |
| 99.5% | 0.5% | 3 h 36 min | 50 min | 1 d 19 h |
| 99.9% ("three nines") | 0.1% | **43.2 min** | 10 min 5 s | 8 h 46 min |
| 99.95% | 0.05% | 21.6 min | 5 min 2 s | 4 h 23 min |
| 99.99% ("four nines") | 0.01% | **4.32 min** | 1 min | 52.6 min |
| 99.999% ("five nines") | 0.001% | 25.9 s | 6 s | 5 min 15 s |

Two things to say about this table in an interview. First, 99.99% is 4.3 minutes a
month — less than one bad deploy, which means you cannot achieve it with a human in the
rollback loop; it requires automated rollback. Second, your SLO cannot exceed the
composition of your dependencies: three serial dependencies at 99.95% each give you
0.9995³ ≈ 99.85% before you write a line of code.

**Burn rate.** Burn rate is "how many times faster than budget-neutral are we spending?"

```
burn rate = (observed error rate) / (1 − SLO)

SLO 99.9%  →  budget error rate = 0.001
observed error rate 1.44%  →  burn rate = 0.0144 / 0.001 = 14.4×

At 14.4× the entire 30-day budget is gone in 720 h / 14.4 = 50 hours ≈ 2 days.
At 6×   → 120 hours ≈ 5 days.
At 1×   → exactly 30 days (budget-neutral).
```

**Google's multi-window, multi-burn-rate configuration for a 99.9% SLO** (SRE Workbook,
Table 5-8):

| Severity | Long window | Short window | Burn rate | Budget consumed when it fires |
|---|---|---|---|---|
| Page | 1 hour | 5 minutes | 14.4× | 2% |
| Page | 6 hours | 30 minutes | 6× | 5% |
| Ticket | 3 days | 6 hours | 1× | 10% |

Both conditions must hold at once. The long window gives the alert meaning — the budget
really is burning at this rate. The short window (roughly 1/12th of the long one) gives
it freshness and a fast reset: without it, a ten-minute incident keeps paging for a full
hour after it's resolved, because the one-hour average is still elevated. The 1× ticket
tier is the one everyone skips, and it's the one that catches slow drift that never
looks like an incident but eats the whole month.

**How the budget changes decisions:**

```
  budget remaining
   100% ┤████████████████████████████  ship freely, take risks, run chaos tests
    50% ┤██████████████                normal: canary + automated rollback
    20% ┤█████                         only low-risk changes; no schema migrations
     0% ┤                              FREEZE features. Reliability work only,
        └──────────────────────────►   until the rolling window recovers.
```

That last row is the whole point. An SLO without a consequence is a dashboard; an SLO
with a release freeze attached is a policy that makes engineers care about reliability
without anyone having to argue about it.

### Enterprise production example

**Google's** SRE Workbook chapter on alerting on SLOs walks through six iterations,
starting from naive threshold alerting and ending at multi-window multi-burn-rate,
explaining exactly what breaks at each step: fixed thresholds have terrible precision,
single long windows have terrible reset time, single short windows fire on every blip.
The published recommendation — 14.4×/1h/5m and 6×/6h/30m as pages, 1×/3d/6h as a
ticket — is calibrated for a 99.9% SLO over 30 days. If you quote those exact numbers
and can explain *why* 14.4 (it's the rate that burns 2% of a monthly budget in an hour:
1h/2% = 50h to exhaust, and 720h/50h = 14.4), you have said something almost no
mid-level candidate says.

### Code

```yaml
# slo-rules.yaml — Prometheus recording + alerting rules for a 99.9% SLO
groups:
  - name: slo:availability:recording
    rules:
      # Define "good" once, reuse everywhere. A request is good if it did not
      # 5xx AND completed under 300 ms. 4xx is the client's fault, not ours.
      - record: job:slo_errors_per_request:ratio_rate5m
        expr: |
          (
            sum(rate(http_requests_total{job="rag-api",status=~"5.."}[5m]))
            +
            sum(rate(http_request_duration_seconds_count{job="rag-api"}[5m]))
            -
            sum(rate(http_request_duration_seconds_bucket{job="rag-api",le="0.3"}[5m]))
          )
          / sum(rate(http_requests_total{job="rag-api"}[5m]))
      # ... identical records for rate30m, rate1h, rate6h, rate3d

  - name: slo:availability:alerting
    rules:
      - alert: ErrorBudgetBurnFast          # 2% of the month in 1 hour
        expr: |
          job:slo_errors_per_request:ratio_rate1h > (14.4 * 0.001)
          and
          job:slo_errors_per_request:ratio_rate5m > (14.4 * 0.001)
        for: 2m
        labels: {severity: page}
        annotations:
          summary: "rag-api burning error budget at 14.4x — exhausted in ~2 days"
          runbook: "https://runbooks.internal/rag-api/fast-burn"

      - alert: ErrorBudgetBurnSlow          # 5% of the month in 6 hours
        expr: |
          job:slo_errors_per_request:ratio_rate6h > (6 * 0.001)
          and
          job:slo_errors_per_request:ratio_rate30m > (6 * 0.001)
        for: 15m
        labels: {severity: page}

      - alert: ErrorBudgetDrift             # 10% of the month over 3 days
        expr: |
          job:slo_errors_per_request:ratio_rate3d > (1 * 0.001)
          and
          job:slo_errors_per_request:ratio_rate6h > (1 * 0.001)
        labels: {severity: ticket}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Request-based SLI for an HTTP API | Uniform-traffic assumption is false | Low-traffic outages under-counted |
| 99.9% for an internal API | 99.99% without automated rollback | 4.3 min/month leaves no human in the loop |
| Burn-rate alerting | Static error-rate thresholds | More rules to maintain; needs recording rules |
| Error budget with a freeze policy | An SLO with no consequence | Real product-velocity cost when you overspend |

### Follow-ups they will ask

**Q: Your dependency has a 99.95% SLA. Can you offer your customers 99.99%?**
A: Not without removing the dependency from the critical path. Either I make it
non-blocking (serve a degraded response when it fails), add a second provider with
failover, or cache aggressively enough that its outage doesn't reach users. Otherwise my
availability is bounded by theirs, and if I have three such dependencies in series it's
bounded by the product, which for three at 99.95% is about 99.85%.

**Q: You've burned 100% of the error budget on day 12. What actually happens?**
A: Feature releases stop; only reliability fixes and rollbacks ship. Then a review of
what consumed it — if a single incident ate the month, the action item is a specific fix;
if it was steady drift, the SLO may be wrong or the system genuinely needs investment.
And I'd check whether the SLO is achievable at all, because a permanently exhausted
budget usually means the target was set aspirationally rather than from evidence.

**Q: Why is the short window in a multi-window alert roughly 1/12th of the long one?**
A: It's a balance between reset time and noise. Too short and it flaps on individual
blips; too long and the alert keeps firing after the incident resolves. Google's
guidance is a short window about 1/12th the duration of the long window, which is where
5m/1h and 30m/6h come from.

**Q: What SLI would you pick for an LLM-backed API where "success" is fuzzy?**
A: Two SLIs, because latency and correctness are different failure modes. Availability
as the proportion of requests that returned a complete non-error response with
time-to-first-token under 2 seconds, and a separate quality SLI measured on a sampled
evaluation set — grounded-answer rate or citation-accuracy rate — evaluated offline.
I would not put model quality in the paging SLO, because you cannot page on something
that takes an hour to evaluate.

**Q: Should the SLO window be rolling or calendar-aligned?**
A: Rolling 30 days for alerting, because a calendar month gives you a free budget reset
on the 1st and creates an incentive to sit out the last week of a bad month. Calendar
alignment is fine for reporting to the business.

### Red flags — do not say this

- ❌ "We aim for 100% uptime." → ✅ "We target 99.9%, which is 43 minutes a month of
  error budget that we deliberately spend on shipping faster."
- ❌ "SLA and SLO are basically the same." → ✅ "The SLA is the contractual promise with
  a penalty; the SLO is the tighter internal target that gives us room to react first."
- ❌ "We set the SLO to our current p99." → ✅ "We set it from where users start
  noticing, then checked it was achievable given our dependencies' SLAs."

---

## 11.8 Alerting

> **One-liner:** Page on symptoms users feel, ticket on causes that will hurt later,
> dashboard everything else — and if an alert has no runbook and no action, delete it.

### Say this in the interview

> My rule is: alert on symptoms, not causes. Users don't experience high CPU; they
> experience slow or failed requests. So the paging alerts are the SLO burn-rate alerts
> plus a small number of "this will definitely become user-visible" signals — the disk
> that will be full in four hours, the certificate that expires in seven days, the
> consumer lag that exceeds the retention window. Everything else is a ticket or a
> dashboard. CPU alerts are almost always wrong in both directions: a batch job pinning
> CPU at 100% is working correctly, and a service at 40% CPU can be completely down
> because it's blocked on a lock or a downstream timeout. If CPU is high and nothing is
> user-visible, there's nothing to page about. Every page must have three properties:
> it is urgent, it is actionable, and it has a runbook link with the first three
> commands to run. If an alert fires and the responder's action is "acknowledge and go
> back to sleep", that alert is training people to ignore the pager, and the next real
> page gets the same treatment.

### Mental model

```
 Does a human need to act RIGHT NOW to prevent or stop user pain?
     │
     ├── yes ──► PAGE.  Must be: urgent + actionable + runbook'd.
     │           Budget: ≤ 2 pages per on-call shift, or it's broken.
     │
     ├── no, but it degrades within days ──► TICKET.
     │           Disk 70% full, cert expires in 21 days, 1× budget burn,
     │           a retry rate that doubled.
     │
     └── no, it's context for an investigation ──► DASHBOARD ONLY.
                 CPU, memory, GC, cache hit rate, per-endpoint breakdowns.
```

**Why CPU alerts are usually wrong:**

| Situation | CPU | User impact | Should it page? |
|---|---|---|---|
| Batch encoder running | 100% | none | No — it's working |
| Autoscaler doing its job | 85% | none | No |
| Blocked on a downstream timeout | 15% | total outage | **Yes** — but CPU says nothing |
| Lock contention / event-loop wedge | 20% | p99 at 30 s | **Yes** — CPU says nothing |
| Genuine capacity exhaustion | 95% | latency climbing | The *latency* alert catches this |

In every row where a page is warranted, a symptom-based alert catches it and CPU either
doesn't fire or fires for the wrong reason. That's the argument.

**Alert fatigue is a measurable thing.** Track: pages per shift, percentage of pages
that were actioned versus acknowledged-and-ignored, and percentage of pages that fired
outside business hours. If more than about a third of pages result in no action, the
alerting is broken and you should delete rules aggressively — the cost of a missed
incident is bounded, the cost of a team that has stopped trusting the pager is not.

**Runbook** — the minimum viable version, linked from the alert annotation:

```
1. WHAT IT MEANS  — one sentence, plain language.
2. USER IMPACT    — who is affected and how badly.
3. FIRST CHECKS   — 3 concrete commands / dashboard links, in order.
4. MITIGATIONS    — roll back, scale up, disable feature flag X, shed load.
5. ESCALATION     — who to wake if the above fails, and after how long.
```

**On-call basics that read as experienced:** a rotation needs at least six people to be
sustainable (one week in six), a documented primary and secondary, an explicit escalation
timeout (15 minutes unacknowledged → secondary), handover notes at the end of each shift,
and time-in-lieu or compensation. Follow-the-sun beats night shifts when you have the
geography for it.

### Enterprise production example

**Google's** SRE book states the principle directly: page on symptoms, use causes for
diagnosis, and hold every page to the bar of being urgent, actionable and requiring
human judgement. Their published alerting evolution (see [11.7](#117-sli-slo-sla--error-budgets))
exists because threshold alerting on causes produced too many false positives at their
scale to be operable — the multi-window burn-rate scheme is essentially a precision
engineering exercise on the alert itself.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Symptom-based paging on SLO burn | Cause-based paging on every metric | Slower detection of some silent failures |
| Ticket tier for slow-moving problems | Paging on everything "important" | Needs someone to actually work the queue |
| Deleting low-value alerts | Keeping alerts "just in case" | Small risk of a missed novel failure |

### Follow-ups they will ask

**Q: A silent failure — the service returns 200 with empty results. No alert fires. How do you catch it?**
A: A business-level SLI, not a technical one. Alert on "successful searches returning
zero results" as a ratio against its own weekly baseline, or run synthetic probes that
assert on content, not status code. Every system has a class of failure where the
technical layer is healthy and the semantic layer is broken; the only defence is
instrumenting the business outcome.

**Q: How do you stop one incident from generating 40 pages?**
A: Alert grouping and inhibition in Alertmanager — group by cluster and service,
and inhibit dependent alerts when a parent alert is firing (if the database-down alert
is active, suppress the twelve service-error alerts it caused). Plus a sane `for:`
duration so transient blips never reach the pager.

**Q: What's your policy on alerts that fire during a deploy?**
A: They should still fire — that's the point of canary analysis. What I don't want is
alerts that fire *because* of the deploy mechanics, like a pod restarting. That's fixed
by alerting on the aggregate SLI rather than per-pod state, and by having the deploy
system correlate the alert with the rollout so the responder sees "started 90 seconds
after deploy abc123" in the notification.

### Red flags — do not say this

- ❌ "We alert when CPU goes above 80%." → ✅ "We page on user-visible symptoms; CPU is
  a dashboard panel we look at once we know something is wrong."
- ❌ "We have 200 alert rules." → ✅ "We have about a dozen paging rules and a larger
  set of ticket-level ones; anything nobody acts on gets deleted."

---

## 11.9 Incident response & postmortems

> **One-liner:** Severity sets the response, MTTD/MTTA/MTTR tell you which part of the
> response to fix, and a blameless postmortem exists to change the system, not to find
> the person.

### Say this in the interview

> When something breaks, the first job is mitigation, not diagnosis — roll back, flip
> the feature flag, fail over — and only then do we find out why. We run explicit
> severity levels: Sev1 is a full outage or data loss and pages everyone immediately
> with a dedicated incident channel and a named incident commander; Sev2 is major
> degradation for a subset of users, paged but handled by the on-call; Sev3 is a
> ticket. The incident commander's job is coordination and communication, not typing —
> separating that from the person actually debugging is the single biggest improvement
> most teams can make. Afterwards we measure four numbers: time to detect, time to
> acknowledge, time to mitigate, and time to resolve, because they point at different
> fixes. A long detect time is a monitoring gap; a long acknowledge time is an on-call
> or paging problem; a long mitigate time usually means we had no rollback or no
> runbook. The postmortem is blameless in a specific, non-fluffy sense: if the answer
> to "why did this happen" is "someone made a mistake", we haven't finished, because
> the real question is why the system let a routine mistake cause an outage. Every
> action item gets an owner, a date and a ticket, or the postmortem was theatre.

### Mental model

```
      incident begins
            │
   MTTD ────┤  detect     ← monitoring gap if long
            │
   MTTA ────┤  acknowledge ← paging/on-call gap if long
            │
   MTTM ────┤  mitigate    ← no rollback / no runbook if long
            │              (users are OK again HERE)
   MTTR ────┤  resolve     ← root cause actually fixed
            ▼
```

Optimise MTTM (mitigate) before MTTR (resolve). Users care about when the pain stops,
not when you found the bug. That is the argument for always having a rollback path and
a kill switch, even for changes you are confident in.

| Sev | Definition | Response |
|---|---|---|
| Sev1 | Full outage, data loss, or security breach | Page immediately, incident commander, war room, exec comms, status page |
| Sev2 | Major degradation or a whole feature down for many users | Page on-call, incident channel, status page if customer-visible |
| Sev3 | Minor degradation, workaround exists, single tenant | Ticket, business hours |

**Blameless postmortem structure:**

```
1. SUMMARY          2–3 sentences. What broke, for whom, for how long.
2. IMPACT           Users affected, requests failed, revenue, budget spent.
3. TIMELINE         UTC timestamps: change → first symptom → detection →
                    ack → mitigation → resolution. Include what you tried
                    that did NOT work — that's where the learning is.
4. ROOT CAUSE       Contributing factors, plural. Not "human error".
5. WHAT WENT WELL   Genuinely — this is how you keep good practices.
6. WHERE WE GOT LUCKY   The near-misses. Often more valuable than the cause.
7. ACTION ITEMS     Each with owner + due date + ticket link, split into
                    prevent / detect faster / mitigate faster.
```

The "where we got lucky" section is the one that separates a real postmortem from a
template exercise — "the failover worked because the secondary happened to have been
restarted last week; it would have had a stale config otherwise" is the finding that
prevents the *next* outage.

### Enterprise production example

**Google's** SRE practice is where "blameless postmortem" comes from, and the core
insight is economic rather than emotional: if reporting a mistake gets you punished,
people stop reporting, you lose the data, and you keep having the same outage. The
corollary they emphasise is that a postmortem's output is a set of tracked action items
— an untracked action item has the same effect as no postmortem at all. The trigger
criteria matter too: postmortems should be written for near-misses and for incidents
resolved quickly, not only for the disasters, because those are the cheap lessons.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Named incident commander for Sev1/2 | IC role for every minor blip | Process overhead; a person not debugging |
| Postmortem for every Sev1/2 + near-misses | Postmortem for everything | Engineering time; document fatigue |
| Mitigate-first culture | Debugging in production during an outage | You sometimes lose diagnostic state |

### Follow-ups they will ask

**Q: Mitigating destroys the evidence you need to diagnose. What do you do?**
A: Capture before you mitigate, but time-box it to a minute or two: grab a heap dump or
a thread dump, snapshot the dashboards, save the current pod logs, and note the exact
timestamp. Then roll back. A rolled-back deploy leaves the artefact and the diff intact,
so you rarely actually lose much — the exception is in-memory state, which is why the
snapshot step is in the runbook.

**Q: The root cause was "a developer deployed on Friday without testing". Is that a root cause?**
A: No, it's the trigger. The root causes are that the pipeline had no automated test
gate for that class of change, that the canary didn't run long enough to catch it, and
that rollback was manual. The fix list should be three system changes, none of which are
"tell people to be careful".

### Red flags — do not say this

- ❌ "We do a root-cause analysis to identify who caused it." → ✅ "We identify the
  contributing factors in the system that let a routine mistake become an outage."
- ❌ "We fixed it, so no postmortem was needed." → ✅ "Fast recovery is exactly when you
  write one — those are the cheap lessons."

---

## 11.10 Disaster recovery strategies

> **One-liner:** Four strategies, ordered by cost: backup & restore, pilot light, warm
> standby, multi-site active-active — and you pick by the RTO/RPO the business will pay
> for, not by which one sounds impressive.

### Say this in the interview

> AWS's disaster recovery whitepaper defines four strategies and I think in those terms
> regardless of cloud. Backup and restore is RPO in hours and RTO in 24 hours or less:
> nothing is running in the recovery region, and on a disaster you deploy infrastructure
> from code and restore from a copied snapshot. Pilot light is RPO in minutes, RTO in
> tens of minutes: the data layer is always on and replicating, the compute tier exists
> but is switched off. Warm standby is RPO in seconds, RTO in minutes: a scaled-down but
> fully functional copy is always serving-capable and you scale it up on failover.
> Multi-site active-active is RPO near zero and RTO potentially zero, because you're
> already serving from both regions — but you now have to solve conflicting writes to
> the same record in two regions, which is the genuinely hard part and the reason most
> companies stop at warm standby. Cost roughly doubles at each step. Separately, the
> rule I actually enforce on backups is that an untested backup is not a backup — I want
> a scheduled restore drill that measures the real restore time, because the first time
> you discover your 2 TB restore takes six hours should not be during an incident.

### Mental model

```
COST  ────────────────────────────────────────────────────────────────►
      lowest                                                    highest

┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│ BACKUP &     │  │ PILOT LIGHT  │  │ WARM STANDBY │  │ MULTI-SITE   │
│ RESTORE      │  │              │  │              │  │ ACTIVE-ACTIVE│
├──────────────┤  ├──────────────┤  ├──────────────┤  ├──────────────┤
│ nothing runs │  │ data layer   │  │ scaled-down  │  │ full stack   │
│ in DR region │  │ on & syncing;│  │ but FULLY    │  │ serving live │
│              │  │ compute off  │  │ functional   │  │ in both      │
├──────────────┤  ├──────────────┤  ├──────────────┤  ├──────────────┤
│ RPO: hours   │  │ RPO: minutes │  │ RPO: seconds │  │ RPO: ~zero   │
│ RTO: <24 h   │  │ RTO: tens of │  │ RTO: minutes │  │ RTO: ~zero   │
│              │  │      minutes │  │              │  │              │
└──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘
   dev/test,        tier-2 apps,      business-         mission-
   archives         internal tools    critical          critical + you
                                                        can solve write
                                                        conflicts
```

Those RTO/RPO figures are AWS's own, from the Well-Architected reliability pillar. Note
one nuance worth quoting: AWS says continuous/automated backups enabling point-in-time
recovery can bring the backup-and-restore RPO down to as low as **5 minutes**, which is
much better than the "hours" headline — the hours figure is about restore *time*, and
about snapshot-only setups. And warm standby scaled all the way up is what they call
**hot standby**, which is the active/passive sibling of active-active.

**Backup strategy:**

```
FULL        every Sunday        largest, simplest restore (1 file)
INCREMENTAL every day, delta    small, but restore = full + every incremental
                                since → longest restore chain
DIFFERENTIAL every day vs full  medium size, restore = full + 1 differential

PITR (point-in-time recovery)   base backup + continuous WAL/binlog archive
                                → restore to ANY second, not just snapshot
                                times. This is what saves you from a bad
                                migration at 14:32:07, not from a dead disk.
```

**The 3-2-1 rule:** 3 copies of the data, on 2 different media/storage classes, with
1 copy off-site (for cloud: a different region, and ideally a different account with
separate credentials so a compromised or malicious admin can't delete both). Modern
addition: at least one copy immutable — object-lock / WORM — because ransomware and
`DROP TABLE` both delete backups that your production credentials can reach.

**The rule that matters most:** an untested backup is not a backup. Schedule a restore
drill (quarterly minimum), restore to a real environment, run a data-integrity check,
and record the measured wall-clock restore time. That measured number *is* your RTO for
this strategy — not the one in the design doc.

### Enterprise production example

**AWS's** prescriptive guidance table for full-stack database DR is the cleanest public
source of these numbers: backup and restore is RTO "hours" / RPO "less than 24 hours"
at low cost; pilot light is "tens of minutes" for both at medium cost; warm standby is
"minutes"/"minutes" at high cost; multi-site active/active is "near zero"/"zero or near
zero" at higher cost, and they explicitly note it "doesn't require a failover task as
part of your DR plan" because there is no break in traffic flow. They also make the
scoping argument that most teams miss: if your disaster definition is "we lost one
availability zone", a well-architected multi-AZ deployment already handles it and you
only need backup and restore. Cross-region DR is for regional loss and for regulatory
requirements — you should not pay for it by default.

### Code

```sql
-- PostgreSQL: what PITR actually requires (the config people forget)
-- postgresql.conf
--   wal_level = replica
--   archive_mode = on
--   archive_command = 'gsutil cp %p gs://pg-wal-archive/%f'   -- GCS; S3 equivalent
--   archive_timeout = 60      -- force a WAL segment at least every 60s
--                             -- ← THIS is what bounds your RPO to 60 seconds

-- Base backup (weekly), then WAL streams continuously:
--   pg_basebackup -D /backup/base -Ft -z -X stream -c fast

-- Recovery to a specific moment (e.g. just before a bad migration):
--   restore the base backup, then in postgresql.conf:
--     restore_command = 'gsutil cp gs://pg-wal-archive/%f %p'
--     recovery_target_time = '2026-03-14 14:32:00+00'
--     recovery_target_action = 'promote'
```

```bash
# restore-drill.sh — run quarterly in CI; failing this fails the on-call review
set -euo pipefail
START=$(date +%s)
gcloud sql instances create dr-drill-$(date +%Y%m%d) --tier=db-custom-4-16384
gcloud sql backups restore "$LATEST_BACKUP_ID" --restore-instance=dr-drill-$(date +%Y%m%d)
psql "$DRILL_DSN" -c "SELECT count(*) FROM orders;" | tee /tmp/drill.out
# Integrity gate: row count must be within 0.1% of production at snapshot time.
python3 verify_integrity.py --expected "$EXPECTED_ROWS" --actual /tmp/drill.out
echo "measured_rto_seconds=$(( $(date +%s) - START ))"   # ← publish as a metric
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Backup & restore: dev, archives, RTO ≥ hours | Revenue-critical systems | Cheapest; hours of downtime |
| Pilot light: tier-2, RTO tens of minutes | You need sub-minute recovery | Data-layer duplication + cross-region replication |
| Warm standby: business-critical | Small teams without failover practice | ~1.3–2× infra; must keep both regions deployed |
| Active-active: mission-critical, global | You can't solve write conflicts | ~2×+ infra, cross-region egress, real complexity |

### Follow-ups they will ask

**Q: Your database is 2 TB. What's your realistic RTO with backup-and-restore?**
A: Dominated by restore throughput, not by the backup. At a realistic 200 MB/s restore
rate that's about three hours for the data, plus index rebuild, plus WAL replay to the
target time, plus infrastructure provisioning — call it 4–6 hours end to end, and I'd
say that number only after I'd measured it in a drill. If the business needs better, the
answer is a replica, not a faster restore.

**Q: How do you protect backups from ransomware or a malicious insider?**
A: Immutability and credential separation. Object-lock / retention-lock on the bucket so
objects cannot be deleted before their retention expires, a separate account or project
for backups that production credentials cannot write to, and MFA-delete. If the same IAM
principal that runs the app can delete the backups, you have one copy, not three.

**Q: Why do backups pass validation but restores still fail?**
A: Because "the backup job exited 0" validates the job, not the data. Common real
failures: the schema restored but an extension (`pgvector`, `postgis`) isn't installed
on the target, the WAL archive has a gap so PITR stops early, or the backup captured
the database but not the object-storage blobs it references, so rows point at files
that don't exist. A drill that runs a real query catches all three.

**Q: What's the difference between high availability and disaster recovery?**
A: HA is within a region — multi-AZ, automatic, handles instance and AZ failure, costs
you a little extra and no operational drama. DR is cross-region, usually involves a
deliberate human decision, and handles regional loss. AWS makes this point explicitly:
if your disaster definition is losing one data centre, a multi-AZ HA design already
covers it and you don't need cross-region DR at all.

### Red flags — do not say this

- ❌ "We take nightly backups, so we're covered." → ✅ "We take nightly base backups plus
  continuous WAL archiving for a 60-second RPO, and we restore-drill quarterly — our
  measured RTO is 4 hours."
- ❌ "We'd just spin up in another region." → ✅ "That's pilot light, and it's tens of
  minutes assuming the Terraform is current and the data has been replicating."

---

## 11.11 RPO & RTO

> **One-liner:** RPO is how much data you may lose, RTO is how long you may be down —
> and RPO=0 is not a target you choose, it is a decision to make every write wait for a
> remote acknowledgement.

### Say this in the interview

> RPO — recovery point objective — is measured backwards from the moment of failure: how
> much recent data am I allowed to lose? RTO — recovery time objective — is measured
> forwards: how long may the service be unavailable? They're independent, and I derive
> both from business impact rather than from what the infrastructure happens to support.
> For payments, RPO is effectively zero because a lost captured payment is a lost
> reconciliation and a real customer dispute; for a recommendations cache, RPO could be
> 24 hours because we can rebuild it. The part people miss is that RPO drives the
> architecture directly, and it costs latency. An RPO of hours is satisfied by nightly
> snapshots. An RPO of minutes needs continuous WAL archiving. An RPO of seconds needs
> asynchronous streaming replication. But RPO of exactly zero means no committed
> transaction may ever be lost, which forces synchronous replication — the primary
> cannot acknowledge a commit until the replica has it durably. If that replica is in
> another region, you have just added the round-trip time to every single write. Between
> two US regions that's roughly 60 to 70 milliseconds, so a workload doing three writes
> in a transaction now pays 200 extra milliseconds. That's the trade I'd put in front of
> the business: zero data loss, or fast writes. Not both across regions.

### Mental model

```
                        ◄──── RPO ────►│◄──────── RTO ────────►
                                       │
  ──●────────●────────●────────●───────╳───────────────────●──────►
    │        │        │        │    DISASTER               │   time
  backup   write    write    write   14:07              service
  13:00    13:20    13:45    14:05                      restored
                                                         16:30
                             └──┬──┘
                          these writes are
                          LOST unless your
                          replication was
                          faster than your
                          backup cadence

  RPO = data-loss window  = 14:07 − 13:00 = 67 minutes  (snapshot only)
                          = 14:07 − 14:06 = 60 seconds  (WAL archived hourly→60s)
  RTO = downtime window   = 16:30 − 14:07 = 143 minutes
```

**Deriving them from business impact** — the conversation to have, with numbers:

```
Q: What does one hour of downtime cost?           →  drives RTO
   e.g. 40,000 orders/day × $30 AOV / 24 h ≈ $50k/hour of lost GMV
Q: What does losing the last N minutes of writes cost?  →  drives RPO
   e.g. losing 5 min of payment captures = ~140 payments to reconcile
        manually at ~15 min each = 35 person-hours + customer trust

Then: is the DR strategy that meets those targets cheaper than the loss?
   Warm standby at +$8k/month vs $50k/hour of exposure → obviously yes.
   Active-active at +$60k/month for a tool with a 4-hour tolerance → no.
```

**How RPO forces the architecture — the explicit chain:**

| RPO target | Forced mechanism | What it costs |
|---|---|---|
| 24 hours | Nightly snapshot | Nothing extra |
| 1 hour | Snapshot + hourly WAL/log shipping | Storage; small |
| 1 minute | Continuous WAL archiving (`archive_timeout=60`) | Storage + archive bandwidth |
| ~seconds | Asynchronous streaming replication | A standby instance; replica lag = your real RPO |
| **0** | **Synchronous replication (quorum commit)** | **Every write waits for the remote fsync + RTT** |

```
ASYNC (RPO ≈ replica lag, typically 100 ms – seconds)
  client ──write──► primary ──ack──► client        (fast: local fsync only)
                       └───────async──────► replica

SYNC  (RPO = 0)
  client ──write──► primary ──────────────► replica
                       ◄───── durable ack ──┘
                       └──ack──► client
                    write latency = local fsync + RTT + remote fsync
                    same-AZ  : +0.5–1 ms      → fine
                    cross-AZ : +1–2 ms        → usually fine
                    cross-region (us-east↔us-west): +60–70 ms → rarely fine
```

This is the single most useful thing to say about RPO in an interview: **RPO=0 across
regions and low write latency are mutually exclusive.** The usual resolution is
synchronous within a region (multi-AZ, RPO=0 for AZ failure) plus asynchronous across
regions (RPO of seconds for regional failure) — which is exactly what managed offerings
like Cloud SQL HA and RDS Multi-AZ give you.

### Enterprise production example

**AWS's** Well-Architected reliability pillar spells out the RPO/RTO pairs per strategy
(see [11.10](#1110-disaster-recovery-strategies)) and is explicit that multi-region
active-active "requires you to synchronize data across Regions" and that write conflicts
"must be avoided or handled, which can be complex" — that sentence is AWS conceding the
hard part. **Google Cloud SQL** and **RDS Multi-AZ** both implement the synchronous-
within-region pattern: the standby is in a different AZ, commits are synchronous, and a
failover is typically tens of seconds — RPO 0, RTO ~60 s, for the AZ-failure case only.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| RPO=0 synchronous within a region | RPO=0 synchronous across regions | +60–70 ms on every write |
| Async cross-region replication | Claiming it gives you RPO=0 | RPO = actual replica lag, which spikes under load |
| Deriving targets from $ of impact | Picking "99.99% and RPO 0" by default | Buying reliability nobody asked for |

### Follow-ups they will ask

**Q: You promised RPO of 5 seconds with async replication. How do you know you're meeting it?**
A: Measure and alert on replication lag directly — `pg_last_wal_replay_lsn` versus the
primary's write LSN, expressed in seconds, not bytes. Lag is not constant: it spikes
during bulk writes, index builds, and vacuum. Your RPO is your *worst* lag, not your
median, so the SLI is the 99th percentile of replication lag and the alert threshold is
your stated RPO.

**Q: RTO is 15 minutes. What in your architecture is incompatible with that?**
A: Anything requiring a human decision, a DNS TTL longer than a couple of minutes,
provisioning that isn't in code, and a restore that hasn't been timed. Fifteen minutes
means the failover has to be mostly automated: health-check-driven traffic steering,
pre-provisioned capacity in the target, and a runbook that is one command. If DNS TTL is
300 s and clients cache aggressively, that alone can eat the budget.

**Q: Can RTO be shorter than RPO?**
A: Yes, and it's common — you can be back up in 2 minutes (RTO) while having lost the
last 30 seconds of writes (RPO). They measure different things. The awkward case is the
reverse-looking one where the business says RPO=0 but tolerates a 4-hour RTO; that's
perfectly coherent and means "never lose an order, but we can be down for the morning".

### Red flags — do not say this

- ❌ "We want RPO and RTO of zero." → ✅ "RPO zero means synchronous replication, which
  puts the replica round trip inside every commit — within a region that's about a
  millisecond and worth it, across regions it's 60+ ms and usually isn't."
- ❌ "RPO is how long recovery takes." → ✅ "RPO is the data-loss window before the
  failure; RTO is the downtime window after it."

---

## 11.12 Multi-region architecture

> **One-liner:** Multi-region is easy for stateless compute and hard for state — the
> whole design is a question about where writes go and what happens when both regions
> accept them.

### Say this in the interview

> Going multi-region, the compute tier is the easy part: it's stateless, I deploy the
> same containers in both regions and put a global load balancer in front. The design
> work is entirely about data. In active-passive, one region owns all writes and the
> other has an async read replica; failover means promoting the replica and repointing
> traffic, so my RPO is the replication lag and my RTO is the promotion plus DNS or
> anycast convergence — realistically minutes. In active-active, both regions take
> writes, and now I have to answer what happens when the same row is written in both
> during a partition. The three honest answers are: partition writes by key so a given
> tenant or user only ever writes in one region — which is what I'd actually do; or use
> a database designed for it, like Spanner with TrueTime or a CRDT-based store, and pay
> for it; or accept last-write-wins and design the data model so conflicts don't matter.
> For routing I'd use a global anycast load balancer rather than GeoDNS, because DNS
> failover is bounded by TTL and by resolvers that ignore it, whereas anycast withdraws
> a route in seconds. And I'd say the cost out loud: you roughly double compute, you pay
> around two cents a gigabyte for cross-region replication traffic, and you need to
> actually run failover drills or the second region is expensive decoration.

### Mental model

```
ACTIVE-PASSIVE (the default; RPO = lag, RTO = minutes)

   users ──► global LB ──┬──100%──► REGION A (primary)
                         │              ├─ app tier   (serving)
                         │              └─ Postgres primary
                         │                     │ async streaming
                         └───0%───► REGION B   ▼
                                        ├─ app tier   (warm, scaled down)
                                        └─ Postgres replica (read-only)

   failover: promote B's replica → flip LB → B is primary
   the hard part: preventing split-brain if A comes back thinking it's primary


ACTIVE-ACTIVE (RPO ≈ 0, RTO ≈ 0; conflicts are now your problem)

   EU users ──► global LB ──► REGION EU ◄──── bi-directional ────► REGION US
   US users ──► global LB ──► REGION US       replication         (both write)

   Same row written in both during a partition → conflict.
   Resolutions, in order of how much I'd recommend them:
     1. PARTITION BY KEY   tenant/user is "homed" to one region; the other
                           region proxies its writes there. No conflicts by
                           construction. ← this is the practical answer
     2. GLOBAL DATABASE    Spanner / CockroachDB: consensus per write, so
                           writes cost a cross-region quorum round trip
     3. LWW / CRDT         accept it, design the model so it doesn't matter
                           (counters, sets, presence — not balances)
```

**Traffic routing options:**

| Mechanism | Failover speed | Granularity | Gotcha |
|---|---|---|---|
| GeoDNS (Route 53, Cloud DNS) | TTL-bound: 60 s config, minutes in practice | Per-resolver | Clients and resolvers ignore short TTLs |
| Anycast global LB (Cloud LB, Global Accelerator) | Seconds | Per-connection | Costs more; single vendor control plane |
| Client-side (SDK with region list) | Immediate | Per-request | You must ship a client update to change it |

The practical answer for a GCP stack is a global external Application Load Balancer with
a single anycast IP and backend services in both regions — failover is health-check
driven and doesn't depend on client DNS behaviour at all.

**The failover runbook** (this is what "operational maturity" means concretely):

```
0. DECIDE     Named person declares failover. Criteria pre-agreed, e.g.
              region unreachable > 5 min OR error rate > 50% for 3 min.
1. FENCE      Stop writes to the old primary. Demote or hard-stop it.
              ← skipping this is how you get split-brain and divergent data
2. VERIFY     Check replica lag == 0 (or record the exact loss window).
3. PROMOTE    Promote the standby. Record the new primary in config/DNS.
4. REPOINT    Flip the LB / update the connection string. Verify writes land.
5. SCALE      Scale the DR region's app tier to production capacity.
6. VALIDATE   Synthetic transaction end-to-end. Check the SLI recovers.
7. COMMUNICATE  Status page, stakeholders, and the exact data-loss window.
8. FAIL BACK  Later, deliberately, off-peak, with the same rigour.
```

**Regional evacuation** is the practised version of this: deliberately draining all
traffic from a region while it's healthy, to prove you can. If you have never done it,
your RTO is a guess.

**Cost.** Rough shape for doubling regions: compute roughly 2× (or ~1.3× for warm
standby scaled down), storage 2×, cross-region replication traffic at roughly $0.02/GB
on AWS and $0.01/GiB on GCP, plus the human cost of every deploy, migration and config
change now being a two-region operation. See
[Module 13 — Cost optimization](./13_Concurrency_And_Performance.md#1313-cost-optimization-as-an-engineering-discipline).

Cross-link: the data-replication mechanics — sync vs async, quorum, replica lag — are in
[Module 06 — Scaling, Replication & Sharding](./06_Scaling_Replication_And_Sharding.md).

### Enterprise production example

**AWS** describes multi-site active-active as the only strategy with no failover task in
the DR plan, precisely because traffic never stops flowing — and in the same breath
flags that write conflicts across regional replicas "must be avoided or handled, which
can be complex". That is the entire multi-region design problem in one sentence. The
"partition by key" resolution — homing a tenant to a region — is what most large
multi-tenant SaaS platforms converge on, because it turns a distributed-consensus
problem into a routing problem, and routing problems are much easier to reason about
during an incident.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Active-passive: regulatory or RTO in minutes | You've never run a failover drill | ~1.3–2× infra; a promotion you must practise |
| Active-active: global latency + RTO ≈ 0 | Strong consistency on a shared row | 2×+ infra, egress, conflict resolution complexity |
| Tenant-homed active-active | Users who move between regions | Cross-region proxy hop for the wrong-region case |

### Follow-ups they will ask

**Q: How do you prevent split-brain during failover?**
A: Fencing before promotion. The old primary must be provably stopped — demoted, its
endpoint revoked, or STONITH'd — before the standby is promoted. Automated failover
needs a quorum witness in a third location so a network partition between two regions
doesn't let both sides declare themselves primary. Without a third vote, two regions
cannot safely decide anything.

**Q: Your global LB fails over in 5 seconds but users still see errors for 3 minutes. Why?**
A: Connection reuse and client-side caching. Existing keep-alive connections, cached DNS
in the JVM or in a mobile SDK, and long-lived WebSockets all keep pointing at the dead
region. Fixes: bound connection lifetimes, set sane DNS TTLs *and* don't rely on them,
and have clients treat consecutive failures as a signal to re-resolve.

**Q: What breaks first in a multi-region deploy that worked fine in one region?**
A: Anything that assumed a single source of truth: sequences and auto-increment IDs
(switch to UUIDv7 or region-prefixed ranges), distributed locks in a single-region Redis,
cron jobs that now run twice, and "read your own write" — a user writes in EU, gets
routed to US on the next request, and sees stale data. That last one is the most common
user-visible bug and is why sticky routing by user is worth the complexity.

**Q: How do you test multi-region without breaking production?**
A: Scheduled regional evacuation during a low-traffic window, starting at 1% of traffic
shifted and ramping, with an announced maintenance window the first few times. Then game
days where you fail over deliberately and time it. The output is a measured RTO number,
which is the only kind worth putting in a design doc.

### Red flags — do not say this

- ❌ "We're multi-region so we're highly available." → ✅ "We're active-passive across
  two regions with an async replica, so our RPO is our replication lag and our RTO is
  the promotion plus LB convergence — about four minutes when we last drilled it."
- ❌ "Active-active just means deploying to two regions." → ✅ "Active-active means both
  regions accept writes, so the design question is how conflicts on the same row are
  prevented or resolved."

---

## 11.13 Deployment safety as reliability

> **One-liner:** Most outages are caused by a change, so the highest-leverage reliability
> investment is not redundancy — it is making every change small, observable, and
> reversible in under a minute.

### Say this in the interview

> The majority of production incidents are triggered by a change we made, so I treat
> deployment safety as a reliability control, not as a CI/CD convenience. Three
> mechanisms do the work. First, feature flags decouple deploy from release: the code
> ships dark, and turning it on is a config change I can reverse in seconds without a
> rebuild — that turns a ten-minute rollback into a five-second one. Second, canary:
> route 1% of traffic to the new version, compare its error rate and latency against
> the baseline version over a fixed bake time, and only then progress to 5%, 25%, 100%.
> The comparison has to be against the *concurrently running* old version, not against
> yesterday, otherwise a traffic pattern change looks like a regression. Third,
> automated rollback wired to the SLO burn rate — if the canary's burn rate exceeds the
> page threshold, the pipeline rolls back without waiting for a human, which is the only
> way to hold a 99.99% SLO where the entire monthly budget is 4.3 minutes. The thing I'd
> add is that schema changes don't roll back, so any migration has to be
> expand/contract: add the new column, dual-write, backfill, switch reads, and only drop
> the old column a release later.

### Mental model

```
PROGRESSIVE DELIVERY — each gate can halt or reverse automatically

  build ──► deploy to 0% (dark) ──► flag on for internal users
                                          │
                                          ▼
                      ┌────────► canary 1%   bake 10 min ──┐
                      │              │                     │
        automated     │         compare vs baseline:       │
        rollback  ◄───┤         error rate, p99, burn rate │
        on any gate   │              │ pass                │
        failure       └────────► 5% ─┴─► 25% ─► 50% ─► 100%┘
```

| Strategy | Traffic during rollout | Rollback speed | Cost | Handles bad schema? |
|---|---|---|---|---|
| Rolling | Mixed old/new, gradual | Minutes (roll forward the old image) | Baseline | No |
| Blue-green | 100% switch at once | Seconds (flip back) | 2× capacity during cutover | No |
| Canary | 1% → 100%, measured | Seconds–minutes | ~1.1× | No |
| Shadow / dark traffic | 0% real — mirrored copies | N/A (no user impact) | 2× compute for the shadowed path | Read-only only |
| Feature flag | 100% deployed, 0% enabled | **Seconds**, config-only | Flag infra + tech debt | No |

Nothing in that table rolls back a database migration, which is why expand/contract is
mandatory — see
[Module 05 — schema migrations](./05_Databases_And_Data_Modeling.md#expandcontract).

**Shadow traffic** deserves a mention because it's the underrated one: mirror real
production requests to the new version, discard its responses, and compare. You get
production traffic shapes against untested code with zero user risk. The constraint is
that it must be side-effect free — mirroring writes will double-charge someone.

### Enterprise production example

**Scenario (labelled as a scenario):** a team with a 99.9% SLO — 43 minutes of monthly
budget — deploys 20 times a week. A bad deploy caught by a human takes, realistically,
5 minutes to notice plus 5 to decide plus 5 to roll back: 15 minutes, or 35% of the
month's entire budget, per incident. Two of those and the month is nearly gone. Wiring
rollback to the canary's burn-rate signal takes the same event to roughly 90 seconds,
which is 3% of the budget. The arithmetic, not the ideology, is why automated rollback
is non-negotiable above about three nines.

### Code

```yaml
# Argo Rollouts canary with an SLO-derived automatic abort
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata: {name: rag-api}
spec:
  strategy:
    canary:
      canaryService: rag-api-canary
      stableService: rag-api-stable
      analysis:
        templates: [{templateName: slo-burn-guard}]
        startingStep: 1              # begin analysis once we're at 1%
        args:
          - {name: canary-svc, value: rag-api-canary}
      steps:
        - setWeight: 1
        - pause: {duration: 10m}     # bake: enough requests for significance
        - setWeight: 5
        - pause: {duration: 10m}
        - setWeight: 25
        - pause: {duration: 15m}
        - setWeight: 100
---
apiVersion: argoproj.io/v1alpha1
kind: AnalysisTemplate
metadata: {name: slo-burn-guard}
spec:
  args: [{name: canary-svc}]
  metrics:
    - name: error-ratio
      interval: 1m
      failureLimit: 0                # ONE bad reading aborts and rolls back
      provider:
        prometheus:
          address: http://prometheus.monitoring:9090
          query: |
            sum(rate(http_requests_total{service="{{args.canary-svc}}",status=~"5.."}[2m]))
            / sum(rate(http_requests_total{service="{{args.canary-svc}}"}[2m]))
      successCondition: result[0] < 0.0144    # 14.4x burn on a 99.9% SLO
    - name: p99-regression
      interval: 1m
      failureLimit: 1
      provider:
        prometheus:
          address: http://prometheus.monitoring:9090
          query: |
            histogram_quantile(0.99, sum by (le) (
              rate(http_request_duration_seconds_bucket{service="{{args.canary-svc}}"}[2m])))
            / histogram_quantile(0.99, sum by (le) (
              rate(http_request_duration_seconds_bucket{service="rag-api-stable"}[2m])))
      successCondition: result[0] < 1.3       # canary p99 within 30% of stable
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Canary for any user-facing change | Very low traffic (no statistical power) | 10–40 min of rollout time per deploy |
| Feature flags for risky behaviour | Flags that live forever | Flag debt; every flag is a branch to test |
| Automated rollback on burn rate | Noisy SLIs that flap | Occasional false rollback; needs a good SLI |
| Blue-green for a fast full switch | Stateful services with long connections | Double capacity during the cutover |

### Follow-ups they will ask

**Q: Your canary is 1% of traffic and your error rate is 0.1%. How long until you can tell?**
A: Long enough to see enough failures to be significant. At 1,000 rps total, 1% canary is
10 rps, and a 0.1% error rate is one error every 100 seconds — so a 2-minute window sees
about one error and tells you nothing. Either raise the canary percentage, extend the
bake time, or gate on a metric with more signal per request, like latency. Canarying at
low traffic is mostly theatre and you should say so.

**Q: The canary looks fine but the full rollout breaks. What did the canary miss?**
A: Anything load-dependent or state-dependent: connection-pool exhaustion that only
appears at full traffic, a cache that was warm on the stable version, a cron job that
only runs at 02:00, a database migration whose lock contention only matters at full write
volume, or a memory leak that needs an hour to manifest. Canaries catch functional
regressions well and capacity regressions poorly.

**Q: How do you avoid feature flags becoming permanent technical debt?**
A: Every flag gets an owner and an expiry date at creation, flags are inventoried and the
stale ones are surfaced in a weekly report, and removing a flag is part of the definition
of done for the feature. A codebase with 300 live flags has 2³⁰⁰ notional configurations
and no one can reason about any of them.

### Red flags — do not say this

- ❌ "We deploy on Fridays because we have good tests." → ✅ "We deploy any day because
  rollback is automated and takes 90 seconds; the risk is in the recovery time, not the
  calendar."
- ❌ "We roll back the database if the deploy fails." → ✅ "Migrations are
  expand/contract and forward-only, so rolling back the code never requires rolling back
  the schema."

---

## Module 11 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. What is the real dividing line between monitoring and observability, and why does
   cardinality decide it?
2. Why can't you average p99s from three pods? What data structure fixes it, and what is
   the exact PromQL that computes the true p99?
3. Name the Four Golden Signals, RED and USE, say who defined each, and say which one
   you'd page on.
4. Draw the four rows of the dashboard you'd build for a brand-new service, in the order
   you'd read them during an incident.
5. Walk through the full W3C `traceparent` header. What does tail-based sampling buy you
   and what infrastructure does it force?
6. Why is a database check in a liveness probe dangerous? Describe the failure with a
   timeline.
7. Describe the Kubernetes shutdown race and the exact fix, including how you'd size
   `terminationGracePeriodSeconds`.
8. How many minutes per month is a 99.9% error budget? A 99.99% one? Why does the second
   number force automated rollback?
9. State Google's multi-window multi-burn-rate configuration for a 99.9% SLO — all three
   tiers — and explain where 14.4 comes from.
10. Give the RTO, RPO and relative cost of all four AWS DR strategies.
11. Why does RPO=0 across regions cost you 60+ ms on every write? What's the standard
    compromise?
12. In active-active multi-region, what are the three ways to handle a write conflict and
    which would you actually implement?

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| 99.9% SLO error budget, 30-day month | 43.2 minutes |
| 99.95% SLO error budget, 30-day month | 21.6 minutes |
| 99.99% SLO error budget, 30-day month | 4.32 minutes |
| 99.999% SLO error budget, 30-day month | 25.9 seconds |
| 99.9% SLO error budget, per year | 8 h 46 min |
| Burn rate that consumes 2% of a monthly budget in 1 hour | 14.4× |
| Google page tier 1 (99.9% SLO) | 14.4× over 1 h **and** 5 min |
| Google page tier 2 | 6× over 6 h **and** 30 min |
| Google ticket tier | 1× over 3 days **and** 6 h |
| Time to exhaust a monthly budget at 14.4× | ~50 hours (~2 days) |
| Recommended short-window ratio in burn alerts | ~1/12th of the long window |
| AWS backup & restore | RPO hours (PITR → as low as 5 min), RTO < 24 h |
| AWS pilot light | RPO minutes, RTO tens of minutes |
| AWS warm standby | RPO seconds, RTO minutes |
| AWS multi-site active-active | RPO ~zero, RTO potentially zero |
| Cross-region replication cost | ~$0.02/GB (AWS), ~$0.01/GiB (GCP) |
| Cross-region RTT, us-east ↔ us-west | ~60–70 ms — the cost of synchronous RPO=0 |
| Kubernetes `preStop` sleep to beat the endpoint race | 5–15 seconds |
| Recommended liveness tolerance | 10 s period × 3 failures ≈ 30 s |
| W3C `traceparent` trace-id / span-id | 16 bytes (32 hex) / 8 bytes (16 hex) |
| Typical tail-sampling ingest reduction | ~98% (keeping all errors + slow traces) |
| Logging volume at 10k rps × 1 KB/request | 864 GB/day |
| Framework origins | USE: Gregg 2012 · RED: Wilkie 2015 · Golden Signals: Google 2016 |
| Minimum sustainable on-call rotation | 6 people (one week in six) |
| 3-2-1 backup rule | 3 copies, 2 media, 1 off-site (+1 immutable) |

---

**Next:** [Module 12 — Monoliths, Microservices & Service Communication](./12_Architecture_Styles.md)
