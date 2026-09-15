# What Is Phyllo (Interview Version)

## 60-second pitch (memorize)

> “Phyllo is a social and creator-data API gateway. Instead of every company integrating Instagram, YouTube, TikTok and others separately, Phyllo connects to 25+ platforms, collects public data and consented first-party data, normalizes it into one schema, and exposes REST APIs plus webhooks. Customers use it for influencer marketing, creator fintech, social KYC, social listening, and screening. Think of it as infrastructure for the creator economy — one integration, many platforms.”

## Shorter one-liner

> “Phyllo is Plaid-for-creators: consented and public social data through one API.”

---

## Two data layers (must know)

| | Public | Consented |
|---|--------|-----------|
| Creator login? | No | Yes (Connect SDK / OAuth) |
| Examples | Profile analytics, content, listening, search | Verified income, private metrics, real audience, publish |
| Used for | Discovery, vetting, listening, screening | Fintech, creator tools, KYC, deep measurement |

---

## Products (say these names)

1. **Connect** — link accounts + manage consent  
2. **Identity** — profile / identity / reputation  
3. **Engagement** — content + engagement metrics  
4. **Audience** — demographics / authenticity  
5. **Income** — earnings + transactions  
6. **Activity** — activity insights  
7. **Publish** — post to connected platforms  
8. **Webhooks** — push updates to customer backends  
9. **Creator Search / Listening / Screening** — public-data products  

---

## Core engineering loop

```
Creator connects account (consent)
        ↓
Phyllo syncs data from source platforms
        ↓
Normalize into one schema
        ↓
Customer reads via APIs
        ↓
Phyllo pushes changes via webhooks (IDs → customer bulk-fetches)
```

---

## Scale signals (use lightly)

- 25+ platforms  
- 470M+ profiles indexed (public search)  
- Billions of signals / month  
- Their webhook blog: ~3M deliveries/day, retry queues, HMAC signatures  

Only mention numbers if relevant to capacity discussion.

---

## Who builds on Phyllo (website tabs → possible LLD)

| Customer type | What they build | Possible LLD |
|---------------|-----------------|--------------|
| Influencer marketing | Vetting, campaign measurement, search | Search, campaign metrics, authenticity |
| Creator tools | In-app analytics, publish, income | Sync, analytics API, publish |
| Fintech / lending | Verified income, social KYC | Income ledger, KYC workflow |
| PR / listening | Mentions, SoV, sentiment | Listening pipeline |
| HR / immigration | Social screening, case reports | Screening + audit report |

---

## What Phyllo is NOT

- Not a full influencer campaign SaaS UI product (they sell APIs/infra)
- Not a scraper-you-operate (they position as compliant public + consented data)
- Not single-platform (multi-platform is the point)
