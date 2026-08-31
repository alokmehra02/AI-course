# Module 12 — Monoliths, Microservices & Service Communication

> **What this module makes you able to do:** defend "start with a modular monolith" as a
> senior answer rather than a junior one, name the specific forcing function that
> justifies each service you split out, and reason about service communication, data
> ownership and tail amplification with numbers instead of adjectives.
>
> **Interview weight:** ★★★★☆
>
> **Prerequisites:** Module 09 — Reliability Patterns, Module 11 — Observability, SLOs &
> Disaster Recovery

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 12.1 | The monolith | ★★★★☆ |
| 12.2 | The modular monolith | ★★★★★ |
| 12.3 | Microservices | ★★★★★ |
| 12.4 | The migration path | ★★★★☆ |
| 12.5 | Service communication | ★★★★★ |
| 12.6 | Service discovery | ★★★☆☆ |
| 12.7 | Service mesh | ★★★☆☆ |
| 12.8 | API composition & the aggregation problem | ★★★★☆ |
| 12.9 | Data ownership | ★★★★★ |
| 12.10 | Deployment strategies | ★★★★☆ |
| 12.11 | Containers & orchestration for design interviews | ★★★☆☆ |
| 12.12 | The 12-factor app | ★★★☆☆ |
| 12.13 | Choosing an architecture in the interview | ★★★★★ |

---

## 12.1 The monolith

> **One-liner:** One deployable unit containing all the business logic — and for most
> systems it is the correct architecture, because a function call is a nanosecond and a
> network call is a millisecond that can also fail.

### Say this in the interview

> A monolith is a single deployable artifact that contains all the business capabilities
> and usually talks to one database. The reason it's the right default is that it makes
> the two hardest things in distributed systems free: a call between two modules is an
> in-process function call, which is nanoseconds and cannot partially fail, and a
> transaction that spans orders and inventory and payments is a single database
> transaction with real ACID guarantees instead of a saga with compensating actions.
> Debugging is one stack trace, deploying is one artifact, and moving a boundary is a
> refactor rather than a data migration and a versioned API. Its limits are real, but
> they're organisational before they're technical. Deploy coupling is the first one to
> hurt: when forty engineers merge into one artifact, one team's bad commit blocks
> everyone's release, and the test suite grows until the feedback loop is an hour.
> Scaling is all-or-nothing — if PDF rendering needs CPU I have to scale the whole
> process, including the parts that only needed memory. And the blast radius is the
> whole app: one unbounded query or one memory leak in a background job takes down the
> checkout path too. Those are the forcing functions I'd point at before splitting
> anything.

### Mental model

```
       ┌─────────────────────────────────────────────┐
       │           ONE DEPLOYABLE PROCESS            │
       │   ┌────────┐ ┌────────┐ ┌────────┐         │
  LB ──┼──►│ orders │→│ billing│→│ notify │  ← ns    │
       │   └────────┘ └────────┘ └────────┘  calls   │
       │        └──────────┬──────────┘              │
       └───────────────────┼─────────────────────────┘
                           ▼
                    ┌─────────────┐
                    │  ONE DB     │  ← one transaction spans everything
                    └─────────────┘
```

**What it genuinely buys you:**

| Property | Monolith | Microservices |
|---|---|---|
| Inter-module call | ~10–100 ns, cannot partially fail | 0.5–5 ms in-cluster, can time out |
| Cross-domain transaction | One `BEGIN … COMMIT` | Saga + compensations + idempotency |
| Debugging one request | One stack trace | Distributed trace across N services |
| Moving a boundary | IDE rename | API version + data migration + deprecation |
| Local development | `docker compose up` (one thing) | Mocks, or 12 containers, or a shared dev cluster |

**Where it actually breaks** — and note that only one of these four is technical:

1. **Deploy coupling.** N teams, one release train. One team's revert blocks everyone.
   Symptom: release cadence goes down as headcount goes up.
2. **Scaling granularity.** You scale the process, not the hot path. Symptom: you're
   running 60 pods because one endpoint is CPU-heavy and the other 200 are idle.
3. **Team contention.** Merge conflicts, a 40-minute test suite, nobody owning the
   shared modules. Symptom: "who owns this file?" has no answer.
4. **Blast radius.** No isolation between a background job and the checkout path.
   Symptom: an OOM in report generation returns 502s to paying customers.

### Enterprise production example

