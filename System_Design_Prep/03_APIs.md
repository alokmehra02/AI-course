# Module 03 — API Design: REST, GraphQL, gRPC & API Gateway

> **What this module makes you able to do:** sketch a complete, correct API contract for
> any system-design prompt in five minutes — resources, methods, status codes,
> pagination, versioning, idempotency and errors — and then defend REST vs GraphQL vs
> gRPC with numbers instead of opinions.
>
> **Interview weight:** ★★★★★ (asked in almost every interview)
>
> **Prerequisites:** Module 01 — Requirements & Estimation, Module 02 — Networking & HTTP

---

## Contents

| # | Topic | Interview weight |
|---|-------|------------------|
| 3.1 | What interviewers actually want from "define the API" | ★★★★★ |
| 3.2 | REST — resource modelling, methods, status codes, idempotency | ★★★★★ |
| 3.3 | Pagination — offset vs cursor/keyset | ★★★★★ |
| 3.4 | API versioning | ★★★★☆ |
| 3.5 | Idempotency in APIs — the `Idempotency-Key` pattern | ★★★★★ |
| 3.6 | Error design | ★★★★☆ |
| 3.7 | GraphQL — resolvers, N+1, DataLoader, complexity limits | ★★★★☆ |
| 3.8 | gRPC — protobuf, streaming, HTTP/2, deadlines | ★★★★☆ |
| 3.9 | REST vs GraphQL vs gRPC vs SOAP — the decision | ★★★★★ |
| 3.10 | Webhooks — the reverse API | ★★★★☆ |
| 3.11 | API Gateway — and how it differs from LB and service mesh | ★★★★★ |
| 3.12 | API contracts & schema evolution | ★★★☆☆ |

---

## 3.1 What interviewers actually want from "define the API"

**Interview weight:** ★★★★★

> **One-liner:** "Define the API" is a five-minute test of whether you can turn vague
> requirements into a contract — and it is the step that locks in your data model, your
> caching story and your failure semantics for the rest of the interview.

### Say this in the interview

> Before I draw any boxes, I want to write down the three or four endpoints that carry
> the actual product, because the API contract forces every other decision. For a URL
> shortener that's `POST /v1/links` to create, `GET /{code}` to redirect, and
> `GET /v1/links/{id}/stats` for analytics. I'll write the request and response bodies
> out, because that's where the interesting questions live — is the short code
> client-supplied or server-generated, is creation idempotent if the client retries, and
> is the redirect a 301 or a 302? I'd use 302 here, because a 301 gets cached by browsers
> and CDNs essentially forever and I'd lose all click analytics and the ability to
> re-point a link. That one decision tells you the redirect endpoint is read-heavy,
> cacheable, and needs to be sub-50 milliseconds, while the create endpoint is
> low-volume and can afford a database round trip. I usually spend about five minutes
> here and then let the API shape drive the data model.

### Mental model

The API is the contract between the parts of the system you're designing and the parts
you're not. Interviewers use it as a probe because a candidate who writes
`POST /createUser` and `POST /getUser` has told them, in ten seconds, that they have
never owned a public API.

What a good five-minute sketch contains, in order:

```text
 1. Nouns        →  what are the resources?      links, users, jobs
 2. Verbs        →  which HTTP methods?          POST / GET / PATCH / DELETE
 3. Shapes       →  request + response JSON      including IDs and timestamps
 4. Semantics    →  status codes + idempotency   201 vs 202, retry-safe?
 5. Scale knobs  →  pagination + filtering       cursor, limit, sort
```

The flow of information in the interview looks like this — notice the API is upstream of
almost everything:

```text
   Requirements
        │
        ▼
   ┌──────────┐  "what are the resources and operations?"
   │   API    │
   └────┬─────┘
        │ shapes the ...
        ├──────────────► Data model   (fields, indexes, keys)
        ├──────────────► Read/write split (which endpoints are hot?)
        ├──────────────► Caching      (which responses are cacheable?)
        ├──────────────► Sync vs async (202 + job id, or 201 + resource?)
        └──────────────► Failure semantics (retry-safe? idempotent?)
```

The single highest-value habit: **for every write endpoint, say out loud whether it is
synchronous or asynchronous.** If the work takes longer than about a second — document
ingestion, video transcode, embedding generation — you return `202 Accepted` with a job
resource and let the client poll or subscribe, rather than holding an HTTP connection
open and inventing a timeout problem.

```text
Synchronous create (fast, < ~500 ms)
  POST /v1/links          →  201 Created
                             Location: /v1/links/abc123
                             { "id": "abc123", "url": "..." }

Asynchronous create (slow, seconds to minutes)
  POST /v1/documents      →  202 Accepted
                             Location: /v1/jobs/j_88f2
                             { "job_id": "j_88f2", "status": "queued" }
  GET  /v1/jobs/j_88f2    →  200 { "status": "processing", "progress": 0.4 }
                          →  200 { "status": "succeeded",
                                   "document_id": "doc_51" }
```

### Enterprise production example

