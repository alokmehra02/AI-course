# Module 01 — Requirements, NFRs & Back-of-the-Envelope Estimation

> **What this module makes you able to do:** turn a one-line prompt like "design a
> notification system" into a written set of functional requirements, numeric
> non-functional targets, and a scale estimate — in the first five minutes, out loud,
> without hedging.
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** none — this is the entry point.

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 1.1 | Functional requirements — eliciting and scoping | ★★★★★ |
| 1.2 | Non-functional requirements — the taxonomy, as numbers | ★★★★★ |
| 1.3 | Availability and the nines | ★★★★★ |
| 1.4 | Reliability vs availability vs durability | ★★★★☆ |
| 1.5 | Scalability — vertical, horizontal, the scale cube | ★★★★☆ |
| 1.6 | Latency vs throughput, Little's Law, percentiles | ★★★★★ |
| 1.7 | Consistency and durability as requirements | ★★★☆☆ |
| 1.8 | Cost as a first-class NFR | ★★★★☆ |
| 1.9 | Back-of-the-envelope estimation | ★★★★★ |
| 1.10 | Writing requirements on the whiteboard | ★★★★☆ |

---

## 1.1 Functional requirements — eliciting and scoping

> **One-liner:** Functional requirements are the verbs your system must support, written
> as actor-action-object sentences, and the job of the first five minutes is to cut them
> down to the three that carry the architecture.

### Say this in the interview

> Before I draw anything I want to agree on what the system actually does, because the
> architecture follows from two or three core operations, not from twenty. For a
> notification system I'd write four functional requirements: a service can enqueue a
> notification for a user; the system delivers it over email, SMS or push; the user can
> set channel preferences and quiet hours; and the sender can query delivery status.
> Everything else — templating, localisation, an admin UI, A/B testing of copy — I'd
> explicitly call out of scope for this session and note that they're product surface,
> not architecture. The reason I scope this hard is that "deliver over three channels"
> and "query delivery status" are the two requirements that force a queue, a worker
> pool and a durable status store; the other fifteen features ride on top of that
> without changing the shape of the system. Is there a requirement you'd like me to
> treat as in-scope that I've just cut?

### Mental model

A functional requirement is a sentence of the form **actor → action → object → outcome**.
"A merchant uploads a CSV of up to 500,000 rows and receives a per-row error report."
That sentence tells you there's an upload path, an async job, a result artifact, and a
retrieval path. Compare it to "the system supports bulk import", which tells you nothing.

The interview failure mode is not asking too few questions — it's asking twenty shallow
questions and never converging. Use a fixed elicitation order:

```text
  1. WHO are the actors?          end user / service / admin / batch job
  2. WHAT are the core verbs?     write path first, then read path
  3. WHAT is the read:write mix?  this single ratio drives 60% of the design
  4. WHAT must be synchronous?    everything else becomes a queue
  5. WHAT is explicitly OUT?      say it out loud; it buys you the whole hour
```

Then apply the **core-three test**: if you deleted this requirement, would the boxes on
the whiteboard change? If no, it is product scope, not system design. Say so and move on.

```text
   Vague prompt                  Scoped FR set                Architecture
  ┌──────────────┐            ┌────────────────────┐        ┌─────────────┐
  │ "Design a    │            │ 1. enqueue notif   │        │ API         │
  │  notifi-     │  scoping   │ 2. fan out to 3    │ forces │  → Queue    │
  │  cation      │ ─────────► │    channels        │ ──────►│  → Workers  │
  │  system"     │  questions │ 3. read status     │        │  → Status DB│
  └──────────────┘            │ (templating: OUT)  │        └─────────────┘
                              └────────────────────┘
```

The arrow labelled "forces" is the one the interviewer is grading. Every box you draw
should be traceable back to a requirement you wrote down.

### Enterprise production example

**Amazon** runs a documented internal process called *Working Backwards*: before a team
writes code, it writes the press release and the FAQ for the finished product, including
the customer-facing description and the hard questions. The artifact is deliberately
customer-language, not engineering-language, and a proposal that cannot produce a
compelling one-page press release usually does not get built. The engineering value is
the same as the interview value — it forces the team to state the two or three
customer-visible operations that justify the system before anyone argues about
databases. When you scope requirements in an interview, you are doing a two-minute
version of the same exercise.

### Code

Skip — requirements are prose, and writing them as a data structure is a tell that you
are avoiding the conversation.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Prompt is one vague sentence — always | Interviewer has already handed you a written spec with numbers | 4–6 minutes of a 45-minute interview |
| You want permission to ignore a feature | You are using it to dodge a hard part they clearly want | Looks evasive if you scope out the interesting problem |
| Read:write ratio is unknown | You're guessing at it instead of asking | A wrong ratio invalidates every later estimate |

### Follow-ups they will ask

**Q: You scoped out templating. What if I tell you templates are the whole point — merchants author them and we render 50 million a day?**
A: Then it stops being product surface and becomes a rendering tier with its own scaling
story: a template store with versioning, a render step that must be sandboxed because
merchant-authored templates are untrusted input, and a render cache keyed on
`template_version + locale + variable-hash`. I'd put rendering *before* the queue so a
bad template fails fast at enqueue time rather than poisoning 50 million worker jobs,
and I'd cap render latency at something like 20 ms p99 so it doesn't dominate enqueue.

**Q: How do you decide read:write ratio when the interviewer says "you tell me"?**
A: I anchor on a comparable product and say the number out loud so it can be corrected.
For a social feed I'd assume 100:1 reads to writes because people scroll far more than
they post; for an internal audit log I'd assume the inverse, maybe 1:50, because
everything is written and almost nothing is read. The ratio matters more than its
precision: 100:1 means I design for a read-optimised cache tier and accept replication
lag, while 1:50 means I design for write throughput and cheap cold storage.

**Q: A stakeholder gives you a requirement that contradicts another. What do you do?**
A: I surface it explicitly rather than picking one silently. "Users must see their own
post immediately" and "feed reads are served from a read replica with 200 ms lag" are in
direct conflict, and the resolution is a design decision — read-your-own-writes via
sticky routing to the primary for that user's own content, or write-through into the
user's own feed cache. Naming the conflict and proposing two resolutions is the answer;
choosing one without mentioning the conflict is the failure.

### Red flags — do not say this

- ❌ "Let's assume standard CRUD requirements." → ✅ "The two operations that shape this system are bulk enqueue and status lookup; let me confirm those before I draw."
- ❌ "I'll design it to support everything." → ✅ "I'm scoping out templating and localisation for this session — they don't change the box diagram. Tell me if you'd rather I include them."
- ❌ Asking ten questions and writing none of them down. → ✅ Writing the answers on the board as a numbered list you refer back to for the rest of the hour.

---

## 1.2 Non-functional requirements — the taxonomy, as numbers

> **One-liner:** An NFR that isn't a number is a mood, and the entire skill is converting
> "highly available and fast" into "99.9% monthly, p99 under 200 ms for reads, 10k peak
> QPS, 5-year retention".

### Say this in the interview

> Functional requirements tell me what to build; non-functional requirements tell me what
> it costs. I'd write down seven of them with numbers attached: availability at 99.9%
> monthly, which is 43 minutes of budget a month; read latency p99 under 200 ms and write
> latency p99 under 500 ms; 10,000 peak read QPS and 200 peak write QPS; durability such
> that we never lose an acknowledged write, so RPO of zero on the transactional path;
> eventual consistency is acceptable for the feed but read-your-own-writes is not
> negotiable; five-year retention for compliance; and a cost ceiling somewhere around a
> tenth of a cent per request. Every one of those is a number I can design against and
> later measure. The reason I insist on numbers is that 99.9% and 99.99% are the same
> English sentence but a completely different architecture — one is a single region with
> good failover, the other is multi-region with all the replication and split-brain
> problems that come with it. Which of these would you like me to treat as the hard
> constraint?

### Mental model

There are exactly nine NFR categories worth memorising, and each has a canonical unit.
Learn the units, not the adjectives.

| NFR | The question | Unit you must give | Typical mid-scale answer |
|---|---|---|---|
| Availability | Can users reach it? | % over a window | 99.9% monthly |
| Latency | How long is one op? | ms at a percentile | p99 < 200 ms read |
| Throughput | How many ops? | QPS / TPS / MB/s | 10k peak QPS |
| Scalability | What happens at 10×? | growth factor + horizon | 3× YoY for 3 years |
| Durability | Can we lose data? | % / RPO | RPO = 0 on writes |
| Consistency | How stale may reads be? | model + bound | eventual, < 1 s lag |
| Reliability | Does it behave correctly? | error rate / MTBF | < 0.1% 5xx |
| Security | Who may do what? | concrete controls | mTLS, per-tenant keys |
| Cost | What does one request cost? | $/request or $/month | < $0.001/request |

The conversion trick is always the same: **take the adjective, ask "compared to what,
measured how, over what window", and the number falls out.**

```text
  "It must be fast"
        │
        ├── compared to what?  → user perceives < 300 ms as instant
        ├── measured how?      → p99 of server-side handler, not average
        └── over what window?  → rolling 5 min, evaluated per endpoint
        ▼
  "p99 server latency < 200 ms on GET /feed, rolling 5-minute window"
```

Google's SRE practice formalises the next step: an **SLI** is the measurement, an **SLO**
is the target, and `1 − SLO` is the **error budget** you are allowed to spend. A 99.9%
monthly SLO gives you 43.2 minutes of budget. That budget is a real currency — if you
have burned 40 of your 43 minutes by the 12th of the month, you freeze risky deploys.
Saying "error budget" in an interview and then explaining what you'd *do* with it is one
of the cheapest ways to sound like you've been on call.

Pair this with the **four golden signals** — latency, traffic, errors, saturation — as
the minimum set you'd instrument. See
[Module 10 — Observability](./10_Observability.md).

### Enterprise production example

**Amazon S3** is the cleanest public illustration that a design target and a contractual
commitment are different numbers. AWS documents S3 Standard as *designed for* 99.99%
availability, but the **S3 Service Level Agreement commits to only 99.9% monthly uptime**,
with service credits of 10% of the bill if monthly uptime falls below 99.9% but stays at
or above 99.0%, 25% below 99.0%, and 100% below 95.0%. Two lessons for your NFR table.
First, the number a vendor engineers to and the number they will pay you for differ by a
full nine — so when you inherit a dependency, plan against its *SLA*, not its marketing
page. Second, an SLA is a refund policy, not a guarantee: a 10% credit on your storage
bill does not compensate you for a day of your product being down, which is why you build
degradation paths instead of relying on someone else's SLA.

### Code

An SLO is only real if it is expressed as a query. This is the burn-rate alert shape used
in most Prometheus setups — a fast burn (2% of a 30-day budget in one hour) pages, a slow
burn ticket-alerts.

```yaml
# 99.9% availability SLO => error budget = 0.1% of requests over 30 days.
# 14.4x burn rate for 1h consumes 2% of the monthly budget -> page.
groups:
  - name: api-slo
    rules:
      - alert: ApiErrorBudgetFastBurn
        expr: |
          (
            sum(rate(http_requests_total{job="api",code=~"5.."}[1h]))
            / sum(rate(http_requests_total{job="api"}[1h]))
          ) > (14.4 * 0.001)
          and
          (
            sum(rate(http_requests_total{job="api",code=~"5.."}[5m]))
            / sum(rate(http_requests_total{job="api"}[5m]))
          ) > (14.4 * 0.001)
        for: 2m
        labels: { severity: page }
        annotations:
          summary: "Burning 30-day error budget 14.4x faster than sustainable"
```

The `and` on a short window is not decoration: it stops a burst that already ended from
paging you an hour later.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Always — before any box is drawn | Never | ~3 minutes, and it saves 20 |
| You want to justify *not* building something | You invent numbers you can't defend | A challenged number you can't derive is worse than no number |
| The interviewer is vague on purpose | You state five nines reflexively | Five nines commits you to multi-region; be sure you want that conversation |

