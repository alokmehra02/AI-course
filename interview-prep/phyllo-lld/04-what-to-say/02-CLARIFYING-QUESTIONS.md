# Clarifying Questions Bank

Ask 5–8 max. Pick from the relevant section. Always ask scale + sync/async + security.

---

## Universal (ask almost every time)

1. Who are the actors — end creator, customer developer, Phyllo admin?  
2. Is this designing Phyllo itself, or an app using Phyllo?  
3. Approximate scale — accounts, events/day, read QPS?  
4. Latency expectation — interactive vs eventual OK?  
5. Consistency — at-least-once events acceptable?  
6. Auth model — API keys / OAuth for developers?  
7. Which platforms in v1 — 2–3 or all 25?  
8. Any compliance constraints — consent revoke, GDPR delete?

---

## Connect + Sync

1. Which products on connect — IDENTITY only, or ENGAGEMENT/INCOME too?  
2. Is Connect SDK in scope, or only backend?  
3. Should disconnect and reauth be in v1?  
4. Initial full sync vs incremental — both?  
5. What happens if platform OAuth token expires mid-sync?  
6. Do we store raw platform payloads or only normalized?

---

## Webhooks

1. Delivery guarantee — at-least-once OK?  
2. Payload style — IDs only or full objects?  
3. ACK timeout — e.g. 5 seconds?  
4. Retry policy expectations?  
5. Ordering required per account?  
6. Customer endpoint auth — HMAC signature? IP allowlist?  
7. Multi-URL per developer or one?

---

## Income

1. Currencies — store original + convert?  
2. Categories — ads, sponsorship, subs, affiliates?  
3. Statement period — calendar month?  
4. Access audit required for fintech?  
5. Only consented accounts, correct?

---

## Creator Search

1. Filters required in v1?  
2. Ranking factors?  
3. Freshness SLA for indexed profiles?  
4. Pagination style?  
5. Personalization per customer or global index?

---

## Social Listening

1. Real-time alerts vs batch aggregates?  
2. Languages / platforms in scope?  
3. Sentiment in-house model or external service?  
4. Dedup across resharing?

---

## Social KYC

1. Proof method — OAuth connect mandatory?  
2. Output — boolean or case-ready PDF/report?  
3. Continuous monitoring or one-time?  
4. Retention policy for evidence?

---

## How to ask without sounding robotic

Bundle them:
> “Quick clarifiers: are we designing Phyllo’s internal sync, what’s rough event volume, is eventual consistency OK for developer reads, and should v1 include reauth and disconnect?”
