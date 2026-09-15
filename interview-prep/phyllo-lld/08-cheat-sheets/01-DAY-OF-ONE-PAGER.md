# Day-of One-Pager

Print or keep this tab open.

---

## Phyllo in 3 lines

Social/creator data API gateway → public + consented data from 25+ platforms → normalized REST APIs + webhooks.  
Core loop: **Connect → Sync → Normalize → API/Webhook**.  
Design language: **Python**.

---

## First 8 minutes

1. Restate problem  
2. Ask: Phyllo-internal or app-on-Phyllo? actors? scale? sync/async? consent/reauth in scope?  
3. Assumptions  
4. Scope lock  

---

## Entities to draw

`Developer → User → Account → Consent/Product`  
`SyncJob → Profile/Content/Income`  
`WebhookSubscription → Delivery`

Account states: `PENDING → CONNECTED → SYNCING → READY` (+ `REAUTH_REQUIRED`, `DISCONNECTED`)

---

## Magic phrases

- “SDK for UX; webhooks for backend truth.”  
- “Webhooks send IDs; bulk fetch hydrates.”  
- “PlatformConnector adapter — new platform without rewriting core.”  
- “At-least-once + idempotent upserts.”  
- “Per-product sync status.”  
- “ACK fast; process async.”  
- “HMAC-SHA256 signature; timeout = failure; TTL retries 5m/60m/360m.”  

---

## Resume bridges

- VoXgent scheduler / Pub-Sub / Cloud Tasks → sync + webhook retries  
- Redis concurrency → rate limits / leases  
- Europa gateway → multi-tenant auth + rate limiting  

---

## Close

> Entities + async sync via adapters + idempotent store + signed webhook retries. Tradeoff: eventual consistency for reliability and platform safety.

---

## If you can only revise one design

**Connect + Sync + Webhooks** end-to-end.