### Follow-ups they will ask

**Q: Your SLO is 99.9% but your cloud provider's database SLA is 99.95%. Is 99.9% achievable?**
A: Only if the database is the sole dependency, and it never is. If my request path
touches a load balancer at 99.99%, a compute tier at 99.95% and a database at 99.95%,
the serial product is about 99.89% — already under my target before I've written a bug.
So I either add redundancy at the weakest link, or I make the dependency non-fatal by
serving stale cache on database failure, or I renegotiate the SLO down to 99.5%. Stating
that composition math out loud is usually the point of the question.

**Q: How do you set the latency target if the product team just says "fast"?**
A: I work backwards from human perception and from the competition. Roughly 100 ms feels
instantaneous, 300 ms is noticeable but fine, and past a second people start switching
tabs. So I'd propose p99 under 200 ms server-side, which leaves room for 100–150 ms of
network and render before the user perceives lag. Then I check it against the cheapest
possible implementation — if a single indexed PostgreSQL point read is 2 ms and I'm
budgeting 200 ms, I have 100× of headroom and the target is not the binding constraint.

**Q: What's the difference between an SLI, an SLO and an SLA, in one sentence each?**
A: The SLI is the measurement — the fraction of requests served under 200 ms. The SLO is
the internal target for that measurement — 99% of requests under 200 ms over 30 days. The
SLA is the contract with a customer that includes a financial penalty when the target is
missed, and it is always set looser than the SLO so that you get paged and fix things
before you owe anybody money.

**Q: Which NFR do candidates most often forget?**
A: Cost, and then retention. Retention is the sneaky one because it silently multiplies
your storage estimate — a 5-year requirement on 10 TB/year of data is a 50 TB problem, and
it changes the storage tier from "one big Postgres" to "hot Postgres plus a Parquet
archive in object storage with a lifecycle policy".

### Red flags — do not say this

- ❌ "It needs to be highly available and scalable." → ✅ "99.9% monthly, which is 43 minutes of downtime budget, and designed to absorb 3× current peak without a re-architecture."
- ❌ "Latency should be low." → ✅ "p99 under 200 ms for reads; I'm using p99 rather than average because averages hide the tail."
- ❌ "We need five nines." → ✅ "99.9% is the right target here; five nines is 26 seconds a month, which rules out any human in the recovery loop and roughly doubles the infrastructure."

---

## 1.3 Availability and the nines

> **One-liner:** Availability is the fraction of a window in which the system serves
> correct responses, it *multiplies* down a dependency chain and *complements* across
> redundant replicas, and almost nobody actually needs five nines.

### Say this in the interview

> Availability is uptime as a percentage over a window, and the only way I keep it honest
> is by converting to minutes. 99.9% is 43 minutes a month, which one bad deploy and a
> rollback will eat. 99.99% is 4.3 minutes a month, which means no human can be in the
> recovery loop — detection and failover both have to be automated. 99.999% is 26 seconds
> a month, and at that point you're multi-region active-active and you've roughly doubled
> your bill. The part people get wrong is that availability composes: if my request path
> hits a load balancer, an API tier, a cache and a database, and each is independently
> 99.9%, the end-to-end number is 0.999 to the fourth, which is 99.6% — that's three hours
> a month, not 43 minutes. Redundancy works the other way: two independent replicas at
> 99% each give you 99.99%, because both have to fail simultaneously. So the design move
> is to shorten the serial chain and add parallelism at the weakest link. For this system
> I'd target 99.9% and spend the money on making failures fast to detect rather than on
> a fifth nine.

### Mental model

**The table. Memorise the year and month columns.**

| Availability | Downtime / year | / month (30 d) | / week | / day |
|---|---|---|---|---|
| 99% ("two nines") | 3.65 days | 7.20 hours | 1.68 hours | 14.4 min |
| 99.9% ("three nines") | 8.77 hours | 43.2 min | 10.1 min | 1.44 min |
| 99.95% | 4.38 hours | 21.6 min | 5.04 min | 43.2 s |
| 99.99% ("four nines") | 52.6 min | 4.32 min | 1.01 min | 8.64 s |
| 99.999% ("five nines") | 5.26 min | 25.9 s | 6.05 s | 864 ms |

Derivation so you never have to memorise the cells: a year is 525,600 minutes, a 30-day
month is 43,200 minutes. Multiply by the complement. 0.1% of 43,200 is 43.2. Done.

**Series composition — dependencies multiply.**

```text
   Client ──► LB ──► API ──► Cache ──► DB ──► response
             99.99   99.95   99.9     99.95

   A_total = 0.9999 x 0.9995 x 0.999 x 0.9995 = 0.99790  ->  99.79%
   = ~1.5 hours of downtime per month, from four "good" components
```

Every synchronous hop you add lowers the ceiling. This is the single strongest technical
argument against gratuitous microservices, and it is why "can this dependency be made
optional?" is the highest-leverage availability question you can ask.

**Parallel composition — redundancy complements.**

```text
              ┌── Replica A (99%) ──┐
   Client ──► │                     │ ──► only fails if BOTH fail
              └── Replica B (99%) ──┘

   A_total = 1 - (1 - 0.99)^2 = 1 - 0.0001 = 99.99%
   Three replicas at 99.9%:  1 - (0.001)^3 = 99.9999999%
```

That last number is fantasy, and knowing why is what separates you from a candidate
reciting formulas. The formula assumes **independent** failures. Real replicas share a
region, a control plane, a deploy pipeline, a config file and a bug. Correlated failure
is the dominant term in practice: three replicas running the same bad binary fail
together, and no amount of `1 − (1−A)^n` saves you. So quote the formula, then
immediately say "in practice correlated failure dominates, so I'd care more about
independent failure domains — different AZs, staged rollouts, and a config change that
can't hit all three at once — than about replica count."

**Why five nines is usually the wrong answer.** Five nines means 26 seconds of budget per
month. Detection alone — a health check with a 5-second interval and a 3-failure
threshold — burns 15 of those seconds before failover even starts. You cannot have a
human paged, awake, and typing. It forces active-active multi-region, which forces
conflict resolution, which forces you to give up strong consistency on the write path,
which is a product decision, not an infrastructure one. Unless you are running a payment
network or telephony, 99.9% or 99.95% is the honest answer, and saying so is a signal of
judgement rather than a lack of ambition.

### Enterprise production example

**Amazon S3** publishes both halves of this in a way you can quote verbatim. S3 Standard
is *designed for* 99.99% availability, and it achieves that by storing every object
redundantly across a minimum of **three Availability Zones**, which AWS documents as
physically separated by many kilometres but all within 100 km (60 miles) of each other —
close enough for synchronous replication latency, far enough that one flood or power
event does not take all three. The **contractual SLA is 99.9% monthly**, with a 10%
service credit between 99.0% and 99.9%, 25% between 95% and 99%, and 100% below 95%. The
S3 One Zone-Infrequent Access class drops the design target to **99.5% availability**
precisely because it removes the multi-AZ redundancy — same durability engineering, one
failure domain, one nine less availability, and a lower price. That is the availability
composition formula showing up on a pricing page.

### Code

Availability is bought with health checks that tell the truth. The distinction that
matters is liveness (restart me) versus readiness (stop sending me traffic) — conflating
them turns a slow dependency into a restart loop.

```python
from fastapi import FastAPI, Response
import asyncio, time

app = FastAPI()
DEPS = {"postgres": pg_ping, "redis": redis_ping}   # each: async () -> None

@app.get("/livez")
async def livez():
    # Liveness must NOT check dependencies. If Postgres is down, restarting
    # this pod does not help and a restart storm makes the outage worse.
    return {"status": "ok"}

@app.get("/readyz")
async def readyz(response: Response):
    results, deadline = {}, 0.5          # hard budget; LB timeout is 1s
    async def probe(name, fn):
        t0 = time.perf_counter()
        try:
            await asyncio.wait_for(fn(), timeout=deadline)
            ms = round((time.perf_counter() - t0) * 1000)
            results[name] = {"ok": True, "ms": ms}
        except Exception as e:
            results[name] = {"ok": False, "error": type(e).__name__}
    await asyncio.gather(*(probe(n, f) for n, f in DEPS.items()))

    # Redis is degradable (we fall back to the DB); Postgres is not.
    if not results["postgres"]["ok"]:
        response.status_code = 503
    return {"deps": results, "degraded": not results["redis"]["ok"]}
```

The judgement call is in the last four lines: Redis being down marks the instance
*degraded* but still ready, because serving slower is better than serving nothing.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| 99.9% — most internal and B2B systems | Life-safety, payments settlement, telephony | One region, automated failover, on-call human in the loop |
| 99.95% — customer-facing revenue path | Early-stage products with no on-call rotation | Multi-AZ everything, blue/green deploys, ~1.3× infra |
| 99.99% — platform others build on | You have any manual recovery step | No human in the loop; automated failover you actually test |
| 99.999% — you almost never need this | Anything with a single-region write path | ~2× infra, multi-region conflict resolution, weakened consistency |

### Follow-ups they will ask

**Q: Your service is 99.9% and calls three downstreams each at 99.9%. What's your real availability, and how do you fix it?**
A: Serially it's 0.999⁴ ≈ 99.6%, about three hours a month. I'd fix it by changing the
*shape* of the dependency rather than the reliability of each part: make two of the three
calls asynchronous through a queue so a downstream outage becomes a delay instead of an
error, and put a circuit breaker plus a stale-cache fallback on the third. Converting a
hard dependency into a soft one moves it out of the multiplication entirely — that's
worth more than adding a nine to any single component.

**Q: Two AZs at 99.9% each give 99.9999% by the formula. Do you believe it?**
A: No. The formula assumes independence and real failures are correlated — same deploy,
same config push, same control plane, same regional network. Empirically the dominant
outage causes are change-related, not hardware, and a change hits every replica. So I'd
quote the formula as an upper bound and then spend effort on decorrelation: staged
rollouts with automatic rollback, config changes that can't apply to all AZs at once, and
a canary. The AWS us-east-1 event in October 2025 is the canonical demonstration —
DynamoDB had three DNS enactors across three AZs for resiliency, and a race condition
*between* those enactors emptied the DNS record for the whole regional endpoint. The
redundancy itself was the failure mechanism.

**Q: How do you actually measure availability — from where?**
A: From the client's perspective, not the server's. Server-side success rate misses the
cases where the load balancer never routed the request, DNS didn't resolve, or the
connection was reset — and those are exactly the failure modes that produce a full
outage. So I'd measure it as good-events over valid-events at the edge, plus an external
synthetic prober hitting the public endpoint from multiple regions on a 30-second
interval. If server-side says 100% and the prober says 92%, the prober is right.

**Q: What does "availability" mean for an asynchronous system with a queue?**
A: It splits into two SLOs. Availability of the *enqueue* path is the classic uptime
number, because that's the part the caller experiences synchronously. Availability of the
*processing* path is better expressed as a freshness or latency objective — "99% of jobs
complete within 60 seconds of enqueue" — because a worker fleet being down for two
minutes with a durable queue behind it is not an outage, it's backlog. Conflating them
makes you either over-engineer the workers or under-engineer the enqueue API.

### Red flags — do not say this

- ❌ "We'll target five nines." → ✅ "99.9% — 43 minutes a month. Five nines is 26 seconds, which rules out any human in the recovery path."
- ❌ "Adding a replica makes it highly available." → ✅ "Two replicas in separate AZs raise the theoretical ceiling, but correlated failure from a bad deploy dominates, so I'd pair it with staged rollout."
- ❌ "Each service is 99.9%, so the system is 99.9%." → ✅ "Serially they multiply — four of them is 99.6%. I'd make two of the hops async to take them out of the product."

