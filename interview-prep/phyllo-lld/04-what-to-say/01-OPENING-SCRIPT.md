# Opening Scripts — What to Say

## A. Soft intro (if they ask “tell me about yourself” briefly)

> “I’m a backend engineer with almost two years of experience, mostly Python and Node. Recently I’ve owned an outbound campaign scheduler on GCP with Pub/Sub and Cloud Tasks, plus real-time voice calling with webhooks, Redis concurrency controls, and earlier an API gateway with auth and rate limiting. I’m comfortable designing event-driven services end to end — which is why Phyllo’s connect-sync-webhook model interested me.”

Keep it under 45 seconds. Then stop.

---

## B. When they give the problem

> “Great. I’ll restate it to confirm, ask a few clarifying questions, list assumptions, then design entities, APIs, schema, and the main flows in Python. I’ll start with the core path and call out extensions.”

---

## C. Restate examples

### Connect
> “We need a system where a customer’s end user can link Instagram/YouTube/etc through Phyllo, grant consent for specific products like identity or income, Phyllo syncs data, and the customer is notified when data is ready.”

### Webhooks
> “We need reliable delivery of events to developer endpoints when account or content data changes, with security, retries, and multi-tenant isolation, at large daily volume.”

### Income
> “We need to aggregate consented income transactions across platforms into verified summaries a fintech or creator app can trust.”

---

## D. When you start drawing

> “I’ll sketch actors and core entities first, then APIs, then the sequence for the critical path.”

---

## E. When moving to failures

> “Happy path is solid. Next I’ll cover failure modes — token expiry, flaky customer webhooks, and rate limits — because that’s where this design usually breaks in production.”

---

## F. Bridge to your experience (use once, naturally)

> “This is similar to what I did for outbound campaign scheduling — enqueue work, bound concurrency with Redis, retry with backoff, and never block the ACK path. I’d apply the same pattern here for sync jobs and webhook delivery.”

---

## G. If they ask “any questions before we start?”

Ask one:
> “Is the use case designing Phyllo’s internal platform, or an application built on top of Phyllo APIs?”

That single question prevents designing the wrong system.