**Stripe** publishes an API where nearly every meaningful object is a plain noun —
`/v1/charges`, `/v1/customers`, `/v1/payment_intents` — and every mutating request
accepts an `Idempotency-Key` header. That combination is not decoration: because create
operations are retry-safe by contract, Stripe's own client libraries retry automatically
with exponential backoff and jitter on network failure. The API shape is what makes the
client library safe. Note also that the version prefix in the path has stayed `v1` since
2011 — Stripe moved versioning into a header instead (see [3.4](#34-api-versioning)),
which is the opposite of what most candidates propose.

### Code

A five-minute sketch you can literally write on the whiteboard. This is the level of
detail that scores.

```http
POST /v1/links
Authorization: Bearer <token>
Idempotency-Key: 8f1c9e2a-...        # retry-safe creation
Content-Type: application/json

{ "url": "https://example.com/very/long", "custom_code": null,
  "expires_at": "2027-01-01T00:00:00Z" }

201 Created
Location: /v1/links/abc123
{ "id": "lnk_01H...", "code": "abc123",
  "short_url": "https://sho.rt/abc123",
  "url": "https://example.com/very/long",
  "created_at": "2026-09-01T04:00:00Z" }

GET /abc123
302 Found
Location: https://example.com/very/long
Cache-Control: private, max-age=0        # keep analytics; see follow-up

GET /v1/links?limit=25&cursor=eyJpZCI6...&sort=-created_at
200 OK
{ "data": [ ... ], "next_cursor": "eyJpZCI6...", "has_more": true }
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Always — spend 5 min on the API in any design round | You're 40 minutes in and haven't drawn the architecture | 5 of your 45 minutes; skipping it costs you the data model |
| Return `202` + job resource for work > ~1 s | The operation is genuinely fast and the client needs the result | Client must poll or subscribe; you now own job state |
| `302` redirect when you need analytics or re-pointing | You want browsers/CDNs to cache the redirect forever | Every redirect hits your origin — you must cache server-side |

### Follow-ups they will ask

**Q: Your URL shortener returns 302. Won't that hammer your origin with every click?**
A: Yes, and that's the deliberate trade. A 301 is cached by browsers and CDNs, so I'd
lose click analytics and could never re-point or expire a link. I keep the 302 and
absorb the read load with a Redis cache in front of Postgres — the code-to-URL mapping is
immutable once created, so it's a perfect cache candidate with a long TTL and roughly a
99% hit rate. That turns a database read into a sub-millisecond Redis GET.

**Q: Should the client generate the resource ID or the server?**
A: Server by default, because the server owns uniqueness. But I'll accept a
client-generated ID when the client needs to create offline or needs the ID before the
round trip completes — then I use a UUIDv7 or ULID so the ID is still roughly
time-ordered for index locality, and I enforce uniqueness with a Postgres unique
constraint so a duplicate arrives as a 409 rather than a second row.

**Q: How do you decide between `PATCH` and `PUT` for updates?**
A: `PATCH` for almost everything, because clients rarely hold the full resource and a
`PUT` with a partial body silently deletes fields. I reserve `PUT` for genuine
whole-resource replacement — like setting a config document — where idempotency matters
more than convenience. If concurrent updates are a real risk I add an `ETag` and require
`If-Match`, so a stale writer gets a 412 instead of clobbering.

**Q: The interviewer says "just design the API for a chat app." What do you write?**
A: `POST /v1/conversations/{id}/messages` to send (with an `Idempotency-Key`, because
mobile clients retry constantly),
`GET /v1/conversations/{id}/messages?limit=50&before=<cursor>` for history — cursor, not
offset, because the list grows at the head — and then I'd say the read path for *live*
messages isn't REST at all: it's a WebSocket or SSE stream, and the REST endpoint exists
for backfill after reconnect.

### Red flags — do not say this

- ❌ "`POST /getUserOrders`" → ✅ "`GET /v1/users/{id}/orders` — the method is the verb;
  the path is a noun."
- ❌ "I'll figure out the API later, let me draw the architecture first." → ✅ "Let me
  pin down three endpoints first, because they determine the data model and which reads
  I need to cache."
- ❌ "The API returns the created object." (for a 30-second job) → ✅ "This takes seconds,
  so I return `202 Accepted` with a job ID and the client polls `GET /v1/jobs/{id}`."

---

## 3.2 REST — resource modelling, methods, status codes, idempotency

**Interview weight:** ★★★★★

> **One-liner:** REST is a set of constraints — resources identified by URIs,
> manipulated with uniform methods, with the method's semantics telling clients and
> intermediaries what is safe to cache and safe to retry.

### Say this in the interview

> REST works because the method carries semantics that everything in the path — browsers,
> CDNs, proxies, my own retry logic — can act on without understanding my domain. `GET`
> is safe, so a CDN can cache it and a client can retry it freely. `PUT` and `DELETE` are
> idempotent, so a proxy that times out can retry without me worrying about duplicate
> side effects. `POST` is neither, which is exactly why every create endpoint that
> matters needs an idempotency key. The distinction I care about is safe versus
> idempotent: safe means no side effects at all, idempotent means the side effect happens
> at most once no matter how many times you send it. `PUT /users/42 {name: "Alok"}` is
> idempotent because it specifies the final state — send it five times and the row says
> Alok. `POST /users {name: "Alok"}` creates a new row every time, so five retries mean
> five users. That single asymmetry is the reason idempotency keys exist, and it's the
> thing I check on every write endpoint I design.

### Mental model

The whole table you need to hold in your head:

```text
Method   Safe?  Idempotent?  Cacheable?  Typical success
──────────────────────────────────────────────────────────────────
GET      yes    yes          yes         200 + body
HEAD     yes    yes          yes         200, no body
POST     no     NO           rarely      201 + Location, or 202
PUT      no     yes          no          200 / 204
PATCH    no     NO*          no          200 / 204
DELETE   no     yes          no          204 (or 200 with body)
```

`*` A `PATCH` that sets absolute values (`{"status": "cancelled"}`) is idempotent in
practice; a `PATCH` that applies a delta (`{"balance_delta": -100}`) is not. If your
PATCH bodies contain deltas, you have a POST wearing a costume — treat it like one and
require an idempotency key.

**Why `PUT` is idempotent and `POST` isn't**, stated as state transitions:

```text
PUT /accounts/42  { "credit_limit": 5000 }

  attempt 1 ──► state: credit_limit = 5000
  attempt 2 ──► state: credit_limit = 5000   (same final state)
  attempt 3 ──► state: credit_limit = 5000
  ▲ the request names the DESTINATION state → replay is a no-op


POST /accounts/42/transactions  { "amount": -100 }

  attempt 1 ──► balance 1000 → 900
  attempt 2 ──► balance  900 → 800   ← duplicate charge
  attempt 3 ──► balance  800 → 700
  ▲ the request names a DELTA and the server picks the ID → replay compounds
```

The Richardson maturity model, briefly, because interviewers occasionally name-drop it:

```text
Level 0  one URI, one verb (POST /api), RPC-over-HTTP  ── "SOAP-ish"
Level 1  resources have URIs, still all POST           ── halfway
Level 2  resources + correct HTTP methods + status     ── THIS IS THE TARGET
Level 3  + hypermedia links in responses (HATEOAS)     ── rarely worth it
```

Say "Level 2 is what production APIs actually ship; Level 3 hypermedia sounds elegant
but almost nobody's clients follow links dynamically, so the extra payload buys nothing."
That's the honest, senior answer. Stripe, GitHub's REST API and Twilio are all
essentially Level 2.

**Nested resources** — nest one level to express ownership, then stop:

```text
Good:  GET  /v1/users/42/orders            "orders belonging to user 42"
       POST /v1/orders/99/refunds          "a refund of order 99"

Bad:   GET  /v1/users/42/orders/99/items/7/reviews/3
       ▲ brittle: the client must know the whole ancestry to fetch one review.
         Instead expose GET /v1/reviews/3 and filter:
         GET /v1/reviews?order_item_id=7
```

Rule: nest to express *containment that the child cannot exist without*; use query
filters for everything else. A resource that has its own stable identity deserves its own
top-level collection.

**Filtering, sorting, search** — conventions that keep you out of trouble:

```text
Filter    ?status=active&created_after=2026-01-01
          ?status=active,pending          (OR within a field, comma-separated)
Sort      ?sort=-created_at,name          (leading '-' = descending)
Sparse    ?fields=id,name,email           (reduce payload without GraphQL)
Search    ?q=alok                         (opaque full-text; different from filter)
Page      ?limit=50&cursor=eyJ...         (see 3.3)
```

Two things that separate careful engineers here: **always cap `limit`** server-side
(`limit = min(client_limit or 25, 100)`) so a client cannot ask for a million rows, and
**only expose filters you have an index for** — an un-indexed filter parameter is a
sequential-scan denial-of-service vector that you shipped yourself.

### Enterprise production example

**GitHub's REST API** is a good Level-2 reference and shows the cost of getting status
codes right. It returns `404 Not Found` rather than `403 Forbidden` for private
repositories the caller can't see, because a 403 would leak the repository's existence.
It also returns `422 Unprocessable Entity` — not `400` — when the JSON parses fine but a
field fails validation, which lets clients distinguish "I sent malformed bytes" from "I
sent well-formed but invalid data." Those two choices are pure API design, cost nothing
at runtime, and are exactly the kind of detail interviewers reward.

### Code

Status codes are where candidates lose points. This FastAPI router shows the full set on
one resource.

```python
from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, HttpUrl

router = APIRouter(prefix="/v1/links")

class LinkCreate(BaseModel):
    url: HttpUrl
    custom_code: str | None = None

@router.post("", status_code=status.HTTP_201_CREATED)
async def create_link(body: LinkCreate, response: Response, db=Depends(get_db)):
    try:
        link = await db.insert_link(body.url, body.custom_code)
    except UniqueViolation:
        # 409, not 400: the request is valid, the CURRENT STATE conflicts.
        raise HTTPException(409, detail="custom_code already taken")
    response.headers["Location"] = f"/v1/links/{link.id}"
    return link

@router.patch("/{link_id}", status_code=status.HTTP_200_OK)
async def update_link(link_id: str, body: LinkPatch, if_match: str | None = Header(None)):
    current = await db.get_link(link_id)
    if current is None:
        raise HTTPException(404)
    if if_match and if_match != current.etag:
        # 412: the client's view of the resource is stale. Prevents lost updates.
        raise HTTPException(412, detail="etag mismatch, re-read and retry")
    return await db.update_link(link_id, body.model_dump(exclude_unset=True))

@router.delete("/{link_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_link(link_id: str):
    await db.delete_link(link_id)          # already gone → still 204: idempotent
    return Response(status_code=204)
```

The status codes worth memorising, with the distinction that matters:

```text
200 OK                    read or update succeeded, body returned
201 Created               + Location header pointing at the new resource
202 Accepted              queued; returns a job id, NOT the result
204 No Content            succeeded, deliberately no body (DELETE, PUT)
304 Not Modified          conditional GET hit — client's ETag still valid
400 Bad Request           malformed syntax / unparseable body
401 Unauthorized          no or bad credentials    ("who are you?")
403 Forbidden             authenticated but not allowed ("not your resource")
404 Not Found             absent — or hidden, to avoid leaking existence
409 Conflict              valid request, conflicting state (dup key, version)
412 Precondition Failed   If-Match / If-Unmodified-Since failed
422 Unprocessable Entity  parsed fine, failed business validation
429 Too Many Requests     + Retry-After: seconds
500 Internal Server Error our bug — the client should NOT keep retrying blindly
502 / 504                 upstream failed / upstream timed out — retryable
503 Service Unavailable   overloaded or shedding + Retry-After — retryable
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Public / partner APIs, browser clients, anything cacheable | Chatty internal service-to-service calls at high QPS | JSON parsing cost and over-fetching; N round trips for N resources |
| Level 2 (resources + methods + status codes) | Level 3 HATEOAS "because REST purity" | Level 3 adds payload and client complexity almost nobody uses |
| Nesting one level to show ownership | Nesting 3+ levels | Deep paths break when the hierarchy changes; clients must know ancestry |

### Follow-ups they will ask

**Q: `POST` isn't idempotent. So how do you make a "create payment" endpoint safe to
retry?**
A: Client-supplied idempotency key in a header, stored server-side and scoped to the
account. First request claims the key and stores the response; a retry with the same key
replays the stored response instead of executing again. That's exactly what Stripe does
with `Idempotency-Key`, and I'd back it with a unique constraint in Postgres so the
guarantee survives a Redis failure — I cover the implementation in
[3.5](#35-idempotency-in-apis--the-idempotency-key-pattern).

**Q: What's the difference between 401, 403 and 404 for a resource I don't own?**
A: 401 means I don't know who you are — bad or missing token. 403 means I know who you
are and you're not allowed. 404 means it doesn't exist *as far as you're concerned* —
and that's the right answer for another tenant's resource, because a 403 confirms the
resource exists and leaks information. GitHub does exactly this for private repos.

**Q: Is `DELETE` really idempotent if the second call returns 404?**
A: Idempotency is about server state, not the response code, so deleting twice is
idempotent either way. But I'd return 204 both times rather than 404 on the second call,
because a client whose first response was lost to a network timeout shouldn't have to
interpret 404 as success. Returning 204 makes the retry trivially safe.

**Q: A client asks for `?limit=100000`. What happens?**
A: The server clamps it — `limit = min(requested, 100)` — and I document the maximum. An
unbounded `limit` is a self-inflicted denial of service: one client can pull the whole
table, blow up memory serialising the response, and hold a database connection for
minutes. Same reasoning applies to filter parameters: I only expose filters that have a
supporting index.

**Q: Where do you put actions that aren't CRUD, like "cancel this order"?**
A: I model the action as a state change on the resource — `PATCH /v1/orders/99
{"status": "cancelled"}` — when cancellation really is just a field. When it has its own
lifecycle, side effects and audit trail, I make it a sub-resource:
`POST /v1/orders/99/cancellations`. That gives the action an ID, a timestamp and a
retryable creation, which a status flip does not.

### Red flags — do not say this

- ❌ "REST means JSON over HTTP." → ✅ "REST is resources plus uniform method semantics —
  which is what lets caches and retries work without domain knowledge."
- ❌ "`POST` and `PUT` are basically the same." → ✅ "`PUT` names the destination state so
  it's idempotent; `POST` creates a new resource each time, so retries duplicate."
- ❌ "I'll return 200 with `{"error": ...}` in the body." → ✅ "I use the status code as
  the machine-readable outcome; a 200 with an error body breaks every client retry
  policy, every proxy and every dashboard."
- ❌ "I'll add HATEOAS for full REST compliance." → ✅ "Level 2 is the production target;
  hypermedia adds payload that almost no client actually follows."

---

## 3.3 Pagination — offset vs cursor/keyset

**Interview weight:** ★★★★★

> **One-liner:** `OFFSET` makes the database read and throw away every row you skipped,
> so deep pages get linearly slower and concurrent inserts silently duplicate or skip
> items; a keyset cursor seeks straight to the row you left off at.

### Say this in the interview

> I default to cursor pagination for any list endpoint, and the reason is mechanical, not
> stylistic. PostgreSQL's own documentation says the rows skipped by an `OFFSET` clause
> still have to be computed inside the server — so `LIMIT 20 OFFSET 1000000` reads a
> million rows, sorts them, discards them, and returns twenty. That's O(n) in the offset,
> so page one is under a millisecond and page fifty thousand is tens to hundreds of
> milliseconds on the same table. The second problem is worse because it's silent: if
> someone inserts a row at the head of the list between my request for page one and page
> two, everything shifts down one position and the client sees the same item twice, or
> misses one entirely. A keyset cursor fixes both — I encode the last row's sort key and
> its ID, and the next query is `WHERE (created_at, id) < (:ts, :id) ORDER BY created_at
> DESC, id DESC LIMIT 20`, which is a single index seek regardless of depth, and it's
> stable because the position is a value in the data rather than a count of rows. The
> price I pay is that clients can't jump to page 500 and I can't cheaply show a total
> count — and for a feed or an infinite scroll, nobody wanted either of those.

### Mental model

```text
OFFSET pagination — the server pays for everything you skip

  SELECT * FROM messages
  ORDER BY created_at DESC
  LIMIT 20 OFFSET 100000;

  ┌────────────────────────────────────────────┬──────────┐
  │ read + sort + DISCARD 100,000 rows         │ return 20│
  └────────────────────────────────────────────┴──────────┘
   ▲ cost grows linearly with the offset, index or no index


KEYSET pagination — the server seeks once

  SELECT * FROM messages
  WHERE (created_at, id) < ('2026-08-30 11:04:02', 918_233)
  ORDER BY created_at DESC, id DESC
  LIMIT 20;

  index (created_at DESC, id DESC)
  ─────────────────────┬──────────┐
        seek here ────►│ return 20│
  ─────────────────────┴──────────┘
   ▲ cost is O(log n + page_size), constant with depth
```

**The drift bug**, which is the part candidates never mention and interviewers love:

```text
t=0  client fetches page 1 (OFFSET 0 LIMIT 3)
     list: [ M9, M8, M7 ] M6 M5 M4 ...          → client has M9 M8 M7

t=1  a new message M10 is inserted at the head
     list: M10 [ M9, M8, M7 ] M6 M5 ...

t=2  client fetches page 2 (OFFSET 3 LIMIT 3)
     list: M10 M9 M8 [ M7, M6, M5 ]             → client gets M7 AGAIN
                                                  (and if a row were DELETED
                                                   instead, it would SKIP one)

Keyset: cursor = (M7.created_at, M7.id) → "give me strictly older than M7".
        Insertions at the head cannot shift the boundary. No dup, no skip.
```

**Why the tie-breaker is mandatory.** If you paginate on `created_at` alone and two rows
share a timestamp, the boundary is ambiguous: `< '2026-08-30 11:04:02'` skips the sibling
row, and `<=` returns it twice. Always make the cursor the full tuple
`(sort_column, unique_id)` and put a matching composite index on
`(sort_column DESC, id DESC)`. Without that index, keyset pagination is just a
sequential scan with extra steps.

**Paginating a feed sorted by popularity** — this is the hard variant, and the honest
answer is that you don't keyset a mutable score directly:

```text
Problem: ORDER BY score DESC where score changes every minute.
         A keyset cursor on (score, id) is unstable — a row you already
         returned can have its score raised and reappear on a later page.

Answer:  snapshot the ranking, paginate the snapshot.

  1. A ranking job writes an ordered list per feed into Redis:
        ZADD feed:u42:v7  <score> <post_id>          (or a materialised table)
  2. The cursor encodes (ranking_version, rank_offset):
        cursor = b64({"v": 7, "rank": 60})
  3. Page fetch is a rank-range read on an immutable snapshot:
        ZREVRANGE feed:u42:v7 60 79        ← O(log N + 20), stable
  4. Hydrate the 20 post IDs from Postgres/cache in one batched query.
  5. New ranking → version 8. Old cursors keep reading v7 (TTL ~30-60 min),
     so a user mid-scroll never sees duplicates; a refresh starts at v8.
```

Inside an immutable snapshot, offset-style rank ranges are fine — the O(n) skip
objection was about the *database* re-sorting rows, and a Redis sorted set indexes by
rank directly. The versioning is what buys stability.

### Enterprise production example

**GitHub's GraphQL API** enforces cursor pagination at the schema level: every connection
*requires* a `first` or `last` argument, its value must be between 1 and 100, and a
single call cannot request more than 500,000 total nodes. Requests that violate the node
ceiling are rejected before execution with a message naming the computed node count —
teams routinely hit it by nesting `commits { authors }` inside a 200-item PR list, which
statically costs `200 × commits × authors` nodes. This is what it looks like when a
platform decides that unbounded pagination is not a client's decision to make.

Stripe's REST API uses the other shape of the same idea: `starting_after` and
`ending_before` take an object ID rather than a page number, so the cursor is a position
in the data, not a count of rows.

### Code

Opaque, signed cursors in FastAPI. Two rules: **make the cursor opaque** so you can
change the underlying keyset without breaking clients, and **fetch `limit + 1` rows** so
you know whether there's a next page without a second `COUNT(*)`.

```python
import base64, json, hmac, hashlib
from fastapi import APIRouter, HTTPException, Query

CURSOR_SECRET = settings.cursor_secret.encode()

def encode_cursor(created_at: str, row_id: int) -> str:
    payload = json.dumps({"t": created_at, "i": row_id}, separators=(",", ":"))
    sig = hmac.new(CURSOR_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16]
    return base64.urlsafe_b64encode(f"{payload}.{sig}".encode()).decode().rstrip("=")

def decode_cursor(cursor: str) -> tuple[str, int]:
    raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    payload, _, sig = raw.rpartition(".")
    expected = hmac.new(CURSOR_SECRET, payload.encode(), hashlib.sha256).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):     # signed so clients can't probe rows
        raise HTTPException(400, "invalid cursor")
    d = json.loads(payload)
    return d["t"], d["i"]

@router.get("/v1/messages")
async def list_messages(
    conversation_id: str,
    limit: int = Query(25, ge=1, le=100),          # HARD server-side cap
    cursor: str | None = None,
    db=Depends(get_db),
):
    args: list = [conversation_id]
    where = "conversation_id = $1"
    if cursor:
        ts, row_id = decode_cursor(cursor)
        where += " AND (created_at, id) < ($2, $3)"   # row-value comparison
        args += [ts, row_id]

    rows = await db.fetch(
        f"""SELECT id, body, created_at FROM messages
            WHERE {where}
            ORDER BY created_at DESC, id DESC
            LIMIT ${len(args) + 1}""",
        *args, limit + 1,                          # +1 probe row => has_more
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = (encode_cursor(page[-1]["created_at"].isoformat(), page[-1]["id"])
                   if has_more and page else None)
    return {"data": page, "next_cursor": next_cursor, "has_more": has_more}
```

The index that makes it O(log n) instead of a scan — say this out loud, because keyset
pagination without it is a trap:

```sql
CREATE INDEX idx_messages_conv_created
  ON messages (conversation_id, created_at DESC, id DESC);
-- Leading equality column first, then the keyset tuple in the exact ORDER BY
-- direction. Postgres can then satisfy WHERE + ORDER BY + LIMIT from one seek.
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **Cursor/keyset:** feeds, infinite scroll, sync/export APIs, any table over ~100k rows | The UI genuinely needs "jump to page 47" | No random page access, no cheap total count, more implementation work |
| **Offset:** small admin tables, internal tools, datasets under a few thousand rows that rarely change | Public APIs, growing tables, anything sorted by a mutable column | O(n) deep-page latency plus silent duplicate/skip on concurrent writes |
| **Snapshot + rank range:** popularity/relevance feeds | Strictly chronological lists (plain keyset is simpler) | Extra ranking store, versioning, and staleness window (30-60 min) |

### Follow-ups they will ask

**Q: The product team insists on showing "Page 7 of 412". Now what?**
A: Two moves. First, replace the exact count with an approximation — in Postgres,
`reltuples` from `pg_class` or a `COUNT(*)` capped by a subquery
(`SELECT count(*) FROM (SELECT 1 FROM t WHERE ... LIMIT 1000) s`) gives "1000+" cheaply,
because an exact `COUNT(*)` on a large filtered set is itself a full scan. Second, keep
keyset for the Next/Previous path and only pay for offset when someone actually clicks a
far page number — which in practice almost nobody does past page three.

**Q: How does a client resume after a 30-minute gap if your snapshot expired?**
A: I version the cursor and handle expiry explicitly rather than silently. If the cursor
names ranking version 7 and only 9 exists, I return `410 Gone` with a
`{"code": "cursor_expired"}` body, and the client restarts from the top of the current
ranking. Silently switching them to version 9 mid-scroll would produce exactly the
duplicate-and-skip behaviour I moved off offset to avoid.

**Q: Why sign the cursor? It's just base64.**
A: Because an unsigned cursor is a client-controlled `WHERE` clause. Someone will decode
it, edit the timestamp or inject a value, and now they're probing rows outside their
result set or triggering an unindexed query path. An HMAC costs microseconds and makes
the cursor genuinely opaque, which also means I can change the underlying keyset columns
later without breaking any client that stored one.

**Q: Does cursor pagination work across a sharded database?**
A: Not directly — a single cursor can't name a position in N independently sorted shards.
The usual answer is a composite cursor holding one position per shard, then a
merge-sorted scatter-gather read that fetches `limit` from each shard and keeps the
global top `limit`. That's `N × limit` rows of read amplification, which is why systems at
that scale usually shard on the same key they paginate within — `conversation_id`, for
instance — so any one list lives entirely on one shard.

**Q: Your keyset query is still slow. What went wrong?**
A: Almost always the index doesn't match the `ORDER BY` direction, so Postgres does a
sort instead of a seek — I'd check `EXPLAIN ANALYZE` for a `Sort` node above the index
scan. The other common cause is a filter column that isn't the leading key of the index,
which forces a scan-and-filter. And I'd run `EXPLAIN` at a realistic depth, not on page
one, because page one looks fine in every implementation.

### Red flags — do not say this

- ❌ "I'll use `LIMIT`/`OFFSET`, it's simpler." → ✅ "Offset makes the database compute and
  discard every skipped row, and it duplicates items when rows are inserted mid-scroll,
  so I use a keyset cursor."
- ❌ "An index fixes the offset problem." → ✅ "An index helps find the sort order, but
  Postgres still has to compute and discard the skipped rows — the offset cost is
  unavoidable."
- ❌ "Cursor is `created_at` of the last row." → ✅ "The cursor is the tuple
  `(created_at, id)`, because timestamp ties would otherwise skip or duplicate a row."
- ❌ "I'll return the total count on every page." → ✅ "An exact `COUNT(*)` on a filtered
  large table is a full scan; I return `has_more`, and an approximate count only if the
  UI truly needs it."

---

## 3.4 API versioning

**Interview weight:** ★★★★☆

> **One-liner:** Versioning is not about the URL — it's about having a rule for what
> counts as a breaking change, a mechanism to serve old shapes from new code, and a
> deprecation policy with a date on it.

### Say this in the interview

> The mistake I see is treating versioning as a URL question when it's really a
> compatibility-contract question. My default for a public API is a major version in the
> path — `/v1/` — for genuinely incompatible rewrites, plus an explicit rule that
> additive changes never bump the version: new endpoints, new optional request
> parameters, and new response fields are all non-breaking, provided clients don't
> validate strictly against unknown fields. Anything that removes a field, renames one,
> tightens validation, or changes a default is breaking, and it needs a new version. The
> design I'd actually point at is Stripe's: their path has said `v1` since 2011, and the
> real version is a date in the `Stripe-Version` header. Your account gets pinned to
> whatever version was current on your first request, and internally their engineers only
> ever write code against the latest schema — a chain of small transformation modules
> rewrites the modern response backwards, one version at a time, until it matches what
> your pinned version expects. That's the key insight: the core business logic has no
> version branches in it at all, which is what makes maintaining a decade of
> compatibility survivable rather than a swamp of if-statements.

### Mental model

Three places to put the version, and what each costs:

```text
1. URL path           GET /v2/users/42
   + trivially visible in logs, curl, dashboards; easy routing/caching
   + easy to run v1 and v2 as separate deployments
   − "v2" tempts you to fork the whole API for one field change
   − clients hardcode URLs everywhere; migration is a code change

2. Custom header      GET /users/42   +  Api-Version: 2026-03-01
   + one URL forever; version can be per-request or per-account
   + fine-grained: dozens of small versions instead of two huge ones
   − invisible in a browser address bar; must remember Vary: Api-Version
   − caches and CDNs need explicit configuration

3. Content negotiation  Accept: application/vnd.acme.user.v2+json
   + "correct" per HTTP semantics; version travels with representation
   − painful to type, poorly supported by tooling, confuses everyone
   − in practice: rarely worth it
```

**How Stripe actually does it** — worth being able to draw, because it's the design that
scales:

```text
        request  (Stripe-Version: 2019-12-03, or account's pinned version)
            │
            ▼
   ┌──────────────────────┐
   │ Request compat layer │  reject/translate params not valid for that version
   └──────────┬───────────┘
              ▼
   ┌──────────────────────┐
   │ CORE BUSINESS LOGIC  │  written ONLY against the latest schema.
   │   (no version ifs)   │  This is the whole point.
   └──────────┬───────────┘
              ▼ response in latest shape
   ┌──────────────────────┐
   │  version change      │  2026-01-15 ─┐
   │  module chain,       │  2025-06-02  │ applied backwards, in order,
   │  applied in reverse  │  2024-04-10  │ until target version is reached
   │                      │  2019-12-03 ─┘
   └──────────┬───────────┘
              ▼
        response in the shape the client pinned to
```

Each version change module is a small, isolated transformer that knows one thing: how to
downgrade the new shape into the old one. Adding a breaking change means writing one new
module, not editing old code.

**The rules for what breaks.** Stripe publishes theirs; adopt them verbatim:

```text
NON-BREAKING (ship freely, no version bump)
  · add a new endpoint or resource
  · add a new OPTIONAL request parameter
  · add a new field to a response
  · reorder fields in a response
  · change the length or format of opaque strings (IDs, error messages)
  · add a new value to an enum you documented as extensible

BREAKING (needs a new version)
  · remove or rename a field or endpoint
  · change a field's type, or make an optional field required
  · tighten validation (a payload that used to be accepted now 422s)
  · change a default value or default sort order
  · change pagination semantics, or reduce a maximum page size
  · add a new enum value clients switch on exhaustively  ← the sneaky one
```

That last one is why you document enums as extensible on day one: "clients must treat
unknown values as `unknown` and not crash." Otherwise every new status you ever add is a
breaking change.

**Deprecation policy** — a version without a sunset date is a version you maintain
forever:

```text
T+0     announce; changelog entry; email the top-N integrators by call volume
T+0     start returning warning headers on every affected call:
          Deprecation: version="2024-04-10"
          Sunset: Wed, 01 Jul 2027 00:00:00 GMT
          Link: <https://docs.acme.com/upgrade/2026-01-15>; rel="deprecation"
T+3mo   dashboard per customer: "N calls on a deprecated version"
T+6mo   brownouts — return 410 for 5 minutes during a low-traffic window,
        twice, announced. This is what actually gets people to migrate.
T+9mo   sunset: 410 Gone with an upgrade link in the error body
```

### Enterprise production example

**Stripe** has maintained backwards compatibility for every API version since 2011.
Versions are named by release date (`2017-05-24`, `2019-12-03`); an account is pinned to
the current version on its very first API call, and can override per-request with the
`Stripe-Version` header or upgrade from the dashboard on its own schedule. Their
engineering blog describes the mechanism directly: engineers write code against the
current schema, and each backwards-incompatible change is encapsulated in a *version
change module* containing documentation, a transformation function, and the set of API
resource types it applies to. Responses are generated in the latest shape and then walked
backwards through every applicable module until they match the caller's target version.
The cost is real — a decade of transformation modules is a decade of code to keep working
— but the benefit is that no integrator has ever been force-migrated.

The contrast worth naming: most companies ship `/v1/` and `/v2/`, then discover that a
"v2" containing forty unrelated changes is something no customer will ever migrate to in
one step. Stripe's many-small-versions approach makes each upgrade a day of work instead
of a quarter.

### Code

The Stripe pattern, small enough to fit in FastAPI. The value here is that the handler
stays version-free.

```python
from datetime import date
from fastapi import Header, Request

# Each entry downgrades a LATEST-shaped payload one step into the past.
# Registered newest-first; applied in that order until we reach the target.
VERSION_CHANGES: list[tuple[date, str, callable]] = []

def version_change(released: str, resources: set[str]):
    def deco(fn):
        VERSION_CHANGES.append((date.fromisoformat(released), resources, fn))
        VERSION_CHANGES.sort(key=lambda v: v[0], reverse=True)
        return fn
    return deco

@version_change("2026-01-15", resources={"customer"})
def split_name_into_first_last(payload: dict) -> dict:
    """Before 2026-01-15, customers had first_name/last_name, not name."""
    name = payload.pop("name", "")
    first, _, last = name.partition(" ")
    payload["first_name"], payload["last_name"] = first, last
    return payload

@version_change("2025-06-02", resources={"customer", "charge"})
def flatten_billing_details(payload: dict) -> dict:
    billing = payload.pop("billing_details", {}) or {}
    payload["address_line1"] = (billing.get("address") or {}).get("line1")
    return payload

def downgrade(payload: dict, resource: str, target: date) -> dict:
    for released, resources, fn in VERSION_CHANGES:
        if released > target and resource in resources:
            payload = fn(dict(payload))
    return payload

async def api_version(request: Request,
                      x_api_version: str | None = Header(None)) -> date:
    if x_api_version:
        return date.fromisoformat(x_api_version)
    return request.state.account.pinned_api_version     # set at first-ever call

@router.get("/v1/customers/{cid}")
async def get_customer(cid: str, version: date = Depends(api_version)):
    customer = await db.get_customer(cid)               # LATEST shape only
    return downgrade(customer.model_dump(), "customer", version)
```

Do not forget the cache key, or you will serve a v2 body to a v1 client:

```python
# FastAPI middleware
response.headers["Vary"] = "Accept, X-Api-Version, Authorization"
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **URL major version:** public API, few big versions, separate deployments per version | You expect many small incompatible changes | Two codebases, or forked handlers; clients hardcode URLs |
| **Date/header version + transform chain:** long-lived platform API with many integrators | Small internal API with two known consumers | Real engineering investment: transform modules forever, plus `Vary` discipline |
| **No versioning, additive-only:** internal services you deploy together | Any external consumer you can't redeploy | You can never remove a field; schema accretes cruft |

### Follow-ups they will ask

**Q: You need to remove a field from a response. Walk me through it.**
A: I never remove it in place. I add the replacement field first and ship both, so
clients can migrate at their own pace. Then I instrument — log which API keys still read
the old field, either from a field-level access counter or from the version they're
pinned to. When usage of the old field on live traffic drops to near zero, I announce a
sunset date with `Deprecation` and `Sunset` headers, and I do one or two announced
brownouts before the actual removal. The metric gate matters more than the calendar: I
don't remove anything I can't prove is unused.

**Q: How many versions can you realistically support?**
A: Many, *if* each version is one small transformation module and your core logic is
version-free — Stripe supports a decade of them. If versioning means forked handlers or
forked services, the honest answer is two, briefly, because every bug fix has to land
twice and the second copy inevitably rots. So the number of versions you can support is
really a function of your versioning *architecture*, not your headcount.

**Q: Should internal microservices be versioned?**
A: Not with URL versions, no. Internally I use additive-only schema evolution — protobuf
field numbers, or Avro with a schema registry — and enforce backwards and forwards
compatibility in CI. The reason is deployment order: during a rolling deploy, new
producers and old consumers coexist for minutes, so the schema has to tolerate both
directions. Explicit versions there just move the problem into routing.

**Q: The client sends no version header at all. What do you do?**
A: For an existing account, use the version pinned at their first-ever call — never the
latest, because "latest" means the client silently breaks the day I ship a change. For a
brand-new key with no history, pin it to the current version and record that pin. The
invariant is that an unmodified client never sees a behaviour change.

### Red flags — do not say this

- ❌ "We'll just make it backwards compatible forever, no versions needed." → ✅ "Additive
  changes need no version; removals and tightened validation do — so I need a rule and a
  sunset policy, not just good intentions."
- ❌ "Bump to `/v2/` for the new field." → ✅ "Adding an optional field is non-breaking; a
  version bump for it trains clients to ignore version bumps."
- ❌ "Every client should just use the latest version." → ✅ "Accounts are pinned on first
  call, so shipping a change never breaks an unmodified client."
- ❌ "We support two versions with two deployments." → ✅ "One deployment, one code path
  against the latest schema, and small transformation modules that downgrade responses —
  otherwise every bug gets fixed twice."

---

## 3.5 Idempotency in APIs — the `Idempotency-Key` pattern

**Interview weight:** ★★★★★

> **One-liner:** The client generates a unique key per logical operation, the server
> claims that key atomically before doing any work, and any retry with the same key
> replays the stored response instead of executing again.

### Say this in the interview

> Every distributed write has an ambiguous failure mode: the client's request times out
> and it has no idea whether the server processed it. Retrying risks a double charge; not
> retrying risks losing the operation. Idempotency keys resolve that ambiguity. The
> client generates a UUID per logical operation — not per HTTP attempt — and sends it in
> an `Idempotency-Key` header. The server's first move is an atomic claim:
> `SET idem:{account}:{key} pending NX EX 86400` in Redis, which succeeds for exactly one
> concurrent request. The winner does the work and writes the response back under that
> key; anyone arriving later either replays the stored response or, if the key is still
> `pending`, waits with a short bounded backoff and then returns 409. I also store a hash
> of the request body with the key, so the same key with a different payload returns 422
> rather than replaying the wrong response — that catches a real client bug where a key
> gets reused across operations. Two details make this production-grade rather than
> demo-grade. First, Redis is a cache, not the source of truth: I put a unique constraint
> on `(account_id, idempotency_key)` in Postgres inside the same transaction as the
> business write, so if Redis is flushed the database still rejects the duplicate.
> Second, I keep keys for 24 hours, which is what Stripe's v1 API retains, because that
> covers every realistic client retry window without turning Redis into a permanent log.

### Mental model

The problem, drawn:

```text
   Client                          Server                    Database
     │  POST /charges  ───────────────►│                          │
     │                                 │── INSERT charge ────────►│  ✅ committed
     │        ✗ response lost (timeout, LB reset, pod killed)     │
     │                                 │                          │
     │  ??? did it work ???            │                          │
     │                                 │                          │
     │  POST /charges (retry) ────────►│── INSERT charge ────────►│  ✅ AGAIN
     │                                 │                          │  💸 double charge
```

The fix — three states, one atomic claim:

```text
   POST /charges
   Idempotency-Key: 8f1c9e2a-...
        │
        ▼
   SET idem:{acct}:{key} "pending:<body_hash>" NX EX 86400
        │
        ├── returned OK (we are the FIRST) ─────────────┐
        │                                              ▼
        │                            BEGIN;
        │                              INSERT idempotency_record
        │                                (account_id, key, body_hash)  ← UNIQUE
        │                              INSERT charge ...
        │                            COMMIT;                 ← both or neither
        │                                              │
        │                            SET key = "<response json>" EX 86400
        │                                              ▼
        │                                        201 Created
        │
        └── returned nil (key already exists) ── read the value
                 │
                 ├── "pending:<same hash>"  → poll w/ backoff ≤ 3 s,
                 │                             then 409 "request in progress"
                 ├── "pending:<diff hash>"  → 422 "key reused w/ different body"
                 └── "<response json>"      → replay it,
                                              + Idempotent-Replayed: true
```

**Why both Redis and Postgres.** Redis gives you the cheap, fast claim and the response
cache. Postgres gives you the guarantee. If you only have Redis, a failover, an eviction
under `maxmemory`, or a `FLUSHALL` during an incident silently disables your duplicate
protection at the exact moment retries are most likely. If you only have Postgres, every
duplicate retry costs a database round trip and you have no place to park the cached
response body. The unique constraint being *in the same transaction as the business
write* is the load-bearing part: it makes "record the key" and "do the work" atomic,
which no amount of application-level locking achieves.

**Where the key must be scoped.** `(account_id, idempotency_key)`, never the key alone.
A global key space means one tenant can guess or collide with another's key and replay
their response.

### Enterprise production example

**Stripe** set the industry standard here, and the details are worth quoting because
interviewers recognise them. Their v1 API accepts `Idempotency-Key` on all `POST`
endpoints (`GET` and `DELETE` ignore it, since they're already idempotent). Keys are up
to 255 characters, recommended to be UUIDv4 or similar high-entropy random strings, and
are scoped per account. Keys are retained for at least 24 hours and then reaped. A
replayed response carries an `Idempotent-Replayed: true` header so clients can tell.
Their newer v2 API extends the window to 30 days and accepts keys on `DELETE` as well —
and changes one important behaviour: where v1 permanently caches a failed request's 500
response (so a client had to mint a fresh key to genuinely retry), v2 re-executes the
failed request and returns the new outcome. That evolution is a good thing to mention: it
shows you understand that caching *errors* under an idempotency key is a design decision
with teeth, not an implementation detail.

Cross-link: the reliability side of this — retries, backoff, exactly-once versus
at-least-once — is in
[Module 09 — Idempotency](./09_Reliability_Patterns.md#94-idempotency).

### Code

Schema first. The unique constraint is the actual guarantee.

```sql
CREATE TABLE idempotency_record (
    account_id      uuid        NOT NULL,
    idempotency_key text        NOT NULL,
    request_hash    text        NOT NULL,   -- catches key reuse w/ new payload
    endpoint        text        NOT NULL,
    response_status int,                    -- NULL while in flight
    response_body   jsonb,
    created_at      timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (account_id, idempotency_key)      -- ← the real guarantee
);
CREATE INDEX idx_idem_created_at ON idempotency_record (created_at);
-- Reap with a daily job; otherwise this table quietly eats your disk:
--   DELETE FROM idempotency_record WHERE created_at < now() - interval '48 hours';
```

The FastAPI dependency. Redis for the fast path, Postgres for the durable guarantee.

```python
import asyncio, hashlib, json
from fastapi import Depends, Header, HTTPException, Request, Response

TTL = 24 * 3600            # matches Stripe v1's retention window
PENDING_WAIT_S = 3.0       # bounded wait for a concurrent in-flight twin

class Idempotency:
    def __init__(self, key, account_id, body_hash, redis, replay=None):
        self.key, self.account_id, self.body_hash = key, account_id, body_hash
        self.redis, self.replay = redis, replay
        self.rkey = f"idem:{account_id}:{key}"

    async def store(self, status: int, body: dict) -> None:
        await self.redis.set(self.rkey, json.dumps({"s": status, "b": body}), ex=TTL)

    async def release(self) -> None:
        """On unhandled failure, drop the claim so the client CAN retry."""
        await self.redis.delete(self.rkey)

async def idempotent(
    request: Request,
    response: Response,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    redis=Depends(get_redis),
) -> Idempotency:
    if not 1 <= len(idempotency_key) <= 255:
        raise HTTPException(400, "Idempotency-Key must be 1-255 characters")

    account_id = request.state.account_id                  # from auth, never body
    body_hash = hashlib.sha256(await request.body()).hexdigest()
    rkey = f"idem:{account_id}:{idempotency_key}"

    claimed = await redis.set(rkey, f"pending:{body_hash}", nx=True, ex=TTL)
    if claimed:
        return Idempotency(idempotency_key, account_id, body_hash, redis)

    deadline = asyncio.get_running_loop().time() + PENDING_WAIT_S
    delay = 0.05
    while True:
        raw = await redis.get(rkey)
        if raw is None:                                     # holder crashed & released
            if await redis.set(rkey, f"pending:{body_hash}", nx=True, ex=TTL):
                return Idempotency(idempotency_key, account_id, body_hash, redis)
        elif raw.startswith("pending:"):
            if raw.split(":", 1)[1] != body_hash:
                raise HTTPException(422, "Idempotency-Key reused with a different body")
            if asyncio.get_running_loop().time() > deadline:
                response.headers["Retry-After"] = "1"
                raise HTTPException(409, "a request with this key is in progress")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 0.4)
        else:
            cached = json.loads(raw)
            response.headers["Idempotent-Replayed"] = "true"
            raise ReplayResponse(cached["s"], cached["b"])   # handled by exc_handler
```

And the handler — note the business write and the key record commit together:

```python
@router.post("/v1/charges", status_code=201)
async def create_charge(body: ChargeCreate, idem: Idempotency = Depends(idempotent),
                        db=Depends(get_db)):
    try:
        async with db.transaction():
            await db.execute(
                """INSERT INTO idempotency_record
                     (account_id, idempotency_key, request_hash, endpoint)
                   VALUES ($1,$2,$3,$4)""",
                idem.account_id, idem.key, idem.body_hash, "POST /v1/charges")
            charge = await db.insert_charge(idem.account_id, body)   # same txn
    except UniqueViolation:
        # Redis lost the key (evicted/flushed) but Postgres remembers. Durable net.
        stored = await db.fetch_idempotency_record(idem.account_id, idem.key)
        if stored.response_body is None:
            raise HTTPException(409, "a request with this key is in progress")
        return stored.response_body
    except Exception:
        await idem.release()                 # let the client retry the same key
        raise

    payload = charge.model_dump()
    await idem.store(201, payload)
    return payload
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Any `POST` with money, messages, external side effects, or provisioning | `GET`/`PUT`/`DELETE` (already idempotent by contract) | One Redis round trip per write; a table that needs reaping |
| Redis claim + Postgres unique constraint | You need the guarantee but only have one datastore | Two systems in the write path; more failure modes to reason about |
| 24 h retention | Long human-in-the-loop flows (Stripe v2 uses 30 days) | Memory; a stale key can replay a response whose resource has since changed |

### Follow-ups they will ask

**Q: Redis goes down. Is your idempotency broken?**
A: Degraded, not broken. The Redis claim is a fast path and a response cache; the actual
guarantee is the unique constraint on `(account_id, idempotency_key)` inside the same
transaction as the business write. With Redis down I fail open to Postgres — duplicates
surface as a `UniqueViolation`, which I catch and turn into a replay or a 409. I lose the
cached response body and pay a database round trip per retry, and that's the right
trade: correctness over latency during an incident.

**Q: The first request succeeded in the database but the pod died before writing the
response to Redis. What does the retry see?**
A: The Redis key is still `pending`, so the retry waits up to about three seconds and
then gets a 409 with `Retry-After`. The next retry after the TTL, or after my crash
handler releases the claim, hits Postgres, trips the unique constraint, and I read the
committed record and return it. The reason that works is that the key row and the charge
row commit in one transaction — if I'd written the key row in a separate transaction,
this exact failure would either lose the guarantee or permanently block the key.

**Q: Should you cache a 500 response under the idempotency key?**
A: This is the interesting one. Caching it means a transient infrastructure failure is
frozen forever and the client must mint a new key to genuinely retry — which is Stripe
v1's behaviour, and it surprises people. I'd cache 4xx responses, since a validation
error is deterministic and replaying it is correct, but for 5xx I release the claim so
the same key can be retried. Stripe's v2 API moved in that direction too: it re-executes
failed requests rather than replaying the cached error.

**Q: The client sends the same key with a different request body. What happens?**
A: 422 with an explicit error code, never a replay. Replaying the first response would
silently discard the client's second, different operation, and it would look like data
loss. This is why I store a hash of the request body alongside the key — it turns a
client bug into a loud, diagnosable error.

**Q: Isn't a distributed lock simpler than all this?**
A: A lock protects the critical section but doesn't remember the outcome, so after the
lock releases the second request still executes. You need the record either way. And
locks add their own failure modes — expiry mid-operation, orphaned locks when a pod dies.
If I do need mutual exclusion I'd prefer `pg_advisory_xact_lock`, which releases when the
transaction ends even if the process is killed, over a Redis lock guarded by a `finally`
block that a `SIGKILL` never runs.

### Red flags — do not say this

- ❌ "I'd check if the record already exists, then insert." → ✅ "That's a race — two
  concurrent requests both see 'not exists'. I need an atomic claim: `SET NX` in Redis
  and a unique constraint in Postgres."
- ❌ "The client should generate a new key on each retry." → ✅ "The key identifies the
  logical operation, not the HTTP attempt — a new key per retry defeats the entire
  mechanism."
- ❌ "Redis handles it." → ✅ "Redis is the fast path; the durable guarantee is a unique
  constraint in the same transaction as the business write."
- ❌ "I'd use a global key namespace." → ✅ "Keys are scoped per account, otherwise one
  tenant's key can collide with — or deliberately replay — another's response."

---

## 3.6 Error design

**Interview weight:** ★★★★☆

> **One-liner:** An error response has two audiences — code that must decide whether to
> retry, and a human debugging at 3 a.m. — so it needs a stable machine-readable code
> *and* a human-readable message, and they must not be the same field.

### Say this in the interview

> I design errors around one question: what should the client *do* next? That means a
> stable, documented error code that clients can branch on — something like
> `card_declined` or `rate_limited` — separate from the human-readable message, which I
> reserve the right to reword at any time. If clients string-match on the message, I can
> never improve the copy. I use RFC 9457 problem-plus-JSON as the envelope because it
> gives me `type`, `title`, `status`, `detail` and `instance` for free, and I extend it
> with a `code` field and a `retryable` boolean, so a client library doesn't have to
> maintain its own table of which status codes are safe to retry. The distinction that
> matters most is retryable versus terminal: a 429, a 502, a 504 and a 503 are transient
> and should be retried with exponential backoff and jitter; a 400, a 401, a 403 and a
> 422 are terminal, and retrying them is just load I have to absorb for nothing. I also
> put the trace ID in every error body, because "request `01HQ...` failed" is a
> five-second log lookup and "something went wrong" is a twenty-minute one.

### Mental model

```text
                     Is it worth retrying?
                              │
        ┌─────────────────────┴─────────────────────┐
        ▼                                           ▼
    TERMINAL                                    RETRYABLE
  the request is wrong                     the request is fine,
  → fix it, don't retry                    the system isn't
                                           → backoff + jitter, cap attempts
  400 malformed                            429 rate limited  (Retry-After!)
  401 bad credentials                      500 our bug*      (retry once)
  403 not allowed                          502 bad gateway
  404 doesn't exist                        503 unavailable   (Retry-After!)
  409 state conflict**                     504 gateway timeout
  422 failed validation                    network timeout / connection reset
  413 payload too large

  *  500s: retry once with backoff. Repeated 500s are a bug, not a blip —
     a circuit breaker should open rather than hammering a broken service.
  ** 409 is terminal for the same body, but retryable after re-reading state
     (e.g. ETag mismatch → GET, merge, retry with the new ETag).
```

RFC 9457 (`application/problem+json`, formerly RFC 7807) envelope:

```json
{
  "type": "https://docs.acme.com/errors/insufficient-quota",
  "title": "Monthly embedding quota exhausted",
  "status": 429,
  "detail": "Account acct_88f used 1,000,000 of 1,000,000 tokens this period.",
  "instance": "/v1/embeddings",
  "code": "quota_exhausted",
  "retryable": false,
  "trace_id": "01HQ8ZM3T9K4",
  "quota": { "limit": 1000000, "used": 1000000, "resets_at": "2026-10-01T00:00:00Z" }
}
```

Note `retryable: false` on a 429 — a quota that resets monthly is *not* something backoff
will fix. That is exactly why an explicit boolean beats inferring retryability from the
status code.

**Partial failures.** Batch endpoints are where error design gets genuinely hard, because
"did it work?" has no single answer:

```text
POST /v1/documents/batch   { "documents": [ d1, d2, d3 ] }

Option A — all or nothing         400/422, nothing was created
   + simplest client contract     − one bad row blocks 999 good ones

Option B — 207 Multi-Status       per-item results in one response
   { "results": [
       {"index":0,"status":201,"id":"doc_1"},
       {"index":1,"status":422,"code":"unsupported_mime_type"},
       {"index":2,"status":201,"id":"doc_3"} ] }
   + partial progress preserved   − client MUST inspect every item
   ⚠ the outer status is 207, so a client that only checks `resp.ok`
     will silently lose item 1. Document this loudly.

Option C — 202 + job resource     async, poll for per-item state
   + best for large/slow batches  − more moving parts; you own job state
```

For anything over a few dozen items, or anything slow (document ingestion, embedding
generation), Option C is the right answer: return `202` with a job ID and expose
per-item status on `GET /v1/jobs/{id}`. Say why: a 207 body for 10,000 items is a
multi-megabyte response that you have to hold in memory to build.

### Enterprise production example

**Stripe's** error objects carry a `type` (`card_error`, `invalid_request_error`,
`api_error`, `rate_limit_error`), a stable machine-readable `code` (`card_declined`), a
separate human `message`, and — for card errors — a `decline_code` from the issuer.
That's four levels of granularity, and the layering is deliberate: `type` tells your code
which broad handler to run, `code` drives specific logic, `decline_code` is for support
staff, and `message` is for humans and may change. Stripe also documents which types are
safe to retry, which is what lets their client libraries retry automatically without
application code. Contrast that with an API that returns
`{"error": "something went wrong"}` and a 200 status — every client of that API ends up
string-matching on prose, and the API can never change its wording again.

### Code

One exception hierarchy and one handler is all this takes in FastAPI.

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

class ApiError(Exception):
    status: int = 500
    code: str = "internal_error"
    retryable: bool = False
    title: str = "Internal server error"

    def __init__(self, detail: str = "", **extra):
        self.detail, self.extra = detail, extra

class RateLimited(ApiError):
    status, code, retryable = 429, "rate_limited", True
    title = "Too many requests"

class ValidationFailed(ApiError):
    status, code, retryable = 422, "validation_failed", False
    title = "Request failed validation"

class UpstreamUnavailable(ApiError):
    status, code, retryable = 503, "upstream_unavailable", True
    title = "A dependency is temporarily unavailable"

@app.exception_handler(ApiError)
async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    headers = {"Content-Type": "application/problem+json"}
    if exc.retryable and (ra := exc.extra.pop("retry_after", None)):
        headers["Retry-After"] = str(ra)       # seconds; clients honour this
    return JSONResponse(
        status_code=exc.status,
        headers=headers,
        content={
            "type": f"https://docs.acme.com/errors/{exc.code}",
            "title": exc.title,
            "status": exc.status,
            "detail": exc.detail,
            "instance": request.url.path,
            "code": exc.code,
            "retryable": exc.retryable,
            "trace_id": request.state.trace_id,   # set by tracing middleware
            **exc.extra,
        },
    )

@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception) -> JSONResponse:
    # Never leak a stack trace or SQL to a client. Log it, hand back a trace id.
    logger.exception("unhandled", extra={"trace_id": request.state.trace_id})
    return await api_error_handler(request, ApiError("An unexpected error occurred."))
```

The matching client, because "retryable" only pays off if someone reads it:

```python
RETRY_STATUS = {429, 500, 502, 503, 504}

async def call_with_retry(client, method, url, *, attempts=4, **kw):
    for attempt in range(attempts):
        r = await client.request(method, url, **kw)
        if r.status_code < 400:
            return r
        problem = r.json() if "problem+json" in r.headers.get("content-type", "") else {}
        if not problem.get("retryable", r.status_code in RETRY_STATUS):
            r.raise_for_status()                          # terminal: fail fast
        if attempt == attempts - 1:
            r.raise_for_status()
        delay = float(r.headers.get("Retry-After", 0)) or (0.2 * 2 ** attempt)
        await asyncio.sleep(delay * (0.5 + random.random()))   # full-ish jitter
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| `problem+json` + stable `code` field on any API with external consumers | A single internal endpoint two teams own | A documented error catalogue you must keep stable forever |
| `207 Multi-Status` for small batches | Batches over ~50 items, or slow per-item work | Clients that only check `resp.ok` silently lose failures |
| `202` + job resource for large/slow batches | Fast, small operations | You now own job state, TTL, and a polling or push channel |

### Follow-ups they will ask

**Q: Why not just return 200 with an error object? Some big APIs do that.**
A: Because the status code is the one field every intermediary understands. A 200 with an
error body means your load balancer's error-rate metric reads zero during an outage, your
CDN happily caches the failure, and every generic HTTP client's retry logic does the
wrong thing. GraphQL suffers from exactly this — errors come back as 200 with an `errors`
array — which is a real operational cost of adopting it.

**Q: How much detail should an error expose?**
A: Enough to fix the request, never enough to map my internals. So field-level validation
detail, yes; stack traces, SQL, internal hostnames and upstream vendor errors, no. For
auth I go further and return 404 instead of 403 for another tenant's resource, since a
403 confirms it exists. And every error carries a trace ID, so support can find the full
detail in logs without me putting it on the wire.

**Q: What should a client do with a 500 versus a 503?**
A: A 503 usually means "overloaded or shedding, come back later," and I send `Retry-After`
with it, so the client backs off for a known duration. A 500 means an unexpected bug —
retry once with backoff in case it was a transient blip, but repeated 500s should open a
circuit breaker rather than keep retrying, because retrying a deterministic bug just
multiplies the load while the service is already failing.

**Q: Your error catalogue is now 200 codes. Is that a problem?**
A: The count isn't the problem; instability is. Error codes are part of the API contract,
so adding one is non-breaking but changing or removing one is breaking, and clients need
to treat unknown codes as generic-by-type rather than crashing. That's why I group codes
under a coarse `type` — a client can branch on `type: "rate_limit_error"` and get correct
behaviour even for a `code` it has never seen.

### Red flags — do not say this

- ❌ "Return 500 for anything that fails." → ✅ "A 500 says it's my bug and the client
  should back off; validation failures are 422 and shouldn't be retried at all."
- ❌ "The client can parse the error message." → ✅ "Messages are for humans and I want to
  reword them; clients branch on a stable `code` field."
- ❌ "I'd return the exception text so debugging is easier." → ✅ "I return a trace ID and
  log the exception — a stack trace on the wire is an information-disclosure bug."
- ❌ "Retry everything until it works." → ✅ "Retry only transient classes with backoff and
  jitter and a cap; retrying a 422 is pure load with zero chance of success."

---

## 3.7 GraphQL — resolvers, N+1, DataLoader, complexity limits

**Interview weight:** ★★★★☆

> **One-liner:** GraphQL lets the client specify the response shape, which eliminates
> over-fetching and round trips — and hands the client the ability to write an expensive
> query against your database, which is now your problem.

### Say this in the interview

> GraphQL is worth it when you have many heterogeneous clients whose data needs change
> faster than you can ship endpoints — a mobile app, a web app and a partner integration
> all wanting different slices of the same object graph. Instead of shipping a new REST
> endpoint per screen, clients declare what they want. The cost is that you've moved query
> planning to the client, and two problems come with it. The first is N+1: the resolver
> model is naturally per-field, so a query for 50 posts each with an author fires one
> query for posts and then 50 separate queries for authors. The fix is DataLoader, which
> batches all author lookups requested within a single event-loop tick into one
> `WHERE id = ANY($1)` and caches per request — that turns 51 queries into 2. The second
> is that a client can send a legal query that is catastrophically expensive, so I enforce
> a static cost budget before execution the way Shopify does: every field has a cost, the
> query's cost is computed up front, and anything over the budget is rejected without
> running. I also cap depth, because a recursive `author { posts { author { posts } } }`
> is a denial-of-service in twelve lines. And I'd say the honest downside out loud: HTTP
> caching mostly stops working, because everything is a POST to one URL, so CDN and
> browser caching go away and I have to rebuild it as server-side caching per resolver.

### Mental model

```text
REST: server decides the shape, client makes N calls

  GET /posts?limit=50          → 50 posts (all fields, incl. ones unused)
  GET /users/1 ... /users/37   → 37 more round trips, or one ?ids= endpoint
                                 you had to build for this screen

GraphQL: client decides the shape, one call

  POST /graphql
  query { posts(first: 50) { id title author { name avatarUrl } } }

  ┌──── one round trip, exactly the fields asked for ────┐
```

The resolver model and where N+1 comes from:

```text
query { posts(first: 50) { title author { name } } }

  posts resolver         ──► SELECT * FROM posts LIMIT 50          1 query
    ├─ post[0].author    ──► SELECT * FROM users WHERE id = 7      ┐
    ├─ post[1].author    ──► SELECT * FROM users WHERE id = 3      │ 50
    ├─ ...                                                          │ queries
    └─ post[49].author   ──► SELECT * FROM users WHERE id = 7  ←dup ┘
                                                          total: 51

with DataLoader:

  posts resolver         ──► SELECT * FROM posts LIMIT 50          1 query
    ├─ post[0].author    ──► loader.load(7)  ┐
    ├─ post[1].author    ──► loader.load(3)  │ collected during the tick,
    ├─ ...                                    │ deduplicated
    └─ post[49].author   ──► loader.load(7)  ┘
                              ▼ end of event-loop tick
                           SELECT * FROM users WHERE id = ANY(ARRAY[7,3,...])
                                                          total: 2
```

**Cost/complexity limiting.** Depth limiting alone is not enough — a shallow query can be
enormous:

```graphql
# depth 3, cost enormous: 100 × 100 × 100 = 1,000,000 potential nodes
query {
  users(first: 100) {
    posts(first: 100) {
      comments(first: 100) { body }
    }
  }
}
```

So you compute cost *statically*, multiplying through the pagination arguments, before
execution:

```text
cost(field) = base_cost + (list_multiplier × Σ cost(children))

users(first:100)          100 × ( 1 + posts_subtree )
  posts(first:100)          100 × ( 1 + comments_subtree )
    comments(first:100)       100 × 1
  ⇒ 100 × (1 + 100 × (1 + 100)) = 1,010,100  → REJECT (budget 1,000)
```

Three defences, layered:

```text
1. Static cost budget    reject before execution   ← the important one
2. Max depth (~10-12)    stops recursive fragments
3. Persisted queries     clients send a hash, not a query string
                         → allowlist: only queries you have reviewed can run
                         → also cuts request size, and restores GET+CDN caching
```

**Why caching is hard.** Everything is `POST /graphql`, so:

```text
REST                                   GraphQL (naive)
GET /posts/42                          POST /graphql  {query: "..."}
  ▲ URL is the cache key                 ▲ POST → not cacheable
  ▲ ETag / Cache-Control work            ▲ one URL for every query
  ▲ CDN caches for free                  ▲ CDN can't help
  ▲ 304 Not Modified                     ▲ response shape varies per caller

Recovery path:
  · persisted queries + GET  →  URL becomes /graphql?sha256=abc&vars=...
                                → now CDN-cacheable again
  · per-entity server-side cache keyed by (type, id) inside DataLoader
  · @cacheControl directives + a caching gateway (Apollo Router / Cosmo)
```

### Enterprise production example

**Shopify's** GraphQL Admin API is the reference implementation of cost-based protection.
It doesn't count requests at all — it charges each query a calculated cost against a
leaky bucket. The response includes an `extensions.cost` object with
`requestedQueryCost` (computed statically before execution), `actualQueryCost` (after),
and `throttleStatus` with `maximumAvailable`, `currentlyAvailable` and `restoreRate`.
Standard plans restore 100 points per second; Shopify Plus restores 1,000 per second. And
critically, **a single query may not exceed 1,000 points regardless of plan** — that
ceiling is enforced *before* execution, so a client that asks for 1,040 points gets
`MAX_COST_EXCEEDED` and the query never touches the database. When the requested cost
overestimates (a connection returns fewer nodes than requested), the difference is
refunded to the bucket. Shopify also routes genuinely large reads to an asynchronous Bulk
Operations API that doesn't consume the bucket at all.

**GitHub's** GraphQL API layers a different limit on the same idea: 5,000 points per hour
per user (10,000 for apps owned by a GitHub Enterprise Cloud org), every connection must
supply `first` or `last` with a value between 1 and 100, and a single call may not request
more than 500,000 total nodes. Exceeding a primary rate limit returns HTTP **200** with an
error body and `x-ratelimit-remaining: 0` — a concrete example of the GraphQL
status-code problem, and a good detail to cite.

### Code

DataLoader, batching and per-request caching. Note the two non-obvious requirements:
results must come back **in the same order as the keys**, and the loader must be created
**per request**, not per process.

```javascript
// loaders.js — Node.js + dataloader + pg
import DataLoader from 'dataloader';

export function createLoaders(pool) {
  const userById = new DataLoader(async (ids) => {
    const { rows } = await pool.query(
      'SELECT id, name, avatar_url FROM users WHERE id = ANY($1::bigint[])',
      [ids],
    );
    const byId = new Map(rows.map((r) => [String(r.id), r]));
    // MUST return one entry per key, in key order. Missing key -> null, not throw.
    return ids.map((id) => byId.get(String(id)) ?? null);
  }, { maxBatchSize: 200, cache: true });

  // Batching a one-to-MANY edge: group children by parent, keep key order.
  const commentsByPostId = new DataLoader(async (postIds) => {
    const { rows } = await pool.query(
      `SELECT * FROM (
         SELECT c.*, row_number() OVER (PARTITION BY post_id
                                        ORDER BY created_at DESC) AS rn
         FROM comments c WHERE post_id = ANY($1::bigint[])
       ) t WHERE rn <= 20`,                       // per-parent limit, one query
      [postIds],
    );
    const byPost = new Map(postIds.map((id) => [String(id), []]));
    for (const r of rows) byPost.get(String(r.post_id))?.push(r);
    return postIds.map((id) => byPost.get(String(id)));
  });

  return { userById, commentsByPostId };
}

// server.js — a NEW loader set per request: the cache must not outlive the
// request, or user A's authorisation decisions leak into user B's response.
const server = new ApolloServer({
  schema,
  plugins: [depthLimitPlugin(12), costLimitPlugin({ maxCost: 1000 })],
});
await startStandaloneServer(server, {
  context: async ({ req }) => ({
    viewer: await authenticate(req),
    loaders: createLoaders(pool),
  }),
});
```

Static cost limiting as an Apollo plugin — reject before execution, not during:

```javascript
function costLimitPlugin({ maxCost }) {
  return {
    async requestDidStart() {
      return {
        async didResolveOperation({ request, document, schema }) {
          const cost = estimateCost({ document, schema, variables: request.variables });
          if (cost > maxCost) {
            throw new GraphQLError(
              `Query cost ${cost} exceeds the limit of ${maxCost}`,
              { extensions: { code: 'MAX_COST_EXCEEDED', cost, maxCost } },
            );
          }
        },
      };
    },
  };
}
```

Python equivalent, since his stack includes FastAPI: Strawberry ships
`strawberry.extensions.QueryDepthLimiter` and `MaxTokensLimiter`, and
`aiodataloader`/`strawberry.dataloader.DataLoader` gives the same batching semantics
inside an async context.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Many heterogeneous clients, deeply related data, frontend iterating faster than backend | One client, or a small stable set of screens | HTTP/CDN caching largely gone; cost limiting, depth limiting and DataLoader are now mandatory |
| A federated graph over many services (BFF replacement) | High-QPS internal service-to-service calls | Gateway hop, per-resolver observability, no protobuf-style codegen contract |
| Persisted queries + allowlist for a first-party app | Truly public API where anyone writes queries | Build-step coupling between client and server |

### Follow-ups they will ask

**Q: How do you rate-limit GraphQL? Requests per minute is meaningless.**
A: You charge by cost, not by request. Compute a static cost from the query and its
pagination arguments before execution, and deduct it from a token bucket — Shopify's
model exactly, with a hard per-query ceiling of 1,000 points on top of the bucket so no
single query can be huge even if you have budget saved up. Then refund the difference
between requested and actual cost once you know how many nodes actually came back.
Counting requests would let one query do the damage of ten thousand.

**Q: DataLoader caches per request. Why not cache across requests for a bigger hit rate?**
A: Because the cache is keyed by entity ID and contains no authorisation context, so a
cross-request cache will hand user B a record that only user A was allowed to see. It
also serves stale data within a mutation — you'd read your own write incorrectly. If I
want a cross-request cache I put it *behind* the loader as an explicit Redis layer with
its own TTL and a tenant-scoped key, so authorisation is re-evaluated on every request.

**Q: A mutation and a query in the same document. What's the execution order?**
A: Top-level mutation fields execute serially in the order written, whereas query fields
execute in parallel. That's part of the spec and it matters: two mutations in one document
are sequential and the second sees the first's effects, but you cannot rely on any
ordering between sibling query fields. It also means one slow mutation blocks the rest of
the document, so I keep mutation documents small.

**Q: Doesn't GraphQL just move the N+1 problem from HTTP to your database?**
A: Without DataLoader, yes — that's exactly what it does, and it's the single most common
GraphQL production incident. With per-request batching it's 2 queries instead of 51. But
I'd add that DataLoader only batches within one event-loop tick, so a resolver that
`await`s something before calling `load()` falls out of the batch window and you're back
to N+1 with the appearance of a fix. I'd verify with query-count assertions in tests, not
by reading the code.

**Q: How do you handle errors and partial data?**
A: GraphQL returns HTTP 200 with `data` partially filled and an `errors` array, so a
resolver failure gives you a `null` field plus an error entry rather than a failed
request. That's genuinely useful for partial degradation — one broken recommendation
service doesn't blank the page — but it breaks every metric and client that keys off
status codes. I compensate by emitting error-rate metrics from the GraphQL layer itself
rather than from the HTTP layer, and by making sure alerting reads those.

### Red flags — do not say this

- ❌ "GraphQL is more efficient than REST." → ✅ "It removes over-fetching and round trips
  for heterogeneous clients, and it costs you HTTP caching plus a cost-limiting
  requirement."
- ❌ "We solved N+1 by adding a cache." → ✅ "We batch with DataLoader per request; a cache
  hides N+1 until the cache is cold, and then it's back."
- ❌ "Depth limiting protects the server." → ✅ "Depth limiting stops recursion, but a
  depth-3 query with `first: 100` at each level is a million nodes — you need static cost
  analysis."
- ❌ "Use GraphQL for internal service-to-service calls." → ✅ "Internally I'd use gRPC:
  strict contracts, codegen, and no query planning at runtime."

---

## 3.8 gRPC — protobuf, streaming, HTTP/2, deadlines

**Interview weight:** ★★★★☆

> **One-liner:** gRPC is a schema-first RPC framework over HTTP/2: you write a `.proto`,
> generate typed clients and servers in every language, and get multiplexed streams,
> header compression, and first-class deadlines you don't have to invent.

### Say this in the interview

> I reach for gRPC for internal service-to-service traffic and stay on REST at the edge.
> The reason is the contract, more than the speed. A `.proto` file generates the client
> and server in every language we use, so a field rename is a compile error rather than a
> runtime `KeyError` at 2 a.m., and adding a field is safe because protobuf identifies
> fields by tag number instead of by name. The performance is a genuine bonus: protobuf
> is binary and typically 30 to 60 percent smaller than the equivalent JSON, HPACK
> compresses repeated headers down to tens of bytes instead of several hundred, and
> HTTP/2 multiplexes many concurrent calls over one TCP connection so I stop paying for
> connection setup per request. gRPC also gives me deadlines as a first-class concept
> rather than a per-client timeout convention — the caller sets a deadline, it propagates
> across every downstream hop, and when it expires every service in the chain stops work
> instead of computing a result nobody is waiting for. Where I wouldn't use it is any
> browser-facing endpoint: browsers can't speak raw gRPC, so you need grpc-web plus a
> translating proxy like Envoy, and at that point REST or GraphQL at the edge is simply
> less machinery. I'd also flag that a proxy or load balancer that downgrades to HTTP/1.1
> silently erases the entire benefit.

### Mental model

```text
   user.proto  ──protoc──►  ┌ Python stubs (grpcio)      → FastAPI-side client
                            ├ Go stubs                    → the service
                            ├ Node stubs                  → another service
                            └ TypeScript (via grpc-web)   → needs a proxy
   ▲ ONE source of truth. Rename a field → the build breaks, not production.
```

The four call types, and what each is actually for:

```text
1. Unary                    rpc GetUser(Req) returns (Resp)
   client ──req──► server        the 95% case: a normal RPC
   client ◄─resp── server

2. Server streaming         rpc Watch(Req) returns (stream Event)
   client ──req──► server        LLM token streaming, tailing logs,
   client ◄─ev1─── server        progress on a long job, change feeds
   client ◄─ev2─── server
   client ◄─ev3─── server

3. Client streaming         rpc Upload(stream Chunk) returns (Summary)
   client ──c1───► server        file/telemetry upload, bulk ingest
   client ──c2───► server        (server replies once, at the end)
   client ──c3───► server
   client ◄─resp── server

4. Bidirectional            rpc Chat(stream Msg) returns (stream Msg)
   client ◄─┬────► server        chat, real-time sync, interactive
            │                    agents; independent read/write streams
   ▲ order is guaranteed WITHIN each stream, not across them
```

HTTP/2 multiplexing — why one connection is enough:

```text
HTTP/1.1                            HTTP/2 (gRPC)
conn 1 ── req A ── resp A ──►       ┌─ stream 1: req A ──► resp A
conn 2 ── req B ── resp B ──►       │─ stream 3: req B ──► resp B
conn 3 ── req C ── resp C ──►       ├─ stream 5: req C ──► resp C
...6-8 connections per host         └─ ONE TCP connection, interleaved frames
  ▲ head-of-line blocking per          ▲ no app-level HOL blocking
    connection; N handshakes           ▲ HPACK: repeated headers ≈ 40-90 bytes
                                         vs ~200-700 uncompressed
  ⚠ one connection also means one LB decision — see the follow-up below.
```

**Deadlines and propagation** — the part most candidates miss entirely:

```text
   Client sets deadline = now + 300 ms
        │  grpc-timeout: 300m  (travels in the HTTP/2 headers)
        ▼
   ┌──────────┐  remaining: 300 ms
   │  API svc │──────────────────────────────┐
   └──────────┘                              ▼
        │                            ┌──────────────┐ remaining: 240 ms
        │  spends 60 ms              │ Search svc   │
        │                            └──────┬───────┘
        │                                   ▼
        │                            ┌──────────────┐ remaining: 180 ms
        │                            │  Vector DB   │
        │                            └──────────────┘
        ▼
   at t = 300 ms: DEADLINE_EXCEEDED propagates and EVERY hop cancels.
   ▲ Without propagation: the client gives up at 300 ms but the vector search
     keeps burning CPU for another 2 seconds on a result nobody will read.
     That is how a latency spike becomes a capacity outage.
```

Rule: always set a deadline on every gRPC call. A call with no deadline can hang until
the connection dies, and gRPC's own guidance is that a missing deadline is a bug.

**Protobuf schema evolution** — the rules that make gRPC safe to deploy:

```text
SAFE                                    UNSAFE
· add a field with a NEW tag number     · change a field's tag number
· rename a field (tags identify it)     · change a field's type
· add a value to an enum (have a        · reuse a tag number of a deleted field
  default/UNKNOWN = 0 case!)              (use `reserved 4;` to prevent it)
· mark a field `deprecated = true`      · remove a required field (proto2)
```

### Enterprise production example

**Netflix's** Zuul 2 rewrite is the clearest public example of what HTTP/2-style
connection multiplexing buys you at scale. Netflix moved their edge gateway from a
blocking thread-per-connection model to an asynchronous Netty-based one, and their
engineering blog is explicit that the primary benefit was not raw throughput but
*connection scaling* — the ability for tens of millions of devices to hold persistent
connections back to Netflix's cloud. On their push cluster, where requests are large but
responses are small and unencrypted (so Zuul does relatively little work), they measured
roughly a **25% increase in throughput with a corresponding 25% reduction in CPU**. They
also named the cost plainly: a system that is much harder to debug, code and test, inside
an ecosystem built on blocking assumptions. That honesty — big win on connections,
moderate win on CPU, real complexity cost — is exactly the shape of the gRPC trade-off.

**Published gRPC-vs-REST benchmarks** (a range, not a single company's claim, because
these numbers are extremely condition-dependent):

| Dimension | gRPC / protobuf | REST / JSON |
|---|---|---|
| Payload size, same data | ~30-60% smaller | baseline |
| Per-request header overhead | ~40-90 bytes (HPACK) | ~200-700 bytes |
| Serialisation CPU, small msg | ~1.5-2× faster | baseline |
| Connections per host | 1, multiplexed | 6-8 (browser default) |
| Throughput at small payloads | commonly 2-3× higher | baseline |

Say the caveat out loud, because it is the senior move: benchmarks that run on localhost
or isolate serialisation overstate the protocol effect, the advantage narrows as payloads
grow past tens of kilobytes, and **any proxy in the path that downgrades to HTTP/1.1
erases all of it**. Validate the whole path end to end before claiming a number.

### Code

The contract:

```protobuf
syntax = "proto3";
package search.v1;
import "google/protobuf/timestamp.proto";

service SearchService {
  rpc Search(SearchRequest) returns (SearchResponse);
  rpc StreamAnswer(SearchRequest) returns (stream AnswerChunk);   // LLM tokens
}

message SearchRequest {
  string tenant_id = 1;
  string query     = 2;
  int32  top_k     = 3;
  reserved 4;                       // was `bool rerank` — never reuse tag 4
  repeated string filters = 5;
}

message SearchResponse {
  repeated Document documents = 1;
  int32 total_matched = 2;
}

message AnswerChunk { string text = 1; bool done = 2; }

message Document {
  string id = 1;
  string chunk = 2;
  float  score = 3;
  google.protobuf.Timestamp indexed_at = 4;
}
```

Server with deadline awareness — check `context.time_remaining()` before expensive work
and bail out rather than doing work nobody will read:

```python
import grpc
from grpc import aio
from search.v1 import search_pb2, search_pb2_grpc

class SearchService(search_pb2_grpc.SearchServiceServicer):
    async def Search(self, request, context: aio.ServicerContext):
        if not request.tenant_id:
            await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "tenant_id required")

        remaining = context.time_remaining()          # seconds, or None
        if remaining is not None and remaining < 0.05:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED,
                                "insufficient time remaining to serve")
        try:
            # Propagate the SAME deadline downstream — do not invent a new one.
            docs = await self.vector_db.search(
                request.tenant_id, request.query, top_k=min(request.top_k or 10, 100),
                timeout=remaining,
            )
        except TimeoutError:
            await context.abort(grpc.StatusCode.DEADLINE_EXCEEDED, "vector search timeout")
        return search_pb2.SearchResponse(documents=docs, total_matched=len(docs))

    async def StreamAnswer(self, request, context):
        async for token in self.llm.stream(request.query):
            if context.cancelled():       # client hung up: stop paying for tokens
                return
            yield search_pb2.AnswerChunk(text=token, done=False)
        yield search_pb2.AnswerChunk(text="", done=True)

async def serve():
    server = aio.server(options=[
        ("grpc.max_receive_message_length", 8 * 1024 * 1024),   # default is 4 MB
        ("grpc.keepalive_time_ms", 30_000),
        ("grpc.keepalive_permit_without_calls", 1),
    ])
    search_pb2_grpc.add_SearchServiceServicer_to_server(SearchService(), server)
    server.add_insecure_port("[::]:50051")            # mTLS via the mesh in prod
    await server.start()
    await server.wait_for_termination()
```

Client — the deadline is the point:

```python
async with aio.insecure_channel("search:50051") as channel:
    stub = search_pb2_grpc.SearchServiceStub(channel)
    try:
        resp = await stub.Search(
            search_pb2.SearchRequest(tenant_id="t_1", query="refund policy", top_k=10),
            timeout=0.3,                          # ALWAYS. A call with no deadline
        )                                         # can hang until TCP notices.
    except grpc.aio.AioRpcError as e:
        if e.code() is grpc.StatusCode.DEADLINE_EXCEEDED:
            ...   # fall back to keyword search, or serve a degraded response
        raise
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Internal service-to-service, polyglot teams, high QPS, streaming | Browser clients, public/partner APIs, webhooks | grpc-web + Envoy for browsers; binary payloads you can't `curl` easily |
| You want a compile-time contract and generated clients | Two-service system where a shared Pydantic model is enough | protoc in the build, generated code in the repo, a schema review process |
| Long-lived streams (LLM tokens, change feeds, telemetry) | Requests that need CDN or HTTP caching | Streams can't be re-balanced once open; harder debugging after failure |

### Follow-ups they will ask

**Q: gRPC multiplexes over one TCP connection. Doesn't that break load balancing?**
A: Yes, and it's the classic gRPC production surprise. An L4 load balancer balances
*connections*, so one long-lived HTTP/2 connection pins all your traffic to a single
backend — add ten replicas and nine stay idle. The fixes are client-side load balancing
with a resolver that knows all the endpoints (gRPC has this built in, backed by DNS or
xDS), or an L7 proxy like Envoy that balances individual HTTP/2 *streams*, or a service
mesh sidecar doing the same. On GCP that means client-side LB or Traffic Director rather
than a plain internal TCP load balancer.

**Q: How do you do gRPC from a browser?**
A: You don't, directly — browsers don't expose enough control over HTTP/2 frames. You use
grpc-web, which needs a translating proxy (Envoy's `grpc_web` filter, or a Connect
gateway), and you give up client streaming and bidirectional streaming; only unary and
server streaming survive. Given that, my default is REST or GraphQL at the edge and gRPC
behind it, so the browser never has to care.

**Q: What happens if you deploy a new proto with a renamed field to only half your fleet?**
A: Nothing breaks, because protobuf identifies fields by tag number, not name — the wire
format is unchanged by a rename. What *would* break is changing a tag number or a type,
so those are forbidden, and I mark deleted tags `reserved` so nobody reuses them. I'd
also add a CI check that runs a buf-style breaking-change detector against the previous
schema, since the whole point of a contract is that it's enforced by the build rather
than by reviewer memory.

**Q: Why is a deadline better than a client-side timeout?**
A: A client-side timeout only stops the client from waiting; the server keeps working. A
gRPC deadline travels in the request metadata and propagates to every downstream hop, so
when it expires the entire call tree is cancelled. That matters during an overload: with
plain timeouts, clients give up and retry while the servers are still burning CPU on the
abandoned first attempts, and you get a queue of doomed work that guarantees the outage
continues. Deadline propagation is what stops that feedback loop.

**Q: Protobuf has no `null`. How do you distinguish "unset" from "zero"?**
A: In proto3 scalar fields have no presence by default, so `0`, `false` and `""` are
indistinguishable from unset — which quietly breaks partial-update semantics. You either
use the `optional` keyword (presence is back in proto3 as of 3.15) or the wrapper types
like `google.protobuf.Int32Value`. For a PATCH-style RPC I'd also pass an explicit
`FieldMask` naming which fields the caller intends to change, which is what Google's own
APIs do.

### Red flags — do not say this

- ❌ "gRPC is faster than REST, so use it everywhere." → ✅ "It's better for internal
  east-west traffic; at the edge the browser support and cacheability of REST win."
- ❌ "gRPC works in the browser." → ✅ "Browsers need grpc-web plus a translating proxy,
  and you lose client and bidirectional streaming."
- ❌ "We put the gRPC service behind our normal L4 load balancer." → ✅ "L4 balances
  connections, so one HTTP/2 connection pins to one backend — I need client-side LB or an
  L7 proxy that balances streams."
- ❌ "We'll set timeouts on the client." → ✅ "I set a deadline, which propagates to every
  hop so downstream work is actually cancelled."

---

## 3.9 REST vs GraphQL vs gRPC vs SOAP — the decision

**Interview weight:** ★★★★★

> **One-liner:** REST at the edge, gRPC internally, GraphQL when you have many
> heterogeneous clients and a fast-moving frontend, SOAP only when a bank or a government
> system makes you.

### Say this in the interview

> My default is REST at the edge and gRPC internally, and I can defend both halves. REST
> at the edge because browsers speak it natively, HTTP caching and CDNs work on it for
> free, every client library and debugging tool in the world supports it, and public
> consumers can integrate with `curl`. gRPC internally because east-west traffic is
> high-volume and machine-to-machine, so binary encoding and multiplexing actually pay
> off, and because a `.proto` gives me generated clients and a compile-time contract
> across services in different languages. I add GraphQL when the shape of the problem
> calls for it specifically: several different clients — mobile, web, partner — each
> wanting a different slice of a deeply connected graph, and a frontend team that's
> blocked waiting on me to ship a new endpoint per screen. I would not introduce GraphQL
> for a single client with stable screens, because I'd be trading away HTTP caching and
> buying a cost-limiting problem for no benefit. SOAP I'd only choose under external
> constraint: a payments or insurance or government counterparty whose WSDL is
> non-negotiable, or a WS-Security requirement. And I'd say the meta-point: these aren't
> exclusive. A real system usually has REST at the edge, gRPC between services, GraphQL
> in a BFF for the app, and webhooks going out — the question is which one at which
> boundary, not which one wins.

### Mental model

```text
                            ┌───────────────────┐
        browsers, mobile ───►│  REST / GraphQL   │  north-south (edge)
        partners, curl       │  over HTTP/1.1+2  │  human-debuggable, cacheable
                            └─────────┬─────────┘
                                      │
                            ┌─────────▼─────────┐
                            │   API Gateway     │
                            └─────────┬─────────┘
                                      │  gRPC / protobuf
              ┌───────────────┬───────┴───────┬───────────────┐
              ▼               ▼               ▼               ▼
          ┌───────┐      ┌────────┐      ┌────────┐     ┌──────────┐
          │ Auth  │◄────►│ Search │◄────►│ Rank   │◄───►│ Embedding│
          └───────┘      └────────┘      └────────┘     └──────────┘
                        east-west (internal): binary, typed, streaming
                                      │
                                      ▼  webhooks (HMAC-signed HTTP POST)
                            partner systems (3.10)
```

### The decision table

| | REST | GraphQL | gRPC | SOAP |
|---|---|---|---|---|
| **Encoding** | JSON (text) | JSON (text) | protobuf (binary) | XML |
| **Transport** | HTTP/1.1, HTTP/2 | HTTP POST | HTTP/2 required | HTTP, SMTP, JMS |
| **Contract** | OpenAPI (optional, often drifts) | schema (mandatory, introspectable) | `.proto` (mandatory, codegen) | WSDL (mandatory, verbose) |
| **Browser support** | native | native | needs grpc-web + proxy | native (painful) |
| **HTTP caching / CDN** | excellent (URL + ETag) | poor (single POST URL) | none | none |
| **Over/under-fetching** | over-fetches; N round trips | client picks fields exactly | fixed message; add RPCs | over-fetches |
| **Streaming** | SSE, or chunked | subscriptions (WS) | 4 native modes | no |
| **Codegen quality** | mediocre from OpenAPI | good (typed clients) | excellent, all languages | good, very verbose |
| **Error signalling** | HTTP status codes | HTTP 200 + `errors[]` | gRPC status codes | SOAP Fault |
| **Rate limiting** | requests/min | must be cost-based | requests or streams | requests/min |
| **Ops/debuggability** | trivial (`curl`, logs) | medium (query in POST body) | harder (binary, needs `grpcurl`) | hard |
| **Biggest risk** | endpoint sprawl, chatty clients | a client writes an expensive query | a proxy downgrades to HTTP/1.1 | nobody left who wants to maintain it |
| **Pick it for** | public/partner APIs, browsers, anything cacheable | many clients × connected graph | internal east-west, streaming, polyglot | mandated integrations only |

### Enterprise production example

**Netflix** is the canonical illustration of "different protocol per boundary": REST-ish
HTTP at the device edge terminating in Zuul, and internally a service mesh of hundreds of
microservices with client-side load balancing (Ribbon) and service discovery (Eureka) —
i.e. the edge is optimised for reach and debuggability, the interior for throughput and
typed contracts. **Stripe** stayed REST at the edge for a decade *specifically* because
integrability beats efficiency for a public API — their entire product depends on a
developer being able to paste a `curl` command and see it work. **GitHub** ships both a
REST API and a GraphQL API side by side and explicitly documents them as having separate
rate-limit buckets (5,000 requests/hour for REST's core bucket, 5,000 *points*/hour for
GraphQL), which is a clean public admission that the two serve different clients rather
than one replacing the other.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| **REST at the edge** — always the safe default | Ultra-chatty mobile screens needing 15 resources | Over-fetching, endpoint sprawl, N round trips |
| **gRPC internally** — high-QPS typed east-west | You have three services and no polyglot problem | protoc in the build; HTTP/2-aware LB required |
| **GraphQL in a BFF** — many clients, connected graph, fast-moving UI | One client, stable screens, cache-heavy reads | Caching, cost limiting, DataLoader discipline forever |
| **SOAP** — a counterparty's WSDL is the requirement | Any greenfield choice | XML tooling, WS-* complexity, scarce expertise |

### Follow-ups they will ask

**Q: Why not use GraphQL everywhere and be done with it?**
A: Because two things break at the edges. Public consumers want stable, cacheable,
`curl`-able endpoints and a rate limit they can reason about, and GraphQL gives them a
single POST URL with cost-based throttling — that's a worse developer experience for a
partner integration. And internally, GraphQL adds runtime query planning to a path where
I want a fixed, typed message and the lowest possible per-call overhead. GraphQL's sweet
spot is genuinely the middle layer: a BFF over several services for several clients.

**Q: When would you actually replace a REST endpoint with GraphQL?**
A: When I can point at a specific screen making six or more REST calls in a waterfall,
where each call's input depends on the previous response, and the mobile team is blocked
on me shipping a bespoke aggregate endpoint per screen. That's the shape GraphQL solves.
If instead the complaint is "responses are too big," sparse fieldsets (`?fields=`) fix
that for a fraction of the cost.

**Q: You have gRPC internally and REST at the edge. Isn't maintaining two contracts
duplicated work?**
A: Some, and there are two ways to cut it. gRPC-Gateway or protobuf's
`google.api.http` annotations generate a REST/JSON facade directly from the `.proto`, so
one contract produces both surfaces. Or Connect, which serves gRPC, gRPC-Web and plain
HTTP/JSON from the same handlers. I'd only do that where the REST surface is genuinely a
thin mirror; for a public API I'd hand-design the REST layer, because a public contract
shouldn't be a mechanical projection of an internal one.

**Q: Where do webhooks fit in this table?**
A: They're the inverse direction and they're not really an alternative — they're how you
push to a system you can't poll. Any of these can be the outbound mechanism, but in
practice webhooks are almost always HTTP POST with JSON and an HMAC signature, because
the receiver is someone else's server and HTTP is the only thing you can assume. That's
[3.10](#310-webhooks--the-reverse-api).

### Red flags — do not say this

- ❌ "GraphQL replaced REST." → ✅ "They solve different problems; GitHub and Shopify ship
  both, deliberately, with separate rate-limit models."
- ❌ "gRPC is the modern choice, REST is legacy." → ✅ "gRPC wins east-west; REST wins at
  the edge because of browsers, caching and debuggability."
- ❌ "SOAP is dead." → ✅ "It's not chosen for greenfield, but plenty of banking and
  insurance integrations mandate a WSDL, and you don't get a vote."
- ❌ "We'll pick one protocol for the whole system." → ✅ "Different protocol per boundary:
  REST at the edge, gRPC internally, webhooks outbound."

---

## 3.10 Webhooks — the reverse API

**Interview weight:** ★★★★☆

> **One-liner:** A webhook is you making an HTTP request into someone else's
> infrastructure, which means you own signing, retries and ordering, and they own
> idempotency — and neither side can assume the other is up.

### Say this in the interview

> A webhook inverts the usual direction: instead of the client polling me, I POST to a
> URL they registered. That flips every reliability assumption, so there are four things
> I always design. First, authentication: I sign the payload with HMAC-SHA256 over the
> timestamp plus the raw request body, using a per-endpoint secret, and put it in a header
> — the same scheme Stripe uses with `Stripe-Signature: t=...,v1=...`. The receiver must
> verify against the raw bytes, not a re-serialised JSON, or the signature will never
> match. Second, replay protection: the timestamp is inside the signed payload, so an
> attacker can't change it, and the receiver rejects anything outside a tolerance window
> — Stripe's libraries default to five minutes. Third, retries: delivery is at-least-once,
> with exponential backoff, and I'd retry for something like three days before disabling
> the endpoint, which is what Stripe does in live mode. That means the receiver *will*
> see duplicates, so the receiver has to be idempotent on the event ID — I'd say that
> explicitly, because it's the part people forget. Fourth, ordering: I don't promise it.
> Parallel workers and retries mean events arrive out of order, so every event carries a
> version or a sequence number and the receiver ignores anything older than what it has
> already applied. If a consumer truly needs ordering I'd give them a per-entity
> partition key and deliver serially per entity, and tell them that costs head-of-line
> blocking.

### Mental model

```text
   Your system                                    Customer's system
   ───────────                                    ─────────────────
   payment.succeeded
        │
        ▼
   ┌──────────────┐   durable outbox: the event is committed in the SAME
   │  outbox tbl  │   transaction as the business change, so you can never
   └──────┬───────┘   "charge but forget to notify"
          ▼
   ┌──────────────┐
   │ delivery     │──POST /hooks/acme ─────────────►┌──────────────────┐
   │ worker pool  │   X-Signature: t=..,v1=..       │  their endpoint  │
   └──────┬───────┘◄──── 2xx = delivered ───────────└────────┬─────────┘
          │        ◄──── 4xx/5xx/timeout ────┐               │
          │                                  │               ▼
          │  exponential backoff + jitter     │      verify sig + timestamp
          │  ~5m, 30m, 2h, 5h, 10h, 12h...    │      dedupe on event_id
          │  give up after ~3 days ───────────┘      ENQUEUE, return 200 fast
          ▼                                                  │
    disable endpoint + notify the customer                    ▼
                                                     process asynchronously
```

**Why the receiver must return 2xx before doing the work.** Senders enforce short
timeouts (Stripe's is a few seconds). If the receiver does its business logic inline and
takes longer, the sender times out and retries — so slow processing manufactures
duplicates. The correct receiver is: verify signature, persist the raw event, return 200,
process from a queue.

**The ordering problem**, concretely:

```text
Events emitted:      subscription.updated(v1)   subscription.updated(v2)
Delivery attempt 1:  ✗ 503 (their DB was down)  ✓ 200
Retry of v1 (+5 m):  ✓ 200

Receiver applied:    v2, then v1  →  final state is v1. WRONG.

Fixes, in order of preference:
  1. Version/sequence field in every event; receiver does
       UPDATE ... WHERE entity_id = $1 AND version < $2     ← idempotent + ordered
  2. Receiver treats the webhook as a signal, not data:
       "something changed" → GET /v1/subscriptions/{id} for current truth
       (this is the most robust pattern and I'd recommend it explicitly)
  3. Sender partitions by entity_id and delivers serially per entity
       → real ordering, at the cost of head-of-line blocking per entity
```

Pattern 2 deserves emphasis: a thin "changed" notification plus a read-back removes
ordering, staleness *and* payload-size problems in one move. The cost is an extra API call
per event and a read-your-writes concern if the sender has read replicas.

### Enterprise production example

**Stripe's** webhook scheme is the de facto standard, and the details are specific enough
to quote. Each request carries `Stripe-Signature: t=1492774577,v1=5257a869e7...`. The
signed payload is the timestamp, a literal `.`, then the *raw* request body; the signature
is HMAC-SHA256 keyed with the endpoint's `whsec_` secret, hex-encoded. Only the `v1`
scheme is valid for live events — their docs say to ignore any other scheme specifically
to prevent downgrade attacks — and the header can carry multiple `v1` values during a
secret rotation, so you must parse it as a list. Their libraries default to a **five-minute
tolerance** on the timestamp. Delivery is at-least-once with exponential backoff for up to
**three days** in live mode, after which the endpoint is disabled and the account owner is
emailed.

The instructive contrast: **GitHub does not automatically retry failed webhook deliveries
at all.** Their guidance is to build your own recovery — poll the Deliveries API for
failures and call the redelivery endpoint yourself. Same word, "webhook", completely
different reliability contract. That's the point to make in an interview: webhooks imply
no delivery guarantee, so you must read each provider's actual policy.

### Code

Receiver in FastAPI. Three things to notice: raw body, constant-time compare, and a
replay cache in addition to the timestamp window.

```python
import hashlib, hmac, time
from fastapi import APIRouter, HTTPException, Request, Response

TOLERANCE_S = 300                       # Stripe's default: 5 minutes

def parse_signature_header(header: str) -> tuple[int, list[str]]:
    ts, sigs = None, []
    for part in header.split(","):
        k, _, v = part.strip().partition("=")
        if k == "t":
            ts = int(v)
        elif k == "v1":                  # ignore v0/other schemes: downgrade defence
            sigs.append(v)
    if ts is None or not sigs:
        raise HTTPException(400, "malformed signature header")
    return ts, sigs

@router.post("/webhooks/acme")
async def receive(request: Request, redis=Depends(get_redis), db=Depends(get_db)):
    raw = await request.body()           # RAW BYTES. Never json.dumps(parsed).
    header = request.headers.get("X-Acme-Signature")
    if not header:
        raise HTTPException(400, "missing signature")
    ts, sigs = parse_signature_header(header)

    if abs(time.time() - ts) > TOLERANCE_S:
        raise HTTPException(400, "timestamp outside tolerance")   # replay defence

    expected = hmac.new(
        settings.webhook_secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256
    ).hexdigest()
    if not any(hmac.compare_digest(expected, s) for s in sigs):   # constant time
        raise HTTPException(401, "signature mismatch")

    event = json.loads(raw)
    event_id = event["id"]

    # Replay defence #2: the timestamp window alone allows replays WITHIN 5 min.
    if not await redis.set(f"wh:seen:{event_id}", "1", nx=True, ex=86400):
        return Response(status_code=200)          # already accepted: ack, do nothing

    # Persist + enqueue, then ack FAST. Do not do business logic inline: the
    # sender's timeout is a few seconds, and a slow 200 manufactures retries.
    await db.execute(
        """INSERT INTO webhook_event (id, type, payload, received_at)
           VALUES ($1,$2,$3, now()) ON CONFLICT (id) DO NOTHING""",
        event_id, event["type"], raw.decode())
    await queue.publish("webhook.received", {"event_id": event_id})
    return Response(status_code=200)
```

The worker, where ordering is handled:

```python
async def handle_subscription_updated(event: dict, db) -> None:
    sub = event["data"]["object"]
    # Version guard: a delayed retry of an OLDER event must not overwrite newer state.
    updated = await db.execute(
        """UPDATE subscriptions
              SET status = $2, plan = $3, version = $4, updated_at = now()
            WHERE id = $1 AND version < $4""",
        sub["id"], sub["status"], sub["plan"], sub["version"])
    if updated == "UPDATE 0":
        logger.info("stale webhook ignored", extra={"id": sub["id"]})
```

Sender side, in Node — the signature and the backoff schedule:

```javascript
import crypto from 'node:crypto';

export function sign(rawBody, secret, timestamp = Math.floor(Date.now() / 1000)) {
  const signed = `${timestamp}.${rawBody}`;
  const v1 = crypto.createHmac('sha256', secret).update(signed).digest('hex');
  return `t=${timestamp},v1=${v1}`;
}

// Attempt schedule; jitter so a recovering endpoint isn't hit by a synchronised herd.
const DELAYS_S = [0, 300, 1800, 7200, 18000, 36000, 43200, 43200, 43200, 43200];

export async function deliver(endpoint, event, attempt = 0) {
  const body = JSON.stringify(event);
  const res = await fetch(endpoint.url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Acme-Signature': sign(body, endpoint.secret),
      'X-Acme-Event-Id': event.id,          // the receiver's dedupe key
      'X-Acme-Delivery-Attempt': String(attempt + 1),
    },
    body,
    signal: AbortSignal.timeout(5_000),      // short: don't let a slow receiver
  });                                        // occupy a worker for a minute
  if (res.ok) return { delivered: true };
  if (attempt + 1 >= DELAYS_S.length) {
    await disableEndpoint(endpoint.id, 'exhausted retries over ~3 days');
    return { delivered: false };
  }
  const jitter = 0.8 + Math.random() * 0.4;
  await scheduleRetry(endpoint, event, attempt + 1, DELAYS_S[attempt + 1] * jitter);
  return { delivered: false };
}
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Pushing events to third parties who can't be polled | Internal service-to-service (use Kafka/Pub/Sub — real ordering and replay) | You own retries, signing, endpoint health, and a delivery-status UI |
| Thin "something changed" event + client reads back | The event payload is the whole point (e.g. a signed receipt) | An extra API call per event; read-replica staleness |
| At-least-once with idempotent receivers | You promised exactly-once (you can't deliver it) | Receiver complexity; every consumer must dedupe |

### Follow-ups they will ask

**Q: A customer's endpoint has been down for two hours and you have 500,000 queued
events for them. What happens?**
A: Two things must hold. First, one bad endpoint cannot starve everyone else, so delivery
is partitioned per endpoint with its own concurrency budget and its own circuit breaker —
otherwise a single dead receiver fills the shared worker pool and delays every other
customer. Second, when they come back I must not deliver 500,000 events at once and knock
them over again, so I ramp: half-open the breaker, send a trickle, and increase
concurrency only while responses stay 2xx. I'd also cap the queue by age rather than
count — events older than the retention window get dropped with a record, and the
customer reconciles via a list API.

**Q: The receiver says your signature verification is broken. What's your first guess?**
A: They're verifying against a re-serialised body. Almost every framework parses JSON
into a dict and hands you that; if you `json.dumps` it back, key order and whitespace
differ from what was signed and the HMAC will never match. The fix is to read the raw
bytes before parsing — in FastAPI, `await request.body()`; in Express,
`express.raw({type: 'application/json'})` on that route only. Second guess is a proxy
that rewrote or re-compressed the body.

**Q: Why isn't a shared secret in a header good enough instead of an HMAC?**
A: A bearer secret in a header authenticates the *sender* but says nothing about the
*payload*, so anything that can see one request can replay it verbatim forever, and
anything in the path can modify the body undetected. An HMAC over timestamp plus body
binds the signature to that exact payload at that exact time, so tampering fails
verification and replays fall outside the tolerance window. It also lets me rotate by
sending two `v1` signatures during the overlap, which a single static secret can't do.

**Q: Can you give a consumer exactly-once delivery?**
A: No, and I'd say so directly. Any network can lose the acknowledgement rather than the
message, so the sender can never distinguish "not delivered" from "delivered, ack lost" —
which is why at-least-once plus an idempotent receiver is the only honest contract. What I
*can* provide is effectively-once processing: a stable `event_id` on every delivery and a
documented expectation that the receiver dedupes on it, which is exactly the same
mechanism as [3.5](#35-idempotency-in-apis--the-idempotency-key-pattern).

**Q: How do you keep an outbound webhook from being an SSRF vector?**
A: The URL is attacker-supplied, so I validate it: HTTPS only, resolve the hostname and
reject private and link-local ranges (`10/8`, `172.16/12`, `192.168/16`, `127/8`,
`169.254/16`, and the IPv6 equivalents), re-check after redirects — or refuse to follow
redirects at all — and pin to the resolved IP to close the DNS-rebinding window between
validation and connection. I'd also send from an egress-restricted worker pool rather than
from a pod with access to the internal network.

### Red flags — do not say this

- ❌ "The receiver checks a secret in the URL query string." → ✅ "HMAC over timestamp plus
  raw body; a URL secret leaks into logs, proxies and browser history."
- ❌ "We guarantee webhooks arrive in order." → ✅ "Retries make ordering impossible; I
  version every event and the receiver ignores stale ones."
- ❌ "We deliver each event exactly once." → ✅ "At-least-once with a stable event ID; the
  receiver dedupes."
- ❌ "The receiver processes the event and then returns 200." → ✅ "Verify, persist,
  enqueue, return 200 in milliseconds — slow processing causes the sender to time out and
  retry, which manufactures duplicates."

---

## 3.11 API Gateway — and how it differs from LB and service mesh

**Interview weight:** ★★★★★

> **One-liner:** An API gateway is the single ingress point that handles the concerns
> every service would otherwise reimplement — authentication, rate limiting, routing,
> TLS termination, request validation and observability — and it is *not* a load balancer
> and *not* a service mesh.

### Say this in the interview

> An API gateway is where I put the cross-cutting concerns that every service would
> otherwise implement badly and inconsistently: terminating TLS, verifying the JWT once
> so downstream services can trust the identity, enforcing rate limits per API key,
> rejecting malformed requests against a schema before they reach business logic, routing
> by path or header, and emitting a uniform access log and trace for every request. The
> distinction I want to be precise about, because candidates blur it, is that a load
> balancer distributes connections or requests across identical backends and knows
> nothing about my API — whereas a gateway understands routes, authentication and
> tenants, and can transform and aggregate. And a service mesh is a different axis
> entirely: the gateway handles north-south traffic entering the system, the mesh handles
> east-west traffic between services via sidecars, doing mTLS, retries and circuit
> breaking without any application code. In practice they compose: an anycast global load
> balancer in front, a gateway for policy, and a mesh inside. I'd also be honest that you
> often don't need one. For a single monolith or three services behind one deployment,
> a managed load balancer plus a middleware in the app does the same job with one fewer
> hop, one fewer thing to operate, and one fewer single point of failure — and a gateway
> nobody owns becomes the place where every team's special case goes to accumulate.

### Mental model

```text
              ╔══════════════ NORTH-SOUTH (ingress) ══════════════╗
              ║                                                    ║
  internet ──►│ DNS ──► Global LB (anycast, TLS, WAF, DDoS)        │
              │           │                                        │
              │           ▼                                        │
              │   ┌─────────────────────────────────────┐          │
              │   │           API GATEWAY               │          │
              │   │  1. TLS termination                 │          │
              │   │  2. authN: verify JWT / API key     │          │
              │   │  3. authZ: coarse scope check       │          │
              │   │  4. rate limit / quota per key      │          │
              │   │  5. request validation (OpenAPI)    │          │
              │   │  6. routing: /search → search-svc   │          │
              │   │  7. aggregation / transformation    │          │
              │   │  8. access log, metrics, trace id   │          │
              │   └───────────────┬─────────────────────┘          │
              ╚═══════════════════│════════════════════════════════╝
                                  │
              ╔═══════════════════▼═══════════════ EAST-WEST ══════╗
              ║   ┌──────────┐        ┌──────────┐                 ║
              ║   │ svc A    │◄──────►│ svc B    │   SERVICE MESH: ║
              ║   │ ┌──────┐ │  mTLS  │ ┌──────┐ │   mTLS, retries,║
              ║   │ │sidecar│ │        │ │sidecar│ │  circuit break,║
              ║   │ └──────┘ │        │ └──────┘ │   traffic split ║
              ║   └──────────┘        └──────────┘                 ║
              ╚════════════════════════════════════════════════════╝
```

### Gateway vs load balancer vs service mesh

| | Load balancer | API gateway | Service mesh |
|---|---|---|---|
| **Traffic direction** | north-south | north-south | east-west |
| **Unit of work** | connection (L4) or HTTP request (L7) | API call on a named route | every inter-service call |
| **Knows about** | backends, health, ports | routes, consumers, API keys, tenants, schemas | services, identities, policies |
| **Auth** | none (mTLS at most) | JWT/OAuth/API key validation, per-consumer | mTLS identity between workloads |
| **Rate limiting** | crude connection limits | per key / per route / per tenant quotas | per-service concurrency limits |
| **Deployed as** | managed cloud LB, or nginx/HAProxy | Apigee, Kong, Envoy Gateway, AWS API Gateway | Istio/Linkerd sidecars, Traffic Director |
| **Fails how** | no route to backends | no API access at all (it's a SPOF — run ≥2) | per-pod sidecar; blast radius is one pod |
| **You need it when** | more than one backend instance | more than one team or external consumers | many services + zero-trust + uniform retries |

The one-line version to say out loud: *"A load balancer answers 'which instance?'; a
gateway answers 'is this caller allowed to do this, and where does it go?'; a mesh answers
'how do services talk to each other safely?'"*

**The BFF pattern** — for when one gateway response shape can't serve every client:

```text
Without BFF: every client calls 6 services and assembles the screen itself
   mobile ──┬──► profile ──┐
            ├──► orders ───┤   6 round trips over a mobile network:
            ├──► rewards ──┤   ~150 ms RTT each = ~900 ms of latency,
            ├──► ...       ┘   and the aggregation logic lives in 3 apps

With a BFF: one aggregate endpoint per client, owned BY that client's team
   mobile ──► BFF-mobile ──┬──► profile   1 round trip; the BFF fans out
   web ─────► BFF-web ─────┤    orders     in-cluster (~2 ms hops) and
   partner ─► BFF-partner ─┘    rewards    returns exactly what the screen needs
   ▲ each BFF is small, owned by the client team, and free to change shape
     without coordinating with the other clients
```

A BFF is a gateway specialised per client, not an extra tier for its own sake. The failure
mode is a BFF that grows business logic — then it's a distributed monolith with a
misleading name. GraphQL is one common way to implement a BFF; a plain aggregating REST
service is another, and usually simpler.

**When you don't need a gateway.** Say this unprompted; it reads as judgement:

```text
Skip it when:
  · one monolith or a handful of services deployed together
  · a single first-party client, no external consumers
  · your managed LB already does TLS, WAF and basic routing
  · auth is a 20-line middleware and rate limiting is one Redis call
Then: DNS → managed LB → app (with middleware). One fewer hop, one fewer
      SPOF, one fewer thing on call.

Add it when:
  · external/partner consumers need keys, quotas and a developer portal
  · many teams need consistent authN/authZ and you can't trust each to do it
  · you need per-tenant quotas or monetisation
  · you need one place to shed load and roll out canaries across services
```

### Enterprise production example

**Netflix's Zuul** is the reference API gateway and its architecture is worth naming: a
filter pipeline of pre-routing, routing, post-routing and error filters, which is the
model Spring Cloud Gateway, Kong and AWS API Gateway all converged on. Netflix's own
engineering blog describes Zuul's job as acting "as the front door to Netflix's server
infrastructure, handling traffic from all Netflix users around the world" — routing
requests, supporting developer testing and debugging, providing insight into service
health, protecting Netflix from attacks, and **channelling traffic to other cloud regions
when an AWS region is in trouble**. That last responsibility is the one candidates never
mention and it's the most interesting: because every request already flows through the
gateway, the gateway is the natural place to execute a regional failover.

The Zuul 2 rewrite moved from blocking thread-per-connection to async Netty, and the blog
is explicit about why: the primary benefit was letting tens of millions of devices hold
persistent connections (they cite "more than 83 million members, each with multiple
connected devices" at the time), with a measured ~25% throughput improvement and ~25% CPU
reduction on their push cluster. And they state the cost — "a system that is much more
complex to debug, code, and test." That pairing of benefit and cost is exactly how to
present a gateway in an interview.

### Code

Envoy-style declarative config, because the config *is* the design and it shows the
responsibilities concretely:

```yaml
# envoy: JWT auth + per-key rate limit + route + retries + timeout
static_resources:
  listeners:
  - name: ingress
    address: { socket_address: { address: 0.0.0.0, port_value: 8443 } }
    filter_chains:
    - transport_socket:                              # 1. TLS termination
        name: envoy.transport_sockets.tls
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
          common_tls_context:
            tls_certificates: [{ certificate_chain: {filename: /certs/tls.crt},
                                 private_key: {filename: /certs/tls.key} }]
      filters:
      - name: envoy.filters.network.http_connection_manager
        typed_config:
          "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
          stat_prefix: ingress
          tracing: { provider: { name: envoy.tracers.opentelemetry } }  # 8. traces
          http_filters:
          - name: envoy.filters.http.jwt_authn                          # 2. authN
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
              providers:
                auth0:
                  issuer: https://acme.auth0.com/
                  remote_jwks:
                    http_uri: { uri: https://acme.auth0.com/.well-known/jwks.json,
                                cluster: auth0, timeout: 3s }
                    cache_duration: { seconds: 600 }
                  forward_payload_header: x-jwt-claims   # downstream trusts this
              rules:
              - match: { prefix: /v1/ }
                requires: { provider_name: auth0 }
              - match: { prefix: /healthz }              # never auth health checks
          - name: envoy.filters.http.local_ratelimit                    # 4. limits
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.http.local_ratelimit.v3.LocalRateLimit
              stat_prefix: per_key
              token_bucket: { max_tokens: 200, tokens_per_fill: 200,
                              fill_interval: 1s }
          - name: envoy.filters.http.router
          route_config:
            virtual_hosts:
            - name: api
              domains: ["api.acme.com"]
              routes:                                                   # 6. routing
              - match: { prefix: /v1/search }
                route:
                  cluster: search_svc
                  timeout: 2s
                  retry_policy:
                    retry_on: 5xx,reset,connect-failure
                    num_retries: 2
                    per_try_timeout: 700ms      # 2 × 700ms < 2s overall budget
              - match: { prefix: /v1/documents }
                route: { cluster: doc_svc, timeout: 30s }   # uploads are slow
```

Two details that separate a working gateway from a broken one, both visible above: the
health-check path is excluded from authentication (otherwise your probes 401 and the
whole fleet drains — see
[Module 04 — Health checks](./04_Scaling_And_LoadBalancing.md#46-health-checks)), and
`num_retries × per_try_timeout` is kept strictly under the overall route timeout, or
retries can never actually fire.

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| Multiple teams/services, external consumers, per-key quotas | One monolith, one first-party client | An extra hop (~1-5 ms), a new SPOF to run redundantly, a config surface to own |
| Aggregation/BFF for chatty clients on slow networks | Clients on fast networks fetching one resource | Coupling: the BFF changes whenever a screen changes |
| One place for authN, WAF, load shedding, regional failover | Teams that need per-service policy divergence | A shared bottleneck: gateway config becomes a queue between teams |

### Follow-ups they will ask

**Q: Isn't the API gateway now a single point of failure?**
A: It is, so it's never a single instance. It runs as a stateless replicated fleet behind
an anycast or DNS-level load balancer across at least two zones, with N+2 capacity so
losing a zone doesn't drop you below headroom. The subtler risk is *configuration* as a
SPOF: one bad route or auth rule takes down every API at once, so gateway config gets the
same treatment as code — version control, staged rollout, and automatic rollback on error
rate. And the control plane must not be in the request path: if the config server dies,
existing gateways keep serving the last known-good config.

**Q: Should the gateway do authorization, or just authentication?**
A: Authentication and coarse authorization at the gateway — is the token valid, is it not
expired, does it carry the scope this route requires. Fine-grained authorization stays in
the service, because "can this user read *this specific document*" needs the document's
tenant and ACL, and the gateway would have to duplicate the domain model to answer it.
The gateway's job is to verify identity once and forward trustworthy claims so services
don't each re-validate a JWT signature.

**Q: What's the difference between an API gateway and a service mesh ingress gateway?**
A: They overlap and that's genuinely confusing. Istio's ingress gateway is an Envoy at the
edge doing TLS, routing and traffic splitting — infrastructure-level ingress. A full API
gateway adds product concerns: API keys, quotas and monetisation, a developer portal,
request/response transformation, OpenAPI validation. If all you need is routing and mTLS,
the mesh's ingress gateway is enough and one fewer component. If you're exposing APIs to
paying third parties, you want the API-management layer.

**Q: You put rate limiting in the gateway. How does it work across 20 gateway replicas?**
A: Local token buckets per replica are cheap but let a client burst up to 20× the intended
limit if they hash unluckily. So for anything I actually enforce, the counter lives in
Redis with an atomic Lua script, and the gateway keeps a small local bucket as a first
line so the common case never touches Redis. The trade is a ~1 ms Redis hop per limited
request, and a decision about failure mode: if Redis is unavailable I fail *open* for
customer-facing limits (availability over precision) and fail *closed* for abuse
protection.

**Q: Should the gateway aggregate calls to three services into one response?**
A: Sparingly. Aggregation is genuinely valuable for a chatty client on a high-latency
mobile network — six sequential 150 ms round trips becomes one, with the fan-out happening
over ~2 ms in-cluster hops. But aggregation logic in a shared gateway becomes business
logic owned by nobody, and one slow upstream now slows a response that three teams share.
So I'd put aggregation in a BFF owned by the client team rather than in the shared
gateway, and I'd make each fan-out call independently timed with a partial-response
fallback.

### Red flags — do not say this

- ❌ "An API gateway is basically a load balancer." → ✅ "A load balancer picks an instance;
  a gateway understands routes, consumers, quotas and schemas, and can transform."
- ❌ "The service mesh replaces the API gateway." → ✅ "Different axes: gateway is
  north-south ingress policy, mesh is east-west inter-service communication."
- ❌ "Every architecture needs an API gateway." → ✅ "For one service with one client, a
  managed LB plus app middleware is one fewer hop and one fewer SPOF."
- ❌ "The gateway does all authorization." → ✅ "AuthN and coarse scopes at the gateway;
  resource-level authorization stays in the service that owns the resource."
- ❌ "We put business logic in the gateway to avoid touching services." → ✅ "Gateway holds
  cross-cutting concerns only; business logic there is a distributed monolith with no
  owner."

---

## 3.12 API contracts & schema evolution

**Interview weight:** ★★★☆☆

> **One-liner:** A contract is only real if CI fails when you break it — an OpenAPI file
> nobody validates against is documentation, not a contract.

### Say this in the interview

> I treat the API contract as a build artifact, not a document. For REST that means an
> OpenAPI spec that is either generated from the code — FastAPI gives me this for free
> from the Pydantic models — or is the source of truth that the server is validated
> against. The important part is the CI gate: a job diffs the new spec against the
> previous released one and fails the build on a breaking change, using the same rules I
> use for versioning — removing a field, renaming one, tightening validation, or making
> an optional parameter required. For internal services I go further with
> consumer-driven contracts: each consumer publishes the subset of the response it
> actually depends on, and the provider's pipeline verifies it still satisfies every
> published expectation before deploying. That's what lets me delete a field with
> confidence, because I can see who reads it rather than guessing. And the sequencing rule
> that prevents most incidents: expand, then migrate, then contract. Add the new field
> while keeping the old one, move every consumer, verify from telemetry that the old field
> has zero reads, and only then remove it — never in one deploy, because during a rolling
> release old and new versions are both live for minutes.

### Mental model

```text
The expand / migrate / contract sequence — never skip a step

  1. EXPAND    add `name`, keep `first_name` + `last_name`. Both populated.
               ✓ old consumers unaffected; new consumers can adopt
  2. MIGRATE   move consumers to `name`. Instrument reads of the old fields.
  3. VERIFY    old-field reads == 0 on live traffic for N days. This is a
               metric gate, not a calendar gate.
  4. CONTRACT  announce Sunset, brownout, then remove `first_name`/`last_name`.

Skipping step 3 is how "nobody uses that field" becomes an incident.
```

Consumer-driven contracts, and why they beat integration tests for this:

```text
Provider-driven (OpenAPI only)
  provider: "here is my schema"      consumer: "I hope it doesn't change"
  ▲ provider can't see which fields are actually read → afraid to delete anything

Consumer-driven (Pact-style)
  consumer test  ─── publishes ──►  ┌─────────────┐
  "when I GET /users/42 I need       │  contract   │
   {id, name} and nothing else"      │   broker    │
                                     └──────┬──────┘
  provider CI  ◄── verifies against ────────┘
  "do I still satisfy every published expectation?"  → fails the build if not
  ▲ now the provider KNOWS the real dependency surface and can delete safely
```

Internal event and RPC schemas need the same discipline in both directions, because
rolling deploys mean old and new coexist:

```text
Backward compatible  = new code can read OLD data   (consumer upgrades first)
Forward compatible   = old code can read NEW data   (producer upgrades first)

You need BOTH during a rolling deploy, because for several minutes you have
new producers talking to old consumers AND old producers talking to new ones.

protobuf: new tag numbers only, never reuse, `reserved` deleted tags.
Avro:     defaults on every new field; register in a schema registry with
          FULL_TRANSITIVE compatibility so CI rejects unsafe changes.
JSON:     additive only, and consumers must ignore unknown fields
          (Pydantic: model_config = ConfigDict(extra="ignore") — the default).
```

### Enterprise production example

**Stripe** publishes an explicit list of what it considers backwards compatible — adding
new resources, adding new *optional* request parameters, adding new response properties,
reordering response properties, and changing the length or format of opaque strings such
as object IDs and error messages. That last one is unusually specific and unusually
useful: they tell integrators that IDs can be up to 255 characters and even that fixed
prefixes like `ch_` may be added or removed, which means "store IDs as
`VARCHAR(255)`, don't parse them." Publishing that list is what makes the contract
enforceable — both sides know in advance which changes require a version and which don't.
Most teams have never written this list down, which is precisely why their "non-breaking"
changes keep breaking clients.

### Code

The CI gate is the whole topic. FastAPI generates the spec; a diff tool enforces it.

```yaml
# .github/workflows/api-contract.yml
name: api-contract
on: [pull_request]
jobs:
  breaking-changes:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - name: Export the OpenAPI spec from the app
        run: python -c "import json,app.main as m; \
                        print(json.dumps(m.app.openapi()))" > openapi.json
      - name: Fetch the last released spec
        run: gh api repos/$GITHUB_REPOSITORY/contents/contracts/openapi.json \
               --jq .content | base64 -d > baseline.json
      - name: Fail the build on a breaking change
        run: |
          docker run --rm -v "$PWD:/w" openapitools/openapi-diff:latest \
            --fail-on-incompatible /w/baseline.json /w/openapi.json
      # Protobuf equivalent:  buf breaking --against '.git#branch=main'
```

And the consumer-side contract test that makes deletion safe:

```python
# consumer repo: declares EXACTLY what it depends on, nothing more.
def test_contract_user_summary(pact):
    (pact
       .given("user 42 exists")
       .upon_receiving("a request for the user summary")
       .with_request("GET", "/v1/users/42")
       .will_respond_with(200, body={
           "id": Term(r"^usr_[a-zA-Z0-9]+$", "usr_42"),
           "name": Like("Alok Mehra"),
           # deliberately NOT asserting on email/created_at: we don't read them,
           # so the provider is free to change or remove them.
       }))
    with pact:
        assert UserClient(pact.uri).get_summary("42").name
```

### Trade-offs

| Use it when | Avoid it when | What it costs you |
|---|---|---|
| OpenAPI + breaking-change CI gate on any API with external consumers | A throwaway internal endpoint | Spec must be generated or validated, or it drifts into fiction |
| Consumer-driven contracts between internal services | Two services owned by the same team, deployed together | A broker to run, and every consumer must write and maintain contracts |
| Schema registry with `FULL_TRANSITIVE` for events | A single producer/consumer pair | Registry as an operational dependency; stricter change review |

### Follow-ups they will ask

**Q: Your OpenAPI spec doesn't match the running server. How did that happen and how do
you stop it?**
A: It happens whenever the spec is hand-maintained alongside the code — they diverge
within a sprint. Two fixes: generate the spec from the code, which FastAPI does from the
Pydantic models so it cannot drift, or make the spec the source of truth and validate
requests and responses against it at the gateway so a mismatch fails loudly. I'd also run
a contract fuzzer like Schemathesis against a staging deployment, which generates requests
from the spec and reports responses that violate it — that catches the cases where the
spec is right and the implementation isn't.

**Q: How do you know a field is safe to delete?**
A: I instrument reads rather than reasoning about it. For REST that's a per-field access
counter on the sparse-fieldset path, or the version each API key is pinned to; for
GraphQL it's field-level usage metrics, which the schema makes easy and is one of
GraphQL's genuine operational advantages. For internal services, consumer-driven
contracts answer it directly: if no published contract references the field, no verified
consumer reads it. Then I announce, brownout, and remove.

**Q: Is adding a field to an event schema really non-breaking?**
A: Usually, but there are two traps. A consumer with strict validation — a JSON schema
with `additionalProperties: false`, or a Pydantic model with `extra="forbid"` — will
reject the new payload outright, so "ignore unknown fields" has to be a documented
requirement from day one. And a new *enum value* breaks any consumer that switches
exhaustively on the enum, which is why every enum I publish is documented as extensible
with a mandatory unknown/default case.

### Red flags — do not say this

- ❌ "We have an OpenAPI spec, so we have a contract." → ✅ "A contract is a CI gate; an
  unenforced spec drifts within one sprint."
- ❌ "Integration tests will catch breaking changes." → ✅ "They catch what they happen to
  cover; a breaking-change differ plus consumer contracts covers the whole surface."
- ❌ "We can remove that field, nobody uses it." → ✅ "I'd instrument reads and confirm
  zero on live traffic before removal — 'nobody uses it' is how incidents start."
- ❌ "Adding a field is always safe." → ✅ "Safe if consumers ignore unknown fields; a
  strict-validation consumer or an exhaustive enum switch breaks."

---

## Module 03 — self-test

Answer out loud, without notes. If you stumble, reread that section.

1. Why is `PUT` idempotent and `POST` not? Give a concrete state transition for each.
2. Explain why `LIMIT 20 OFFSET 1000000` is slow, and why it is also *incorrect* on a
   list that's receiving inserts. What exactly does a keyset cursor replace it with?
3. You need to paginate a feed sorted by a popularity score that changes every minute.
   Keyset on `(score, id)` doesn't work. What do you do instead, and why?
4. Walk through the full idempotency-key flow, including what happens when Redis has the
   key marked `pending` and the pod that claimed it has died.
5. Why must the idempotency record and the business write commit in the same transaction?
6. What are the exact rules for a backwards-compatible API change? Name at least five
   non-breaking changes and four breaking ones.
7. Describe Stripe's versioning architecture. Why does it let one codebase support a
   decade of versions without version branches in the business logic?
8. What is the N+1 problem in GraphQL, why does DataLoader fix it, and why must the
   loader be created per request rather than per process?
9. Why is depth limiting insufficient for GraphQL, and what does Shopify do instead?
   What's the specific per-query ceiling?
10. Name the four gRPC call types and one real use for each. Why does a gRPC service
    behind a plain L4 load balancer end up sending all traffic to one backend?
11. What is a gRPC deadline and why is it strictly better than a client-side timeout
    during an overload?
12. Draw the difference between a load balancer, an API gateway and a service mesh in one
    sentence each. Then say when you would deploy none of them.
13. Reconstruct Stripe's webhook signature scheme from memory — header format, what is
    signed, which hash, and what the tolerance window is for.
14. Why can't you promise exactly-once webhook delivery, and what do you promise instead?
15. Explain expand/migrate/contract, and what specifically has to be true before the
    contract step.

---

## Key numbers from this module

| Fact | Number |
|------|--------|
| Stripe `Idempotency-Key` max length | 255 characters |
| Stripe v1 idempotency key retention | at least 24 hours (v2: 30 days) |
| Idempotency TTL to state in an interview | 24 h (`SET NX EX 86400`) |
| Stripe webhook signature tolerance (default) | 300 s / 5 minutes |
| Stripe webhook retry window (live mode) | up to 3 days, then endpoint disabled |
| GitHub webhook automatic retries | none — you poll the Deliveries API yourself |
| Shopify GraphQL: max cost of a single query | 1,000 points, enforced before execution |
| Shopify GraphQL restore rate | 100 points/s standard, 1,000/s Plus |
| GitHub GraphQL rate limit | 5,000 points/hour/user (10,000 for GHEC apps) |
| GitHub GraphQL node ceiling per call | 500,000 nodes; `first`/`last` must be 1-100 |
| Postgres offset pagination at depth | O(n) — "rows skipped by OFFSET still have to be computed inside the server" |
| Published keyset vs offset at ~1M rows deep | ~87 ms → sub-millisecond |
| Default page size to propose / hard cap | 25 default, 100 maximum |
| protobuf payload vs equivalent JSON | ~30-60% smaller |
| HTTP/2 HPACK header overhead vs HTTP/1.1 | ~40-90 bytes vs ~200-700 bytes |
| gRPC connections per host vs HTTP/1.1 | 1 multiplexed vs 6-8 |
| Netflix Zuul 2 (async Netty) on push cluster | ~25% more throughput, ~25% less CPU |
| gRPC default max message size | 4 MB (raise explicitly if you need more) |
| GraphQL depth limit to propose | 10-12 |
| Webhook receiver ack budget | return 2xx in < ~1 s; process from a queue |

---

**Next:** [Module 04 — Scaling, Load Balancing & Stateless Services](./04_Scaling_And_LoadBalancing.md)