---

## 1.4 Reliability vs availability vs durability

> **One-liner:** Available means you got a response, reliable means the response was
> correct and keeps being correct, and durable means the bytes you acknowledged are still
> there in ten years — they are three different numbers and S3 is the proof.

### Say this in the interview

> These three get used interchangeably and they measure completely different things.
> Availability is "did the request get a response" — it's uptime, measured as a
> percentage of a window. Reliability is "was the response correct, and does the system
> keep behaving correctly over time" — a service returning HTTP 200 with a stale or wrong
> balance is perfectly available and completely unreliable. Durability is about stored
> data surviving failure, and it's a different order of magnitude entirely: S3 is designed
> for eleven nines of durability, 99.999999999%, but its contractual availability SLA is
> only 99.9%. That gap is deliberate and it's the most useful example I know — AWS is
> saying "you may occasionally not be able to reach your object, but we are essentially
> never going to lose it." The classical reliability metrics are MTBF and MTTR, and
> availability is MTBF over MTBF plus MTTR, which tells you something important: you can
> buy availability either by failing less often or by recovering faster, and recovering
> faster is almost always the cheaper lever.

### Mental model

```text
                      the question it answers            typical unit
  ┌──────────────┬──────────────────────────────────┬────────────────────┐
  │ AVAILABILITY │ Can I reach it right now?        │ 99.9% monthly      │
  │ RELIABILITY  │ Is the answer correct, always?   │ <0.1% error rate,  │
  │              │                                  │ MTBF in hours      │
  │ DURABILITY   │ Are my stored bytes still there? │ 99.999999999%/year │
  └──────────────┴──────────────────────────────────┴────────────────────┘

  You can be:  available + unreliable = serving wrong answers, fast
               unavailable + durable  = S3 in an outage: safe, unreachable
               reliable + non-durable = a correct cache; reboot = gone
```

**MTBF and MTTR.**

```text
   ├──── uptime ────┤├─ down ─┤├──── uptime ────┤├─ down ─┤
                MTBF = mean time between failures
                MTTR = mean time to recovery

              MTBF                    e.g. MTBF = 720 h, MTTR = 1 h
   A = ─────────────────                 A = 720/721 = 99.86%
        MTBF + MTTR                   halve MTTR to 30 min -> 99.93%
```

Halving MTTR bought a nine's worth of improvement without touching failure rate. This is
why mature teams invest in fast rollback, feature flags and runbooks rather than in
never failing: **MTTR is under your control; MTBF mostly isn't.**

**Why eleven nines of durability is a real number and eleven nines of availability isn't.**
Durability is engineered with erasure coding and continuous background verification. Split
an object into `k` data shards plus `m` parity shards spread across independent failure
domains; the object survives any `m` losses, and a scrubber continuously re-verifies
checksums and rebuilds lost redundancy *before* the next failure arrives. The probability
of losing enough shards simultaneously, given fast repair, genuinely reaches 10⁻¹¹ per
year. Availability cannot be engineered the same way because it depends on the *entire
request path* being up right now — network, DNS, load balancers, auth, control plane —
and none of that can be repaired in the background before you need it.

### Enterprise production example

**Amazon S3**, from the AWS documentation, is the whole lesson in one row of a table:

| Storage class | Durability (designed) | Availability (designed) | Availability SLA | AZs |
|---|---|---|---|---|
| S3 Standard | 99.999999999% | 99.99% | 99.9% | ≥ 3 |
| S3 Standard-IA | 99.999999999% | 99.9% | 99% | ≥ 3 |
| S3 One Zone-IA | 99.999999999% | 99.5% | 99% | 1 |
| S3 Express One Zone | 99.999999999% | 99.95% | 99.9% | 1 |

Read the columns. **Durability never changes** — every class is eleven nines, because
durability comes from redundancy *within* the storage layer and AWS is not willing to sell
a class that loses data. **Availability changes with the number of AZs**, dropping to 99.5%
for One Zone-IA. And the **SLA is always looser than the design target**, by one nine or
more. When you are asked "what durability do you need", the answer is essentially always
"whatever the managed object store gives me"; the interesting question is what
*availability* you're buying, and that is a price and blast-radius decision.

### Code

Skip — this is a vocabulary and measurement topic; code adds nothing.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Optimise MTTR — rollback, flags, runbooks | You've already got sub-minute recovery | Engineering time on tooling nobody demos |
| Optimise MTBF — redundancy, better hardware | Failures are change-induced (usually) | Money; and it doesn't help with bad deploys |
| Multi-AZ object storage (S3 Standard) | Data is re-derivable (thumbnails, caches) | ~2× the price of One Zone-IA for one extra nine |
| Single-AZ storage (One Zone-IA) | Data is the source of truth | 99.5% availability and total loss if the AZ is destroyed |

### Follow-ups they will ask

**Q: Your database has 99.99% availability and 11 nines of durability. Do you still need backups?**
A: Yes, and the reason is that durability protects against *hardware* loss, not against
*logical* loss. Replication faithfully replicates a `DELETE FROM users` to every replica in
milliseconds. Backups and point-in-time recovery protect against the application, the
migration script and the operator — which are the actual causes of data loss in
practice. So I'd run continuous WAL archiving with a defined RPO, plus periodic snapshots
retained beyond the incident-detection window, and — the part people skip — a scheduled
restore test, because an untested backup is a hypothesis.

**Q: A service returns HTTP 200 with stale data during a partition. Is it available? Is it reliable?**
A: Available yes, reliable no. That is exactly the trade CAP describes: during a partition
you either refuse the request and stay correct, or answer and risk being wrong. Which one
is right is a product question — a "likes" counter should answer with a stale number, a
bank balance shown before a transfer should refuse or clearly mark itself stale. The
engineering obligation is to make staleness *visible*: return the read timestamp, or a
header saying the response came from a degraded path, so the caller can decide.

**Q: How would you increase availability without touching MTBF?**
A: Attack MTTR, because availability is MTBF over MTBF plus MTTR. Concretely: automated
health-check-driven failover so detection isn't human; one-command rollback and
feature-flag kill switches so a bad deploy is reverted in under two minutes; and
pre-provisioned standby capacity so recovery isn't gated on autoscaling cold start.
Cutting MTTR from an hour to five minutes on a monthly failure moves you from about
99.86% to about 99.99% with no change to how often things break.

### Red flags — do not say this

- ❌ "S3 has eleven nines of availability." → ✅ "Eleven nines of *durability*; the availability SLA is 99.9% monthly and the design target is 99.99%."
- ❌ "We replicate, so we don't need backups." → ✅ "Replication protects against hardware loss; backups protect against a bad migration. I need both, plus a tested restore."
- ❌ "It was up the whole time, so we met our SLO." → ✅ "It was reachable, but 4% of responses had stale balances — that's a reliability failure and it should burn error budget."

---

## 1.5 Scalability — vertical, horizontal, the scale cube

> **One-liner:** Scalability is what happens to cost and latency when load multiplies, and
> the honest first answer at mid-scale is usually "buy a bigger box", because horizontal
> scaling is a distributed-systems bill you pay forever.

### Say this in the interview

> Scaling vertically means a bigger machine and scaling horizontally means more machines,
> and the industry reflex is to jump straight to horizontal, which is often wrong.
> Vertical is genuinely the right call when the workload is a single stateful thing that's
> expensive to split — most commonly the primary database. A managed PostgreSQL instance
> today goes to well over a hundred vCPUs and a terabyte of RAM, and a hundred-thousand
> writes-per-second workload that fits on one primary is enormously simpler than the same
> workload sharded, because you keep transactions, joins and foreign keys. The moment you
> shard you give all three up and inherit routing, rebalancing, cross-shard queries and a
> much harder failover story. So my rule is: scale the stateless tier horizontally from
> day one because it's free to do — the servers hold no state, so I just add instances
> behind a load balancer — and scale the stateful tier vertically for as long as I can
> afford to, using read replicas and caching to buy time before I shard. The thing to
> watch for is that vertical scaling has a hard ceiling and a discontinuity: the last
> instance size is often two to three times the price of the one below it for the same
> incremental capacity, and above it there is nothing.

### Mental model

```text
   VERTICAL (scale up)                HORIZONTAL (scale out)
   ┌───────────────────┐              ┌────┐ ┌────┐ ┌────┐ ┌────┐
   │  4 vCPU / 16 GB   │              │ n1 │ │ n2 │ │ n3 │ │ n4 │
   │        ▼          │              └──┬─┘ └──┬─┘ └──┬─┘ └──┬─┘
   │ 128 vCPU / 864 GB │                 └──────┴───┬──┴──────┘
   └───────────────────┘                        Load balancer
   + no code change                   + no ceiling
   + keeps transactions/joins         + failure of one node is survivable
   - hard ceiling, then a cliff       - state must move out of the node
   - one machine = one failure domain - coordination, consistency, ops cost
   - reboot = downtime                - you now own a distributed system
```

**The scale cube** (from *The Art of Scalability*) gives you three independent axes, and
naming them shows you understand that "scaling" isn't one thing:

```text
        Z: shard by data
        (users A-M / N-Z)
             ▲
             │
             │
             └──────────────► X: clone the whole thing
            ╱                    (identical stateless replicas)
           ╱
          ▼
     Y: split by function
     (auth svc / order svc / search svc)
```

- **X — cloning.** Add identical instances behind a load balancer. Cheapest, requires
  statelessness, does nothing for a database write bottleneck.
- **Y — functional decomposition.** Split by concern into services. Lets you scale the
  expensive part independently, and costs you network hops and availability
  multiplication (see 1.3).
- **Z — data partitioning.** Shard by a key. The only axis that scales writes. Costs you
  cross-shard queries, rebalancing, and hot-shard risk.

Do them in that order. Most teams that "need microservices" needed X and a cache.

**Load patterns** determine which scaling actually helps:

| Pattern | Shape | What it demands |
|---|---|---|
| Steady | flat, ±20% | Right-size and reserve capacity; cheapest per request |
| Diurnal | 3–5× day/night | Autoscaling with a 5–10 min warm-up budget |
| Spiky | 10–100× in seconds | Pre-warmed capacity + queue + load shedding; autoscaling is too slow |
| Seasonal | 5–20× for days | Pre-scale on a schedule; run load tests at forecast peak |

The interview-relevant insight: **autoscaling does not solve spikes.** A container takes
30–90 seconds to be healthy and in rotation; a traffic spike arrives in two. For spikes you
need headroom, a queue to absorb the burst, and a shedding policy — autoscaling is for the
diurnal and seasonal curves.

### Enterprise production example

**Shopify's** Black Friday / Cyber Monday 2025 is the best public dataset on seasonal
scaling. Over the weekend the platform served **2.2 trillion edge requests** and 90 PB of
data, with the edge averaging **312 million requests/minute across BFCM and peaking at 489
million requests/minute** — about 8.15 million requests per second at peak. Their global
Kubernetes fleet ran **over 3.18 million CPU cores** at peak, and the MySQL 8 database
fleet sustained **53.8 million queries/second and 4.28 billion row operations/second**.

The scaling lesson is in how they got there, published on Shopify's engineering blog: from
April through October they ran **five major scale tests** against forecast traffic. By the
fourth test they hit 146 million requests/minute and over 80,000 checkouts/minute; the
final test targeted their p99 forecast of **200 million requests/minute**. Note that they
load-tested *above* their expected peak and months in advance. That is what "seasonal load
pattern" actually costs an organisation — not clever autoscaling, but nine months of
rehearsal. Also note the database story: 53.8 million QPS is not one big MySQL, it is a
sharded fleet, which is Z-axis scaling at the only scale where Z-axis is unavoidable.

### Code

The most common scalability bug at mid-scale is not the database — it's that the app tier
opens more connections than the database can serve. Little's Law (1.6) sizes the pool.

