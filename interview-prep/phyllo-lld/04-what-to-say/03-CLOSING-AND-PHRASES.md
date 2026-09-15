# Closing Scripts + Phrases Mid-Interview

## Closing summary template

> “Summarizing the design:
> 1) **Entities** — Developer, User, Account, Consent, SyncJob, and domain data like Profile/Content.
> 2) **Flow** — Connect with scoped consent, async sync through platform adapters, normalize and upsert idempotently.
> 3) **Notify** — Webhooks send IDs; customers bulk-fetch; HMAC + retry with backoff.
> 4) **Hardening** — Per-product sync status, reauth, tenant isolation, and rate limits.
> Main tradeoff: eventual consistency on the customer read path for reliability and platform safety.”

Swap nouns to match the problem.

---

## Useful mid-interview phrases

| Moment | Say |
|--------|-----|
| Before assumptions | “I’ll assume X unless you want otherwise.” |
| Scope control | “I’ll lock v1 to these three flows; treat search as phase 2.” |
| When interviewer nods | “I’ll go one level deeper on the sync worker next.” |
| When challenged | “Good point — here’s the failure mode and how I’d handle it…” |
| When wrong | “You’re right — I’d change that to Y because…” |
| Need time | “Give me 20 seconds to structure the tables.” |
| Offer depth | “I can deepen schema, connector interface, or retries — which helps most?” |
| Tie to Phyllo | “This matches how Phyllo docs describe ID-only webhooks plus bulk retrieve.” |

---

## If time is running out

> “I have five minutes — I’ll finalize the schema and the retry policy, and leave ranking/ML as an extension.”

---

## If they ask “what would you do differently at 10x?”

> “Split hot paths: dedicated queues per tenant tier, shard sync jobs by account_id, move search to a dedicated index cluster, and add backpressure when platform 429s spike. Schema stays; topology changes.”
