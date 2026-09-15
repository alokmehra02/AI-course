# Resume → Phyllo Talking Points

Use **one** bridge per interview, naturally — don’t force all.

---

## VoXgent.AI — campaign scheduler

**You built:** Python scheduler on GCP Pub/Sub + Cloud Tasks, retries, Redis concurrency, 500+ concurrent calls.

**Say for Phyllo:**
> “Sync jobs and webhook retries are the same shape as my outbound scheduler — enqueue, lease/execute, backoff on failure, bound concurrency so one noisy tenant doesn’t starve others.”

---

## VoXgent — Gemini Live + Twilio webhooks

**You built:** Webhook-driven call lifecycle.

**Say:**
> “Same rule I use in production: webhook handler verifies and ACKs fast, then async work continues on queues.”

---

## Europa Locks — API gateway

**You built:** Gateway over 8+ services, auth, rate limiting, Redis cache.

**Say:**
> “Phyllo’s multi-tenant API edge needs the same gateway concerns — authn/authz by developer, rate limits, and protecting downstream platform connectors.”

---

## Europa — MQTT event-driven

**Say:**
> “I’m used to event-driven fanout when device/account state changes — similar to account/content update events feeding webhook delivery.”

---

## Positioning line (optional)

> “I’ve been working on production event-driven backends in Python; Phyllo’s connect-sync-notify architecture is directly in that wheelhouse.”