```javascript
// Node.js + node-postgres. Pool size is a DATABASE-side budget, not an
// app-side one.
//
//   Postgres max_connections = 200
//   Reserved for admin/replication/migrations = 20
//   Usable = 180. With 12 app pods -> 15 connections per pod. NOT 15 per pod
//   "because that feels right" - because 12 x 15 = 180 is the whole budget.
import pg from 'pg';

const pool = new pg.Pool({
  host: process.env.PGHOST,
  max: Number(process.env.PG_POOL_MAX ?? 15),
  min: 2,
  idleTimeoutMillis: 30_000,
  connectionTimeoutMillis: 2_000,   // fail fast; queueing here is invisible
  statement_timeout: 5_000,         // a runaway query must not hold a slot
  query_timeout: 5_000,
  application_name: process.env.SERVICE_NAME,
});

// Surface pool saturation as a metric. If waitingCount > 0 sustained, you are
// queueing on connections and adding app pods will make it strictly worse.
setInterval(() => {
  metrics.gauge('pg.pool.total', pool.totalCount);
  metrics.gauge('pg.pool.idle', pool.idleCount);
  metrics.gauge('pg.pool.waiting', pool.waitingCount);
}, 10_000);

pool.on('error', (err) => logger.error({ err }, 'idle client error'));
```

Beyond roughly 200–400 connections, put PgBouncer in transaction-pooling mode between the
app and Postgres and let the app pools be generous against PgBouncer instead.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Vertical: single stateful primary, workload fits | You're near the largest instance size | Hard ceiling; a reboot is downtime; price cliff at the top |
| Horizontal X (clone): any stateless tier | Service holds in-memory session state | Requires externalising state to Redis/DB |
| Horizontal Y (split by function): a tier has a genuinely different scaling profile | Team is smaller than ~15 engineers | Network hops, availability multiplies down, distributed debugging |
| Horizontal Z (shard): write throughput exceeds one primary | Reads are the bottleneck (use replicas + cache) | Lose cross-shard joins and transactions; rebalancing is a project |

### Follow-ups they will ask

**Q: When would you deliberately choose vertical scaling over horizontal in 2026?**
A: For the primary write node of a relational database, and for anything with a large
in-memory working set that's expensive to partition — a single-node Redis holding a 200 GB
cache, or an analytics box doing large joins. The reasoning is that vertical scaling
preserves the programming model. I keep multi-row transactions, foreign keys and joins,
which means the application stays simple. I'd go vertical until I'm within about 40% of
the largest available instance, then start the sharding project, because sharding takes
months and I don't want to start it under duress.

**Q: You added 10 more app servers and throughput didn't improve. What happened?**
A: I hit a shared bottleneck downstream, and the most likely candidate is database
connections. Ten more pods times fifteen connections each is 150 more connections against
a fixed `max_connections`, so requests now queue *inside* Postgres instead of inside the
app — same throughput, worse latency, and connection errors. The diagnostic is the pool's
`waiting` count and the database's active-versus-idle-in-transaction breakdown. Other
candidates in order of likelihood: a hot Redis key, a downstream API rate limit, and a
single-partition Kafka topic capping consumer parallelism.

**Q: What breaks first when traffic goes 10×?**
A: Almost always the stateful tier, and specifically the write path, because the stateless
tier scales by adding pods and the database does not. Concretely I'd expect the order to
be: connection pool exhaustion, then a hot partition or hot cache key, then disk IOPS on
the primary, then replication lag pushing read replicas out of the acceptable staleness
window. I'd want a load test that finds which of those it actually is rather than
guessing, because the fix for each is completely different.

**Q: Is autoscaling a scalability strategy?**
A: It's a cost strategy that happens to help with slow-moving load. Autoscaling matches
capacity to a diurnal or seasonal curve so you don't pay for peak all day. It does not
help with spikes, because a new pod takes 30 to 90 seconds to pass readiness and join
rotation, while a spike arrives in two seconds. For spikes the answer is headroom — run at
50–60% utilisation — plus a queue to absorb the burst and a shedding rule so the overflow
gets a fast 429 instead of a slow timeout.

### Red flags — do not say this

- ❌ "We'll just scale horizontally." → ✅ "Stateless tier scales horizontally from day one; the primary I'd scale vertically plus read replicas until write throughput actually forces sharding."
- ❌ "Autoscaling handles the spike." → ✅ "Autoscaling handles the daily curve. For the spike I need pre-warmed headroom, a queue, and a shed policy — pods take a minute to come up."
- ❌ "Microservices are more scalable." → ✅ "Functional split lets me scale the expensive tier independently, but it multiplies availability down and adds network hops. I'd only do it when one tier's scaling profile genuinely diverges."

---

## 1.6 Latency vs throughput, Little's Law, percentiles

> **One-liner:** Latency is how long one request takes, throughput is how many finish per
> second, Little's Law ties them together through concurrency, and the number you report
> must be a percentile because averages are a lie told by the fast requests.

### Say this in the interview

> Latency is time per operation and throughput is operations per unit time, and they're
> linked by Little's Law: the number of requests in flight equals arrival rate times
> average time in the system. That's the most useful formula in capacity planning. If I'm
> taking two thousand requests a second and each one spends fifty milliseconds in the
> system, I have a hundred requests in flight at any moment — so I need at least a hundred
> units of concurrency, and if each request holds a database connection for twenty of
> those fifty milliseconds, I need forty database connections, not four hundred. People
> size connection pools by instinct and then wonder why the database is queueing. The
> second thing is that latency and throughput trade off through queueing: as utilisation
> climbs toward one hundred percent, wait time goes as one over one minus utilisation, so
> at seventy percent load you've roughly tripled your wait and at ninety-five percent
> you've multiplied it by twenty. That's why I run systems at sixty to seventy percent and
> not at ninety-five. And I always quote p99, never the mean, because in a fan-out system
> the tail becomes the median — Dean and Barroso showed that if a backend has a one
> percent chance of being slow and you fan out to a hundred of them, sixty-three percent
> of user requests hit at least one slow backend.

### Mental model

**Little's Law: `L = λ × W`.**

```text
   L = concurrency  (requests in flight)
   λ = arrival rate (requests / second)
   W = latency      (seconds in the system, end to end)

        λ = 2000 req/s            L = 2000 x 0.050 = 100 in flight
   ────────────────────►  ┌──────────────┐  ────────────────────►
                          │   SYSTEM     │
                          │  W = 50 ms   │
                          └──────────────┘

   Same law, applied per RESOURCE, is how you size pools:
     DB time per request = 20 ms  ->  L_db = 2000 x 0.020 =  40 connections
     LLM call per request = 900 ms ->  L_llm = 20 x 0.900 =  18 in flight
```

Rearranged, it gives you the throughput ceiling of any bounded resource:

```text
   max throughput = pool size / service time
   e.g. 20 connections / 20 ms  =  1,000 queries/s, hard ceiling.
        Everything above that queues, and queue time is pure added latency.
```

**Why they trade off — the queueing curve.** For a single-server queue, the mean wait
scales as `1 / (1 − ρ)` where ρ is utilisation:

```text
   wait multiple
      20x │                                            ●
          │                                       ●
      10x │                                 ●
          │                        ●
       5x │            ●
       2x │   ●
       1x │●
          └────┬────┬────┬────┬────┬────┬────┬────┬───► utilisation
              0.1  0.3  0.5  0.7  0.8  0.9  0.95 0.99

   rho=0.50 -> 2x    rho=0.80 ->  5x    rho=0.95 -> 20x    rho=0.99 -> 100x
```

You cannot have both maximum throughput and low latency on the same hardware. Pushing
utilisation from 70% to 95% buys you 35% more throughput and costs you 4× the wait.

**The latency numbers.** These are Jeff Dean and Sanjay Ghemawat's 2025 update to the
famous 2007 table, published in Google's *Performance Tips of the Week* (abseil.io):

| Operation | Latency | 2007 value |
|---|---|---|
| L1 cache reference | 0.5 ns | 0.5 ns |
| L2 cache reference | 3 ns | 7 ns |
| Branch mispredict | 5 ns | 5 ns |
| Mutex lock/unlock (uncontended) | 15 ns | 100 ns |
| Main memory reference | 50 ns | 100 ns |
| Compress 1 KB with Snappy | 1 µs | 10 µs |
| Read 4 KB from SSD | 20 µs | — |
| **Round trip within same datacenter** | **50 µs** | 500 µs |
| Read 1 MB sequentially from memory | 64 µs | 250 µs |
| Read 1 MB over 100 Gbps network | 100 µs | 10 ms (1 Gbps) |
| Read 1 MB from SSD | 1 ms | — |
| Disk seek (spinning) | 5 ms | 10 ms |
| Read 1 MB sequentially from disk | 10 ms | 30 ms |
| **Packet CA → Netherlands → CA** | **150 ms** | 150 ms |

Two things to notice, and both are worth saying out loud. First, **the cross-continent
round trip did not improve at all** — 150 ms in 2007, 150 ms in 2025 — because it is set by
the speed of light in fibre, roughly 200,000 km/s, and no engineering fixes that. Every
other number improved between 2× and 100×. That is why multi-region synchronous writes are
permanently expensive and why you place data near users rather than trying to make the
network faster. Second, **reading 1 MB over a modern datacenter network (100 µs) is now
100× faster than reading it off a spinning disk (10 ms)**, which is the whole justification
for disaggregated storage.

Numbers you should add for your own stack:

| Operation | Rough cost |
|---|---|
| Redis GET, same VPC | 0.2–0.5 ms p99 |
| PostgreSQL indexed point read, warm | 0.5–2 ms |
| PostgreSQL commit with `synchronous_commit=on` | 2–10 ms |
| Cross-AZ round trip, same region | ~0.5–1 ms |
| Cross-region round trip (us-east ↔ eu-west) | ~80–100 ms |
| Kafka produce with `acks=all` | 5–20 ms |
| LLM time-to-first-token (hosted, mid-size model) | 300–900 ms |
| LLM full generation, 500 output tokens | 3–15 s |

**Percentiles, and why the average lies.** Take 100 requests: 99 take 10 ms, one takes
1,000 ms. Mean = 19.9 ms. p50 = 10 ms. p99 = 1,000 ms. The mean describes nobody: it is
twice as slow as the typical request and fifty times faster than the worst one. Report:

- **p50** — the typical experience. Use it for capacity, not for SLOs.
- **p95 / p99** — the SLO number. This is what "the site feels slow" means.
- **p99.9** — where you find GC pauses, cold caches, lock convoys, noisy neighbours.
- **max** — where you find bugs. Always look, never alert on it.

One more trap: **you cannot average percentiles.** The p99 of two services is not the mean
of their p99s. Aggregate with histograms (Prometheus `histogram_quantile`, or t-digest),
never by averaging pre-computed quantiles from each pod.

**Tail latency amplification.** This is the highest-value idea in the section.

```text
   Request fans out to N backends; the user waits for the SLOWEST one.
   P(at least one slow) = 1 - (1 - p)^N          p = per-backend slow prob.

     N=1   ->  1.0%      N=50  -> 39.5%
     N=10  ->  9.6%      N=100 -> 63.4%      (p = 1%)
     N=20  -> 18.2%      N=200 -> 86.6%

   Consequence: the backend's p99 becomes the USER's p50 at N=100.
```

Dean and Barroso's *The Tail at Scale* (CACM, 2013) states it directly: a server with a
10 ms typical response and a 1-second p99, fanned out to 100 servers, means **63% of user
requests take more than one second**. Even at a 1-in-10,000 slow rate, a 2,000-way fan-out
leaves almost one in five user requests over a second. Their measurements from a real
Google service: p99 for a *single* leaf request measured at the root was **10 ms**, but p99
for *all* leaf requests to finish was **140 ms** — and p99 for 95% of requests to finish was
70 ms, meaning waiting for the slowest 5% accounted for half the total p99.

