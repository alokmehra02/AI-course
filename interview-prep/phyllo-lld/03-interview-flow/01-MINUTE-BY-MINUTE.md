# Minute-by-Minute Interview Flow

Assume **45–60 minutes**. Adjust if they say 30.

---

## Phase 0 — Settle (0:00–0:02)

**You say:**
> “Looking forward to this. I’ll treat this as an LLD round — clarify requirements, then design entities, APIs, schema, and key flows in Python. Does that match what you had in mind?”

If they give a problem immediately, skip the meta and go to Phase 1.

---

## Phase 1 — Clarify (0:02–0:08)

Do **not** start drawing classes yet.

1. Restate the problem in 1–2 sentences  
2. Ask clarifying questions (functional)  
3. Ask non-functional: scale, latency, consistency, multi-tenant  
4. State assumptions  
5. Confirm scope: “I’ll focus on X first; Y as extension. OK?”

**Output of this phase:** a short written requirements list.

---

## Phase 2 — Skeleton (0:08–0:15)

On board/paper:

1. Actors  
2. Core entities (5–8 boxes)  
3. Module boxes (API / Connect / Sync / Webhook / DB / Queue)  
4. 4–6 API endpoints outline  

Speak while drawing. Keep boxes empty of fields at first.

---

## Phase 3 — Deep design (0:15–0:40)

Pick **one primary flow** and go deep:

### If Connect+Sync
- Sequence: create user → SDK token → OAuth → account connected → sync jobs → normalize → store → webhook  
- State machine for Account  
- PlatformConnector interface  
- Tables + indexes  

### If Webhooks
- Event → enqueue → worker POST → signature → retry queues → alert  
- Delivery table + idempotency  
- Timeout policy  

### Always cover in this phase
- Happy path sequence  
- One failure path  
- Idempotency  
- Where async happens  

---

## Phase 4 — Hardening (0:40–0:50)

Interviewer usually probes here. Proactively touch:

- Rate limits (platform + developer)  
- Reauth / token expiry  
- Multi-tenant isolation  
- Ordering / delayed webhooks  
- Observability (sync lag, delivery success %)  
- Extensibility (new platform)  

---

## Phase 5 — Wrap (0:50–0:55)

**You say:**
> “To summarize: we modeled Connect with consented products, async sync via workers and adapters, normalized storage with idempotent upserts, and at-least-once webhooks with HMAC and backoff retries. Main tradeoff was eventual consistency for developer reads in exchange for reliability and platform-rate-limit safety.”

Then ask them a question.

---

## If stuck

Use this recovery line:
> “Let me slow down and lock the contract first — entities and the API for the critical path — then I’ll fill concurrency.”

Or:
> “I’ll assume X for now and mark it; we can revisit if needed.”

---

## Timebox cheat card

| Min | Do |
|-----|----|
| 0–2 | Align on LLD |
| 2–8 | Clarify + assumptions |
| 8–15 | Entities + modules + API list |
| 15–40 | Deep flow + schema + classes |
| 40–50 | Failures / scale / tradeoffs |
| 50–55 | Summary + questions |
| 55–60 | Buffer / their questions |
