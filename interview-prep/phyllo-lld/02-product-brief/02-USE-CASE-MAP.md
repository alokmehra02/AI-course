# Use Case Map — From Website → Interview Problem

HR said the use case will come from Phyllo’s website/products. Use this map.

---

## How to extract a use case in 5 minutes

For any website capability, write:

```
Name:
Actors:
Happy path (5 steps):
Entities:
Sync or async?:
Hard parts (consent / scale / multi-platform / reliability):
Likely LLD ask:
```

---

## Ranked use cases

### P0 — Highest chance

#### 1) Connect + Consent + Account Linking
- **Website/docs:** Connect SDK, Authenticated APIs  
- **Ask:** Design account linking so creators grant Phyllo access to Instagram/YouTube/etc.  
- **Hard parts:** OAuth, scoped consent, SDK token, reauth, disconnect  

#### 2) Data Sync + Normalization Pipeline
- **Website:** “normalized data”, multi-platform coverage  
- **Ask:** After connect, sync identity/content/income continuously  
- **Hard parts:** rate limits, cursors, idempotent upserts, per-product status  

#### 3) Webhook Delivery System
- **Website/blog:** distributed webhook system  
- **Ask:** Notify developers on account/content/income updates reliably at millions/day  
- **Hard parts:** retries, timeouts, HMAC, poison customers, idempotency  

---

### P1 — Strong chance

#### 4) Verified Income Aggregation
- Consented earnings across ad/sponsorship/subs/affiliates  
- Ledger + monthly statement + FX + audit  

#### 5) Creator Search (470M profiles)
- Filters: niche, location, audience, growth  
- Search index, ranking, pagination  

#### 6) Social Listening
- Mentions, sentiment, share of voice  
- Ingest → dedupe → classify → aggregate → alert  

#### 7) Social KYC / Ownership Verification
- Prove user owns claimed accounts  
- OAuth proof + case-ready report  

---

### P2 — Possible stretch / infra

#### 8) Multi-tenant API Gateway + Rate Limiting  
#### 9) Campaign Measurement for influencer ROI  
#### 10) Fake-follower / authenticity scoring pipeline  
#### 11) Cross-platform Publish  

---

## If interviewer says “pick something from our site”

Recommend this sentence:

> “I’d like to design the core loop — Connect, multi-platform sync, and reliable webhook delivery — since that’s the backbone every Phyllo customer depends on. I can then extend into income or search if you want.”

---

## Mapping table (quick)

| Website phrase | LLD problem |
|----------------|-------------|
| Connect SDK | OAuth session + token + account state machine |
| Public vs consented | AuthZ + data classification |
| Normalized schema | Adapter + canonical model |
| Webhooks | Reliable delivery subsystem |
| Creator search | Indexing + query service |
| Social listening | Stream processing pipeline |
| Verified income | Transaction aggregation service |
| Social KYC | Verification workflow + audit |
| Influencer vetting | Feature store + scoring API |
| 7 days to production | Sandbox, DX, clear sync states |