### Enterprise production example

**Google's** fix for this, from the same paper, is the one to quote. **Hedged requests**:
send the request to one replica, and if it hasn't returned by roughly the 95th-percentile
expected latency, send a duplicate to a second replica and take whichever answers first.
Because slowness is usually caused by transient interference on a specific machine — GC, a
noisy neighbour, a background compaction — rather than by the request itself, the second
copy usually returns fast.

The measured result: in a Google benchmark reading 1,000 keys from a BigTable table spread
across 100 servers, **sending a hedging request after a 10 ms delay reduced the
99.9th-percentile latency from 1,800 ms to 74 ms while sending just 2% more requests.** A
24× tail improvement for 2% extra load. They also describe **tied requests** — enqueue on
two servers, each tagged with the other's identity, and the one that starts first cancels
its twin — which in Google's distributed file system cut median latency by 16% and p99.9
by nearly 40%.

And **micro-partitioning**: rather than one partition per machine, Google's systems create
many more partitions than machines — BigTable machines manage between **20 and 1,000
tablets** each — so load can be shed in ~5% increments and failure recovery spreads across
many machines instead of one.

### Code

Little's Law turned into a concurrency limiter. This is the pattern for an LLM gateway,
where the downstream provider has a hard concurrency quota and unbounded queueing turns a
slow provider into an out-of-memory crash.

```python
import asyncio, time
from contextlib import asynccontextmanager
from fastapi import HTTPException

# Little's Law: with W = 0.9s per LLM call and a target of 20 req/s,
# L = 20 * 0.9 = 18 concurrent calls. We permit 24 for headroom and
# REJECT beyond that rather than queueing - an unbounded queue converts
# a latency problem into a memory problem and then into an outage.
MAX_INFLIGHT = 24
MAX_QUEUE_WAIT = 0.25          # shed fast; the caller can retry with backoff

_sem = asyncio.Semaphore(MAX_INFLIGHT)
_inflight = 0

@asynccontextmanager
async def llm_slot():
    global _inflight
    try:
        await asyncio.wait_for(_sem.acquire(), timeout=MAX_QUEUE_WAIT)
    except asyncio.TimeoutError:
        metrics.increment("llm.shed")
        raise HTTPException(status_code=429, headers={"Retry-After": "1"})
    _inflight += 1
    metrics.gauge("llm.inflight", _inflight)
    t0 = time.perf_counter()
    try:
        yield
    finally:
        _inflight -= 1
        _sem.release()
        metrics.histogram("llm.latency_ms", (time.perf_counter() - t0) * 1000)

async def complete(prompt: str) -> str:
    async with llm_slot():
        # Hedge: if the primary hasn't produced a first token by p95, race a
        # second provider. Costs ~5% extra spend, cuts the tail dramatically.
        primary = asyncio.create_task(provider_a(prompt))
        done, _ = await asyncio.wait({primary}, timeout=1.2)
        if done:
            return primary.result()
        hedge = asyncio.create_task(provider_b(prompt))
        done, pending = await asyncio.wait({primary, hedge},
                                           return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()
        return done.pop().result()
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Little's Law to size pools/workers | You have real measurements — use those | Nothing; it's arithmetic |
| Run at 60–70% utilisation | Cost is the binding constraint and latency isn't | ~40% more machines than a 95%-utilised fleet |
| Hedged requests to cut p99 | The operation is a non-idempotent write | 2–5% extra load if hedged at p95; much more if hedged early |
| Report p99 | Comparing two systems' throughput | p99 is noisy at low request volume; needs enough samples |

### Follow-ups they will ask

**Q: Your p50 is 20 ms and your p99 is 900 ms. Where do you look first?**
A: A 45× spread points at a bimodal cause, not at general slowness, so I'd look for
something that happens to a small fraction of requests. In order: cache misses falling
through to a cold path, garbage collection or runtime pauses, connection-pool queueing
under burst, and a specific slow query on an unindexed column that only some inputs hit.
A distributed trace filtered to the slow bucket answers this in minutes — I'd compare the
span breakdown of a p99 trace against a p50 trace, and the extra time will be sitting in
one span.

**Q: You have 4 servers at 80% CPU. You add 4 more. What happens to p99?**
A: Utilisation halves to 40%, and by the queueing relation the wait component drops from
roughly 5× service time to roughly 1.7×, so p99 improves substantially — often more than
people expect, because at 80% you were already on the steep part of the curve. But this
only holds if CPU is genuinely the bottleneck. If the real constraint is the database,
adding servers adds connections and makes p99 *worse*. So the honest answer is "it should
improve a lot, and I'd verify CPU is the bottleneck first by checking whether latency
correlates with CPU or with database wait time."

**Q: A request fans out to 50 microservices. Each has a p99 of 30 ms. What's the user-facing p99?**
A: Much worse than 30 ms, and the framing matters. If the calls are parallel, the user
waits for the maximum of 50 draws, so the probability of hitting at least one p99 tail is
`1 − 0.99⁵⁰ ≈ 39%` — the backend p99 becomes something like the user's p60. If the calls
are serial, the latencies *add* and you're looking at 50 × p50 as a floor. Either way the
fix is architectural, not per-service tuning: reduce fan-out by batching, hedge the calls
that are idempotent, and set aggressive per-call timeouts with partial-result degradation
so one slow leaf can't hold the whole response.

**Q: Can you increase throughput and latency at the same time?**
A: Yes, but only by removing work rather than by tuning. Caching does both — a cache hit is
faster *and* frees capacity downstream. Batching increases throughput at the cost of
latency, so it's a trade, not a win. Adding hardware improves latency only by lowering
utilisation. The general rule is that pure tuning moves you along the latency-throughput
curve; only eliminating work moves the curve.

**Q: Why can't you average p99s across pods?**
A: Because a percentile is a property of a distribution, not a value you can arithmetically
combine — the p99 of the union is not the mean of the p99s, and it can be far higher if one
pod is pathological. The correct approach is to export latency as a histogram with shared
bucket boundaries, sum the bucket counters across pods, and compute the quantile from the
merged histogram. That's exactly what `histogram_quantile(0.99, sum(rate(bucket[5m])) by (le))`
does in Prometheus, and getting this wrong is one of the more common observability bugs.

### Red flags — do not say this

- ❌ "Average latency is 50 ms." → ✅ "p50 is 20 ms, p99 is 180 ms — the average hides the tail and the tail is what users complain about."
- ❌ "We'll run the fleet at 90% CPU for efficiency." → ✅ "60–70%, because wait time goes as 1/(1−ρ) and at 90% I've paid 10× in queueing for 20% more throughput."
- ❌ "Each service is fast, so the system is fast." → ✅ "With 50-way fan-out, a 1% per-service tail means 39% of user requests hit at least one slow backend. I'd hedge the idempotent calls and cap fan-out."
- ❌ "We'll optimise the database." → ✅ "The trace says 900 ms of the 1.1 s is the LLM call. Optimising Postgres from 4 ms to 2 ms is 0.2% — I'd cache prompts instead."

---

## 1.7 Consistency and durability as requirements

> **One-liner:** Consistency is a product requirement disguised as a database setting —
> decide per read path how stale an answer may be, and only then pick the storage.

### Say this in the interview

> Consistency shows up in requirements as "how stale can this read be", and I like to
> answer it per endpoint rather than per system, because the answer is almost never the
> same everywhere. In a typical product I'd say: the user's own profile after they edit it
> needs read-your-own-writes, which I get by routing that user's reads to the primary for
> a few seconds after a write, or by writing through their cache entry. A public feed can
> be eventually consistent with a lag budget — I'd write down "under one second p99
> replication lag" and alert on it, because "eventual" with no bound is not a
> requirement. And anything touching money or inventory needs a transaction on a single
> primary, because a double-spend is not a latency problem I can apologise for. On
> durability the question is simply whether an acknowledged write may be lost, and for the
> transactional path the answer is no, so RPO is zero, which means synchronous commit and
> synchronous replication to at least one standby — and I should say that costs me a
> couple of milliseconds on every write. The full treatment of replication, isolation
> levels and CAP is a topic on its own.

### Mental model

```text
  Per-READ-PATH consistency budget (write it in the requirements table)

  GET /me                      -> read-your-own-writes   (route to primary 5s)
  GET /feed                    -> eventual, lag < 1s p99 (read replica)
  GET /orders/{id}             -> strong                 (primary, in txn)
  GET /products/{id}/stock     -> strong on decrement,   (txn + row lock)
                                  eventual on display    (cache, 10s TTL)
  GET /analytics/daily         -> hours stale is fine    (warehouse)
```

Durability is the same exercise on the write path: for each write, state the **RPO** —
the amount of data you may lose. RPO = 0 means synchronous commit plus synchronous
replication and costs a network round trip per commit. RPO = 5 minutes means asynchronous
replication or periodic snapshots and is dramatically cheaper.

Full treatment in [Module 06 — Consistency, Replication & CAP](./06_Consistency_And_CAP.md);
durability mechanics in [Module 04 — Databases](./04_Databases.md).

### Follow-ups they will ask

**Q: The interviewer says "make it strongly consistent everywhere." What do you say?**
A: I'd push back with the cost, not with a refusal. Strong consistency on every read means
every read goes to the primary — I lose read replicas as a scaling tool, and my read
capacity is now capped by one machine. If the read:write ratio is 100:1, that's throwing
away the cheapest scaling lever I have. I'd propose strong consistency on the paths where
a stale read causes a correctness bug — money, inventory, permissions — and a bounded
staleness budget everywhere else, and I'd instrument replication lag so the budget is
enforced rather than assumed.

### Red flags — do not say this

- ❌ "We'll use eventual consistency." → ✅ "Eventual with a bound — under one second p99 replication lag, alerted, and read-your-own-writes on the user's own resources."
- ❌ "NoSQL is eventually consistent and SQL is strong." → ✅ "Both are configurable. Postgres with an async replica gives eventual reads; DynamoDB offers strongly consistent reads at double the read-capacity cost."

---

## 1.8 Cost as a first-class NFR

> **One-liner:** Every architecture decision has a price per request, and the three that
> reliably blow up a cloud bill are egress bandwidth, cross-AZ chatter, and NAT Gateway —
> none of which appear on an architecture diagram.

### Say this in the interview

> I treat cost as a non-functional requirement with a number, the same as latency, and the
> unit I use is cost per request or cost per active user per month, because that's the
> number that has to stay flat as we grow. The specific traps I watch for are all in
> networking rather than compute. Egress to the internet is around nine cents a gigabyte
> on AWS and twelve cents on GCP's premium tier, while ingress is free — so any design
> that ships large payloads out of the cloud is a bandwidth business, not a compute
> business. Cross-AZ traffic is a penny a gigabyte in each direction, which sounds
> trivial until you realise a chatty microservice mesh spread across three AZs pays it on
> every internal hop, and I've seen that line item exceed the compute it connects. And NAT
> Gateway is the classic: four and a half cents an hour per AZ just to exist, plus four and
> a half cents per gigabyte processed — so a private-subnet service pulling five terabytes
> a month from S3 pays over two hundred dollars in NAT processing for traffic that never
> leaves AWS, when a VPC gateway endpoint would have made it free. For an LLM product the
> dominant cost moves to tokens, and there the levers are prompt caching, a smaller model
> for the easy 80% of requests, and capping max output tokens.

### Mental model

```text
  Where the money actually goes in a typical mid-scale cloud app

  ┌──────────────────────────────────────────────────────────────┐
  │ Compute (EC2/GKE/Cloud Run)  ████████████████████  ~40%      │
  │ Managed DB (RDS/Cloud SQL)   ██████████████        ~25%      │
  │ NETWORK (egress+NAT+xAZ)     ██████████            ~20%  <-- │
  │ Storage (S3/GCS + EBS/PD)    ██████                ~10%      │
  │ Observability (logs/metrics) ███                    ~5%      │
  └──────────────────────────────────────────────────────────────┘
   The 20% nobody drew on the architecture diagram is where the
   surprises live. Logs can also silently become the top line item.
