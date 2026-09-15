# Phyllo LLD Interview Resource Book

**Candidate:** Aalok (Python / FastAPI / Redis / Pub-Sub / Webhooks)  
**Company:** Phyllo ([getphyllo.com](https://www.getphyllo.com/))  
**Round type:** Low-Level Design (use case from their products)  
**Language for design + code:** Python

---

## 0. How to use this book (tomorrow morning + night before)

| Block | Time | What to do |
|-------|------|------------|
| 1 | 45–60 min | Read §1 + §2 (product map). Open website + docs while reading. |
| 2 | 90 min | Drill §5 Priority-1 designs end-to-end on paper/whiteboard. |
| 3 | 60 min | Practice the Python skeletons in §6–§7 (classes, APIs, DB). |
| 4 | 45 min | Mock: pick 1 use case from §5, speak for 40–45 min as if interviewer. |
| 5 | 30 min | Revise §8 checklist + §9 “link your experience” talking points. |

**Docs to skim once (do not deep-read everything):**
- https://www.getphyllo.com/
- https://docs.getphyllo.com/
- https://www.getphyllo.com/post/building-a-distributed-webhook-system *(gold — they published their own LLD)*

---

## 1. What Phyllo actually is (say this in 60 seconds)

Phyllo is a **social / creator data API gateway**.

Instead of every app integrating Instagram, YouTube, TikTok, Twitch, Shopify, Upwork, etc. separately, Phyllo:

1. Connects to **25+ platforms**
2. Collects **public data** (no login) and **consented data** (creator OAuth / Connect SDK)
3. **Normalizes** everything into one schema
4. Exposes REST APIs + **webhooks** to developers
5. Powers apps in influencer marketing, creator fintech, social KYC, social listening, background screening

**One-liner for interview:**
> “Phyllo is Plaid-for-creators / Stripe-for-social-data — one integration, many platforms, consented + public data, normalized APIs.”

### Two data layers (critical distinction)

| Layer | Needs creator login? | Examples | Powers |
|-------|----------------------|----------|--------|
| **Public APIs** | No | Profile analytics, content, comments, social listening, creator search (470M+ profiles) | Discovery, vetting, listening, screening |
| **Consented / Authenticated APIs** | Yes (Connect SDK) | Verified income, private engagement, real audience demographics, publish | Fintech, creator tools, KYC, campaign measurement |

### Core product surfaces (from website + docs)

| Product | What it does |
|---------|----------------|
| **Connect** | Consent + account linking (SDK + APIs) |
| **Identity** | Profile / identity / reputation |
| **Engagement** | Content + likes / views / shares etc. |
| **Audience** | Demographics, authenticity |
| **Activity** | Activity insights |
| **Income** | Earnings / transactions across platforms |
| **Publish** | Post content to connected platforms |
| **Comments** | Comment streams on content |
| **Webhooks** | Push sync / update events to customer backends |
| **Creator Search / Listening / Screening** | Public-data products for discovery & risk |

**Engineering scale signals they advertise / blog about:**
- 470M+ profiles indexed
- 5B+ signals / month
- 99.99% uptime claim
- Their webhook system: **~3M webhook deliveries / day**, retry queues, HMAC signatures

---

## 2. How to reverse-engineer “use cases from the website”

HR said the LLD problem will come from **their products**. That usually means one of:

1. **Design a subsystem Phyllo itself would build** (webhook delivery, Connect flow, data sync worker)
2. **Design an app that *uses* Phyllo** (influencer marketplace, creator lending, social KYC)
3. **Design a feature on their website** (creator search, social listening pipeline, income aggregation)

### Your extraction method (do this tonight, 20 min)

Open getphyllo.com and for each capability write:

```
Use case name:
Actors:
Primary flow (happy path):
Data entities:
Async vs sync:
Hard constraints (consent, rate limits, multi-platform, idempotency):
Likely LLD ask:
```

### Highest-probability LLD prompts (ranked)

| Rank | Prompt | Why likely |
|------|--------|------------|
| **P0** | Design Phyllo’s **webhook delivery system** | They published a full eng blog on it |
| **P0** | Design **Connect / account linking + consent + sync** | Core product; every customer uses it |
| **P0** | Design a **creator data sync pipeline** (fetch → normalize → store → notify) | Heart of the gateway |
| **P1** | Design **verified income aggregation** API | Distinctive consented product |
| **P1** | Design **influencer discovery / search** over 470M profiles | Public product, scale-heavy |
| **P1** | Design **social listening** (mentions, sentiment, share of voice) | Website-featured |
| **P1** | Design **social KYC / account ownership verification** | Fintech + screening tabs |
| **P2** | Design **rate limiter + multi-tenant API gateway** for Phyllo APIs | Infra; matches your Europa work |
| **P2** | Design **campaign measurement** for influencer marketing | Customer-facing use of Engagement |
| **P2** | Design **cross-platform publish** | Publish product |
| **P2** | Design **fake-follower / authenticity scoring** | Vetting use case |

If they say “pick something from our site,” volunteer **Connect + Sync + Webhooks** — it shows you understood their core loop.

---

## 3. What LLD means in this round (vs HLD / DSA)

| Layer | Focus |
|-------|--------|
| HLD | Boxes, scale numbers, Kafka vs Redis, sharding |
| **LLD (this round)** | Classes, entities, APIs, DB schema, sequence flows, concurrency, failure handling, **code-shaped design** |
| DSA | Algorithms on leetcode-style problems |

**They expect you to cover:**
1. Clarify requirements (functional + non-functional)
2. Core entities / class diagram
3. API contracts (REST-ish)
4. DB schema (tables + indexes)
5. Sequence diagrams for 2–3 critical flows
6. Concurrency, idempotency, retries, rate limits
7. Extensibility (new platform = plugin, not rewrite)
8. Optional: Python interfaces / method signatures

**Timebox for a 45–60 min LLD:**
- 5 min clarify
- 5 min entities + APIs outline
- 20–25 min deep design of core flows
- 10 min scale / failure / tradeoffs
- 5 min wrap + questions

---

## 4. Phyllo domain model (memorize these entities)

Use these names in the interview — they match Phyllo vocabulary.

```
Developer / CustomerApp
  └── has many Users (end creators in customer's app)
        └── has many Accounts (Instagram, YouTube, …)
              ├── Profile (Identity)
              ├── AudienceDemographics
              ├── ContentItems[]
              ├── Comments[]
              ├── IncomeTransactions[]
              └── SyncStatus per Product (IDENTITY, ENGAGEMENT, INCOME, …)

WorkPlatform (instagram, youtube, tiktok, …)
SDKToken (short-lived, scoped to products)
WebhookSubscription (url, events[], secret)
WebhookDelivery (event, payload, retry_count, status)
ConsentGrant (user, platform, scopes/products, granted_at)
```

### Product enum (as in docs)

`IDENTITY | ENGAGEMENT | INCOME | ACTIVITY | AUDIENCE | PUBLISH | …`

### Account / sync states (design these explicitly)

```
AccountConnectionStatus: PENDING | CONNECTED | DISCONNECTED | ERROR | REAUTH_REQUIRED
DataSyncStatus:          NOT_STARTED | IN_PROGRESS | SYNCED | FAILED | PARTIAL
```

### Important design choice Phyllo documents

Webhooks often send **IDs only**, not full objects → receiver must:
1. ACK fast (200)
2. Enqueue
3. Bulk-fetch (up to 100 IDs)
4. Persist

Mention this. It shows product literacy.

---

## 5. Question bank — full LLD prompts + how to crack them

---

### Q1. [P0] Design Phyllo’s distributed webhook delivery system

**Prompt:**  
“Design a system that notifies developers whenever creator account data changes. Millions of deliveries/day. Must be reliable, secure, and handle flaky customer endpoints.”

**Clarify:**
- Events: ACCOUNTS.CONNECTED, PROFILES.ADDED/UPDATED, CONTENTS.ADDED/UPDATED, INCOME.*, etc.
- At-least-once delivery OK?
- SLA for first attempt? Retry window?
- Payload: IDs vs full body?
- Multi-tenant: one URL per developer app

**Entities / classes (Python mindset):**
- `WebhookEvent`, `WebhookSubscription`, `DeliveryAttempt`
- `WebhookDispatcher`, `SignatureService`, `RetryPolicy`
- Queues: MAIN, RETRY_1 (5m), RETRY_2 (60m), RETRY_3 (360m), ALERT

**APIs (customer-facing):**
- `POST /v1/webhooks` register
- `GET /v1/webhooks`
- `DELETE /v1/webhooks/{id}`
- Internal: enqueue delivery jobs

**Critical flows:**
1. Data sync completes → emit event → enqueue MAIN
2. Worker POSTs to customer URL with `X-Phyllo-Signature` (HMAC-SHA256)
3. Success (2xx within timeout) → mark DELIVERED
4. Failure (5xx / timeout) → bump retry → RETRY queues via TTL/DLQ
5. 4th failure → ALERT queue → email developer + CS

**DB tables:**
- `webhook_subscriptions(id, developer_id, url, secret, events[], is_active)`
- `webhook_deliveries(id, subscription_id, event_type, payload_json, status, retry_count, next_attempt_at)`
- `webhook_delivery_attempts(id, delivery_id, http_status, latency_ms, error, created_at)`

**NFRs to state:**
- Idempotency key per event so customer can dedupe
- ACK timeout (e.g. 5s) — slow customers = failure
- TLS 1.2+, IP allowlist
- Horizontal workers; per-tenant concurrency caps so one bad URL doesn’t starve others

**Tie to Phyllo blog:** ActiveMQ + TTL retry queues + HMAC — paraphrase; don’t claim you work there.

**Python sketch they may ask:**
```python
import hmac, hashlib

def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

class RetryPolicy:
    DELAYS = [5 * 60, 60 * 60, 360 * 60]  # seconds

    def next_delay(self, retry_count: int) -> int | None:
        if retry_count >= len(self.DELAYS):
            return None  # alert
        return self.DELAYS[retry_count]
```

---

### Q2. [P0] Design Connect: account linking + consent + initial sync

**Prompt:**  
“Design the Connect flow so a creator can link Instagram/YouTube to a customer app and Phyllo can start syncing consented products.”

**Actors:** Creator (end user), Customer App, Phyllo API, Connect SDK, Source Platform (Meta/Google/…)

**Happy path (memorize order):**
1. Customer backend: `POST /users` → `user_id`
2. Customer backend: `POST /sdk-tokens` with `user_id` + products `["IDENTITY","ENGAGEMENT"]`
3. Frontend: init Connect SDK with token → creator logs into platform → grants consent
4. SDK event `onAccountConnected` (UX only) + webhook `ACCOUNTS.CONNECTED` (source of truth)
5. Phyllo starts async sync per product
6. Webhooks: `PROFILES.ADDED`, `CONTENTS.ADDED`, …
7. Customer fetches via retrieve / bulk APIs

**Classes:**
- `UserService`, `SDKTokenService`, `ConnectSession`
- `PlatformConnector` (interface)
- `InstagramConnector`, `YouTubeConnector` (adapters)
- `ConsentStore`, `AccountService`, `SyncOrchestrator`

**Extensibility pattern (say this aloud):**
> Strategy / Adapter: `PlatformConnector` with `oauth_start`, `exchange_code`, `fetch_profile`, `fetch_content`, `fetch_income`. New platform = new adapter + config, not new core.

**Security points:**
- Client ID/secret **server-side only**
- SDK token short-lived, scoped
- No password storage; OAuth tokens encrypted at rest
- Consent scopes stored; revoke → stop sync + DISCONNECTED

**State machine:** Draw this on board — interviewers love it.

```
CREATED → CONNECTING → CONNECTED → SYNCING → READY
                 ↘ FAILED
CONNECTED → REAUTH_REQUIRED → CONNECTED
CONNECTED → DISCONNECTED
```

**DB:**
- `users(id, external_user_id, developer_id)`
- `accounts(id, user_id, work_platform_id, status, platform_account_ref)`
- `oauth_credentials(account_id, access_token_enc, refresh_token_enc, expires_at)`
- `consents(account_id, product, granted_at, revoked_at)`
- `sync_jobs(id, account_id, product, status, cursor, attempts)`

---

### Q3. [P0] Design the multi-platform data sync & normalization pipeline

**Prompt:**  
“After an account connects, design how Phyllo continuously fetches, normalizes, stores, and notifies updates.”

**Pipeline stages:**
```
Scheduler / Change detector
   → Fetch workers (per platform, rate-limited)
   → Normalizer (platform schema → Phyllo canonical schema)
   → Persistence (upsert by natural keys)
   → Diff / change detection
   → Webhook emitter
```

**Canonical content model (example fields):**
```python
@dataclass
class ContentItem:
    id: str
    account_id: str
    platform: str
    platform_content_id: str
    type: str              # video | image | reel | short | post
    caption: str | None
    published_at: datetime
    metrics: dict          # likes, comments, views, shares, saves, impressions
    media_urls: list[str]
    raw_hash: str          # for change detection
```

**Hard problems to discuss:**
1. **Per-platform rate limits** — token bucket / leaky bucket per platform + per account
2. **Backfill vs incremental** — first sync full; later cursors / webhooks from platform if available
3. **Idempotent upserts** — unique `(platform, platform_content_id)`
4. **Partial failure** — ENGAGEMENT synced, INCOME failed → per-product status
5. **Ordering** — webhooks may be delayed/out-of-order → version / `updated_at` / event_id
6. **PII & consent** — never sync products not consented

**Queue design (map to your VoXgent experience):**
- Pub/Sub or Redis streams: `sync.fetch`, `sync.normalize`, `sync.notify`
- Cloud Tasks / workers with retries
- Dead-letter for poison messages

**Say:** “I’d use an event-driven pipeline with bounded concurrency and per-tenant/platform rate limits — similar to how I’d schedule high-concurrency outbound work with queues and retries.”

---

### Q4. [P1] Design Verified Income Aggregation

**Prompt:**  
“Design an API that returns a creator’s verified monthly income across ad revenue, sponsorships, subscriptions, affiliates from connected platforms.”

**Functional:**
- Aggregate by month / currency
- Breakdown by stream type + platform
- Only consented accounts
- Refresh on transaction webhooks

**Entities:**
- `IncomeTransaction(id, account_id, platform, category, amount, currency, occurred_at, raw_ref)`
- `IncomeStatement(user_id, period_start, period_end, totals, breakdown)`

**APIs:**
- `GET /v1/accounts/{id}/income/transactions`
- `GET /v1/users/{id}/income/summary?from=&to=`
- Bulk retrieve by transaction IDs (webhook pattern)

**Design nuances:**
- FX conversion strategy (store original + normalized USD)
- Late-arriving transactions → recompute statement or materialize on read
- Fraud / integrity: source = platform, not self-reported
- Fintech compliance: audit log of access

**Class sketch:**
```python
class IncomeAggregator:
    def summarize(self, user_id: str, start: date, end: date) -> IncomeSummary:
        txns = self.repo.list_transactions(user_id, start, end)
        return IncomeSummary.from_transactions(txns)
```

---

### Q5. [P1] Design Creator Search (470M+ profiles)

**Prompt:**  
“Design search so brands find creators by niche, location, audience, growth.”

**This is more search/index LLD:**
- Ingestion from public profile pipeline
- Document model in Elasticsearch / OpenSearch
- Filters: niche tags, geo, follower ranges, engagement rate, growth velocity
- Ranking: relevance + quality + authenticity score
- Pagination: search_after / cursor, not deep offset

**Document example:**
```json
{
  "platform": "instagram",
  "handle": "mayamakes",
  "niche": ["beauty", "skincare"],
  "location": {"city": "Austin", "country": "US"},
  "followers": 120000,
  "engagement_rate": 0.047,
  "growth_30d": 0.08,
  "authenticity_score": 0.91,
  "last_indexed_at": "..."
}
```

**APIs:**
- `POST /v1/creator-search` with filter DSL
- Saved searches + alerts (optional stretch)

**Tradeoffs:** freshness vs cost; denormalize for read; async reindex.

---

### Q6. [P1] Design Social Listening

**Prompt:**  
“Track brand mentions, sentiment, share of voice across 25+ platforms.”

**Pipeline:**
```
Ingest public posts/comments matching keywords
 → Normalize
 → Deduplicate
 → Classify (sentiment / intent)  # LLM or ML service
 → Aggregate (SoV, trends)
 → Alerting
```

**Entities:** `Mention`, `KeywordWatch`, `SentimentLabel`, `ShareOfVoiceSnapshot`

**LLD focus:**
- Keyword matching at scale (streaming)
- Exactly-once-ish dedupe by platform post id
- Async classification workers
- Multi-tenant watches with fair scheduling

---

### Q7. [P1] Design Social KYC / account ownership verification

**Prompt:**  
“Verify that a user owns the social accounts they claim (for lending / visa / hiring).”

**Flow:**
1. User claims handles OR starts Connect
2. Consented connect proves ownership via OAuth
3. Optionally challenge-based for public-only (post a code) — discuss tradeoffs
4. Emit verification report with timestamps

**Entities:** `VerificationCase`, `ClaimedAccount`, `OwnershipProof`, `RiskFlag`

**Output:** case-ready report (website literally says this for immigration use case)

---

### Q8. [P2] Design rate limiting for Phyllo public APIs

**Prompt:**  
“Developers have different plans. Design rate limiting (e.g. 10 rps/developer) with 429 + Retry-After.”

**Algorithms:** Token bucket / sliding window  
**Storage:** Redis (`INCR` + TTL or Lua)  
**Keys:** `rl:{developer_id}:{route}:{window}`  
**Headers:** `X-RateLimit-Remaining`, `Retry-After`  
**Fairness:** per-developer + global platform protection

You already built rate limiting on Europa API gateway — reuse that story.

---

### Q9. [P2] Design Influencer Campaign Measurement

**Prompt:**  
“Brand runs a campaign with 50 creators. Measure delivered reach/engagement across platforms.”

**Design:**
- `Campaign`, `CampaignCreator`, `TrackedContent`, `MetricsSnapshot`
- Ingest via public content APIs + consented private metrics if connected
- Attribute posts via tracking codes / time windows / disclosed handles
- Aggregate dashboards

---

### Q10. [P2] Design Authenticity / fake-follower scoring

**Prompt:**  
“Score audience authenticity for vetting.”

**LLD angle:** feature extraction jobs + model service + score storage + explanation fields  
Don’t invent fake ML math — focus on **pipeline, versioning, recompute, API**.

---

## 6. Universal LLD template (use every time)

Copy this structure onto the board:

### A. Requirements
**Functional**
- …
**Non-functional**
- Scale (accounts, QPS, webhook fanout)
- Latency (sync UX vs eventual consistency)
- Consistency (at-least-once events)
- Security (OAuth, HMAC, secrets)
- Multi-tenant isolation

### B. Assumptions
- Write them down (e.g. “at-least-once webhooks”, “Python/FastAPI services”, “Postgres + Redis + queue”)

### C. High-level modules (still LLD-friendly)
```
API Gateway → Connect Service → Sync Workers → Normalizer → Data Store
                     ↓
              Webhook Service → Customer endpoints
```

### D. Class diagram (minimum)
- Services + Repositories + Domain models + Platform adapters

### E. APIs (REST)
Method, path, request, response, error codes

### F. Schema
Tables, PK/FK, unique constraints, indexes

### G. Sequences
Happy path + 1 failure path

### H. Concurrency & failures
Idempotency keys, retries, poison queue, rate limits, reauth

### I. Extensibility
New platform / new product / new webhook event

### J. Tradeoffs
Polling vs webhooks, sync vs async, SQL vs search index, etc.

---

## 7. Python LLD toolkit (what to write on the board)

Prefer **clear OOP + interfaces**, not framework noise.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from datetime import datetime

class Product(str, Enum):
    IDENTITY = "IDENTITY"
    ENGAGEMENT = "ENGAGEMENT"
    INCOME = "INCOME"

class AccountStatus(str, Enum):
    PENDING = "PENDING"
    CONNECTED = "CONNECTED"
    DISCONNECTED = "DISCONNECTED"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"

@dataclass
class Account:
    id: str
    user_id: str
    platform: str
    status: AccountStatus

class PlatformConnector(ABC):
    @abstractmethod
    def fetch_profile(self, credentials) -> dict: ...

    @abstractmethod
    def fetch_content(self, credentials, cursor: str | None) -> tuple[list[dict], str | None]: ...

class SyncOrchestrator:
    def __init__(self, connectors: dict[str, PlatformConnector], queue, repo): ...

    def enqueue_initial_sync(self, account_id: str, products: list[Product]) -> None: ...

    def process_fetch_job(self, job_id: str) -> None: ...
```

**FastAPI-shaped endpoints (only if asked to code):**
```python
@router.post("/v1/users")
def create_user(...): ...

@router.post("/v1/sdk-tokens")
def create_sdk_token(...): ...

@router.post("/webhooks/phyllo")  # customer side
async def receive_webhook(request: Request): ...
```

**Idempotency pattern:**
```python
def upsert_content(item: ContentItem) -> None:
    # UNIQUE(platform, platform_content_id)
    repo.insert_on_conflict_update(item)
```

**Webhook ACK pattern (customer OR Phyllo worker):**
```python
async def handle(request):
    body = await request.body()
    verify_signature(secret, body, request.headers["X-Phyllo-Signature"])
    await queue.publish(body)
    return Response(status_code=200)  # ACK fast; process async
```

---

## 8. Patterns Phyllo interviewers will love (checklist)

Tick these mentally during the design:

- [ ] **Consent-first** data access
- [ ] **Adapter pattern** for platforms
- [ ] **Async sync** + **webhooks over polling**
- [ ] **Light webhook payloads (IDs) + bulk fetch**
- [ ] **HMAC signature** verification
- [ ] **Exponential backoff / TTL retry queues**
- [ ] **Idempotent upserts** + delivery dedupe
- [ ] **Per-product sync status**
- [ ] **Rate limits** (platform + tenant)
- [ ] **Reauth** when tokens expire
- [ ] **PII minimization** + encryption of tokens
- [ ] **Multi-tenant** isolation (developer_id everywhere)
- [ ] **Observability**: delivery metrics, sync lag, failure reasons

---

## 9. Map YOUR resume → Phyllo (say this naturally)

| Your experience | Phyllo parallel |
|-----------------|-----------------|
| VoXgent campaign scheduler (Pub/Sub, Cloud Tasks, retries) | Sync job orchestration + webhook retries |
| Gemini Live + Twilio webhooks | Connect SDK events + webhook lifecycle |
| Redis concurrency / session controls | Rate limits, locks, sync leases |
| Europa API Gateway + rate limiting + auth | Phyllo multi-tenant API gateway |
| MQTT event-driven IoT | Event-driven account/content updates |
| Python + FastAPI | Same stack language as design language |

**Sample bridge sentence:**
> “In production I owned an outbound scheduler on Pub/Sub and Cloud Tasks with retries and Redis concurrency caps. Phyllo’s sync + webhook delivery is the same shape: enqueue work, bound concurrency, retry with backoff, and never block the ACK path.”

---

## 10. Likely follow-up questions (rapid fire)

1. Why webhooks instead of polling?  
2. At-least-once vs exactly-once for webhook delivery?  
3. How do you prevent a slow customer from blocking the queue?  
4. How do you add a new platform in <1 sprint?  
5. What if Instagram API schema changes?  
6. How do you handle token expiry mid-sync?  
7. How do you backfill 2 years of YouTube videos without blowing rate limits?  
8. How do you ensure developer A cannot read developer B’s users?  
9. SQL vs Elasticsearch for creator search?  
10. How would you test Connect without hitting real Instagram? (sandbox)  
11. What indexes for `GET content by account_id + published_at desc`?  
12. How do you version the normalized schema?  
13. Race: CONTENTS.UPDATED arrives before CONTENTS.ADDED?  
14. How do you redact data after consent revoke / GDPR delete?  
15. Where would you put caching (Redis) in the read path?

**Short answers to memorize:**
- Webhooks: push, lower load, near-real-time; polling burns quota.
- At-least-once + idempotent consumers.
- Per-tenant queues or concurrency limits + timeouts.
- Platform adapter + config + connector certification tests.
- Normalizer versioning; raw payload archive optional.
- Mark REAUTH_REQUIRED; pause jobs; notify via webhook.
- Priority queues, checkpoint cursors, trickle QPS.
- `developer_id` on every row + authz middleware.
- Postgres source of truth; OpenSearch for discovery queries.
- Sandbox connectors returning fixtures.
- `(account_id, published_at DESC)` composite index.
- `schema_version` on normalized docs; expand-contract migrations.
- Upserts keyed by platform IDs; ignore stale `updated_at`.
- Soft-delete + async purge workers; stop sync immediately.
- Cache profile summaries TTL; never cache raw OAuth tokens in shared Redis without encryption/isolation.

---

## 11. Mini schemas you can redraw fast

### Connect / Sync
```
developers(id, name, client_id, client_secret_hash)
users(id, developer_id, external_id)
work_platforms(id, name, connector_key)
accounts(id, user_id, work_platform_id, status, external_account_id)
consents(id, account_id, product, status)
sync_jobs(id, account_id, product, status, cursor, locked_until)
profiles(account_id PK, handle, display_name, followers, payload_json, updated_at)
content_items(id, account_id, platform_content_id, published_at, metrics_json, UNIQUE(account_id, platform_content_id))
```

### Webhooks
```
webhook_subscriptions(id, developer_id, url, secret, events[])
webhook_deliveries(id, subscription_id, event_id UNIQUE, event_type, payload, status, retry_count)
```

---

## 12. 40-minute mock script (practice out loud)

**Interviewer:** “Design account connect and data sync for a Phyllo-like platform.”

**You:**
1. “Phyllo-style: multi-platform consented data gateway. I’ll design Connect + Sync + notify.”
2. Requirements: link account, consent products, initial+incremental sync, notify developers, secure tokens, handle reauth.
3. NFRs: eventually consistent reads OK; at-least-once webhooks; horizontal workers; rate limits.
4. Entities: Developer, User, Account, Consent, SyncJob, Profile, Content, WebhookSubscription.
5. APIs: create user, create sdk token, list accounts, get profile, list content, register webhook.
6. Flow sequence: token → SDK → OAuth → ACCOUNT.CONNECTED → sync jobs → normalize → upsert → webhook IDs → customer bulk GET.
7. Classes: PlatformConnector adapters, SyncOrchestrator, WebhookDispatcher, SignatureService.
8. Failures: retries, REAUTH_REQUIRED, DLQ, per-product status.
9. Scale: shard jobs by account_id; Redis rate limits; queue per priority (initial vs incremental).
10. “Extensible via new connector implementation.”

Stop and ask: “Want me to deepen webhooks, schema, or connector interface?”

---

## 13. Night-before product cheat sheet (website → interview language)

| Website phrase | LLD translation |
|----------------|-----------------|
| Public vs Consented | AuthZ + connector type + data classification |
| Connect SDK | OAuth session + short-lived SDK token + client events |
| Normalized data | Canonical schema + platform adapters |
| Creator Search 470M | Search index + ingestion pipeline |
| Social listening | Stream ingest + NLP/classifiers + aggregates |
| Verified income | Transaction ledger + statements |
| Social KYC | Ownership proof workflow + audit report |
| Influencer vetting | Profile features + authenticity + brand safety flags |
| Webhooks | Reliable delivery subsystem |
| 7 days to production | DX: sandbox, SDKs, clear sync states |

---

## 14. What exactly you need to prepare (bottom line)

### Must-have (do not skip)
1. Explain Phyllo in 60 seconds + public vs consented  
2. Draw **Connect → Sync → Webhook** end-to-end  
3. Design **webhook retries + HMAC** (their blog)  
4. Class/API/schema for **multi-platform adapters**  
5. Speak LLD in **Python** (dataclasses, ABC connectors, FastAPI-ish routes)  
6. Idempotency, rate limits, reauth, multi-tenant safety  

### Nice-to-have
7. Income aggregation  
8. Creator search indexing  
9. Social listening pipeline  

### Do NOT waste time on
- Memorizing every Phyllo endpoint field  
- Building UI for Connect  
- Deep ML for sentiment  
- LeetCode during LLD prep night  

---

## 15. Links (official)

- Product: https://www.getphyllo.com/  
- About: https://www.getphyllo.com/about  
- Docs: https://docs.getphyllo.com/  
- Webhook eng blog: https://www.getphyllo.com/post/building-a-distributed-webhook-system  
- Webhook handling guide: https://docs.getphyllo.com/docs/api-reference/guides/handling-phyllo-webhooks  
- Connect SDK getting started: https://docs.getphyllo.com/docs/api-reference/connect-SDK/getting-started-with-connect-SDK  

---

## 16. Day-of interview checklist

- [ ] Laptop charged; pen + paper ready for entities  
- [ ] Open blank doc for API list while talking  
- [ ] Start with clarifying questions every time  
- [ ] Use Phyllo words: user, account, work platform, products, sync status, webhook  
- [ ] Code/design in Python  
- [ ] Mention tradeoffs unprompted once  
- [ ] Link 1–2 resume stories (scheduler / gateway / webhooks)  
- [ ] End with: “I can go deeper on connector abstraction, schema, or failure modes — which is most useful?”  

---

*Good luck, Alok. Your production work on queues, webhooks, Redis, and API gateways is already the shape of Phyllo’s core systems — make that the spine of every design.*