**Shopify** runs one of the largest Ruby on Rails codebases in existence as a monolith —
their engineers have publicly described it at roughly 2.8–3 million lines, 500,000+
lifetime commits and ~40,000 files, with well over a thousand developers, and their
public position is that the majority of the platform will stay in the core monolith
because standard horizontal scaling techniques have worked. They did not conclude "the
monolith failed"; they concluded that its *internal structure* had failed, which is a
completely different diagnosis and leads to [12.2](#122-the-modular-monolith).

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Team ≤ ~25 engineers, one product | 5 teams need independent release cadence | Deploy coupling, all-or-nothing scaling |
| Domain boundaries still moving | Boundaries are stable and proven | Discipline required or it becomes a big ball of mud |
| Transactional consistency across domains | One component needs radically different scaling | Blast radius spans the whole app |

### Follow-ups they will ask

**Q: At what point does a monolith stop being the right answer?**
A: When a specific, nameable constraint bites — not at a headcount or a line count. The
honest triggers are: two teams whose release cadences genuinely conflict; one component
whose resource profile is 10× different from the rest (GPU inference, video transcode);
a compliance boundary that requires isolation; or a component that must survive when the
rest is down. If I can't name which of those applies, splitting adds cost for nothing.

**Q: Can a monolith scale to millions of users?**
A: Yes — horizontally, behind a load balancer, with read replicas and a cache, exactly
like any stateless service. The monolith is a *deployment* topology, not a scaling limit.
What doesn't scale is a monolith with sticky sessions and in-process state, and that's a
statelessness problem, not a monolith problem.

**Q: Isn't a monolith a single point of failure?**
A: Not inherently — you run many instances of it across zones. What it does have is a
shared *failure mode*: a leak or a hot loop in any module degrades every endpoint,
because they share a process. That's blast radius, not SPOF, and the mitigation inside a
monolith is bulkheading — separate thread/worker pools and separate deployments of the
same artifact for the risky workload.

### Red flags — do not say this

- ❌ "Monoliths don't scale." → ✅ "Monoliths scale horizontally fine; what doesn't scale
  is the number of teams committing to one release train."
- ❌ "We should use microservices because we expect to grow." → ✅ "We'd start with a
  modular monolith and split when a specific team or scaling constraint forces it."

---

## 12.2 The modular monolith

> **One-liner:** One deployable, but with enforced internal boundaries — you get service-
> like ownership and clear interfaces without paying the network tax or the distributed-
> transaction tax.

### Say this in the interview

> A modular monolith keeps one deployable artifact but splits the code into modules with
> explicit public interfaces and *machine-enforced* dependency rules. Orders can call
> `Billing.charge()`; orders may not reach into billing's tables or its internal classes,
> and CI fails the build if it tries. That last part is what makes it different from
> "we have folders" — a boundary that isn't enforced by tooling has always eroded within
> two quarters, in every codebase I've seen. What you get is most of the benefit people
> actually want from microservices: clear ownership, a real interface, the ability to
> reason about one module in isolation, and — critically — a boundary you can test
> before you commit to it. And you keep in-process calls, one transaction, one deploy,
> one stack trace. The reason I think this is usually the right mid-level answer is that
> the expensive, irreversible part of microservices is splitting the database, and a
> modular monolith lets you get the module boundaries right first, at refactor cost
> rather than migration cost. Shopify is the reference case: they audited about six
> thousand Ruby classes into components in 2017 and built Packwerk in 2020 to enforce
> the dependencies statically, rather than breaking up a three-million-line codebase
> into services.

### Mental model

```
  ┌───────────────────────────────────────────────────────────────┐
  │                    ONE DEPLOYABLE PROCESS                     │
  │                                                               │
  │  ┌─ orders ─────────┐   ┌─ billing ────────┐  ┌─ catalog ──┐  │
  │  │ public:          │   │ public:          │  │ public:    │  │
  │  │   OrdersApi      │──►│   BillingApi     │  │  CatalogApi│  │
  │  │ internal:        │ ✗ │ internal:        │  │ internal:  │  │
  │  │   OrderRepo ─────┼─┐ │   Invoice, Ledger│  │  PriceRepo │  │
  │  └──────────────────┘ │ └──────────────────┘  └────────────┘  │
  │                       │                                       │
  │      ✗ = CI FAILS: orders imported billing's internal class    │
  │      ✗ = CI FAILS: billing wrote to orders_* tables            │
  └───────────────────────────────────────────────────────────────┘
                              ▼
                   one DB, but one schema per module,
                   and each module owns only its own tables
```

**The four rules that make it real:**

1. **A module has a public API surface and everything else is internal.** Python:
   `__all__`, package structure, and an import-linter contract. Node: package
   boundaries in a monorepo with `eslint-plugin-boundaries` or `dependency-cruiser`.
2. **Dependencies are declared and acyclic.** If `orders → billing` is allowed, then
   `billing → orders` must not be. Cycles are how you end up unable to split later.
3. **Each module owns its tables.** Same physical database, separate schemas, no
   cross-schema joins and no cross-schema foreign keys. This is the single most
   important rule, because it is the one that makes a future extraction possible.
4. **CI enforces 1–3.** A boundary that only exists in a wiki is not a boundary.

**Why this is often the best mid-level interview answer:** it demonstrates that you know
the expensive part of microservices is the data, not the code. You can move a module
boundary in a modular monolith with a rename. Moving it after you've split the database
means a dual-write, a backfill, an API version, and a coordinated deploy across two
teams.

### Enterprise production example

**Shopify** is the canonical case and the numbers are public. Their core Rails
application had grown past ~2.8 million lines with 500,000+ lifetime commits and around
40,000 files, worked on by over a thousand developers. In early 2017 a team formed under
the internal name "Break-Core-Up-Into-Multiple-Pieces", which became "Componentization".
They audited roughly **6,000 Ruby classes in a spreadsheet**, manually labelling which
business component each belonged to, then reorganised the codebase from Rails' default
`models/views/controllers` layout into domain folders — orders, shipping, inventory,
billing — in a single large scripted PR. In 2020 they open-sourced **Packwerk**, a static
dependency analyser, and organised the monolith into **37 components with defined public
entrypoints**.

The honest epilogue matters too, and mentioning it is a strong signal: Shopify's own
later retrospective reported that strict privacy checks were eventually removed from
Packwerk because of architectural misalignment and maintenance cost. Enforcement is
work, and even the flagship example had to soften a rule. What they did *not* do was
break the monolith into hundreds of services.

### Code

```python
# import-linter contract — this is the file that turns "modules" into boundaries.
# .importlinter, run in CI: `lint-imports` exits non-zero on violation.

[importlinter]
root_package = shopmono

[importlinter:contract:layers]
name = Domain layers must not invert
type = layers
layers =
    shopmono.interfaces     # HTTP/CLI/worker entrypoints
    shopmono.orders
    shopmono.billing
    shopmono.catalog
    shopmono.platform       # db, cache, telemetry — everyone may use it

[importlinter:contract:module-privacy]
name = Modules may only import each other's public API
type = forbidden
source_modules =
    shopmono.orders
forbidden_modules =
    shopmono.billing.internal
    shopmono.catalog.internal
```

```python
# shopmono/billing/__init__.py — the public surface, and nothing else
from shopmono.billing.api import BillingApi, ChargeResult, ChargeFailed

__all__ = ["BillingApi", "ChargeResult", "ChargeFailed"]
# Invoice, Ledger, StripeClient live in shopmono.billing.internal and are
# unreachable from orders — enforced above, not by convention.
```

```sql
-- One database, one schema per module. This is what makes extraction possible.
CREATE SCHEMA orders;   CREATE SCHEMA billing;   CREATE SCHEMA catalog;

-- Enforce it at the database layer too, so an ORM mistake can't cross the line:
CREATE ROLE orders_module;
GRANT USAGE ON SCHEMA orders TO orders_module;
REVOKE ALL ON SCHEMA billing FROM orders_module;   -- no cross-schema reads
-- And no cross-schema FKs: billing.invoices.order_id is a plain UUID column,
-- not a REFERENCES orders.orders(id). That FK is the thing you cannot split.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Boundaries are still being discovered | Teams genuinely need independent deploys | Enforcement tooling and the discipline to keep it |
| You want ownership without the network | One module needs radically different infra | Still one deploy, one blast radius |
| You may split later and want the option | The team won't respect the rules anyway | CI complexity; occasional awkward refactors |

### Follow-ups they will ask

**Q: What stops a modular monolith from decaying into a big ball of mud?**
A: Only automated enforcement. Import contracts in CI, per-schema database grants, and
code ownership files that require the owning team's review to change a module's public
API. Every codebase I've seen that relied on "team discipline" had cross-module reaching
within a couple of quarters, because the pressure to ship a fix quickly always beats an
unenforced rule.

**Q: How does a modular monolith make a future extraction cheaper?**
A: Because the two hard parts are already done. The public API of the module becomes the
service's API almost verbatim, and the module's schema is already isolated with no
cross-schema joins or foreign keys, so it can be moved to its own database without
untangling queries. Extraction becomes "put HTTP in front of an interface that already
exists" instead of "discover what the boundary should have been".

**Q: Can two modules in a monolith share a transaction? Should they?**
A: They can — that's the main advantage. Whether they should depends on whether you ever
intend to split them. If `orders` and `billing` commit in one transaction today, that's
a dependency you'll have to replace with a saga later. I'd allow it inside a bounded
context and forbid it across the boundaries I expect to become services.

**Q: Isn't this just microservices without the benefits?**
A: It's microservices without the *costs*, and with most of the benefits that mid-size
teams actually wanted — ownership, interfaces, isolated reasoning. What you don't get is
independent deployment and independent scaling, which are exactly the two things you
should be able to name a concrete need for before paying for them.

### Red flags — do not say this

- ❌ "We have a modular monolith — we organised the code into folders." → ✅ "The module
  boundaries are enforced in CI by import contracts and per-schema database grants."
- ❌ "Modular monolith is a stepping stone to microservices." → ✅ "It's a valid end
  state. It's also the cheapest way to find out where the boundaries really are, if we
  do split later."

---

## 12.3 Microservices

> **One-liner:** Independently deployable services aligned to business capabilities —
> an organisational scaling technique with a large, permanent operational bill attached.

### Say this in the interview

> Microservices are independently deployable services, each owning its own data,
> organised around business capabilities. The real benefit is organisational: a team can
> ship on its own cadence without coordinating with anyone, which is what actually stops
> working in a monolith at scale. Independent scaling and fault isolation are real too,
> but you only get fault isolation if you build timeouts, circuit breakers and fallbacks
> — a synchronous chain of five services without those is *less* reliable than a
> monolith, because now you multiply five availabilities together. Before I'd recommend
> splitting, I'd check for four prerequisites: automated CI/CD so deploys aren't a
> ceremony, distributed tracing and centralised logs so debugging is possible at all,
> per-team on-call so the people who ship also carry the pager, and a platform layer
> with service templates so each team isn't reinventing health checks and auth. Without
> those you get a distributed monolith — services that must be deployed together, share
> a database, and fail together — which is strictly worse than the monolith you started
> with. On sizing, I go by business capability or DDD bounded context, never by lines of
> code. And Conway's Law is not a joke: the architecture will end up mirroring the team
> structure regardless of what the diagram says, so I'd draw the team boundaries first.

### Mental model

```
  BENEFIT (real)                       PRECONDITION (must already exist)
  ─────────────────────────────────    ────────────────────────────────────
  independent deploy cadence      ←    CI/CD, automated tests, contract tests
  independent scaling             ←    orchestration + autoscaling + metrics
  fault isolation                 ←    timeouts, circuit breakers, fallbacks
  team autonomy / clear ownership ←    per-team on-call, service catalogue
  tech heterogeneity              ←    a paved road, or you get 6 stacks and
                                       nobody who can debug any of them
```

**Conway's Law** (Melvin Conway, 1967): *organisations design systems that mirror their
own communication structure.* The practical version: if you have one backend team and
one frontend team, you will get a backend service and a frontend service no matter what
the architecture diagram says. The Inverse Conway Manoeuvre is to deliberately shape the
teams into the structure you want the system to have — which is why Amazon's two-pizza
teams and its service architecture are the same decision, not two decisions.

**Service sizing.** "Micro" is the most misleading word in the term.

```
  ✗ by lines of code        "no service over 500 lines" → 400 nano-services
  ✗ by entity/table         one service per table → a distributed schema
  ✗ by technical layer      "the validation service" → chatty and coupled
  ✓ by business capability  "pricing", "fulfilment", "identity"
  ✓ by DDD bounded context  where the ubiquitous language changes meaning
  ✓ by team ownership       a service should have exactly one owning team;
                            a team can own several services
```

A useful test: can the service be changed, tested and deployed without coordinating with
another team? If no, the boundary is wrong.

**The distributed monolith** — the failure mode, and the thing interviewers probe for:

```
  Symptoms, any one of which means you built one:
    · services must be deployed together in a specific order
    · a shared database that several services read and write
    · a shared library whose version bump requires redeploying everything
    · a synchronous call chain 4+ deep on the request path
    · one team's change requires another team's PR

  Result: all the operational cost of distribution, none of the autonomy.
          Availability multiplies down: 5 services at 99.9% in series
          = 0.999^5 = 99.5%  →  3.6 hours/month instead of 43 minutes.
```

### Enterprise production example

**Amazon**, circa 2002, is the origin story. Jeff Bezos's API mandate — as recounted
publicly by former Amazon engineer Steve Yegge — required that all teams expose their
data and functionality through service interfaces, that teams communicate only through
those interfaces, that there be *no* direct linking, no direct reads of another team's
data store, no shared-memory model and no back doors, and that every interface be
designed to be externalisable from the ground up. Pair that with **two-pizza teams** —
small enough to be fed by two pizzas, with single-threaded ownership of one service —
and **"you build it, you run it"**, which Werner Vogels articulated in a 2006 ACM Queue
interview with Jim Gray: "Giving developers operational responsibilities has greatly
enhanced the quality of the services." Note the order of events: Amazon changed the
organisation and the ownership model at the same time as the architecture. The
architecture alone would not have worked.

**Uber** is the cautionary sequel. By mid-2018 Uber had grown to around **2,200 critical
microservices**, and dependency chains had become many layers deep and effectively
un-reasonable-about. Their answer, published in 2020, was **DOMA** — Domain-Oriented
Microservice Architecture — which classified those **2,200 microservices into about 70
domains**, each fronted by a single gateway, with layers that constrain which
dependencies a domain may take. Their published example: the Uber Maps organisation is
split into three domains with **80 microservices behind 3 gateways**, so an upstream
consumer calls one interface instead of dozens. That is a company re-introducing
monolith-like modularity on top of microservices because the service count itself became
the problem.

**Netflix** built the tooling generation that made this feasible for everyone else —
Eureka for service discovery, Ribbon for client-side load balancing, Zuul at the edge,
Hystrix for circuit breaking, Chaos Monkey for failure injection. A Netflix engineer
stated on the Eureka issue tracker that "both Zuul (specifically version 2) and Eureka
are core products for Netflix and almost all traffic that comes in touches both". Public
estimates of Netflix's service count vary widely and Netflix does not publish an
authoritative figure, so quote the tooling, not a number.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Multiple teams blocked by one release train | Fewer than ~4 teams | A platform team, tracing, per-team on-call |
| One component needs different infra (GPU, memory) | Boundaries still shifting weekly | Sagas instead of transactions; eventual consistency |
| Compliance/isolation requires it | You lack CI/CD and observability | Availability multiplies down across the chain |

### Follow-ups they will ask

**Q: How do you keep a transaction consistent across three services?**
A: You don't — you replace it with a saga: a sequence of local transactions where each
step publishes an event and each step has a compensating action. Order created →
payment authorised → inventory reserved; if inventory fails, you issue a refund rather
than roll back. That means every step must be idempotent (retries are guaranteed) and
the user-visible state must tolerate being briefly inconsistent. See
[Module 09 — Idempotency](./09_Reliability_Patterns.md#94-idempotency).

**Q: Five services in series, each 99.9%. What's your availability?**
A: 0.999⁵ ≈ 99.5%, which is 3.6 hours a month instead of 43 minutes — the split made you
*less* available. Fixing it means removing services from the synchronous path: make
calls parallel where possible, make non-critical calls async, add caching and fallbacks
so a dependency failing degrades rather than fails, and set aggressive timeouts so a
slow dependency doesn't consume your capacity.

**Q: A shared library is used by 30 services. Is that a distributed monolith?**
A: It depends on whether a version bump forces a coordinated redeploy. A library of pure
utilities that services adopt at their own pace is fine. A library containing shared
domain logic or shared database models, where everyone must upgrade in lockstep, is the
distributed monolith — you've reintroduced deploy coupling with extra network hops. The
tell is whether services can run different versions of it in production simultaneously.

**Q: How small should a microservice be?**
A: Big enough that it owns a complete business capability and can be changed without
touching another team's code; small enough that one team can hold all of it in their
heads and rewrite it in a quarter if they had to. If I'm splitting because a file got
long, I'm splitting for the wrong reason.

**Q: Your team is 8 engineers and the interviewer suggests microservices. What do you say?**
A: That eight engineers cannot staff per-service on-call, and that the coordination
problem microservices solve doesn't exist at that size. I'd propose a modular monolith
with enforced boundaries plus one or two genuinely separate services where the infra
profile differs — for example, GPU inference workers behind a queue.

### Red flags — do not say this

- ❌ "Microservices are more scalable." → ✅ "Microservices scale the organisation.
  Compute scales horizontally either way."
- ❌ "Each service should be small — a few hundred lines." → ✅ "Each service should own
  one business capability; size is an output of that, not a target."
- ❌ "We'd use microservices for fault isolation." (without qualifying) → ✅ "You only get
  fault isolation if every call has a timeout, a circuit breaker and a fallback.
  Otherwise you've made failures more likely, not less."

---

## 12.4 The migration path

> **One-liner:** Strangler fig: put a routing layer in front, move one capability at a
> time behind it, and accept that decomposing the database — not the code — is where the
> whole project actually lives.

### Say this in the interview

> I'd never do a big-bang rewrite; I'd use the strangler fig pattern. Put a routing
> facade in front of the monolith, extract one capability behind it, route that path to
> the new service, and leave everything else untouched — so at every point you have a
> working system and a cheap rollback, which is a routing change. Choosing what to cut
> first matters: I want a capability with low coupling to the rest, high rate of change
> so the payoff is real, and clear team ownership. Usually that's something on the edge
> — notifications, search, reporting — not the core order model. The part that dominates
> the schedule is the database, and it goes in three stages: everything shares one
> database; then each service gets its own schema in the same physical database with no
> cross-schema joins or foreign keys; then, only once the queries are clean, its own
> database instance. The moment you split the database you lose joins and cross-service
> transactions, and you replace them with API calls, replicated read models and sagas —
> that's the real cost. And I'd cite Segment as the cautionary case: they went to over
> 140 services with a small team, drowned in operational overhead and dependency drift,
> and in 2017 deliberately consolidated back into a single service. Going back is a
> legitimate outcome, not a failure.

### Mental model

```
STRANGLER FIG — the facade is the whole trick

 phase 0   client ──► MONOLITH ──► DB

 phase 1   client ──► FACADE ──┬──► MONOLITH ──► DB
                     (router)  └──► (nothing yet)

 phase 2   client ──► FACADE ──┬──► MONOLITH ──────► DB
                               └──► search-svc ──► own index
                                   (1% → 50% → 100%, revert = routing change)

 phase 3   client ──► FACADE ──┬──► monolith (shrinking)
                               ├──► search-svc
                               └──► notify-svc

 The monolith is strangled: it shrinks until what remains is either
 genuinely cohesive (keep it) or small enough to finish off.
```

**Choosing the seam.** Score candidates on three axes and cut the highest total:

| Axis | Good candidate | Bad candidate |
|---|---|---|
| Coupling to the rest | Few inbound calls, no shared tables | Sits in the middle of every write path |
| Rate of change | Changes weekly (payoff is real) | Hasn't changed in two years (no payoff) |
| Ownership | One team clearly owns it | Four teams touch it |
| Data | Owns a self-contained set of tables | Joined to everything |

Notifications, search, reporting, media processing and document ingestion score well.
"The order service" almost never does, which is why teams that start there stall.

**Database decomposition — the actual hard part:**

```
STAGE 1  shared database, shared schema
   orders-svc ──┐
   billing-svc ─┼──► one DB, one schema, everyone SELECTs everything
   catalog-svc ─┘
   ✗ not microservices — a schema change breaks three deploys

STAGE 2  schema per service, same physical database
   orders-svc ───► schema: orders   ┐
   billing-svc ──► schema: billing  ├─ one Postgres instance
   catalog-svc ──► schema: catalog  ┘
   rules: no cross-schema JOINs, no cross-schema FOREIGN KEYs,
          per-schema DB roles so it's enforced not requested
   ✓ this stage is where 80% of the work is, and it's reversible

STAGE 3  database per service
   orders-svc ───► Postgres A
   billing-svc ──► Postgres B
   catalog-svc ──► Postgres C   (or DynamoDB, or Elasticsearch — now you
                                 can pick per workload)
   you have now permanently lost: joins, cross-service transactions,
   and a single point to run analytics against
```

Stage 2 is the one to emphasise in an interview. It is cheap, reversible, and it forces
you to discover every illegal join *before* you've committed to separate infrastructure.
Most teams that "failed at microservices" skipped it.

### Enterprise production example

**Segment** (now Twilio Segment) published the most useful public reversal story, and
Aalok should know its details. Segment's product routes customer events to hundreds of
third-party destinations. They split their event pipeline into one microservice and one
queue per destination — which genuinely helped at first, because one misbehaving
destination could no longer block the others. But by early 2017 they had **over 140
services, queues and repos** maintained by a small team. Their published account of what
broke:

- **Dependency drift.** Each of the 140+ repos had its own versions of shared libraries.
  Improving a shared library meant deploying 140+ services.
- **Operational overhead.** The on-call engineer was routinely paged for load spikes.
  Their engineering lead's words were that they were "literally losing sleep over it".
- **Resource inefficiency.** Low-traffic destinations sat idle while high-traffic ones
  struggled; per-destination autoscaling could not smooth the spikes.
- **Velocity collapse.** "As our velocity plummeted, our defect rate exploded."

Their fix was **Centrifuge**, which replaced the per-destination queues with virtualised
per-customer-per-destination queues feeding a **single monolithic service**, plus a
consolidation of all destination code into one repository with one version of every
dependency. They also built a **Traffic Recorder** to record and replay real destination
traffic so the test suite ran in milliseconds instead of requiring live network calls.
The rollout took roughly five months from design to first traffic. Their conclusion, in
their own words: "In some parts of our infrastructure, microservices work well but our
server-side destinations were a perfect example of how this popular trend can actually
hurt productivity and performance."

The lesson to state out loud: **microservices solve an organisational scaling problem.
Segment had ~15 engineers and hundreds of services — the ratio was the bug.**

### Code

```python
# facade.py — the strangler routing layer, with per-capability percentage
# rollout and automatic fallback to the monolith on failure.
import os, hashlib
import httpx
from fastapi import FastAPI, Request, Response

app = FastAPI()
MONOLITH = "http://monolith.internal"
ROUTES = {                     # capability prefix -> (new service, % traffic)
    "/api/search":        ("http://search-svc.internal",  100),
    "/api/notifications": ("http://notify-svc.internal",   25),
}
_client = httpx.AsyncClient(timeout=httpx.Timeout(5.0, connect=0.5))


def _target(path: str, routing_key: str) -> str:
    for prefix, (upstream, pct) in ROUTES.items():
        if path.startswith(prefix):
            # Stable per-user bucketing: a given user always gets the same
            # side of the split, so they never see inconsistent behaviour.
            bucket = int(hashlib.sha256(routing_key.encode()).hexdigest()[:8], 16) % 100
            return upstream if bucket < pct else MONOLITH
    return MONOLITH


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(path: str, request: Request) -> Response:
    routing_key = request.headers.get("X-User-Id", request.client.host)
    upstream = _target(request.url.path, routing_key)
    body = await request.body()
    try:
        resp = await _client.request(
            request.method, f"{upstream}{request.url.path}",
            content=body, headers=dict(request.headers), params=request.query_params)
    except (httpx.TimeoutException, httpx.ConnectError):
        if upstream == MONOLITH:
            raise
        # New service is down: fall back to the monolith, which still has
        # the code. This safety net is why strangler migrations are low-risk
        # — but it only works while the monolith path is still live.
        resp = await _client.request(
            request.method, f"{MONOLITH}{request.url.path}",
            content=body, headers=dict(request.headers), params=request.query_params)
    return Response(resp.content, status_code=resp.status_code,
                    headers={k: v for k, v in resp.headers.items()
                             if k.lower() not in ("content-length", "transfer-encoding")})
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Strangler fig for any live migration | Big-bang rewrite of a running system | A facade to build and operate; a long dual period |
| Schema-per-service as the first data step | Jumping straight to database-per-service | Discovering illegal joins later, expensively |
| Dual-run with fallback to the monolith | Deleting the old path on day one | Double compute during the migration window |

### Follow-ups they will ask

**Q: You've extracted a service but it still needs a join against the monolith's tables. Now what?**
A: Three options in order of preference. Replicate the data you need into the new
service's store via events or CDC and join locally — best for read-heavy access. Call the
monolith's API per request — simplest, but adds latency and a hard dependency. Or accept
that the boundary was wrong and merge them back. The one thing I won't do is let the new
service reach into the monolith's tables, because that recreates the coupling with
network latency added.

**Q: How do you verify the new service behaves identically before cutting over?**
A: Shadow traffic. Mirror real requests to the new service, discard its responses, and
diff them against the monolith's — same input, compare output. It catches behavioural
drift with zero user risk, provided the shadowed path is side-effect free. That's
essentially what Segment's Traffic Recorder did for their destination tests.

**Q: How long should the dual-running period be?**
A: Long enough to cover a full business cycle — month-end, a peak sales day, a batch
run — because those are when the edge cases show up. And bounded: I'd set an explicit
deletion date for the old path when I start, because "we'll clean it up later" is how you
end up with two implementations forever and a bug fixed in only one of them.

**Q: When is going back to a monolith the right call?**
A: When the service count exceeds what the team can operate — Segment's ratio of
hundreds of services to ~15 engineers is the clearest published example — or when the
services are so chatty and co-deployed that you're paying network costs for no autonomy.
Consolidating is a legitimate architectural decision, not an admission of defeat.

### Red flags — do not say this

- ❌ "We'd rewrite it as microservices." → ✅ "We'd strangle it: facade in front, one
  capability at a time, monolith stays live and is the fallback."
- ❌ "Splitting the code is the hard part." → ✅ "Splitting the data is the hard part —
  the code split is a refactor, the data split is irreversible."

---

## 12.5 Service communication

> **One-liner:** Synchronous when the caller genuinely cannot proceed without the answer;
> asynchronous for everything else — and know that ten sequential calls at 20 ms p99 do
> not produce a 200 ms p99, they produce a much worse *body* of the distribution.

### Say this in the interview

> The first question is whether the caller needs the answer to continue. If yes — reading
> data to render a response, validating a payment before confirming an order — it's
> synchronous, and I'd use REST at the edge and gRPC internally where the contract is
> strict and the latency matters. If no — sending an email, updating a search index,
> triggering analytics — it's an event, because publishing is fast, it decouples the
> deploy schedules, and the consumer can be down without failing the user's request. The
> second question is orchestration versus choreography. Orchestration means one service
> owns the workflow and calls the others in order: you can see the whole flow in one
> place and debug it, at the cost of the orchestrator knowing about everybody.
> Choreography means services react to each other's events with no central brain: maximum
> decoupling, but no one can tell you what the current state of an order is without
> replaying events across five services. For anything with money or a support team, I
> pick orchestration. The third thing I'd raise unprompted is tail amplification. If a
> request fans out to ten services and each has a 1% chance of being slow, the chance
> that at least one is slow is about 10%, so your service's p90 is now your dependency's
> p99. Jeff Dean's numbers from Google make this concrete: touch a hundred servers where
> 1% of calls exceed a second, and 63% of your requests exceed a second.

### Mental model

```
SYNCHRONOUS (request/response)          ASYNCHRONOUS (event)
  A ──request──► B                        A ──publish──► [broker] ──► B
    ◄─response──                          A returns immediately
  · caller blocked on B's latency         · caller unaffected by B
  · B down ⇒ A fails (unless fallback)    · B down ⇒ messages queue
  · A's availability ≤ B's                · A's availability independent
  · easy to reason about, easy to trace   · eventual consistency; ordering,
  · latency and failure compose badly       duplicates, DLQs are now yours
```

| Choose | When |
|---|---|
| REST/HTTP | Public APIs, browser clients, cacheable reads, human-debuggable |
| gRPC | Internal service-to-service, strict contract, streaming, low latency — roughly 3–6× faster serialization and 50–85% smaller payloads than JSON for typical mixed messages |
| Events (Kafka/Pub/Sub) | Fire-and-forget, fan-out to many consumers, buffering, replay |
| Queue (SQS/RabbitMQ) | Work distribution to a pool, retries, DLQ semantics |

**Orchestration vs choreography:**

```
ORCHESTRATION                        CHOREOGRAPHY
   ┌──────────────┐                    order-svc
   │ order-saga   │                       │ emits OrderCreated
   │ (owns flow)  │                       ▼
   └──┬───┬───┬───┘                   ┌───────┐
      │   │   │                       │ topic │
      ▼   ▼   ▼                       └┬──┬──┬┘
   pay inv ship                        ▼  ▼  ▼
                                      pay inv ship  (each emits its own)
 + the flow is in ONE place          + zero central coupling
 + easy to see current state         + add a consumer without touching anyone
 + compensations are explicit        − no single place shows the flow
 − orchestrator knows everyone       − "why didn't this order ship?" is a
 − it can become a god service         five-service archaeology exercise
```

**Chatty services and tail amplification** — the piece that separates senior answers:

```
SEQUENTIAL FAN-OUT: 10 calls, each p99 = 20 ms, each mean = 5 ms

  ✗ naive:  "p99 = 10 × 20 ms = 200 ms"
  Why that's wrong: the p99 of a SUM is not the sum of the p99s. It's
  unlikely all ten calls are simultaneously at their own 99th percentile,
  so the sum concentrates — the total's p99 is far below 200 ms.

  ✓ what actually happens: P(at least one call is above its p99)
                         = 1 − 0.99¹⁰ = 9.6%
  So ~1 request in 10 contains a slow call. The dependency's TAIL has
  become your service's BODY: your p90 is now driven by their p99.

PARALLEL FAN-OUT: same 10 calls, issued concurrently, wait for all
  total latency = MAX of the ten, not the sum
  → mean improves enormously, but the tail gets WORSE:
    the max of 10 samples is above the p99 9.6% of the time.

GOOGLE'S NUMBER (Dean & Barroso, "The Tail at Scale", CACM 2013):
  1% of calls take > 1 s, request touches 100 servers
  → 1 − 0.99¹⁰⁰ = 63% of user requests take > 1 s.
```

The practical conclusions to state: reduce the number of calls on the request path
(batch, or denormalise into a local read model); make them parallel when they're
independent; set per-call timeouts *below* your own SLO so one slow dependency can't
consume your budget; and use hedged requests — issue a second copy after the p95 and
take the first response — for read-only calls where the tail matters more than the extra
load.

### Enterprise production example

**Uber's** DOMA gateways exist partly for this reason: before DOMA, a product team
needing a domain's functionality had to call numerous downstream services individually;
after, they call one gateway. Collapsing an N-call fan-out into one call is not just an
ergonomics win, it removes N−1 opportunities for a tail event to land in the request
path. When they classified 2,200 microservices into ~70 domains, the practical effect on
the request path was fewer hops per user request.

### Code

```python
# fanout.py — parallel calls, per-call timeouts under the service SLO,
# and graceful degradation instead of total failure.
import asyncio
import httpx
from dataclasses import dataclass

SERVICE_SLO_MS = 300          # our own p99 budget
PER_CALL_TIMEOUT = 0.12       # 120 ms: two parallel calls fit inside the SLO


@dataclass
class ProductView:
    product: dict
    price: dict | None        # None => degraded, we show "price unavailable"
    reviews: list | None       # None => degraded, we hide the reviews block


async def _get(client: httpx.AsyncClient, url: str) -> dict | None:
    try:
        r = await client.get(url, timeout=PER_CALL_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (httpx.TimeoutException, httpx.HTTPStatusError):
        return None            # degrade this field; do NOT fail the request


async def build_product_view(pid: str, client: httpx.AsyncClient) -> ProductView:
    # Parallel, not sequential: total latency is the max, not the sum.
    product, price, reviews = await asyncio.gather(
        _get(client, f"http://catalog.internal/products/{pid}"),
        _get(client, f"http://pricing.internal/prices/{pid}"),
        _get(client, f"http://reviews.internal/products/{pid}/reviews?limit=5"),
    )
    if product is None:
        raise RuntimeError("catalog is the critical dependency; fail loudly")
    return ProductView(product=product, price=price, reviews=reviews)
```

```python
# hedged.py — hedge a read after the p95 to cut the tail. Costs ~5% extra
# load; only ever do this for idempotent reads.
async def hedged_get(client: httpx.AsyncClient, url: str, p95: float = 0.05) -> dict:
    first = asyncio.create_task(client.get(url, timeout=PER_CALL_TIMEOUT))
    done, _ = await asyncio.wait({first}, timeout=p95)
    if done:
        return first.result().json()
    second = asyncio.create_task(client.get(url, timeout=PER_CALL_TIMEOUT))
    done, pending = await asyncio.wait({first, second},
                                       return_when=asyncio.FIRST_COMPLETED)
    for task in pending:
        task.cancel()
    return done.pop().result().json()
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Sync REST/gRPC: caller needs the answer now | Notifications, indexing, analytics | Availability multiplies; latency adds |
| Async events: fire-and-forget, fan-out | The user must see the result immediately | Eventual consistency, duplicates, DLQ ops |
| Orchestration: money, support-visible flows | Simple pub/sub notifications | The orchestrator becomes a coupling point |
| Choreography: loose coupling, many consumers | You need to answer "what's the state?" | No single view of the workflow |

### Follow-ups they will ask

**Q: Ten sequential calls, each with a 20 ms p99. What's the request p99?**
A: Not 200 ms. The sum of ten independent latencies concentrates around the sum of the
*means*, so if the mean is 5 ms the total mean is 50 ms and the p99 of the sum is well
under 200 ms. What actually degrades is the body of the distribution: the probability
that at least one call hits its p99 is 1 − 0.99¹⁰ ≈ 9.6%, so roughly one request in ten
now contains a slow call. The dependency's tail becomes my p90.

**Q: How do you set timeouts across a chain?**
A: Budget from the outside in. If my SLO is 300 ms, the edge gets a 300 ms deadline and
each hop passes the *remaining* budget downstream rather than each hop having its own
independent 5-second default. gRPC deadlines propagate this natively; with HTTP I pass a
deadline header and compute the remainder. Independent per-hop timeouts that sum to more
than the SLO mean the client has already given up while five services are still working.

**Q: When would you pick gRPC over REST internally?**
A: When the contract is strict and shared between teams, when payloads are numeric- or
enum-heavy (protobuf is roughly 4–5× smaller than JSON there, versus only marginally
smaller for string-heavy payloads), when I need bidirectional streaming, or when
serialization CPU shows up in profiles at high RPS. I'd stay on REST at the edge for
browser clients, cacheability, and debuggability with curl.

**Q: An event consumer is down for four hours. What happens?**
A: With Kafka or Pub/Sub, nothing is lost — messages accumulate and the consumer catches
up, which is the main reason to prefer a log over a fire-and-forget call. What I check
is whether the backlog exceeds the retention window (then you *do* lose data), whether
the catch-up burst will overwhelm a downstream (rate-limit the consumer on recovery), and
whether ordering matters, because parallel catch-up can reorder within a partition key.

**Q: How do you avoid a synchronous chain five deep?**
A: Flatten it. Either the top service calls the leaves directly in parallel, or the
intermediate services publish events and each maintains a local read model so the data
is already there. Chains form when each service asks the next for data it could have
kept a copy of — see [12.9](#129-data-ownership).

### Red flags — do not say this

- ❌ "We'd use events everywhere for loose coupling." → ✅ "Events where the caller
  doesn't need the answer; synchronous where it does. Making a read asynchronous just
  moves the wait into the client."
- ❌ "Ten 20 ms calls means 200 ms." → ✅ "The sum concentrates below that, but the
  probability of hitting at least one slow call is about 10%, so their p99 becomes my
  p90."

---

## 12.6 Service discovery

> **One-liner:** How a caller finds a healthy instance of a callee — and in 2026 the
> answer is almost always "Kubernetes Services", with the older registries worth knowing
> because interviewers name them.

### Say this in the interview

> Service discovery answers "what IP and port should I send this to, right now, given
> instances are constantly being created and destroyed?" There are two shapes. In
> client-side discovery the client queries a registry, gets the list of healthy
> instances, and load-balances itself — Netflix's Eureka plus Ribbon is the classic
> example. It's efficient because there's no extra network hop, but every client needs
> the registry library, which means language lock-in and a redeploy to change the load-
> balancing policy. In server-side discovery the client talks to a stable address and
> something in the path — a load balancer or a proxy — does the lookup. That's simpler
> for clients and language-agnostic, at the cost of one extra hop. Kubernetes is
> server-side discovery with the registry built in: a Service gets a stable ClusterIP
> and DNS name, the endpoint controller keeps an EndpointSlice of ready pod IPs, and
> kube-proxy or the CNI programs the routing. That's why I wouldn't deploy Consul or
> Eureka on a new project — the platform already does it. The gotcha I watch for is DNS
> caching: JVM clients and some HTTP libraries cache resolutions indefinitely and keep
> hitting a pod that no longer exists.

### Mental model

```
CLIENT-SIDE (Eureka + Ribbon)          SERVER-SIDE (K8s Service, ALB)
  ┌────────┐  1. "where is billing?"     ┌────────┐
  │ client │ ──────► ┌──────────┐        │ client │ ──► billing.svc:80
  │        │ ◄────── │ registry │        └────────┘         │
  │        │  [ip1,  └──────────┘                           ▼
  │  LB in │   ip2,       ▲                          ┌─────────────┐
  │ client │   ip3]       │ register+heartbeat       │ LB / proxy  │
  └───┬────┘             ip1 ip2 ip3                 │ (does the   │
      │ 2. pick one                                  │  lookup)    │
      └──────────► ip2                               └──┬──┬──┬────┘
                                                        ▼  ▼  ▼
  + no extra hop, client controls policy               ip1 ip2 ip3
  − a library per language; redeploy to change      + language-agnostic, thin
                                                    − one extra hop
```

| Mechanism | How it works | Watch out for |
|---|---|---|
| **Kubernetes Service** | ClusterIP + CoreDNS + EndpointSlice of ready pods | DNS caching in clients; `publishNotReadyAddresses` |
| **Headless Service** | DNS returns all pod IPs, no virtual IP | Client must load-balance; used by StatefulSets |
| **Consul** | Agent per node, health checks, KV store, DNS + HTTP API | Operational burden; you're running a cluster |
| **Eureka** | AP registry, client-side, self-preservation mode | Java-centric; Netflix-era ecosystem |
| **etcd / ZooKeeper** | Strongly consistent KV; the primitive under others | CP means it can refuse writes during a partition |
| **Plain DNS** | A/SRV records with a TTL | TTL granularity; clients ignoring TTLs |

**The DNS-caching trap**, which is the part with a real production story attached: many
HTTP clients and the JVM's default `networkaddress.cache.ttl` cache resolutions well
past the record's TTL. Pods get replaced, the IP is reassigned or goes dark, and the
client keeps dialling a dead address until it's restarted. Fixes: bound connection
lifetime (`keepalive` max age), set the JVM TTL explicitly, or use a client that
re-resolves per connection.

**Discovery is not enough on its own.** You still need health checking (only *ready*
endpoints get traffic — see
[Module 11 — health checks](./11_Observability_And_SRE.md#116-health-checks--graceful-shutdown)),
load-balancing policy, and outlier detection to eject an instance that resolves fine but
returns errors.

### Enterprise production example

**Netflix** built and open-sourced the client-side stack — **Eureka** for the registry,
**Ribbon** for client-side load balancing, and **Zuul** at the edge — and a Netflix
engineer stated on Eureka's issue tracker that "both Zuul (specifically version 2) and
Eureka are core products for Netflix and almost all traffic that comes in touches both".
Zuul's routing filter resolves a service name through Eureka and Ribbon picks an
instance, which means adding pods requires no gateway configuration change at all. The
reason most teams no longer build this: Kubernetes ships the equivalent, and the
client-library approach binds every service to one language ecosystem.

### Code

```yaml
# The modern default: no registry to operate, discovery is DNS + endpoints.
apiVersion: v1
kind: Service
metadata: {name: billing}
spec:
  selector: {app: billing}       # membership = label match + readiness
  ports: [{port: 80, targetPort: 8000}]
# Callers just use: http://billing.default.svc.cluster.local  (or http://billing)
# The EndpointSlice controller keeps the ready-pod list current; kube-proxy or
# the CNI programs the dataplane. Nothing to register, nothing to heartbeat.
---
apiVersion: v1
kind: Service
metadata: {name: billing-headless}
spec:
  clusterIP: None                # headless: DNS returns every pod IP
  selector: {app: billing}       # use when the CLIENT must do the balancing,
  ports: [{port: 8000}]          # e.g. gRPC round-robin over a stable set
```

```python
# The gRPC caveat: HTTP/2 multiplexes on ONE connection, so a ClusterIP
# Service load-balances the CONNECTION, not the requests — all your traffic
# pins to one pod. Fix: headless service + client-side round-robin.
import grpc

channel = grpc.aio.insecure_channel(
    "dns:///billing-headless.default.svc.cluster.local:8000",
    options=[("grpc.lb_policy_name", "round_robin"),
             ("grpc.enable_retries", 1),
             ("grpc.keepalive_time_ms", 30000)],
)
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Kubernetes Services (default) | Multi-cluster/multi-cloud without a mesh | Nothing; it's already there |
| Headless + client LB for gRPC | HTTP/1.1 traffic (ClusterIP is fine) | Client must implement the policy |
| Consul | You're on Kubernetes already | A cluster to run, patch and page on |

### Follow-ups they will ask

**Q: Why does gRPC load-balance badly through a normal Kubernetes Service?**
A: Because kube-proxy balances at the connection level and gRPC multiplexes many
requests over a single long-lived HTTP/2 connection. One connection means one pod gets
everything. The fixes are a headless Service with client-side `round_robin`, an L7 proxy
that understands HTTP/2, or a service mesh sidecar doing per-request balancing.

**Q: A pod is deleted. How long until traffic stops going to it?**
A: Not instantly — the EndpointSlice update and the kube-proxy programming on every node
happen asynchronously and in parallel with the pod's shutdown. That gap is exactly why
you need a `preStop` sleep; see
[Module 11 — health checks](./11_Observability_And_SRE.md#116-health-checks--graceful-shutdown).

**Q: How does discovery work across clusters or regions?**
A: Not by default. You need either a multi-cluster service mesh, a global load balancer
with backends in both clusters, or an external DNS/registry federating the two. This is
one of the few places a mesh earns its keep, and it's also where people reach for Consul.

### Red flags — do not say this

- ❌ "We'd use Eureka for service discovery." (on a new K8s project) → ✅ "Kubernetes
  Services give us discovery, health-gated endpoints and DNS with nothing to operate."
- ❌ "Service discovery handles load balancing." → ✅ "Discovery tells you the healthy
  set; you still choose a balancing policy and outlier detection."

---

## 12.7 Service mesh

> **One-liner:** A sidecar proxy next to every service that takes over mTLS, retries,
> circuit breaking, traffic splitting and telemetry — real capability, real per-hop
> latency, and real operational weight.

### Say this in the interview

> A service mesh moves cross-cutting network concerns out of your application and into a
> proxy — classically an Envoy sidecar in every pod, with a control plane configuring
> them. What you get is mutual TLS between every service without touching application
> code, uniform retries and timeouts and circuit breaking, percentage-based traffic
> splitting for canaries, and consistent L7 telemetry for every hop whether or not the
> service was instrumented. The cost is honest and measurable: Istio's own benchmarks at
> 1,000 requests per second with a 1 KB payload put sidecar-mode p90 latency around 0.63
> to 0.88 milliseconds added per request, with each sidecar consuming roughly 0.2 vCPU
> and 60 MB of memory — on a cluster with a few hundred pods that's tens of cores spent
> on proxies. Ambient mode changes that arithmetic: a shared per-node ztunnel handles
> L4, costing about 0.06 vCPU and 12 MB per node and adding around 0.17 to 0.20
> milliseconds, and you only pay for an L7 waypoint proxy in namespaces that need it.
> My default at mid-scale is: not a mesh. A shared client library or a gateway covers
> retries and timeouts for a handful of services. I'd adopt a mesh when I need mTLS
> everywhere for compliance, or when I have enough services in enough languages that a
> library stops being viable.

### Mental model

```
SIDECAR MODE                          AMBIENT MODE
 ┌── pod A ─────────┐                  ┌── pod A ──┐   ┌── pod B ──┐
 │ app │ envoy ◄────┼──┐               │    app    │   │    app    │
 └─────┴───────┘    │  │               └─────┬─────┘   └─────▲─────┘
        │  mTLS     │  │ control             │  ┌───────────┐│
        ▼           │  │ plane          node │  │ ztunnel   ││ node
 ┌── pod B ─────────┐  │ (istiod)       ─────┴──┤ (shared,  ├┴─────
 │ envoy │ app │    │◄─┘                        │  DaemonSet)│
 └───────┴─────┘    │                           └───────────┘
                                        + optional waypoint for L7
 2 proxies per request                  2 ztunnel hops (L4) or +1 waypoint
 0.20 vCPU / 60 MB PER POD              0.06 vCPU / 12 MB PER NODE
 p90 ≈ 0.63–0.88 ms added               p90 ≈ 0.16–0.20 ms (L4)
                                        waypoint adds 0.40–0.50 ms (L7)
```

All figures above are from Istio's published performance documentation (Istio 1.24,
1,000 rps, 1 KB HTTP/1.1 payloads, mTLS enabled). A waypoint proxy costs about 0.25 vCPU
and 60 MB, but there's one per namespace rather than one per pod.

**What the mesh actually gives you:**

| Capability | Without a mesh | With a mesh |
|---|---|---|
| mTLS between services | TLS config in every service | Automatic, with cert rotation |
| Retries / timeouts / circuit breaking | Per-language library, redeploy to change | Config, applies instantly, uniform |
| Traffic splitting (canary) | LB weights or a custom router | Declarative `VirtualService` weights |
| L7 telemetry per hop | Instrument every service | Free, uniform, even for uninstrumented apps |
| Authorization policy | In every service | Declarative, centrally auditable |

**Mesh vs library vs gateway:**

```
GATEWAY (Kong, Envoy Gateway, ALB)   north-south only: client → cluster.
   Does auth, rate limiting, TLS termination, routing at the edge.
   Says nothing about service-to-service traffic.

LIBRARY (resilience4j, tenacity, opossum)  in-process.
   + zero latency overhead, full app context
   − one per language; upgrading policy = redeploying everything

MESH                                  east-west: service → service.
   + language-agnostic, config-driven, uniform
   − latency per hop, a control plane to run, hard debugging
     (is the 503 from my app, my sidecar, or theirs?)
```

### Enterprise production example

**Istio's** own performance documentation is the honest source here, and quoting it is
better than quoting a vendor claim. At 1,000 rps with 1 KB payloads and mTLS on: a
sidecar with 2 worker threads is about **0.20 vCPU and 60 MB**; a waypoint about **0.25
vCPU and 60 MB**; a ztunnel about **0.06 vCPU and 12 MB**. Latency added, p90 to p99:
sidecar **0.63–0.88 ms**, ambient L4 **0.16–0.20 ms**, waypoint adds a further
**0.40–0.50 ms**. Istio itself frames the design rationale plainly: "the overhead for
processing protocols at Layer 7 is substantially higher than processing network packets
at Layer 4. For a given service, if your requirements can be met at L4, service mesh can
be delivered at substantially lower cost." That is the argument for ambient in one
sentence, and it's why "do you need L7 features on this namespace?" became the design
question rather than "mesh or no mesh".

Do the arithmetic in the interview: 300 pods × 0.20 vCPU = 60 vCPU of proxy, versus 20
nodes × 0.06 = 1.2 vCPU for ztunnels. That is a real line item.

### Code

```yaml
# What the mesh buys you that a library can't do without a redeploy:
# a canary defined declaratively, adjustable in seconds.
apiVersion: networking.istio.io/v1
kind: VirtualService
metadata: {name: rag-api}
spec:
  hosts: [rag-api]
  http:
    - match: [{headers: {x-canary: {exact: "true"}}}]
      route: [{destination: {host: rag-api, subset: v2}}]   # opt-in testers
    - route:
        - {destination: {host: rag-api, subset: v1}, weight: 95}
        - {destination: {host: rag-api, subset: v2}, weight: 5}
      retries:
        attempts: 2
        perTryTimeout: 500ms
        retryOn: 5xx,reset,connect-failure
      timeout: 1.2s          # must stay under the caller's own SLO budget
---
apiVersion: networking.istio.io/v1
kind: DestinationRule
metadata: {name: rag-api}
spec:
  host: rag-api
  subsets: [{name: v1, labels: {version: v1}}, {name: v2, labels: {version: v2}}]
  trafficPolicy:
    connectionPool:
      http: {http2MaxRequests: 200, maxRequestsPerConnection: 100}
    outlierDetection:          # eject a pod that resolves but returns errors
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50   # never eject more than half — avoids cascading
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| mTLS everywhere for compliance | Under ~10 services, one language | 0.6–0.9 ms/hop sidecar, or 0.2 ms ambient L4 |
| Polyglot services needing uniform policy | You can't staff a control plane | 0.2 vCPU + 60 MB per pod (sidecar mode) |
| Declarative traffic splitting at scale | Latency-critical sub-millisecond paths | Debugging gets harder: whose 503 is it? |

### Follow-ups they will ask

**Q: Can you get mTLS and retries without a mesh?**
A: Yes. mTLS via cert-manager and TLS config in each service, or by terminating at a
gateway and trusting the cluster network; retries and circuit breaking via a library.
That's a perfectly good answer under about ten services. The mesh wins when the number of
services × number of languages makes maintaining libraries more expensive than running a
control plane.

**Q: A request fails with a 503. How do you tell whether it's the app or the mesh?**
A: Envoy's response flags in the access log — `UO` is upstream overflow (circuit breaker
open), `UF` upstream connection failure, `URX` retry limit exceeded, `NR` no route. That's
the first thing I check, and it's also the concrete answer to "meshes make debugging
harder": the information is there, but it's a new vocabulary the whole team has to learn.

**Q: Sidecar or ambient for a new cluster?**
A: Ambient, unless I need per-pod L7 policy everywhere. The resource arithmetic is
decisive at scale — per-node instead of per-pod — and I can enable waypoints for the
namespaces that genuinely need L7. Istio has documented ambient as production-ready for
single-cluster use since 1.22.

**Q: The mesh adds 0.7 ms per hop. When does that matter?**
A: When the hop count is high or the baseline is low. A 5 ms internal call becoming 5.7 ms
is 14% — irrelevant for a user-facing 300 ms budget, significant for a hot path called
ten times per request, and dominant for something like a cache lookup where the call
itself is 0.5 ms. That's the case for keeping the highest-frequency calls out of the mesh
or on the L4 path.

### Red flags — do not say this

- ❌ "We'd add a service mesh for observability." → ✅ "The mesh gives uniform L7
  telemetry per hop, but it can't see inside the process — I'd still instrument the app
  with OpenTelemetry."
- ❌ "A mesh makes microservices reliable." → ✅ "It makes retry and circuit-breaker
  policy uniform and changeable without a redeploy. Badly-set retries in a mesh cause
  retry storms just as effectively as badly-set retries in code."

---

## 12.8 API composition & the aggregation problem

> **One-liner:** Once data is spread across services, someone has to assemble it — do it
> in a BFF per client type, and watch for the N+1 that now costs a network round trip
> per item instead of a query.

### Say this in the interview

> When you split services, a screen that used to be one join becomes five calls, and
> somebody has to make them. I'd put that in a backend-for-frontend — one aggregation
> service per client type, so the mobile BFF can return a compact payload shaped for a
> phone while the web BFF returns something richer, and neither client is making six
> round trips over a mobile network. The alternative is aggregating in the API gateway,
> which is fine for simple cases but tends to turn the gateway into a place where
> business logic accumulates and every team needs to deploy. GraphQL federation is the
> heavier option: each service owns a slice of one schema, a router plans the query
> across them, and clients ask for exactly the fields they need — good when you have
> many clients with genuinely different data needs, at the cost of a router to operate
> and the caching and query-cost problems GraphQL brings. The failure mode I watch for
> is N+1 across services: fetch fifty orders, then call the user service once per order
> to get the buyer's name. In a monolith that's a bad join; across services it's fifty
> network round trips, and at a 5 ms p99 each that's 250 milliseconds of pure overhead.
> The fix is a batch endpoint — `GET /users?ids=1,2,3` — plus a request-scoped loader
> that coalesces and dedupes the calls.

### Mental model

```
NO AGGREGATION (chatty client)      BFF (aggregate server-side)
  mobile ──► catalog                  mobile ──► mobile-BFF ─┬─► catalog
  mobile ──► pricing                                         ├─► pricing
  mobile ──► reviews                  web ──► web-BFF ───────┼─► reviews
  mobile ──► inventory                                       └─► inventory
  4 round trips over a 60 ms          1 round trip; the fan-out happens
  mobile RTT = 240 ms                 in-datacentre in parallel (~15 ms)
  + client controls everything        + one payload, shaped per client
  − latency, battery, versioning      − a service per client type to own
```

**The N+1 across services:**

```
✗ BAD                                    ✓ GOOD
  orders = GET /orders?limit=50            orders = GET /orders?limit=50
  for o in orders:                         ids = {o.user_id for o in orders}
      GET /users/{o.user_id}               users = GET /users?ids=<batch>
  ────────────────────────────             ──────────────────────────────
  1 + 50 calls                             1 + 1 calls  (or 1 + ceil(n/100))
  @ 5 ms p99 each ≈ 255 ms                 ≈ 10 ms
  and 50 chances to hit a tail event       and 1
```

| Approach | Best for | Cost |
|---|---|---|
| **BFF** | Distinct client types (mobile/web/partner) | One more service per client type to own |
| **Gateway aggregation** | A few simple compositions | Gateway accretes business logic; shared deploy |
| **GraphQL federation** | Many clients, many overlapping entities | A router to operate; caching and cost-limiting |
| **Client-side composition** | Internal tools, low latency to services | Chatty over WAN; every client reimplements it |

**GraphQL federation** in one picture:

```
   client ──query{ order { id, buyer { name }, items { title } } }──►
                            │
                    ┌───────▼────────┐
                    │ federated      │  plans and stitches
                    │ router         │
                    └──┬────┬────┬───┘
        orders-svc ◄───┘    │    └───► catalog-svc
         @key(id)           ▼           @key(sku)
                        users-svc
                         @key(id)
   Each service owns its types and resolves references by key.
   The router handles the fan-out — and can itself produce an N+1
   unless each subgraph implements batched reference resolution.
```

### Enterprise production example

The **BFF pattern** originates from SoundCloud's move off a monolithic API, and was
popularised by Sam Newman: one general-purpose API tried to serve web, iOS and Android
simultaneously and ended up serving none of them well — every client got fields it didn't
need, and every client change required a change to the shared API owned by another team.
Splitting into a BFF per client type let each front-end team own its own aggregation
layer and iterate at its own pace. The trade they accepted is duplicated aggregation
logic across BFFs, which they judged cheaper than the coordination cost of one shared
API.

### Code

```python
# loader.py — request-scoped batching + dedupe. This is the fix for cross-
# service N+1, and it's the same idea as DataLoader in the GraphQL world.
import asyncio
from collections import defaultdict
import httpx

BATCH_WINDOW_S = 0.005      # 5 ms: enough to collect a page's worth of ids
MAX_BATCH = 100             # keep URLs and upstream queries bounded


class UserLoader:
    """One instance per request. Never share across requests — you'd leak
    one user's data into another's response."""

    def __init__(self, client: httpx.AsyncClient):
        self._client = client
        self._pending: dict[str, asyncio.Future] = {}
        self._flush_task: asyncio.Task | None = None

    async def load(self, user_id: str) -> dict:
        if user_id in self._pending:              # dedupe within the request
            return await self._pending[user_id]
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[user_id] = fut
        if self._flush_task is None:
            self._flush_task = asyncio.create_task(self._flush_soon())
        return await fut

    async def _flush_soon(self) -> None:
        await asyncio.sleep(BATCH_WINDOW_S)
        pending, self._pending, self._flush_task = self._pending, {}, None
        ids = list(pending)
        for chunk in (ids[i:i + MAX_BATCH] for i in range(0, len(ids), MAX_BATCH)):
            try:
                r = await self._client.get("http://users.internal/users",
                                           params={"ids": ",".join(chunk)},
                                           timeout=0.15)
                r.raise_for_status()
                found = {u["id"]: u for u in r.json()["users"]}
            except Exception as exc:
                for uid in chunk:
                    pending[uid].set_exception(exc)
                continue
            for uid in chunk:
                # Missing user is a value, not an error — a deleted account
                # shouldn't fail the whole order list.
                pending[uid].set_result(found.get(uid, {"id": uid, "name": None}))
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| BFF per client type | One client, simple payloads | A service per client to own and deploy |
| Batch endpoints + loaders | Per-item calls in a loop | Batch endpoints need pagination and limits |
| GraphQL federation | Few clients, stable payloads | Router ops; HTTP caching mostly stops working |

### Follow-ups they will ask

**Q: The BFF calls six services and one is slow. What does the user see?**
A: Whatever I designed them to see. I'd classify dependencies as critical or optional:
the product must render, so catalog failing is a 503; price and reviews are optional, so
their failures return `null` and the UI hides or greys those blocks. Every optional call
gets a timeout well inside the BFF's own budget. Without that classification, a
non-essential reviews service takes down the product page.

**Q: Doesn't a BFF become a distributed monolith of its own?**
A: It can, if one BFF serves every client and every team must change it. The discipline
is one BFF per client type, owned by that client's team, containing only aggregation and
shaping — no business rules. The moment domain logic appears in a BFF, it belongs in the
owning service instead.

**Q: How do you cache aggregated responses?**
A: At the pieces, not the whole. Caching the composed response gives you a low hit rate
(any component changing invalidates everything) and a permissions hazard. I cache each
upstream response by its own key and TTL, so the pricing call can be cached for 60
seconds while the inventory call isn't cached at all, and the BFF assembles fresh each
time from mostly-warm parts.

### Red flags — do not say this

- ❌ "The client can just call the services directly." → ✅ "Over a mobile network at
  60 ms RTT, four sequential calls is a quarter of a second before any work happens — I'd
  aggregate server-side."
- ❌ "GraphQL solves over-fetching so we should use it." → ✅ "It solves over-fetching and
  creates a caching and query-cost problem. Worth it with many heterogeneous clients, not
  worth it for one web app."

---

## 12.9 Data ownership

> **One-liner:** Exactly one service may write a given piece of data; everyone else gets
> it by API call, by a replicated read model kept current with events, or by CDC — and
> never by reading someone else's tables.

### Say this in the interview

> The rule that makes microservices actually work is that each service owns its data and
> nobody else touches its database. A shared database is the single fastest way to build
> a distributed monolith: the moment two services read the same table, neither can change
> its schema without coordinating, and you've paid for network hops while keeping every
> coupling you had. So how do you get data you don't own? Three ways. Call the owning
> service's API — simplest, always fresh, but it adds latency and your availability now
> multiplies with theirs. Subscribe to their events and keep a local read model — a
> denormalised copy of just the fields you need — which makes reads local and fast and
> survives the owner being down, at the cost of eventual consistency and having to handle
> duplicates and ordering. Or use change data capture, reading their transaction log with
> something like Debezium, which is the pragmatic option when the owning service is legacy
> and can't be modified, though it couples you to their schema rather than a contract.
> My default is: events into a local read model for anything on a hot read path, API calls
> for anything that must be strictly current, like a balance check before a withdrawal.
> And for reference data — country codes, currencies, tax rates — I don't build a service
> at all; I ship it as a versioned library or a table everyone replicates, because a
> network call to look up a currency symbol is absurd.

### Mental model

```
   ✗ SHARED DATABASE                    ✓ OWNED DATA + REPLICATION
   ┌─────────┐ ┌─────────┐              ┌─────────┐        ┌─────────┐
   │ orders  │ │ billing │              │ orders  │        │ billing │
   └────┬────┘ └────┬────┘              └────┬────┘        └────┬────┘
        └─────┬─────┘                        │ owns              │ owns
              ▼                          ┌───▼────┐  events  ┌───▼────┐
        ┌───────────┐                    │ DB(ord)│─────────►│ DB(bil)│
        │  one DB   │                    └────────┘  Order   └────────┘
        └───────────┘                                Created  (+ local copy
   billing's migration breaks                                  of the 3 order
   orders. Neither can move.                                   fields it needs)
```

**The three ways to get data you don't own:**

| Mechanism | Freshness | Availability coupling | Best for |
|---|---|---|---|
| **Synchronous API call** | Always current | Yours ≤ theirs | Must-be-current reads: balance, entitlement, stock at checkout |
| **Event → local read model** | Eventually consistent (ms–s) | None — you serve from your own store | Hot read paths, listing pages, denormalised views |
| **CDC (Debezium etc.)** | Near-real-time | None | Legacy owners you cannot modify |
| **Reference data as a library/table** | Deploy-time or slow-refresh | None | Currencies, countries, tax bands, feature catalogues |

**The local read model** is the pattern to name, because it's what teams actually build:

```
  users-svc                              orders-svc
  ┌──────────────┐                       ┌──────────────────────────────┐
  │ users (owner)│  UserUpdated event    │ orders (owner)               │
  │  id          │ ────────────────────► │ order_user_view (READ MODEL) │
  │  name        │        Kafka          │   user_id  PK                │
  │  email       │                       │   name        ← copied       │
  │  address     │                       │   updated_at  ← for staleness│
  │  preferences │                       │ (NOT email, NOT address —    │
  │  ...30 cols  │                       │  copy only what you render)  │
  └──────────────┘                       └──────────────────────────────┘

  Consequences you must own:
   · eventual consistency — a renamed user shows the old name for ~1 s
   · duplicates — the consumer must be idempotent (upsert by id + version)
   · ordering — out-of-order events must not overwrite newer data
   · bootstrapping — you need a backfill/snapshot for existing users
   · GDPR deletion — a delete event must propagate to every read model
```

That last bullet is a genuinely good thing to raise unprompted: once you replicate
personal data into five services, "delete this user" becomes a distributed operation, and
you need a deletion event with acknowledgement rather than a single `DELETE`.

**The reference-data problem.** Some data is read by everyone, written by almost nobody,
and tiny: currency codes, country lists, tax rates, plan definitions. Building a
`reference-data-service` means every service adds a network call and a new failure mode
to answer "how many decimal places does JPY have?". Better options: ship it as a
versioned library and redeploy on change; or publish it as a compacted Kafka topic every
service materialises into a local table; or just accept a long-TTL cache with a
stale-while-revalidate refresh.

### Enterprise production example

**Amazon's** 2002 API mandate made the rule explicit and non-negotiable: teams communicate
only through service interfaces, and there are to be "no direct reads of another team's
data store, no shared-memory model, no back-doors whatsoever". The reason that clause is
in the mandate at all is that direct database reads are the path of least resistance —
they're faster to write, they're faster at runtime, and they silently destroy the
independence that the whole exercise was for. **Uber's** DOMA extension architecture
addresses the same pressure from the other side: logic and data extensions let a team add
behaviour or fields to a domain without modifying the owning service, which is what teams
would otherwise achieve by reaching into someone else's data.

### Code

```python
# read_model.py — consuming another service's events into a local read model.
# Idempotent, out-of-order safe, and it copies only the fields we render.
import json
from google.cloud import pubsub_v1
import psycopg

UPSERT = """
INSERT INTO order_user_view (user_id, name, source_version, updated_at)
VALUES (%(user_id)s, %(name)s, %(version)s, now())
ON CONFLICT (user_id) DO UPDATE
   SET name = EXCLUDED.name,
       source_version = EXCLUDED.source_version,
       updated_at = now()
 WHERE order_user_view.source_version < EXCLUDED.source_version
"""
# ^ the WHERE clause is the whole trick: an older event that arrives late
#   updates nothing, so out-of-order delivery cannot resurrect stale data.
#   Combined with ON CONFLICT it is also idempotent under redelivery.


def handle(message: pubsub_v1.subscriber.message.Message, conn: psycopg.Connection):
    event = json.loads(message.data)
    try:
        with conn.cursor() as cur:
            if event["type"] == "UserDeleted":
                # GDPR: deletion must propagate to every replica of the data.
                cur.execute("DELETE FROM order_user_view WHERE user_id = %s",
                            (event["user_id"],))
            else:
                cur.execute(UPSERT, {"user_id": event["user_id"],
                                     "name": event["payload"]["name"],
                                     "version": event["version"]})
        conn.commit()
        message.ack()
    except Exception:
        conn.rollback()
        message.nack()          # redelivery is safe: the upsert is idempotent
```

```sql
-- Staleness must be observable, or "eventual" quietly becomes "never".
-- Emit this as a gauge and alert when it exceeds your stated freshness SLO.
SELECT EXTRACT(EPOCH FROM now() - min(updated_at)) AS oldest_row_age_seconds
FROM order_user_view;
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Local read model for hot reads | Data that must be strictly current | Eventual consistency; backfill; GDPR propagation |
| Sync API call for must-be-current | Read paths called on every page load | Latency + availability multiplies |
| CDC for legacy owners | Greenfield services (publish events instead) | Coupling to their schema, not a contract |
| Reference data as a library/table | A `reference-data-service` | Redeploy or refresh lag on change |

### Follow-ups they will ask

**Q: A user renames themselves and their old name shows on the orders page for two seconds. Acceptable?**
A: For a display name, yes — and I'd make it explicit as a freshness SLO ("read models
are within 5 seconds at p99") with a metric on replication lag so it's monitored rather
than assumed. For anything where staleness is a correctness or compliance problem — a
permission, an account balance, a price at checkout — I call the owner synchronously
instead.

**Q: How do you bootstrap a read model for data that existed before you started consuming events?**
A: A snapshot plus a replay. Either the owner exposes a bulk export you load first and
then you consume from a recorded offset, or you use a log-compacted topic that contains
the latest state for every key, so a new consumer replaying from the beginning naturally
gets a full snapshot. Either way the consumer must be idempotent, which the upsert-by-
version pattern already gives you.

**Q: Two services both need to write the same entity. What do you do?**
A: That's a boundary error, not a data-access problem. Either the entity belongs to one
service and the other sends it a command, or the "entity" is really two entities that
happen to share a name — an order in the fulfilment sense and an order in the billing
sense are different aggregates with different lifecycles. Splitting the concept is
usually the right answer.

**Q: How do you run analytics that spans every service's data?**
A: You don't query the services. You stream every service's events, or CDC feeds, into a
warehouse or lakehouse and do analytics there. Letting BI tools query production service
databases directly recreates the shared database with worse access patterns and a report
that can take down checkout.

### Red flags — do not say this

- ❌ "The services share a database for simplicity." → ✅ "Each service owns its schema;
  we replicate what we need via events into local read models."
- ❌ "Eventual consistency is fine, users won't notice." → ✅ "We publish a freshness SLO
  — read models within 5 seconds at p99 — and we alert on replication lag, and anything
  correctness-critical reads from the owner synchronously."

---

## 12.10 Deployment strategies

> **One-liner:** Rolling, blue-green, canary, shadow and feature flags differ in how much
> traffic sees the new version and how fast you can undo it — and none of them roll back
> a database migration, which is why expand/contract is mandatory.

### Say this in the interview

> I pick a deployment strategy based on how fast I need to undo it. Rolling is the
> default — replace pods gradually, both versions serve traffic during the rollout, and
> rollback means rolling forward to the previous image, which takes minutes. Blue-green
> keeps two full environments and flips 100% of traffic at once: rollback is seconds
> because the old environment is still running, but you're paying for double capacity
> during the cutover. Canary sends 1% to the new version, compares its error rate and
> latency against the version running beside it, and progresses only if the comparison
> passes — that's my choice for anything user-facing. Shadow traffic mirrors real
> requests to the new version and throws away the responses, which is the only way to
> test with production traffic shapes at zero user risk, but it only works for read-only
> paths because mirrored writes double every side effect. Feature flags are the fastest
> undo of all — the code is already deployed, so turning a feature off is a config change
> that takes seconds, no rebuild. The thing all of them share is that none of them help
> with schema changes: a rolling deploy means old and new code run simultaneously against
> the same database, so every migration has to be backwards-compatible. That's
> expand/contract — add the new column, dual-write, backfill, switch reads, and drop the
> old one a release later.

### Mental model

```
ROLLING          ▓▓▓▓▓▓▓▓ → ▓▓▓▓▓▒▒▒ → ▓▓▒▒▒▒▒▒ → ▒▒▒▒▒▒▒▒
                 both versions live throughout; rollback = another rollout

BLUE-GREEN       blue ▓▓▓▓ (100%)      green ▒▒▒▒ (0%, warm)
                        └── flip ──►   green ▒▒▒▒ (100%)
                 rollback = flip back (seconds); costs 2× during cutover

CANARY           ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▒  1% → measure → 5% → 25% → 100%
                 automated abort on SLO burn; see Module 11.13

SHADOW           ▓▓▓▓ ──serves──► users
                   └──mirror──► ▒▒▒▒ (responses discarded)
                 zero user risk; READ-ONLY paths only

FEATURE FLAG     ▒▒▒▒▒▒▒▒ deployed everywhere, behaviour off
                 flip config → on for 1% of users → on for all
                 rollback in seconds, no rebuild, no rollout
```

| Strategy | Users on new code | Rollback | Extra cost | Good for |
|---|---|---|---|---|
| Rolling | Gradual, uncontrolled | Minutes | ~0 | Routine, low-risk changes |
| Blue-green | 0% then 100% | **Seconds** | 2× during cutover | Big-bang cutovers, quick undo |
| Canary | 1% → 100%, measured | Seconds–minutes | ~1.1× | Anything user-facing |
| Shadow | 0% (mirrored) | N/A | 2× on that path | Rewrites, engine swaps |
| Feature flag | Config-controlled | **Seconds** | Flag infra + debt | Risky behaviour, gradual release |

**How each one handles a database schema change — the answer is "it doesn't":**

```
Rolling:      old and new code run SIMULTANEOUSLY against one schema
              ⇒ the migration must be compatible with BOTH
Blue-green:   both environments point at the SAME database
              ⇒ same constraint, and now the flip-back must also work
Canary:       same — 1% new + 99% old, one database
Feature flag: same — the column exists whether the flag is on or off

⇒ EXPAND / CONTRACT is not optional, it is the precondition for all of them:

   1. EXPAND    add new nullable column / new table. Deploy. Nothing reads it.
   2. DUAL-WRITE new code writes BOTH old and new. Deploy. Old code still fine.
   3. BACKFILL  batch-migrate historical rows. No deploy. Throttled.
   4. SWITCH    new code reads the new column. Deploy. Old code still fine.
   5. STOP      stop writing the old column. Deploy.
   6. CONTRACT  drop the old column — a release later, once rollback window
                has passed. This is the ONLY irreversible step.
```

Details of the migration mechanics — locking, `NOT NULL` with defaults, index builds
`CONCURRENTLY` — are in
[Module 05 — schema migrations](./05_Databases_And_Data_Modeling.md#expandcontract).

### Enterprise production example

**Segment's Traffic Recorder** is a nice concrete instance of the shadow idea applied to
testing rather than deployment: because their destination code called hundreds of live
third-party APIs, their test suite was slow and flaky. They recorded real destination
traffic and replayed it, which let the full suite run in milliseconds with no network
calls. The same recorded-traffic technique is what makes shadow deployments credible for
a rewrite: you're not guessing at the request distribution, you're replaying it.

### Code

```yaml
# Blue-green with an Argo Rollout: green is fully deployed and health-checked
# before a single user sees it, and the old ReplicaSet stays for fast undo.
apiVersion: argoproj.io/v1alpha1
kind: Rollout
metadata: {name: orders-api}
spec:
  replicas: 10
  strategy:
    blueGreen:
      activeService: orders-api           # what users hit
      previewService: orders-api-preview  # internal-only, for smoke tests
      autoPromotionEnabled: false         # a human (or a gate) flips it
      scaleDownDelaySeconds: 600          # keep blue warm for 10 min ⇒ instant
                                          # rollback within the window
      prePromotionAnalysis:
        templates: [{templateName: smoke-tests}]
      postPromotionAnalysis:
        templates: [{templateName: slo-burn-guard}]   # auto-rollback on burn
```

```python
# Expand/contract, step 2: dual-write. This is the code that must exist in
# production during the transition, and the reason schema changes take
# three releases instead of one.
async def update_address(conn, user_id: str, address: dict) -> None:
    await conn.execute(
        """
        UPDATE users
           SET address_line = %(legacy)s,        -- OLD: denormalised string
               address      = %(structured)s     -- NEW: jsonb
         WHERE id = %(user_id)s
        """,
        {"user_id": user_id,
         "legacy": f"{address['line1']}, {address['city']} {address['postcode']}",
         "structured": json.dumps(address)},
    )
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Canary for user-facing changes | Very low traffic (no statistical power) | 10–40 min per rollout |
| Blue-green for instant rollback | Stateful services, long-lived connections | 2× capacity during the cutover window |
| Shadow for rewrites and engine swaps | Anything with side effects | 2× compute on the shadowed path |
| Feature flags for risky behaviour | Flags with no expiry | Flag debt; combinatorial test surface |

### Follow-ups they will ask

**Q: Blue-green with one shared database — what can still go wrong?**
A: The schema. Green may have migrated the database in a way blue can't handle, so
flipping back breaks the "instant rollback" promise you were paying 2× capacity for.
Blue-green only delivers on that promise if every migration is backwards-compatible,
which means expand/contract again. Also in-flight sessions and long-lived connections,
which don't move when you flip the service.

**Q: How do you canary a background worker or a Kafka consumer? There's no traffic to split.**
A: Split by partition or by message attribute rather than by request. Run the new
consumer version in its own consumer group over a subset of partitions, or route a
percentage of messages by key hash to a canary topic. Compare processing error rate and
per-message duration between the two groups. If neither is possible, shadow: run the new
version in a parallel consumer group that processes but doesn't commit side effects.

**Q: What's the actual risk of a rolling deploy?**
A: Both versions serve simultaneously, so anything that assumes a single version breaks:
a changed serialization format in a shared cache (v2 writes a shape v1 can't read), a
changed message schema on a queue, or a session cookie only one version understands. The
mitigation is the same as for schema changes — make every change backwards-compatible for
one release, including cache and message formats, not just the database.

### Red flags — do not say this

- ❌ "We do blue-green so rollback is instant." → ✅ "Rollback is instant for the code;
  the schema still has to be backwards-compatible or the flip-back fails."
- ❌ "Canary at 1% for two minutes." → ✅ "Bake time has to be long enough to see enough
  events to be significant — at low traffic 1% for two minutes tells you nothing."

---

## 12.11 Containers & orchestration for design interviews

> **One-liner:** Know pods, deployments, services, HPA and requests/limits well enough to
> use them as vocabulary, know the serverless-vs-container decision, and do not go down
> the Kubernetes rabbit hole.

### Say this in the interview

> For a design interview I treat Kubernetes as five nouns. A pod is one or more
> containers sharing a network namespace — the unit of scheduling, and it's disposable. A
> deployment manages a replica set of identical pods and does rolling updates. A service
> gives that set a stable virtual IP and DNS name and load-balances across the ready
> ones. The horizontal pod autoscaler adds and removes replicas based on a metric —
> usually CPU, but for a queue-driven worker I'd scale on queue depth or consumer lag via
> KEDA, because CPU is a terrible proxy for backlog. And resource requests and limits
> matter more than people think: the request is what the scheduler reserves and what
> determines whether you get placed at all, and the limit is the hard cap. Exceeding a
> memory limit gets you OOM-killed, and exceeding a CPU limit gets you throttled by the
> CFS quota, which shows up as mysterious p99 latency spikes rather than as high CPU —
> that's the trap. My general rule is to always set memory requests equal to limits, and
> to be cautious about CPU limits on latency-sensitive services. On the bigger question:
> I'd use serverless for spiky, low-baseline, event-driven work, containers for
> steady-state services, and VMs only when I need something the platform won't give me.

### Mental model

```
  Deployment (desired: 6 replicas, image v2)
        │  manages
        ▼
  ReplicaSet ──► Pod ──► Pod ──► Pod ──► Pod ──► Pod ──► Pod
                  │       │       │       │       │       │
                  └───────┴───┬───┴───────┴───────┴───────┘
                              │ selected by labels
                        ┌─────▼──────┐
                        │  Service   │  stable ClusterIP + DNS
                        └─────┬──────┘  routes only to READY pods
                              ▼
                     HPA watches a metric ──► scales the Deployment
                     (CPU, or queue depth via KEDA — prefer the latter
                      for workers: CPU doesn't measure backlog)
```

**Requests and limits — the part that causes real incidents:**

| | Request | Limit |
|---|---|---|
| What it is | Reserved; used for scheduling | Hard ceiling |
| CPU over it | Nothing (you can burst) | **Throttled** by CFS quota → latency spikes at normal CPU% |
| Memory over it | Eviction candidate under node pressure | **OOMKilled** immediately |
| Rule of thumb | Set from observed p95 usage | Memory: = request. CPU: often leave unset for latency-sensitive services |

The CPU-limit trap is worth being able to describe: with a limit of `500m`, the kernel
gives the container 50 ms of CPU per 100 ms period. A request that needs 80 ms of CPU in
one burst gets throttled for 50 ms and your p99 jumps, while your CPU utilisation graph
shows a comfortable 50%. The symptom looks like a network or lock problem; the cause is
the quota. Check `container_cpu_cfs_throttled_seconds_total`.

**Serverless vs containers vs VMs:**

| | Serverless (Lambda, Cloud Run, Functions) | Containers (GKE, ECS) | VMs |
|---|---|---|---|
| Scales to zero | Yes | Cloud Run yes; K8s not really | No |
| Cold start | 100 ms–several seconds (worse with big deps/ML libs) | None once running | None |
| Max duration | Bounded (minutes) | Unbounded | Unbounded |
| Ops burden | Lowest | Medium (cluster, upgrades) | Highest |
| Cost at steady high load | Highest per request | Medium | Lowest (with commitments) |
| Best for | Spiky, event-driven, cron, glue | Steady-state services | Licensing, special hardware, legacy |

**Cold starts** deserve one specific sentence because AI workloads make them worse: a
small Node or Go function is typically in the low hundreds of milliseconds, but a Python
container importing `torch`, `transformers` and a tokenizer can take many seconds, and if
it loads model weights it can take much longer. Mitigations: minimum instances / provisioned
concurrency, lazy imports, moving the model to a separate always-on service, and keeping
the deployment artifact small.

### Enterprise production example

**Scenario (labelled as a scenario):** a RAG ingestion pipeline on GCP. The API is on
Cloud Run with `min-instances=1` so the first user of the day doesn't pay the cold start.
Embedding workers run on GKE with a KEDA scaler on Pub/Sub subscription backlog, scaling
0→40 pods, because CPU-based HPA would only react *after* the backlog had already grown
enough to saturate the existing pods — queue depth is the leading indicator and CPU is the
lagging one. The workers use Spot/preemptible nodes because the work is idempotent and
retryable, which is the discipline described in
[Module 13 — Cost optimization](./13_Concurrency_And_Performance.md#1313-cost-optimization-as-an-engineering-discipline).

### Code

```yaml
# The four things worth showing an interviewer, and nothing more.
apiVersion: apps/v1
kind: Deployment
metadata: {name: rag-api}
spec:
  replicas: 3
  selector: {matchLabels: {app: rag-api}}
  template:
    metadata: {labels: {app: rag-api}}
    spec:
      containers:
        - name: api
          image: eu.gcr.io/acme/rag-api:2026.3.1
          resources:
            requests: {cpu: "500m", memory: "512Mi"}
            limits:   {memory: "512Mi"}   # memory limit = request; NO cpu limit
                                          # on this latency-sensitive service
          readinessProbe: {httpGet: {path: /readyz, port: 8000}, periodSeconds: 5}
          livenessProbe:  {httpGet: {path: /healthz, port: 8000}, periodSeconds: 10}
---
apiVersion: keda.sh/v1alpha1
kind: ScaledObject
metadata: {name: embed-worker}
spec:
  scaleTargetRef: {name: embed-worker}
  minReplicaCount: 0            # scale to zero between ingestion batches
  maxReplicaCount: 40
  cooldownPeriod: 300
  triggers:
    - type: gcp-pubsub          # backlog, NOT cpu — this is the leading signal
      metadata:
        subscriptionName: embed-jobs-sub
        mode: SubscriptionSize
        value: "20"             # target ~20 undelivered messages per pod
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Kubernetes for many services, one platform team | 2 services and 4 engineers | A cluster to upgrade, secure and page on |
| Cloud Run / serverless for spiky and bursty | Steady high load, long jobs | Cold starts; higher per-request cost |
| Scale-to-zero workers on queue depth | Latency-critical synchronous paths | Cold start on the first message |

### Follow-ups they will ask

**Q: Your service has normal CPU usage but p99 latency spikes. What do you check first?**
A: CPU throttling — `container_cpu_cfs_throttled_seconds_total`. A CPU limit means the
container is capped per 100 ms scheduling period, so a bursty request can be throttled
mid-flight while average utilisation looks fine. That's my first check before I look at
the database or the network.

**Q: Why not scale workers on CPU?**
A: Because CPU tells you how hard the current workers are working, not how much work is
waiting. A queue with a 50,000-message backlog and four pods at 60% CPU won't trigger a
CPU-based HPA at all, yet it's hours behind. Queue depth or consumer lag is the leading
indicator, and KEDA (or a custom metric adapter) is how you scale on it.

**Q: Kubernetes or Cloud Run for this design?**
A: Cloud Run if the workload is HTTP or Pub/Sub-driven, scales to zero, and doesn't need
custom networking or daemonsets — it removes the cluster from my operational surface
entirely. Kubernetes when I have many services with shared infrastructure needs, need
GPUs or specific node types, or need to run things Cloud Run can't host. For a two-person
team I'd take Cloud Run and not apologise for it.

### Red flags — do not say this

- ❌ "We'd run it on Kubernetes for scalability." → ✅ "We'd run it on Cloud Run because
  it's HTTP-driven and bursty; Kubernetes would give us the same scaling and a cluster
  to operate."
- ❌ "Set CPU limits on everything." → ✅ "Always set memory limits equal to requests;
  be careful with CPU limits on latency-sensitive services because CFS throttling shows
  up as p99 spikes."

---

## 12.12 The 12-factor app

> **One-liner:** Five of the twelve factors actually come up in design discussions —
> config in the environment, backing services as attached resources, stateless processes,
> disposability, and logs as event streams — and they're the ones that make a service
> horizontally scalable at all.

### Say this in the interview

> The 12-factor methodology is about making a service safely disposable and horizontally
> scalable, and in a design conversation about five of the factors carry all the weight.
> Config lives in the environment, not in the code and not in a per-environment file
> checked into the repo, so the same image runs in staging and production and rotating a
> credential doesn't need a rebuild. Backing services — the database, Redis, the queue,
> the object store — are attached resources reached by a URL from config, so swapping a
> local Postgres for Cloud SQL is a config change with no code change. Processes are
> stateless and share nothing: any instance can serve any request, session state lives in
> Redis or a signed cookie, and uploads go to object storage rather than local disk.
> Disposability means fast startup and graceful shutdown on SIGTERM, which is exactly
> what makes rolling deploys, autoscaling and spot instances safe. And logs are an
> unbuffered stream to stdout — the process should know nothing about files, rotation or
> shipping. Those five together are what "cloud native" actually means in practice; the
> rest of the twelve are good hygiene but rarely decide a design.

### Mental model

```
THE FIVE THAT MATTER IN A DESIGN INTERVIEW

  III. CONFIG          env vars, not files in the repo
       ⇒ one image, many environments; rotate secrets without a rebuild

  IV.  BACKING SERVICES  DB/cache/queue/blob = attached resources via URL
       ⇒ swap local Postgres → Cloud SQL with a config change

  VI.  PROCESSES       stateless, share-nothing
       ⇒ ANY instance serves ANY request ⇒ horizontal scaling works
       ⇒ no sticky sessions, no local file uploads, no in-process cache
         you depend on for correctness

  IX.  DISPOSABILITY   fast start, graceful SIGTERM shutdown
       ⇒ rolling deploys, autoscaling and spot instances are all safe

  XI.  LOGS            unbuffered stream to stdout
       ⇒ the platform collects; no rotation, no disk-full failure mode

  The other seven (codebase, dependencies, build/release/run, port binding,
  concurrency, dev/prod parity, admin processes) are good hygiene and
  almost never the crux of a design question.
```

**The statelessness test**, which is the practical version of factor VI: *if I kill any
instance right now, mid-request, does any user lose anything they can't retry?* If yes,
that state needs to move to Redis, the database, or object storage.

```
  ✗ in-process session dict        ✓ session in Redis / signed JWT cookie
  ✗ upload written to /tmp         ✓ upload streamed to GCS via signed URL
  ✗ in-memory job scheduler        ✓ a queue with visibility timeouts
  ✗ local cache as source of truth ✓ local cache as an optimisation only,
                                     with a shared cache or DB behind it
```

### Enterprise production example

**Heroku** published the 12-factor methodology in 2011, and factor VI exists because their
platform restarts dynos routinely and without warning — an application that kept state in
process simply did not work there. Kubernetes made the same assumption mandatory a few
years later: pods are evicted, rescheduled, preempted and rolled at the platform's
discretion. The factors read like a philosophy and are really a set of preconditions for
running on a platform that will kill your process at an arbitrary moment.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Stateless processes | Genuinely stateful systems (databases, brokers) | Every request pays a lookup for state |
| Config in the environment | Very large config blobs | Secret sprawl; needs a secret manager |
| Logs to stdout | You need guaranteed local audit logs | You depend on the platform's collector |

### Follow-ups they will ask

**Q: WebSockets are stateful. Does that violate factor VI?**
A: The connection is stateful; the application state doesn't have to be. I keep the
connection on one instance but the session, subscriptions and presence in Redis, so if
that instance dies the client reconnects to any other and resumes. What I avoid is
per-instance data that only exists there — that's what makes a pod undeletable.

**Q: Config in environment variables — what about secrets?**
A: Env vars are fine as the delivery mechanism but not as the storage: they leak into
crash dumps, child processes and `kubectl describe`. I'd store them in Secret Manager or
Vault and inject at start, or mount them as files with restricted permissions, and rotate
on a schedule. The factor is about *externalising* config, not about literally using
`export`.

### Red flags — do not say this

- ❌ "We follow all twelve factors." → ✅ "The ones that shape the design are stateless
  processes, config in the environment, and disposability — those are what make
  autoscaling and rolling deploys safe."

---

## 12.13 Choosing an architecture in the interview

> **One-liner:** Start with a modular monolith plus managed services, then justify every
> single split by naming the specific forcing function — this is the answer that sounds
> senior, because it's what experienced engineers actually do.

### Say this in the interview

> My default answer is: one well-structured deployable, with enforced module boundaries
> and a schema per module, on top of managed services — Cloud SQL, Redis, Pub/Sub, object
> storage — so we're not operating stateful infrastructure. Then I split a service out
> only when I can name the specific thing forcing it. There are five forcing functions I
> accept. One, a different resource profile: GPU inference or video transcoding doesn't
> belong in the same process as an HTTP API, so that goes out first. Two, a different
> scaling shape: something that needs to burst 50× on a queue while the API sits flat.
> Three, deploy-cadence conflict: two teams whose release schedules genuinely block each
> other, which usually shows up around five or six teams. Four, a compliance or blast-
> radius boundary: payment card data, or a component that must keep working when
> everything else is down. Five, a technology mismatch where a different runtime is
> clearly right. What I won't accept as a reason is "we might scale later", "microservices
> are best practice", or team size on its own. And I'd say the direction is reversible:
> Segment went to 140-plus services and deliberately came back to one, and that was the
> right call for them. Choosing the smaller architecture and being able to explain the
> conditions under which you'd change it is a stronger answer than drawing twelve boxes.

### Mental model

**The script, in order:**

```
1. "I'd start with a modular monolith on managed services."
   ┌──────────────────────────────────────────────────────┐
   │  LB ─► app (orders │ billing │ catalog │ ingest)      │
   │           └─► Cloud SQL (schema per module)           │
   │           └─► Redis    └─► Pub/Sub   └─► GCS          │
   └──────────────────────────────────────────────────────┘

2. "The first thing I'd split out is <X>, because <forcing function>."
   e.g. embedding workers — GPU profile + bursty queue-driven scaling
   ┌──────────────────────────────────────────────────────┐
   │  LB ─► app ──► Pub/Sub ──► embed-workers (GPU, 0–40)  │
   └──────────────────────────────────────────────────────┘

3. "I'd split further only if <specific condition> happens."
   e.g. "if the payments team's release cadence starts blocking ours"

4. "And here's what I'd be watching to know when."
   deploy lead time, cross-team PR blocking, per-endpoint resource skew
```

**The five forcing functions — accept these, reject everything else:**

| # | Forcing function | Concrete signal |
|---|---|---|
| 1 | Different resource profile | Needs GPUs / 32 GB RAM / long-running while the API doesn't |
| 2 | Different scaling shape | Bursts 50× on a queue; API traffic is flat |
| 3 | Deploy-cadence conflict | Two teams' releases block each other; lead time rising with headcount |
| 4 | Compliance / blast-radius boundary | PCI scope, or must survive when the rest is down |
| 5 | Technology mismatch | The right tool is a different runtime entirely |

**Reject these:**

- "We might need to scale later." Scale horizontally now; split when it hurts.
- "Microservices are best practice." Best practice is context-dependent by definition.
- "We have twelve engineers." Team count justifies module boundaries, not network hops.
- "It's a big system." Big systems can be one deployable — Shopify is the proof.

**The three-question test** before every proposed split:

```
  1. What specific problem does this split solve that a module boundary can't?
  2. What does it cost? (network hop, eventual consistency, saga, on-call,
     one more thing to deploy and monitor)
  3. Can we undo it in a quarter if we're wrong?
```

If question 1 has no concrete answer, don't split.

### Enterprise production example

The two bookends are the most useful pair to hold in your head. **Shopify** ran into
monolith pain at roughly 2.8–3 million lines and 1,000+ developers, and chose
componentisation over decomposition, keeping one deployable. **Segment** split into 140+
services with a small team, found that dependency drift and operational overhead had
destroyed their velocity — "as our velocity plummeted, our defect rate exploded" — and
deliberately consolidated back to a single service. Between them sits **Uber**, which
built 2,200 microservices and then spent two years grouping them into ~70 domains behind
gateways because the service count itself had become the complexity. Three companies with
enormous engineering organisations, and none of the three concluded that more services is
better. That's the argument, and it's stronger than any opinion you could offer.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Modular monolith + managed services as default | You have a named forcing function today | Deploy coupling until you split |
| Splitting on a forcing function | Splitting on speculation | A network hop, a saga, an on-call rotation |
| Saying "I'd start smaller" in an interview | Drawing 12 boxes to look impressive | Nothing — it's the stronger answer |

### Follow-ups they will ask

**Q: The interviewer says "assume 100 million users". Does that change your answer?**
A: It changes the data layer and the caching strategy far more than the deployment
topology. I'd shard or partition, add read replicas, add a CDN and cache aggressively,
and split out the components with distinct resource profiles. What 100 million users
does *not* automatically require is 40 services — Shopify serves an enormous merchant
base from a core monolith with horizontal scaling and pod-based isolation.

**Q: You said you'd start with a monolith. The interviewer looks skeptical. What now?**
A: I'd make the cost concrete rather than defend the position abstractly: with N teams
and one product, microservices need a platform team, distributed tracing, per-service
on-call and sagas replacing transactions — and I'd ask which of those exist today. Then
I'd name the first split I *would* make and why. Being specific about what would change
my mind is what makes it a judgement rather than a preference.

**Q: How do you know when the modular monolith has stopped working?**
A: I'd watch three signals: deploy lead time rising as headcount rises, the fraction of
PRs blocked on another team's review, and resource skew — how much capacity is
provisioned for one endpoint's profile. When any of those degrades consistently, the
forcing function has arrived and I split the specific thing causing it, not everything.

### Red flags — do not say this

- ❌ "I'd use microservices because the system is large." → ✅ "I'd start with one
  deployable and split the embedding workers out first, because their resource profile
  and scaling shape are completely different from the API's."
- ❌ "Monolith first is a compromise." → ✅ "It's the cheapest way to learn where the
  boundaries actually are, and every real boundary I discover makes a later split safe."

---

## Module 12 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Name the four real limits of a monolith. Which of them are technical and which are
   organisational?
2. What makes a modular monolith different from "a monolith with folders"? Name the
   enforcement mechanisms.
3. What did Shopify do, and what are the numbers — codebase size, component count, the
   tool they built?
4. List the four prerequisites you'd want before recommending microservices, and describe
   the distributed monolith.
5. State Conway's Law and explain what it implies about drawing an architecture diagram
   before drawing the team structure.
6. Walk through the strangler fig migration, including the three database stages. Which
   stage does most of the work?
7. What happened at Segment, with numbers, and what's the lesson?
8. Ten sequential calls at 20 ms p99 each. What's the request p99, and why isn't it
   200 ms? What is Google's 100-server / 1% number?
9. Client-side versus server-side discovery — give an example of each and say what
   Kubernetes does.
10. Give Istio's real per-hop latency and resource numbers for sidecar versus ambient
    mode.
11. Three ways to get data your service doesn't own. When do you use each?
12. Which deployment strategy rolls back a database migration? Explain expand/contract.
13. Give your five forcing functions for splitting a service out, and three reasons you'd
    reject.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| In-process call vs in-cluster network call | ~10–100 ns vs 0.5–5 ms |
| Five services in series at 99.9% each | 99.5% ≈ 3.6 h/month |
| Shopify core Rails codebase | ~2.8–3 M lines, 500k+ commits, ~40k files |
| Shopify Ruby classes audited into components (2017) | ~6,000 |
| Shopify components with defined public entrypoints | 37 (Packwerk, 2020) |
| Uber critical microservices (mid-2018) | ~2,200 |
| Uber domains after DOMA | ~70 |
| Uber Maps org | 3 domains, 80 microservices, 3 gateways |
| Amazon API mandate | 2002 — no direct reads of another team's data store |
| Segment services at the breaking point (2017) | 140+ services, queues and repos |
| Segment consolidation project duration | ~5 months design → first traffic |
| Tail amplification: 10 calls, 1% slow each | 1 − 0.99¹⁰ ≈ 9.6% of requests hit a slow call |
| Google "Tail at Scale": 100 servers, 1% > 1 s | 63% of requests exceed 1 s |
| Protobuf vs JSON, typical mixed payload | 50–85% smaller, 3–6× faster to serialize |
| Protobuf vs JSON, string-heavy payload | only ~4% smaller |
| Istio sidecar resource cost (1k rps, 1 KB) | ~0.20 vCPU + 60 MB **per pod** |
| Istio ztunnel (ambient L4) | ~0.06 vCPU + 12 MB **per node** |
| Istio waypoint (ambient L7) | ~0.25 vCPU + 60 MB per namespace |
| Istio sidecar added latency p90–p99 | ~0.63–0.88 ms |
| Istio ambient L4 added latency p90–p99 | ~0.16–0.20 ms (waypoint adds 0.40–0.50 ms) |
| Kubernetes CPU limit period | 100 ms (CFS quota) — throttling looks like latency |
| Expand/contract releases required | 3 (expand+dual-write, switch, contract) |

---

**Next:** [Module 13 — Concurrency, Performance & Cost](./13_Concurrency_And_Performance.md)