```

**The price list to have memorised** (AWS list price, 2026; GCP is comparable):

| Item | Price | Note |
|---|---|---|
| Ingress from internet | $0 | Free on all three clouds |
| Egress to internet | $0.09/GB first 10 TB | Tiers down to ~$0.05/GB above 150 TB |
| GCP egress, Premium tier | $0.12/GB first TB | Standard tier ~$0.085/GB |
| Cross-AZ, same region | $0.01/GB **each direction** | $0.02/GB round trip; billed both sides |
| Cross-region | ~$0.02/GB | Billed on the source region |
| NAT Gateway | $0.045/hour/AZ **+ $0.045/GB** | The dual charge is the trap |
| VPC Gateway Endpoint (S3, DynamoDB) | $0 | Free; removes NAT processing entirely |
| CloudFront egress | ~$0.085/GB N. America | Cheaper than origin egress at scale |

**Cost per request thinking.** Reduce everything to one number:

```text
   monthly cost / monthly requests = cost per request

   Example: $12,000/month, 400M requests  ->  $0.00003/request  (0.003 cents)
   Now sanity-check it against revenue per request. If a request is worth
   $0.0001, you have a 3:1 margin and a fragile business.
```

Then decompose it. The useful move in an interview is to notice which term dominates:

```text
   cost/request = compute + db + cache + network + storage_amortised + LLM

   Classic CRUD API:   compute + db dominate. Optimise: cache, right-size.
   Media/download app: network dominates.     Optimise: CDN, smaller assets.
   RAG/LLM app:        tokens dominate 10x.   Optimise: prompt cache, small
                                              model routing, output caps.
```

**The five classic traps**, in the order they bite:

1. **NAT Gateway for S3/DynamoDB traffic.** Free to fix with a gateway endpoint.
2. **Cross-AZ chatter.** A service mesh with no zone-affinity routing pays $0.02/GB round
   trip on every internal call. Enable topology-aware routing.
3. **Log volume.** Ingesting every request body at $0.50–$3.00/GB into a hosted log
   platform routinely outgrows the compute bill. Sample debug logs; keep errors at 100%.
4. **Idle non-production.** Dev and staging running 24/7 is ~4× the cost of running them
   during working hours. Schedule them down.
5. **Over-provisioned managed databases.** The default reflex is to size for peak; a read
   replica plus a cache is usually cheaper than the next instance size up.

### Enterprise production example

The clearest market signal that egress is the dominant hidden cost is **Cloudflare R2**,
an S3-compatible object store launched explicitly with **zero egress fees**. Cloudflare's
positioning is that egress charges are a lock-in mechanism rather than a cost-recovery
one, and the product exists because the price gap is large enough to be a business. Put
numbers on it: serving 100 TB/month from S3 to the internet at roughly $0.085/GB is about
**$8,500/month in bandwidth alone**, before storage or requests. The same 100 TB from R2 is
$0. That single line item is why media-heavy products either run a CDN with a very high
cache-hit ratio, negotiate committed-use bandwidth discounts, or move the object store.

Compare it with **Shopify's** BFCM 2025 numbers to see the same force from the other side:
their CDN served **183 million requests/minute at a 97.8% cache-hit ratio**. That 97.8% is
not a performance statistic, it is a cost statistic — the 2.2% that missed is what they
paid origin egress on. Moving a cache-hit ratio from 90% to 97.8% cuts origin bandwidth by
more than 75%.

### Code

Cost per request is only manageable if it is measured per request. Attach it to the trace.

```python
# FastAPI middleware that stamps an estimated cost on every LLM-backed request
# and emits it as a metric dimensioned by tenant and model. Without this you
# discover your unit economics from the monthly invoice.
PRICING = {                       # USD per 1M tokens; keep in config, not code
    "gpt-4o-mini":  {"in": 0.15,  "out": 0.60},
    "gpt-4o":       {"in": 2.50,  "out": 10.00},
}

def estimate_cost(model: str, tokens_in: int, tokens_out: int) -> float:
    p = PRICING[model]
    return (tokens_in * p["in"] + tokens_out * p["out"]) / 1_000_000

@app.middleware("http")
async def cost_accounting(request, call_next):
    request.state.cost = 0.0
    response = await call_next(request)
    tenant = request.headers.get("x-tenant-id", "unknown")
    if request.state.cost:
        metrics.histogram("request.cost_usd", request.state.cost,
                          tags={"tenant": tenant, "route": request.url.path})
        # Per-tenant monthly budget enforcement lives here, not in the invoice.
        await budget.consume(tenant, request.state.cost)
        response.headers["X-Estimated-Cost-USD"] = f"{request.state.cost:.6f}"
    return response
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Quote cost/request in the NFR table | You have no idea of the pricing — don't bluff | Nothing; it's the cheapest way to sound senior |
| CDN in front of any static or media path | Content is fully personalised and uncacheable | CDN fees, cache-invalidation complexity |
| VPC gateway endpoints for S3/DynamoDB | Never — this one is free and strictly better | Ten minutes of Terraform |
| Reserved/committed-use discounts | Load is unpredictable or you're pre-product-market-fit | 1–3 year lock-in for 30–60% off |
| Smaller model for the easy 80% of LLM traffic | Quality regression is unacceptable and unmeasured | An eval harness you must actually build |

### Follow-ups they will ask

**Q: Your bill doubled and traffic didn't. Where do you look?**
A: Network and logs before compute, because those are the two that grow without a
corresponding traffic signal. Concretely: a new service deployed across AZs without
zone-affinity routing now pays cross-AZ on every call; a debug log level left on in
production; a NAT Gateway newly in the path of S3 traffic; or a cache-hit ratio that
dropped, which converts cheap edge traffic into expensive origin egress. I'd pull
cost-allocation-tagged data by service and by usage type — the "DataTransfer-Regional-Bytes"
and "NatGateway-Bytes" line items specifically — rather than guessing.

**Q: How do you cut LLM costs by 50% without hurting quality?**
A: Three levers in order of yield. First, cache: exact-match on the prompt hash for
repeated queries, and provider-side prompt caching for the long static system prompt, which
often cuts input token cost by 50–90% on RAG workloads where the retrieved context repeats.
Second, route by difficulty — classify the request and send the easy majority to a model
that's 10–20× cheaper, keeping the expensive model for the hard tail; this needs an eval
set so the regression is measured, not assumed. Third, cap `max_tokens` and trim retrieved
context aggressively, since RAG prompts are usually padded with chunks that never
influence the answer. See [Module 14 — LLM System Design](./14_AI_LLM_System_Design.md).

**Q: Is it ever right to spend more to make the system simpler?**
A: Frequently, and I'd say so explicitly. A managed database at 2× the cost of self-hosting
is cheaper than an engineer's week per quarter plus the outage risk. A single larger
instance is cheaper than the six months of engineering that sharding costs. The number I'd
compare against is fully-loaded engineer-hours: if a $2,000/month decision saves a
half-time engineer, it pays for itself several times over.

### Red flags — do not say this

- ❌ "Cost isn't a concern for this design." → ✅ "I'd target under a tenth of a cent per request; the dominant term here is egress, so the CDN cache-hit ratio is the lever."
- ❌ "We'll use S3 and serve directly from it." → ✅ "S3 behind CloudFront — direct S3 egress at $0.09/GB would be $8,500/month at 100 TB, and the CDN both lowers that and cuts latency."
- ❌ "Storage is cheap." → ✅ "Storage is cheap; egress and IOPS are not. 12 PB/year at $0.023/GB is about $280k/month before anyone reads a byte."

---

## 1.9 Back-of-the-envelope estimation

> **One-liner:** Convert daily active users into peak QPS, storage per year and bytes per
> second in about ninety seconds of arithmetic, out loud, so that every later design
> decision has a number behind it.

### Say this in the interview

> Let me size this before I design it, because the answer changes completely between a
> hundred requests a second and a hundred thousand. My method is always the same. I start
> from daily active users and an actions-per-user-per-day number, multiply to get requests
> per day, and divide by a hundred thousand — there are eighty-six thousand four hundred
> seconds in a day and I round it to ten to the fifth because it makes the mental
> arithmetic instant and it's within fifteen percent. That gives average QPS. Then I
> multiply by two to three for peak, because traffic is never flat — a consumer app peaks
> at two to three times its daily average in the evening. For storage I take writes per
> day times bytes per write, add about thirty percent for indexes, multiply by the
> replication factor, and then by three hundred sixty-five and the retention period. For
> bandwidth I take QPS times average payload size in each direction. And for cache I apply
> the eighty-twenty rule — twenty percent of the keys serve eighty percent of the reads —
> so I size memory for twenty percent of the daily working set. The numbers don't need to
> be right, they need to be defensible and within an order of magnitude, because their job
> is to tell me whether I need one Postgres or a sharded fleet.

### The constants you must have memorised

**Powers of two → decimal.** This is the whole trick for storage math.

| Power | Exact | Call it | Unit |
|---|---|---|---|
| 2¹⁰ | 1,024 | 1 thousand | 1 KB |
| 2²⁰ | 1,048,576 | 1 million | 1 MB |
| 2³⁰ | 1,073,741,824 | 1 billion | 1 GB |
| 2⁴⁰ | ~1.1 × 10¹² | 1 trillion | 1 TB |
| 2⁵⁰ | ~1.1 × 10¹⁵ | 1 quadrillion | 1 PB |

**Time.**

| Quantity | Exact | Use this |
|---|---|---|
| Seconds in a day | 86,400 | **10⁵ (100,000)** |
| Seconds in a month (30 d) | 2,592,000 | 2.6 × 10⁶ |
| Seconds in a year | 31,536,000 | ~3.15 × 10⁷ |
| Minutes in a year | 525,600 | ~5.3 × 10⁵ |

The `÷100,000` shortcut over-estimates QPS by 16%, which is a *safety* margin in the
direction you want. Say "I'm rounding 86,400 to 100,000, which is conservative by about
15%" and the interviewer knows you know.

**Bytes per thing.**

| Data | Size |
|---|---|
| ASCII character / UTF-8 (Latin) | 1 byte |
| `int` / `int4` / float32 | 4 bytes |
| `bigint` / timestamp / float64 | 8 bytes |
| UUID (binary / as text) | 16 B / 36 B |
| Boolean | 1 byte |
| 1 KB of text | ~1,000 chars ≈ 170 words |
| LLM token | ~4 chars ≈ 4 bytes |
| Typical narrow DB row (ids + timestamps) | 100–200 bytes |
| Typical wide DB row (with text fields) | 500 B – 2 KB |
| **Index overhead** | **+30% of table size** |
| JSON API response, small object | 500 B – 2 KB |
| Thumbnail image | 10–50 KB |
| Web-optimised photo (JPEG/WebP) | 200–500 KB |
| Original phone photo | 3–5 MB |
| 1 minute of 1080p video | 50–100 MB |
| 1 minute of 4K video | 300–400 MB |

**Capacity rules of thumb** (conservative; state them as assumptions).

| Resource | Assume |
|---|---|
| App server (4 vCPU), simple JSON + cache read | 2,000–5,000 QPS |
| App server (4 vCPU), does real DB work | 300–800 QPS |
| PostgreSQL primary, indexed point reads | 10k–50k QPS |
| PostgreSQL primary, writes with `synchronous_commit` | 1k–5k TPS |
| Redis single node | 100k+ ops/s, sub-millisecond |
| Kafka broker | 100+ MB/s sustained |
| Target CPU utilisation | 60–70%, never 90% |
| Peak : average traffic ratio | 2–3× (consumer), up to 10× (event-driven) |
| Cache hit ratio, well-tuned | 80–95% |

