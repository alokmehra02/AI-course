# Module 13 — Concurrency, Performance & Cost

> **What this module makes you able to do:** explain why your Node.js API stops at one CPU core
> unless you know what blocks the event loop, why `async def` in FastAPI does not make CPU work
> parallel, find and fix the N+1 that is hiding in your ORM, size a connection pool with Little's
> Law instead of guessing, and talk about cloud cost like an engineer who has seen a bill spike.
>
> **Interview weight:** ★★★★☆
>
> **Prerequisites:** [Module 05 — Databases](./05_Databases_Relational.md) (locking, pools),
> [Module 11 — Observability](./11_Observability_And_SRE.md) (golden signals, profiling),
> [Module 01 — Little's Law](./01_Requirements_And_NFRs.md#16-latency-vs-throughput-littles-law-percentiles)

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 13.1 | [Concurrency vs parallelism](#131-concurrency-vs-parallelism) | ★★★★★ |
| 13.2 | [The Node.js concurrency model](#132-the-nodejs-concurrency-model) | ★★★★★ |
| 13.3 | [Python GIL, asyncio & the FastAPI trap](#133-python-gil-asyncio--the-fastapi-trap) | ★★★★★ |
| 13.4 | [Race conditions](#134-race-conditions) | ★★★★★ |
| 13.5 | [Locking & atomics in application code](#135-locking--atomics-in-application-code) | ★★★★☆ |
| 13.6 | [Optimistic vs pessimistic concurrency](#136-optimistic-vs-pessimistic-concurrency) | ★★★★☆ |
| 13.7 | [Connection pools — sizing & failure modes](#137-connection-pools--sizing--failure-modes) | ★★★★★ |
| 13.8 | [Worker sizing & Little's Law](#138-worker-sizing--littles-law) | ★★★★★ |
| 13.9 | [Finding bottlenecks systematically](#139-finding-bottlenecks-systematically) | ★★★★★ |
| 13.10 | [Performance killers — the N+1 problem](#1310-performance-killers--the-n1-problem) | ★★★★★ |
| 13.11 | [Batching](#1311-batching) | ★★★★☆ |
| 13.12 | [Compression](#1312-compression) | ★★★☆☆ |
| 13.13 | [Cost optimization as an engineering discipline](#1313-cost-optimization-as-an-engineering-discipline) | ★★★★☆ |

---

## 13.1 Concurrency vs parallelism

> **One-liner:** Concurrency is juggling many tasks by switching between them; parallelism is
> doing many tasks at the same time on different cores — and confusing the two is how you ship
> an API that handles 10,000 idle connections but still melts on one hot CPU loop.

### Say this in the interview

> Concurrency and parallelism are related but not the same thing. Concurrency is about
> structure: I have many tasks in flight and I interleave them so that when one is waiting on
> I/O, another can run. Parallelism is about hardware: I have multiple CPU cores and I execute
> instructions on more than one of them at the same instant. A single-core machine can be highly
> concurrent — a Node.js process handling fifty thousand WebSocket connections is concurrent —
> but it is not parallel for CPU work, because only one thread is executing JavaScript at a
> time. Parallelism requires either multiple threads, multiple processes, or handing work to
> something else like a GPU or a worker pool. The design mistake I see constantly is treating
> `async/await` as parallelism. It is not. It is a way to write concurrent I/O without blocking
> a thread, which is enormously valuable, but a tight loop or a JSON parse of a ten-megabyte
> payload still occupies the one thread that runs your event loop until it finishes. So when I
> size a system I ask two separate questions: how many things can be *waiting* at once, which
> is about connections, queues and memory, and how much *CPU* work can happen at once, which is
> about cores, worker processes and whether the language runtime can actually use them.

### Mental model

```
CONCURRENCY (one core, many tasks)          PARALLELISM (many cores, many tasks)

   Task A  ████░░░░████░░░░                     Core 1  ████████████████████
   Task B  ░░░░████░░░░████                     Core 2  ████████████████████
   Task C  ░░░░░░░░████░░░░                     Core 3  ████████████████████
            ^ CPU switches when A blocks on I/O       ^ all three run simultaneously

   Node.js: 1 JS thread, concurrent I/O          Node cluster / Python multiprocessing:
   Python asyncio: 1 thread, concurrent I/O       4 workers = 4 cores doing CPU in parallel
```

**The three axes that actually matter in interviews:**

| Axis | What it measures | What increases it | What does *not* increase it |
|---|---|---|---|
| **Concurrent connections** | How many clients can be connected | Event loop, async I/O, epoll/kqueue | More `async` keywords |
| **Concurrent requests in flight** | How many requests are being processed | Thread pool, worker pool, queue depth | Bigger instance type alone |
| **Parallel CPU throughput** | How much compute per wall-clock second | More cores, SIMD, GPU, native extensions | `async def` on a GIL-bound interpreter |

**I/O-bound vs CPU-bound — the decision that drives everything:**

```
I/O-bound (waiting on network, disk, DB, LLM API)
  -> concurrency wins: one thread/process can multiplex thousands of waits
  -> example: API gateway at 3,000 req/s, 40 ms p99, mostly Postgres + Redis
  -> tool: async Node, asyncio FastAPI, connection pooling

CPU-bound (parsing, compression, embedding, image resize, crypto)
  -> parallelism wins: you need cores actually working simultaneously
  -> example: embedding 500 chunks/s on a 4-vCPU box
  -> tool: worker processes (= cores), job queue, separate compute tier

Mixed (most real systems)
  -> keep I/O on the async API tier, push CPU to workers
  -> example: FastAPI accepts upload (I/O), Pub/Sub job embeds (CPU), webhook on done
```

**Amdahl's Law — why parallelism has diminishing returns:**

If 30% of a request is inherently serial (auth check, one DB round trip you cannot batch),
then even infinite cores cannot make it more than ~3.3× faster overall:

```
speedup = 1 / (S + (1-S)/N)

S = 0.30 serial fraction, N = 8 cores
speedup = 1 / (0.30 + 0.70/8) = 2.4×   (not 8×)
```

This is the honest answer when someone asks "why didn't we just add more pods?"

### Enterprise production example

**Cloudflare** runs one of the highest-concurrency systems on the internet — every edge PoP
terminates millions of concurrent connections — but their architecture deliberately separates
*connection handling* from *CPU-heavy work*. The edge proxy (historically nginx-based, now
their own stack) is I/O-concurrent: it accepts, parses headers, routes. CPU-heavy tasks —
WAF rule evaluation, Workers isolates, image resizing — run in separate pools with explicit
concurrency limits per isolate. Their public Workers documentation states a default of
128 concurrent requests per isolate before queuing, because giving every connection unbounded
CPU would let one customer starve the PoP. That is concurrency vs parallelism made operational:
the proxy layer juggles connections; the compute layer parallelises only where cores exist and
caps how many compute tasks share them.

### Code

Node.js: I/O-concurrent API, CPU work offloaded to a worker pool.

```javascript
// api.js — event loop stays free; CPU work does not block other requests
const express = require('express');
const { Worker } = require('worker_threads');
const os = require('os');

const CPU_WORKERS = Math.max(1, os.cpus().length - 1);
const pool = [];
let next = 0;

function runOnWorker(task) {
  return new Promise((resolve, reject) => {
    const worker = pool[next++ % CPU_WORKERS];
    const onMessage = (msg) => {
      worker.off('message', onMessage);
      worker.off('error', reject);
      msg.error ? reject(new Error(msg.error)) : resolve(msg.result);
    };
    worker.on('message', onMessage);
    worker.postMessage(task);
  });
}

for (let i = 0; i < CPU_WORKERS; i++) {
  pool.push(new Worker('./cpu-worker.js'));
}

const app = express();
app.post('/embed', express.json({ limit: '1mb' }), async (req, res) => {
  try {
    const vector = await runOnWorker({ texts: req.body.texts });
    res.json({ vectors: vector });
  } catch (err) {
    res.status(500).json({ error: 'embed_failed' });
  }
});
```

```javascript
// cpu-worker.js — runs on a separate thread; true parallel CPU with other workers
const { parentPort } = require('worker_threads');
const { embedBatch } = require('./embedder'); // ONNX / native — blocks this thread only

parentPort.on('message', async ({ texts }) => {
  try {
  const result = await embedBatch(texts);
    parentPort.postMessage({ result });
  } catch (e) {
    parentPort.postMessage({ error: e.message });
  }
});
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Async I/O for network-bound APIs | CPU-bound work on the same thread as the event loop | Debugging async stack traces; one blocked thread stalls everything |
| Worker pool / process pool for CPU work | Tiny payloads where IPC overhead exceeds compute | Memory per worker (~30–80 MB each in Node); harder deployment |
| Separate compute tier (Pub/Sub + workers) | Latency budget < 100 ms end-to-end | Operational complexity: queue, retries, idempotency |

### Follow-ups they will ask

**Q: Is Node.js single-threaded?**
A: The JavaScript execution model is single-threaded — one call stack, one event loop. But
Node uses a libuv thread pool (default four threads) for some blocking I/O like file system
and DNS, and `worker_threads` give real parallel JavaScript. So "single-threaded" is true for
your JS code and false for the process as a whole. The interview answer is: "single-threaded
for JS, which is why CPU work blocks the event loop."

**Q: How many concurrent connections can one Node process handle?**
A: Tens of thousands of *idle or I/O-waiting* connections are normal — C10K was solved in 1999.
The limit is memory (~4–8 KB per connection for buffers) and what happens when they all become
active at once. Fifty thousand connections each firing a 50 ms DB query is not a concurrency
problem; it is a database problem.

**Q: When would you use threads vs processes?**
A: Threads share memory — fast, but one segfault kills everyone and you need locks for shared
state. Processes are isolated — slower IPC, but the blast radius is one worker and you get true
parallelism on CPU-bound Python. For Node I use `worker_threads` for CPU; for Python I use
multiprocessing or a separate worker service, not threads, because of the GIL.

### Red flags — do not say this

- ❌ "`async` makes it parallel." → ✅ "`async` makes I/O concurrent on one thread; CPU
  parallelism needs cores and a runtime that can use them."
- ❌ "Just scale horizontally." → ✅ "Scale the tier that's actually saturated — I/O waiters
  need more efficient waiting; CPU burners need more cores or a queue."

---

## 13.2 The Node.js concurrency model

> **One-liner:** One thread runs your JavaScript; libuv runs the event loop and a small thread
> pool; and anything synchronous that takes longer than a few milliseconds is a outage waiting
> to happen.

### Say this in the interview

> Node's concurrency model is an event loop on a single JavaScript thread plus libuv handling
> OS async primitives underneath. When I call `await db.query()`, the query goes to Postgres,
> the promise registers a callback, and the event loop moves on to the next request — that is
> why one Node process can serve thousands of in-flight HTTP requests without thousands of
> threads. The catch is anything that runs synchronously on the main thread: `JSON.parse` on a
> five-megabyte body, a tight `for` loop, `bcrypt.compare` at cost factor twelve, or a
> synchronous file read — all of that blocks every other request in that process until it
> finishes. At p50 that might be invisible; at p99 one slow parse shows up as a latency cliff
> for unrelated endpoints sharing the process. I treat the event loop like a single-lane road:
> I never park on it. CPU work goes to `worker_threads` or a separate service, blocking I/O
> that libuv cannot async-ify goes to the thread pool, and I monitor event loop lag — if p99
> lag exceeds roughly ten milliseconds, something is blocking and I find it with a CPU profile
> before I add pods.

### Mental model

```
  HTTP request
       |
       v
  +------------------+     timers/setImmediate     +------------------+
  |   EVENT LOOP     |<--------------------------->|  callback queue  |
  |  (1 JS thread)   |                             +------------------+
  +--------+---------+
           |
     +-----+-----+--------------+
     |           |              |
     v           v              v
  microtask   thread pool    kernel async I/O
  queue       (default 4)    (epoll: sockets)
  (Promises)  fs, dns,       Postgres, Redis,
              some crypto    HTTP client

BLOCKING THE LOOP                    NOT BLOCKING THE LOOP
  JSON.parse(5 MB)                     await fetch(url)
  bcrypt.sync()                        await pg.query()
  while(true){}                        setImmediate(() => ...)
  fs.readFileSync()                    fs.promises.readFile()  -> thread pool
```

**Phases of the event loop (order matters for debugging):**

```
   ┌─────────────┐
   │   timers    │  setTimeout / setInterval callbacks due now
   └──────┬──────┘
          v
   ┌─────────────┐
   │   pending   │  I/O callbacks deferred from previous iteration
   └──────┬──────┘
          v
   ┌─────────────┐
   │    poll     │  retrieve new I/O events; block here if no timers
   └──────┬──────┘
          v
   ┌─────────────┐
   │    check    │  setImmediate callbacks
   └──────┬──────┘
          v
   ┌─────────────┐
   │ close cb    │  e.g. socket.on('close')
   └─────────────┘

Between every phase: process ALL microtasks (Promise .then / await continuations).
That is why a runaway Promise chain can starve timers.
```

**Event loop lag — the metric that tells the truth:**

```
healthy:  p99 event loop delay < 10 ms
warning:  p99 10–50 ms — investigate before peak traffic
bad:      p99 > 100 ms — you are effectively down; LB health checks may still pass

Measure with: perf_hooks.monitorEventLoopDelay() (Node 16+)
Or: prom-client collectDefaultMetrics() includes nodejs_eventloop_lag_seconds
```

### Enterprise production example

**Netflix** has published extensively on Node in production for their UI rendering and BFF
layers. Their operational guidance — mirrored across the industry — centres on *never blocking
the event loop* and *measuring event loop lag as a first-class SLO*. Teams that migrated
synchronous template rendering or large in-process transforms to worker pools or edge
caching reported tail latency improvements of 40–60% without adding instances, because the
fix removed head-of-line blocking rather than adding capacity. The pattern is consistent: Node
scales with connection count until something synchronous appears in the hot path; the fix is
always relocation, not more pods.

### Code

Production-shaped Express middleware: body size limit, event loop monitoring, and safe JSON
parse via worker when payload is large.

```javascript
const express = require('express');
const { monitorEventLoopDelay } = require('perf_hooks');
const { Worker } = require('worker_threads');

// --- observability: event loop lag histogram ---
const loopDelay = monitorEventLoopDelay({ resolution: 10 });
loopDelay.enable();
setInterval(() => {
  const lagMs = loopDelay.mean / 1e6;
  const p99Ms = loopDelay.percentile(99) / 1e6;
  // export to Prometheus / Cloud Monitoring
  if (p99Ms > 50) console.warn({ msg: 'event_loop_lag', p99Ms, meanMs: lagMs });
  loopDelay.reset();
}, 10_000).unref();

function parseJsonOffThread(buf) {
  if (buf.length < 256 * 1024) return Promise.resolve(JSON.parse(buf)); // small: inline OK
  return new Promise((resolve, reject) => {
    const w = new Worker(`
      const { parentPort, workerData } = require('worker_threads');
      try { parentPort.postMessage(JSON.parse(workerData)); }
      catch (e) { parentPort.postMessage({ __err: e.message }); }
    `, { eval: true, workerData: buf.toString('utf8') });
    w.on('message', (m) => (m?.__err ? reject(new Error(m.__err)) : resolve(m)));
    w.on('error', reject);
  });
}

const app = express();
app.use(express.raw({ type: 'application/json', limit: '2mb' }));

app.post('/ingest', async (req, res, next) => {
  const deadline = Date.now() + 8_000;
  try {
    const body = await parseJsonOffThread(req.body);
    if (Date.now() > deadline) return res.status(503).json({ error: 'server_busy' });
    // ... business logic, all async I/O from here ...
    res.status(202).json({ accepted: true, id: body.id });
  } catch (e) {
    next(e);
  }
});

// cluster mode for CPU parallelism across cores (one process per core)
// require('cluster').isPrimary ? fork workers : app.listen(3000)
```

**`UV_THREADPOOL_SIZE`:** libuv's default thread pool is four. If you do heavy `fs` or
`crypto.pbkdf2` concurrently, bump it: `UV_THREADPOOL_SIZE=16` — but remember those threads
compete with your event loop for CPU; profiling first.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| I/O-heavy APIs, WebSockets, BFF aggregation | CPU-heavy transforms on the main thread | Single-threaded JS debugging; shared-nothing per process |
| `cluster` module / K8s replicas for multi-core | You need shared in-memory state across cores | Sticky sessions or external state store required |
| Worker threads for isolated CPU bursts | Sub-millisecond tasks where IPC > compute | ~2–5 ms overhead per worker message |

### Follow-ups they will ask

**Q: What happens if I `await` inside a `for` loop vs `Promise.all`?**
A: Sequential `await` sums latencies: ten 20 ms queries = 200 ms. `Promise.all` runs them
concurrently on the event loop — still one thread, but all ten I/O operations are in flight,
so wall time is ~20 ms plus connection pool contention. The limit becomes your pool size and
what Postgres can absorb, not JavaScript threading.

**Q: How do you find what's blocking the event loop?**
A: `node --cpu-prof` under load, or `clinic doctor` / `0x` flamegraphs. In production,
`monitorEventLoopDelay` correlated with request path via OpenTelemetry. The flamegraph shows
a fat bar on `JSON.parse` or `bcrypt` — that is your blocker.

**Q: Node cluster vs Kubernetes replicas?**
A: Functionally similar — one process per core. In K8s I usually run one container per pod with
`replicas = cores` or use a single process and scale pods horizontally, because K8s gives me
health checks, rolling deploys and autoscaling for free. Cluster module is fine on a single VM.

### Red flags — do not say this

- ❌ "Node can't handle heavy load." → ✅ "Node handles concurrent I/O well; synchronous CPU
  or blocking calls on the event loop are what break it."
- ❌ "I'll use `sync` bcrypt because it's simpler." → ✅ "I'll use `bcrypt` async or offload
  to a worker — cost factor 12 sync takes ~250 ms and blocks every request in the process."

---

## 13.3 Python GIL, asyncio & the FastAPI trap

> **One-liner:** The GIL lets only one thread execute Python bytecode at a time; `async def`
> makes I/O concurrent but not parallel; and `def` endpoints in FastAPI run your blocking code
> on a thread pool that exhausts itself long before your database does.

### Say this in the interview

> Python's Global Interpreter Lock means that even if I spawn ten threads, only one executes
> Python bytecode at any instant — so threads do not give me parallel CPU for pure Python code.
> They do help for I/O, because a thread blocked on a socket releases the GIL, which is why
> the old threaded Flask model worked for database-heavy APIs. `asyncio` is different: one
> thread, many coroutines, explicit `await` points — great for thousands of concurrent I/O
> waits with less memory than a thread per request. But `async def` does not make `pandas`,
> `json.loads` on a huge blob, or a synchronous `requests.get` non-blocking. Those run on the
> event loop thread and block every other coroutine until they finish. The FastAPI trap is this:
> if I write `def read_items()` instead of `async def`, FastAPI runs it in a default thread
> pool of roughly forty workers. Forty concurrent blocking requests is the ceiling before
> queuing — not thousands. And if I write `async def` but call blocking code inside without
> `run_in_executor`, I block the entire event loop instead. My rule: async endpoints, async
> database drivers (`asyncpg`, `httpx`), and anything CPU-bound goes to `ProcessPoolExecutor`
> or a separate worker service, because processes have separate interpreters and separate GILs.

### Mental model

```
THE GIL (simplified)

  Thread 1:  [====Python====]     [====Python====]
  Thread 2:       waiting GIL          [==Python==]
  Thread 3:  [==I/O==, release GIL, wait, acquire, ==Python==]
                              ^
                    only one runs bytecode at a time

asyncio (single thread, cooperative)

  coro A:  await db.fetch() ----idle---- resume ----
  coro B:       ---- await http.get() ----idle---- resume
  coro C:  await sleep() ---- ...
            ^ event loop schedules whoever has a ready callback

FastAPI routing decision:

  async def handler()  -> runs ON event loop thread
                          MUST NOT call blocking/sync I/O or CPU work

  def handler()        -> runs IN threadpool (default ~40 threads)
                          OK for sync ORM, but pool exhausts fast
```

**The three traps, in order of how often I see them:**

| Trap | Symptom | Fix |
|---|---|---|
| `async def` + `requests.get()` | Whole API freezes under load | `httpx.AsyncClient` or `run_in_executor` |
| `async def` + `time.sleep(1)` | Event loop stalled 1 s | `await asyncio.sleep(1)` |
| `def` + heavy traffic | Thread pool queue, 503s at ~40 concurrent | `async def` + async driver, or more workers via gunicorn |

**Gunicorn + Uvicorn worker model:**

```
gunicorn -w 4 -k uvicorn.workers.UvicornWorker app:app

4 processes = 4 GILs = 4 cores of parallel Python (for CPU)
              4 separate event loops (for I/O)

Rule: workers = (2 × cores) + 1 is a starting point for sync;
      for async I/O-bound, workers ≈ cores (often just cores, not 2×+1)
```

### Enterprise production example

**Instagram** ran Django on CPython for years at enormous scale and publicly documented that
their path to performance was not "rewrite in Go" but *multiprocessing* for the heaviest
workloads and careful separation of I/O-bound request handling from CPU-bound image processing.
Image filters and video transcode did not run in the request path — they ran in Celery workers
(separate processes). That is the FastAPI lesson at production scale: the framework concurrency
model is not your architecture; what you put inside the handler is.

**Dropbox** migrated performance-critical components from Python to Rust (their "2017–2018
performance push") specifically where the GIL prevented parallel CPU utilisation on multi-core
machines — not because Python was slow at I/O, but because sync CPU on hot paths could not
scale with cores. The interview takeaway: identify whether the bottleneck is GIL-bound Python
CPU (rewrite, C extension, or process pool) or I/O wait (asyncio is fine).

### Code

FastAPI: correct async I/O, executor for blocking, process pool for CPU.

```python
import asyncio
import json
from concurrent.futures import ProcessPoolExecutor
from functools import partial

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI()
http = httpx.AsyncClient(timeout=5.0, limits=httpx.Limits(max_connections=100))
cpu_pool = ProcessPoolExecutor(max_workers=4)  # separate GIL per process

class IngestBody(BaseModel):
    doc_id: str
    text: str

def heavy_tokenize(text: str) -> list[str]:
    # CPU-bound — would block event loop if called directly in async def
    return text.split()  # stand-in for tiktoken / regex / NLP

@app.on_event("shutdown")
async def shutdown():
    await http.aclose()
    cpu_pool.shutdown(wait=False, cancel_futures=True)

@app.post("/ingest")
async def ingest(body: IngestBody):
    loop = asyncio.get_running_loop()
    tokens = await loop.run_in_executor(cpu_pool, partial(heavy_tokenize, body.text))

    try:
        resp = await http.post(
            "https://embedding-service.internal/v1/embed",
            json={"doc_id": body.doc_id, "tokens": tokens[:512]},
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail="embed_upstream_failed") from e

    return {"doc_id": body.doc_id, "token_count": len(tokens)}

# ANTI-PATTERN — do not ship this:
# @app.get("/bad")
# async def bad():
#     return requests.get("https://slow.api").json()  # blocks entire event loop
```

SQLAlchemy async session — the database half must match the endpoint:

```python
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

engine = create_async_engine(
    "postgresql+asyncpg://app@db/prod",
    pool_size=10,
    max_overflow=5,
    pool_timeout=3,
)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

@app.get("/documents/{doc_id}")
async def get_document(doc_id: str):
    async with AsyncSessionLocal() as session:
        row = await session.get(Document, doc_id)  # non-blocking asyncpg
        if row is None:
            raise HTTPException(404)
        return {"id": row.id, "title": row.title}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `asyncio` + async drivers for I/O-heavy APIs | CPU-bound numerical work in pure Python | Ecosystem split: not every library has async support |
| `def` endpoints + sync ORM for low-traffic internal APIs | > ~40 concurrent blocking ops per worker | Thread pool exhaustion without warning |
| `ProcessPoolExecutor` for CPU bursts | Tiny functions where pickle IPC > compute | 30–80 MB per worker process; harder to debug |

### Follow-ups they will ask

**Q: Does the GIL matter in 2026?**
A: For I/O-bound web APIs, rarely — asyncio or threads release the GIL during waits. For CPU-
bound Python (ML preprocessing, parsing, compression), yes — you need multiprocessing, native
extensions (numpy releases GIL for many ops), or another language. Always profile before
rewriting.

**Q: How many Uvicorn workers should I run?**
A: Start with one worker per vCPU for async I/O-bound services. Load-test and watch CPU: if
workers are idle but latency is high, the bottleneck is downstream (DB, pool), not worker count.
If CPU is saturated, you need fewer workers doing more efficient work or a compute split.

**Q: `run_in_executor` with threads vs processes?**
A: Threads for blocking I/O that releases the GIL (sync DB driver, file read). Processes for
CPU-bound Python. Wrong choice gives you either no speedup (CPU on threads) or high overhead
(I/O on processes).

### Red flags — do not say this

- ❌ "FastAPI is async so it's fast." → ✅ "FastAPI is async-capable; my handlers and drivers
  must be async too, or blocking work goes to an executor with explicit limits."
- ❌ "I'll just add more threads." → ✅ "Threads help blocking I/O up to pool size; CPU-bound
  Python needs processes because of the GIL."

---

## 13.4 Race conditions

> **One-liner:** A race condition is when the correctness of your program depends on the
> timing of concurrent operations — and "it works in dev" means you have not been lucky enough
> long enough yet.

### Say this in the interview

> A race condition happens when two or more flows read and write shared state without
> coordination, and the outcome depends on who wins the timing lottery. The classic example is
> read-modify-write: both requests read `balance = 100`, both subtract 50, both write 50 — but
> the answer should be 0 and the database says 50. The fix is never "it probably won't happen
> simultaneously"; the fix is making the update atomic, serialising access, or designing so
> there is no shared mutable state. At the database layer that is a single `UPDATE ... SET
> balance = balance - 50 WHERE id = $1 AND balance >= 50` or a transaction with the right
> isolation level. At the application layer it is a distributed lock, a compare-and-swap, or
> pushing the invariant into a queue so only one worker touches it. I assume races exist
> everywhere two requests can touch the same row, the same Redis key, or the same file — and I
> write code that is correct even when they arrive in the same millisecond.

### Mental model

```
LOST UPDATE (the interview favourite)

  Request A                    Request B
  READ balance = 100           READ balance = 100
  compute 100 - 60 = 40        compute 100 - 40 = 60
  WRITE balance = 40           WRITE balance = 60   <- B wins, A's debit vanishes

CHECK-THEN-ACT (equally common)

  if not cache.get(key):       if not cache.get(key):
      cache.set(key, val)          cache.set(key, val)
  Two expensive DB fills; stampede; duplicate work

TOCTOU (time-of-check-time-of-use)

  if os.path.exists(f):        # check
      open(f, 'w')             # use — another process created it between
```

**Where races hide in real systems:**

| Location | Example | Correctness tool |
|---|---|---|
| Database row | Inventory decrement | Atomic UPDATE or `SELECT FOR UPDATE` (see [5.7](./05_Databases_Relational.md#57-locking)) |
| Redis | Rate limit counter | `INCR` + `EXPIRE` in Lua, or Redis 8+ atomic commands |
| Object storage | "Upload if not exists" | Conditional PUT with etag / generation |
| In-memory (single process) | Counter in Node global | Still racy across cluster — use Redis or DB |
| Message queue | At-least-once delivery | Idempotent consumer (see [Module 09](./09_Reliability_Patterns.md)) |

### Enterprise production example

**GitHub** documented a class of race conditions in their API around repository creation and
name reuse — two users attempting related operations in parallel could observe inconsistent
states when check-then-act spanned multiple services. Their mitigation pattern — used widely in
fintech and marketplace systems — is *unique constraints as the final arbiter*: attempt the
operation, let the database reject duplicates with a conflict error, map `23505` (unique
violation) to a 409. Application-level locks are optimisation; constraints are correctness.

**Stripe**'s idempotency keys exist partly because retries create races: the same payment
submit arrives twice, and without an idempotency key the second could double-charge. The race
is between the client's retry and the server's slow response — not between threads, but
between network timing and human impatience. Same class of problem, different layer.

### Code

Wrong vs right: inventory decrement.

```python
# WRONG — read-modify-write race
async def decrement_wrong(pool, sku: str, qty: int):
    row = await pool.fetchrow("SELECT qty FROM inventory WHERE sku=$1", sku)
    if row["qty"] < qty:
        raise ValueError("insufficient")
    await pool.execute(
        "UPDATE inventory SET qty=$1 WHERE sku=$2", row["qty"] - qty, sku
    )

# RIGHT — single atomic statement; 0 rows updated = insufficient stock
async def decrement_right(pool, sku: str, qty: int) -> bool:
    result = await pool.execute(
        """
        UPDATE inventory
           SET qty = qty - $2,
               updated_at = now()
         WHERE sku = $1
           AND qty >= $2
        """,
        sku, qty,
    )
    return result.endswith("UPDATE 1")

# RIGHT — explicit serialisation when you need the row for more logic
async def decrement_with_lock(pool, sku: str, qty: int):
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT qty FROM inventory WHERE sku=$1 FOR UPDATE", sku
            )
            if row["qty"] < qty:
                raise ValueError("insufficient")
            await conn.execute(
                "UPDATE inventory SET qty = qty - $1 WHERE sku=$2", qty, sku
            )
```

Redis check-then-act fixed with atomic SET NX:

```javascript
// WRONG
const exists = await redis.get(`lock:${jobId}`);
if (!exists) await redis.set(`lock:${jobId}`, '1', 'EX', 300);

// RIGHT — SET NX is atomic at the server
const acquired = await redis.set(`lock:${jobId}`, ownerId, 'NX', 'EX', 300);
if (acquired !== 'OK') return { skipped: true };
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Atomic SQL for simple invariants | Logic spans multiple tables without FK | Retries on conflict; harder to read than RMW |
| `FOR UPDATE` when you need multi-step logic | Long think-time while holding lock | Lock wait latency; deadlock risk |
| Unique constraint + handle conflict | You need ordering guarantees | 409 UX; client must retry or merge |

### Follow-ups they will ask

**Q: How do you test for race conditions?**
A: Stress tests with parallel workers hammering the same key — `pytest-xdist`, `k6` with one
SKU. Run under ThreadSanitizer for C/Rust; for Python/Node, property-based tests with concurrent
`asyncio.gather`. In CI, a test that fires 100 parallel decrements on stock=50 and asserts
final stock is 0, not 10.

**Q: Is a JavaScript single-threaded server immune to races?**
A: No. One event loop serialises JS, but two pod replicas, two `await` interleavings with
non-atomic Redis, or a worker thread sharing state still race. "Single-threaded" is not
"atomic."

**Q: Race vs data race vs bug?**
A: In interview loose talk, "race condition" = correctness depends on timing. A *data race*
(strict sense) is unsynchronised concurrent access in languages with defined memory models.
In backend interviews they usually mean lost updates and check-then-act.

### Red flags — do not say this

- ❌ "We only get 100 QPS, races won't happen." → ✅ "Races are about concurrency, not QPS —
  two requests in the same millisecond are enough."
- ❌ "I'll add a mutex in the app." → ✅ "I'll make the database update atomic first; app locks
  don't span replicas."

---

## 13.5 Locking & atomics

> **One-liner:** Prefer a single atomic statement in the database or Redis over read-modify-write
> in application code across replicas.

### Say this in the interview

> The bug pattern is read value, compute in Python, write value — two requests interleave and
> one update is lost. The fix is push the invariant into an atomic operation: `UPDATE accounts
> SET balance = balance - $1 WHERE id = $1 AND balance >= $1`, Redis `INCR`, or Lua scripts for
> multi-key atomicity. `SELECT FOR UPDATE` when I need multi-step logic in one transaction.
> Distributed locks are a last resort — see Module 09.

### Red flags — do not say this

- ❌ "Single-threaded Node can't race." → ✅ "Two pods, or two awaits with shared Redis, still race."

---

## 13.6 Optimistic vs pessimistic locking

> **One-liner:** Pessimistic locks rows up front; optimistic checks a version on write and
> retries on conflict.

### Say this in the interview

> I use pessimistic (`FOR UPDATE`) when contention is high and conflicts are expensive —
> inventory on flash sale. I use optimistic (`version` column, `UPDATE ... WHERE version = $n`)
> when conflicts are rare — profile edits. Optimistic fails with 409 and the client retries.
> Cross-link: [Module 05 §5.8](./05_Databases_Relational.md#58-optimistic-vs-pessimistic-concurrency-control).

### Code

```sql
UPDATE products SET stock = stock - 1, version = version + 1
WHERE id = $1 AND version = $2 AND stock > 0
RETURNING *;
-- 0 rows -> conflict, retry or 409
```

---

## 13.7 Connection pools & resource limits

> **One-liner:** A pool caps concurrent database connections; size it to what Postgres can
> serve, not to your thread count.

### Say this in the interview

> Each Postgres connection is a process — typically 1–10 MB and CPU on connect. A pool of
> 200 connections on an 8-core DB often performs *worse* than 20, because the database spends
> time context-switching. Rule of thumb: `pool_size ≈ (cores × 2) + effective_spindles`, often
> under 20 for OLTP. Queueing at the pool is intentional — Little's Law: if each query holds
> 20 ms and I have 20 connections, max throughput is about 1,000 qps. Cross-link Module 05 §5.13.

---

## 13.8 Thread/worker pool sizing (Little's Law)

> **One-liner:** `concurrency = throughput × latency` — size workers from the math, not from
> CPU count alone.

### Say this in the interview

> Little's Law: L = λW. At 500 requests per second with 200 ms average service time, I need
> 500 × 0.2 = 100 in-flight requests — that is my worker or connection budget. For Uvicorn,
> `workers = (2 × cores) + 1` is a starting point for CPU-bound sync workers; for async,
> one process per core with async I/O often suffices unless blocking calls leak into the loop.

---

## 13.9 Finding the bottleneck (USE, profiling, latency budget)

> **One-liner:** Measure end-to-end, then USE each resource — Utilisation, Saturation, Errors.

### Say this in the interview

> I build a latency budget table: auth 5 ms, cache 1 ms, DB 30 ms, external API 200 ms.
> Whatever dominates gets profiled first. If CPU is 30% but p99 is high, I am waiting — check
> pool queue depth, lock waits, or network. `py-spy`/`clinic.js` flamegraphs for CPU;
> `EXPLAIN ANALYZE` for Postgres. Never optimise the 2 ms step when 180 ms is an LLM call.

---

## 13.10 Common performance killers (N+1, etc.)

> **One-liner:** N+1 queries, missing indexes, unbounded `SELECT *`, and chatty microservice
> fan-out dominate real backends more than algorithm choice.

### Say this in the interview

> The classic ORM trap: load 50 orders, then 50 queries for each user. Fix with JOIN,
> `WHERE id = ANY($1)` batching, or DataLoader at the BFF. In microservices, 10 sequential
> HTTP calls at 20 ms p99 each is not 200 ms p99 — tail latency multiplies; batch endpoints
> or parallel `asyncio.gather` with a deadline.

---

## 13.11 Batching, debouncing & coalescing

> **One-liner:** Batch to amortise round-trip cost when latency slack exists.

### Say this in the interview

> Fifty single-row inserts are fifty parse/plan round trips; one `executemany` or `COPY` is one.
> I micro-batch Kafka produces (linger.ms) and embedding API calls (32 texts, 50 ms max wait).
> Debouncing collapses search keystrokes; coalescing merges duplicate in-flight cache fetches
> (single-flight in Module 07).

---

## 13.12 Compression & payload size

> **One-liner:** gzip JSON above ~1 KB; protobuf inside the cluster; field selection beats
> compression for over-fetching.

### Say this in the interview

> Enable `gzip`/`br` on text APIs; skip already-compressed media. Cross-AZ egress at ~$0.01/GB
> and internet egress at ~$0.08–0.12/GB makes payload size a billing line item — `?fields=`
> and pagination are often cheaper than brotli.

---

## 13.13 Cost optimization as an engineering discipline

> **One-liner:** Compute $/request from the invoice; attack egress, over-provisioned compute,
> and retention before re-architecting.

### Say this in the interview

> To cut cost 30%: rightsizing, lifecycle policies on object storage, same-region traffic,
> spot/preemptible for batch workers (idempotent consumers), and LLM routing to smaller models
> where quality allows — Module 14. FinOps is a design-review question, not a quarterly cleanup.

---

## Module 13 — self-test

Answer out loud, without notes.

1. Concurrency vs parallelism — Node and Python examples.
2. What blocks the Node event loop?
3. FastAPI `def` vs `async def` with blocking ORM?
4. Atomic SQL fix for lost update?
5. Size a Postgres pool on 8 cores.
6. Little's Law at 500 RPS, 200 ms latency.
7. USE method on a slow API with low CPU.
8. Fix N+1 in one sentence.
9. When to batch vs not batch?
10. Three cloud cost levers before re-architecting.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| libuv thread pool default | 4 |
| Postgres pool (typical OLTP) | often < 20 |
| Little's Law | L = λ × W |
| gzip on JSON | ~70–90% smaller |
| Event-loop lag alert | p99 > 100 ms sustained |

---

**Next:** [Module 14 — AI & LLM System Design](./14_AI_LLM_System_Design.md)