**The pipeline.** Say these six steps in this order, every time.

```text
   1. DAU x actions/user/day            = requests/day
   2. requests/day / 100,000            = AVERAGE QPS
   3. average QPS x 2..3                = PEAK QPS
   4. writes/day x bytes/write x 1.3    = storage/day  (x replication factor)
      storage/day x 365 x retention_yrs = TOTAL STORAGE
   5. QPS x payload bytes               = BANDWIDTH (in and out separately)
   6. peak QPS / QPS-per-server, x1.5   = SERVER COUNT
      daily working set x 20%           = CACHE SIZE
```

---

### Worked example A — URL shortener

**Given / assumed** (state every assumption out loud):

```text
   New short URLs created:     500 M / month
   Read : write ratio:         100 : 1
   Retention:                  5 years
   Avg long URL length:        100 characters
   Replication factor:         3 (primary + 2 replicas)
```

**Step 1–2 — QPS.**

```text
   Writes/day  = 500,000,000 / 30                    =  16.7 M/day
   Write QPS   = 16,700,000 / 100,000                =  167 writes/s
   Read QPS    = 167 x 100                           =  16,700 reads/s
```

**Step 3 — peak.**

```text
   Peak writes = 167 x 3   =    ~500 writes/s
   Peak reads  = 16,700 x 3 = ~50,000 reads/s
```

**Step 4 — storage.** Row layout, then arithmetic:

```text
   short_code   char(7)      7 B
   long_url     varchar     100 B  (avg; cap at 2048)
   user_id      bigint        8 B
   created_at   timestamptz   8 B
   expires_at   timestamptz   8 B
   click_count  bigint        8 B
   ------------------------------------
   row                      ~140 B  -> round to 200 B with row overhead
   + indexes (PK on code, idx on user_id) +30%   -> ~260 B, call it 300 B

   Per month  = 500 M x 300 B         = 150 GB
   Per year   = 150 GB x 12           = 1.8 TB
   5 years    = 1.8 TB x 5            = 9 TB
   x3 replicas                        = 27 TB provisioned
```

**Key-space check** — the one candidates forget:

```text
   base62 (a-z A-Z 0-9), 7 characters:  62^7 = 3.5 x 10^12  = 3.5 trillion
   Consumption: 6 B/year (500M x 12)
   Runway = 3.5e12 / 6e9 = ~580 years.        7 chars is right.
   6 characters: 62^6 = 56.8 billion -> ~9 years. Too tight. 7 it is.
```

**Step 5 — bandwidth.**

```text
   Read response is an HTTP 301 with a Location header: ~500 B
     egress = 16,700 x 500 B      = 8.4 MB/s   = ~700 GB/day
     at $0.09/GB internet egress  = ~$63/day   = ~$1,900/month
   Write request/response: ~1 KB in, 200 B out
     ingress = 167 x 1 KB = 167 KB/s  (free)
```

Bandwidth is not the constraint here. Note that out loud — it tells the interviewer you
checked rather than skipped.

**Step 6 — servers and cache.**

```text
   Redirect handler = Redis GET + 301. Assume 4,000 QPS per 4-vCPU instance
   at 65% target utilisation.
     50,000 / 4,000 = 12.5 -> 13 instances
     x1.5 for AZ redundancy and headroom -> ~20 instances across 3 AZs

   Cache sizing (80/20):
     Distinct URLs read per day: assume 100 M (most links are one-shot)
     Hot 20% = 20 M keys x (7 B key + 100 B value + ~90 B Redis overhead)
             = 20 M x ~200 B = 4 GB
     Round up for fragmentation and TTL churn -> 8 GB
     -> one r6g.xlarge Redis with a replica. Not a cluster. Say so.
```

**The conclusion you say out loud:** "So this is a read-heavy system at fifty thousand
peak reads per second, nine terabytes of data over five years, and a cache that fits in
eight gigabytes. That means the redirect path is entirely a cache-plus-CDN problem, the
database is comfortably one sharded-later Postgres, and the interesting engineering is in
key generation and cache warming — not in scaling writes at a hundred and sixty-seven a
second."

---

### Worked example B — photo-sharing feed

**Given / assumed:**

```text
   DAU:                        100 M
   App opens per user per day: 5   (each = 1 feed request)
   Photos posted per user/day: 0.1 (i.e. 1 in 10 users posts once)
   Photos per feed page:       20
   Retention:                  forever (this matters)
```

**Step 1–3 — QPS.**

```text
   Feed reads/day  = 100 M x 5              = 500 M/day
   Feed read QPS   = 500 M / 100,000        = 5,000 QPS average
   Peak (x3)                                = 15,000 QPS

   Photo uploads/day = 100 M x 0.1          = 10 M/day
   Upload QPS        = 10 M / 100,000       = 100 uploads/s average
   Peak (x3)                                = 300 uploads/s
```

**Step 4 — storage. This is where the design changes.**

```text
   Per photo we store 3 renditions:
     original   3 MB
     web/1080   300 KB
     thumb/320   30 KB
     ------------------
     total     ~3.33 MB  -> call it 3.4 MB

   Blob storage/day  = 10 M x 3.4 MB        = 34 TB/day
   Blob storage/year = 34 TB x 365          = 12.4 PB/year
   At S3 Standard ~$0.023/GB-month, year 1 average holding ~6 PB:
     6,000,000 GB x $0.023                  = ~$138,000/month, and it GROWS

   Metadata row (Postgres):
     photo_id bigint 8, user_id bigint 8, caption 200 B, created_at 8,
     geo 16, width/height 8, counters 24, s3_key 64  -> ~340 B
     +30% indexes -> ~450 B, call it 500 B
   Metadata/day  = 10 M x 500 B             = 5 GB/day
   Metadata/year = 5 GB x 365               = 1.8 TB/year
```

**Say the implication:** "Twelve petabytes a year of blobs versus under two terabytes a
year of metadata — that four-orders-of-magnitude gap is the design. Blobs go to object
storage with a lifecycle policy tiering originals to a colder class after ninety days.
Metadata stays in Postgres, where one primary handles years of growth. I would never put
image bytes in the database."

**Step 5 — bandwidth. This is the expensive part.**

```text
   API JSON per feed page: 20 items x 500 B  = 10 KB
     5,000 QPS x 10 KB      = 50 MB/s  from the API tier. Fine.

   IMAGES, if every feed page loaded 20 web-size images from origin:
     5,000 x 20 x 300 KB    = 30 GB/s
                            = 2.6 PB/day
     at $0.085/GB           = ~$220,000/DAY   (~$80 M/year)
```

That number is the point of the exercise. Now apply the levers and say them in order:

```text
   1. CDN with 95% hit ratio -> origin egress drops 20x   -> ~$11,000/day
   2. Client + HTTP cache: users re-see photos; assume 40% of image
      requests never reach the CDN                        -> ~$6,600/day
   3. Serve AVIF/WebP at 120 KB instead of JPEG at 300 KB -> ~$2,600/day
   4. Lazy-load: only ~8 of 20 images are actually viewed -> ~$1,050/day
   Combined: ~$220k/day -> ~$1k/day. Two orders of magnitude, zero
   changes to the box diagram.
```

**Step 6 — servers and cache.**

```text
   Feed API: precomputed feed IDs in Redis, hydrate metadata from cache.
     Assume 3,000 QPS per 4-vCPU pod at 65% utilisation.
     15,000 / 3,000 = 5 pods -> x1.5 headroom, x3 AZs -> ~12 pods

   Feed cache (fan-out-on-write, 200 post IDs per user):
     200 IDs x 8 B = 1.6 KB per user
     Hot 20% of DAU = 20 M users x 1.6 KB     = 32 GB
     + metadata cache for hot photos:
       hot 20% of a week's photos = 14 M x 500 B = 7 GB
     Total ~40 GB -> Redis cluster, 6 nodes (3 primary + 3 replica)

   Upload path at 300/s peak: presigned URLs so bytes never touch the API.
     Thumbnailing is async: 300/s x ~2 s CPU each = 600 concurrent workers
     (Little's Law again). Autoscale on queue depth.
```

**The conclusion you say out loud:** "So the read path is fifteen thousand peak QPS, which
is a dozen pods and a forty-gigabyte Redis — completely unremarkable. The two real
problems are twelve petabytes a year of blob growth, which is a lifecycle-policy and
storage-tiering problem, and image egress, which without a CDN would be two hundred and
twenty thousand dollars a day. That tells me the CDN and the image pipeline are the
architecture, and the API tier is almost an afterthought."

---

### Enterprise production example

Use **Shopify's** published BFCM 2025 numbers to calibrate your intuition about what
"large" means, and to sanity-check your own estimates:

| Metric | Value | Derived |
|---|---|---|
| Edge requests, whole weekend | 2.2 trillion | — |
| Edge requests/minute, average | 312 M | **5.2 M/s** |
| Edge requests/minute, peak | 489 M | **8.15 M/s** |
| **Peak : average ratio** | — | **~1.57×** |
| App-server requests/min, peak | 117 M | 1.95 M/s |
| API requests/min, peak | 31.8 M | 530 k/s |
| Database queries/second, peak | 53.8 M | MySQL 8, sharded |
| Row operations/second, peak | 4.28 B | ~80 rows per query |
| CDN requests/minute | 183 M | **97.8% cache hit** |
| Kubernetes CPU cores, peak | 3.18 M | — |
| Async jobs/minute, peak | 23.2 M | 387 k/s |
| Log volume, peak | 11 TB/minute | — |
| GMV, peak | $5.1 M/minute | — |

Three calibration lessons. First, the **peak-to-average ratio within the peak weekend was
only about 1.57×** — your 2–3× multiplier is for peak-versus-normal-day, not
peak-versus-peak-period, and saying which one you mean is a mark of precision. Second, note
the **edge-to-app funnel**: 8.15 M/s at the edge collapses to 1.95 M/s at app servers, a 4×
reduction, almost all of it CDN caching at a 97.8% hit ratio. Third, **11 TB of logs per
minute** — at typical hosted-log pricing that would be an absurd number, which is why
observability at this scale is sampled and self-hosted. Estimate log volume in your
interviews; almost nobody does.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Every design interview, in the first 10 minutes | The interviewer has explicitly given you the numbers | 3–5 minutes; it buys the rest of the hour |
| Rounding aggressively (86,400 → 100,000) | The question is explicitly about precision | ~16% over-estimate, which is the safe direction |
| Stating assumptions out loud | You'd rather look confident than correctable | Nothing — it's the single best signal you can send |
| Recomputing after the interviewer changes a number | You've built the whole design on the old number | 30 seconds, and it demonstrates the numbers are live |

### Follow-ups they will ask

**Q: Why divide by 100,000 instead of 86,400?**
A: Because I'm doing this in my head in front of you and 16% of error is irrelevant when
the decision is "one Postgres or a sharded fleet". It also errs high, so I over-provision
rather than under-provision. If the answer came out near a decision boundary — say 4,800
QPS when a single primary handles about 5,000 — I'd redo it with 86,400 and check whether
the boundary actually moves.

**Q: Where does the 2–3× peak multiplier come from, and when is it wrong?**
A: It comes from diurnal human behaviour: a consumer app concentrates most of its traffic
into an 8-hour window, so the peak hour is roughly 2–3× the 24-hour average. It's wrong in
two directions. For an internal B2B tool used only in business hours in one timezone, the
peak-to-average is closer to 5–8×, because the denominator includes 16 hours of nothing.
For event-driven traffic — a ticket on-sale, a live sports moment, a marketing push — it
can be 50–100× within seconds, and at that point the multiplier is meaningless and you
design for a queue plus load shedding instead.

**Q: You estimated 12 PB/year of photos. Is that actually a problem?**
A: It's a cost and lifecycle problem, not a technical one, because object storage scales
essentially without a ceiling. At S3 Standard pricing 12 PB is roughly $280,000/month once
fully accumulated, so the engineering response is tiering: keep the web and thumbnail
renditions in Standard because they're served constantly, and move originals to
Infrequent-Access after 30 days and Glacier Instant Retrieval after a year, since almost
nobody re-downloads a two-year-old original. That's a lifecycle policy, maybe fifteen
lines of configuration, and it typically cuts the storage line by 60–70%.

**Q: How many database connections do you need for 15,000 QPS?**
A: Little's Law, applied to the database specifically rather than to the request. If the
average query takes 2 ms, then `L = 15,000 × 0.002 = 30` connections busy at any moment. I'd
provision maybe 60 for burst and skew, spread across pods. The mistake is to reason from
pod count — twenty pods times a default pool of ten is two hundred connections against a
database that performs best around a hundred, and every extra connection past the knee
makes throughput *worse* because of context switching and lock contention. Above a few
hundred I'd put PgBouncer in transaction mode in between.

**Q: Your estimate says one server is enough. Do you still design for horizontal scaling?**
A: For the stateless tier, yes, because it's free — I run two instances behind a load
balancer regardless, since one instance is a single point of failure and I need to deploy
without downtime. For the stateful tier, no: I'd run one primary with a standby and be
explicit that sharding is a future project with a documented trigger, like "when sustained
write throughput exceeds 60% of primary capacity". Designing sharding into a system that
does 167 writes a second is the most expensive kind of premature optimisation.

### Red flags — do not say this

- ❌ "It'll be about a million requests per second." → ✅ "100 M DAU × 5 actions ÷ 100,000 seconds = 5,000 QPS average, 15,000 peak. Let me check that against the read:write ratio."
- ❌ Doing the arithmetic silently. → ✅ Narrating every step, so a wrong assumption gets corrected at second 20 instead of minute 20.
- ❌ "Storage will be a few terabytes." → ✅ "10 M photos/day × 3.4 MB = 34 TB/day, so 12 PB/year. That forces object storage with lifecycle tiering, not a database."
- ❌ Forgetting index overhead and replication. → ✅ "500 bytes per row plus 30% for indexes, times 3 for replicas — so budget 2 KB of provisioned storage per logical row."

---

## 1.10 Writing requirements on the whiteboard

> **One-liner:** In the first five minutes you write eleven lines — four functional, five
> numeric non-functional, one out-of-scope, one estimate — and you refer back to them for
> the rest of the hour.

### Say this in the interview

> Let me put the requirements up here first so we're designing against something concrete,
> and I'll keep referring back to it. On the left I'll write the functional requirements
> as numbered actor-action sentences, and under them an explicit out-of-scope line so we
> both know what I'm not building. On the right I'll write the non-functional targets as
> numbers — availability, read and write latency at p99, peak QPS, storage over the
> retention period, and consistency per read path. Then one line of estimation showing how
> I got the QPS. This takes me about four minutes and it earns them back three times over,
> because every time I make a design choice later I can point at a line and say "I'm
> adding a cache because of this read QPS number" rather than because caches are good.
> If you want to change any of these numbers as we go, tell me and I'll redo the affected
> arithmetic out loud.

### Mental model

The exact board layout. Keep it in this shape every time so you never have to think about
the format under pressure.

```text
 ┌──────────────────────────────┬──────────────────────────────────────┐
 │ FUNCTIONAL                   │ NON-FUNCTIONAL                       │
 │                              │                                      │
 │ F1 user shortens a URL       │ Availability  99.9%  (43 min/mo)     │
 │ F2 user follows short URL    │ Read  p99     < 50 ms                │
 │    -> 301 to original        │ Write p99     < 200 ms               │
 │ F3 owner sees click count    │ Peak QPS      50k read / 500 write   │
 │ F4 links may expire          │ Storage       9 TB @ 5y retention    │
 │                              │ Consistency   RYOW on create;        │
 │ OUT: custom domains, auth,   │               eventual on counts     │
 │      analytics dashboard,    │ Cost          < $0.00002 / redirect  │
 │      bulk import             │                                      │
 ├──────────────────────────────┴──────────────────────────────────────┤
 │ ESTIMATE  500M/mo writes -> 16.7M/day / 1e5 = 167 w/s; x100 read    │
 │           ratio = 16.7k r/s; x3 peak = 50k r/s. 300 B/row -> 9 TB.  │
 └─────────────────────────────────────────────────────────────────────┘
```

Rules for the board:

1. **Number the functional requirements** (F1, F2…) so you can say "this queue exists
   because of F2" instead of re-describing it.
2. **Every NFR has a unit.** If a line has no number on it, delete the line.
3. **Write the out-of-scope list.** It is the cheapest way to control the hour, and
   interviewers read it as scoping judgement rather than laziness.
4. **Leave the estimate visible.** When they change a number at minute 30 — and they will,
   that's the standard curveball — you update one line and re-derive out loud.
5. **Don't erase it.** This block stays on the board for the whole session. Everything else
   can be redrawn around it.

### Enterprise production example

This mirrors how a real design review works. **Amazon's** Working Backwards process (1.1)
produces a PR-FAQ before implementation; **Google's** SRE practice requires an SLO document
with numeric SLIs before a service is accepted for production support; the **AWS
Well-Architected Framework** review is literally a checklist of questions across
reliability, performance, cost, security and operations that must be answered with
specifics. In all three, the artifact is written *before* the architecture and referred back
to during it. The whiteboard block is a compressed version of the same discipline, and
saying "this is the same thing as an SLO doc, just faster" is a legitimate framing.

### Code

Skip — it's a whiteboard, not a program.

### Follow-ups they will ask

**Q: The interviewer changes DAU from 100 M to 1 B at minute 30. What do you do?**
A: I go back to the estimate line and redo it out loud: 10× the DAU is 10× the QPS, so
50,000 peak reads becomes 500,000, and 12 PB/year of storage becomes 120 PB. Then I state
which decisions *survive* and which break — the CDN and object-storage choices survive
because they scale linearly, the single Postgres primary does not, so that's where sharding
enters and I'd talk about the partition key. The valuable part is showing which parts of
the design were scale-independent, because that's evidence the design was principled rather
than fitted to one number.

**Q: You've spent five minutes and drawn no boxes. Isn't that wasteful?**
A: It's the highest-return five minutes in the hour. Without it I'd spend twenty minutes
designing a sharded multi-region system for a workload that turns out to be two hundred
requests a second, and the interviewer would spend that time waiting to tell me. With it,
every subsequent decision has a stated justification, and if my numbers are wrong I get
corrected while the correction is still cheap.

### Red flags — do not say this

- ❌ Starting to draw boxes before writing any requirement down. → ✅ "Give me four minutes to write requirements and a scale estimate, then I'll draw."
- ❌ Writing NFRs as adjectives on the board. → ✅ Every line ends in a number and a unit.
- ❌ Erasing the requirements block to make room for the architecture. → ✅ Keep it in a corner and point at it when justifying each component.

---

## Module 01 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Convert 99.9%, 99.95% and 99.99% into downtime per month, from memory.
2. Four services in series, each 99.95%. What is the end-to-end availability, and what is
   the *one* architectural change that improves it most?
3. State Little's Law, then use it to size a database connection pool for 3,000 QPS where
   each request spends 15 ms in the database.
4. Why is `1 − (1 − A)^n` optimistic for real redundant systems? Give a concrete failure
   that breaks the independence assumption.
5. S3 is designed for 11 nines of durability. What is its availability SLA, and why is the
   gap so large?
6. A request fans out to 100 backends, each with a 1% chance of being slow. What fraction
   of user requests are slow, and what is the single technique Google published to fix it?
7. Estimate peak QPS for 40 M DAU performing 12 actions per day, showing every step.
8. A photo service stores 5 M photos/day at 3 MB each. What is the annual storage, and
   what does that force about the storage tier?
9. Name the three most common cloud cost traps and the fix for each.
10. Why can you not average p99 latencies across pods, and what do you do instead?
11. When is vertical scaling genuinely the correct choice, and what is the trigger to stop?
12. Write the eleven lines you put on the whiteboard in the first five minutes.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Seconds in a day (rounded for QPS math) | 86,400 → **use 10⁵** |
| Minutes in a 30-day month | 43,200 |
| 99% availability | 3.65 days/yr, 7.2 h/month |
| 99.9% availability | 8.77 h/yr, **43.2 min/month** |
| 99.95% availability | 4.38 h/yr, 21.6 min/month |
| 99.99% availability | 52.6 min/yr, **4.32 min/month** |
| 99.999% availability | 5.26 min/yr, 25.9 s/month |
| Series availability | A₁ × A₂ × … (dependencies multiply) |
| Parallel availability | 1 − (1 − A)ⁿ (assumes independence — it isn't) |
| Availability from MTBF/MTTR | A = MTBF / (MTBF + MTTR) |
| S3 durability (designed) | 99.999999999% — 11 nines |
| S3 Standard availability (designed / SLA) | 99.99% / **99.9% monthly** |
| S3 SLA credit tiers | 10% < 99.9%, 25% < 99.0%, 100% < 95.0% |
| S3 Standard AZ count / AZ separation | ≥ 3 AZs, within 100 km |
| Little's Law | L = λ × W |
| Queueing wait multiple at ρ = 0.7 / 0.9 / 0.95 | ~3× / ~10× / ~20× |
| Target CPU utilisation | 60–70% |
| L1 cache reference | 0.5 ns |
| Main memory reference | 50 ns |
| Read 4 KB from SSD | 20 µs |
| **Round trip within a datacenter** | **50 µs** |
| Read 1 MB over 100 Gbps network | 100 µs |
| Read 1 MB from SSD | 1 ms |
| Disk seek | 5 ms |
| **CA → Netherlands → CA round trip** | **150 ms (unchanged since 2007)** |
| Cross-AZ round trip | ~0.5–1 ms |
| Cross-region round trip (US ↔ EU) | ~80–100 ms |
| Redis GET, same VPC | 0.2–0.5 ms p99 |
| Postgres indexed point read | 0.5–2 ms |
| LLM time-to-first-token | 300–900 ms |
| Tail amplification, p=1% | N=10 → 9.6%, N=100 → **63.4%**, N=200 → 86.6% |
| Google hedged requests (BigTable, 1,000 keys / 100 servers) | p99.9 **1,800 ms → 74 ms** for 2% extra load |
| Google tied requests (GFS) | median −16%, p99.9 −40% |
| BigTable tablets per machine (micro-partitioning) | 20–1,000 |
| Index overhead on a table | +30% |
| Peak : average traffic | 2–3× consumer, 5–8× B2B, 50×+ event-driven |
| Cache 80/20 rule | 20% of keys serve 80% of reads |
| AWS internet egress | $0.09/GB (first 10 TB); ingress free |
| GCP internet egress (Premium / Standard) | $0.12 / $0.085 per GB |
| Cross-AZ transfer (AWS, GCP) | $0.01/GB **each direction** |
| NAT Gateway | $0.045/hr/AZ + $0.045/GB processed |
| VPC Gateway Endpoint (S3, DynamoDB) | $0 |
| Shopify BFCM 2025 edge peak | 489 M req/min = **8.15 M req/s** |
| Shopify BFCM 2025 edge average | 312 M req/min (peak:avg ≈ 1.57×) |
| Shopify BFCM 2025 DB fleet | 53.8 M queries/s, 4.28 B row ops/s |
| Shopify BFCM 2025 CDN hit ratio | **97.8%** |
| Shopify BFCM 2025 peak log volume | 11 TB/minute |

---

**Next:** [Module 02 — Networking: DNS, HTTP, TCP/UDP, WebSockets](./02_Networking.md)
