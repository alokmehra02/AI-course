# Walkthroughs — Interview-ready scripts

Each file is a **full 60-min speaking script**: what to say, clarifiers, patterns, board, code, follow-ups, close.

**Parent one-file guide:** [`../PHYLLO_INTERVIEW_ONE_FILE.md`](../PHYLLO_INTERVIEW_ONE_FILE.md)

---

## Index

| # | File | What it’s for | Patterns |
|---|------|---------------|----------|
| 0 | [ADAPTER_CANONICAL_INTERVIEW_SCRIPT.md](ADAPTER_CANONICAL_INTERVIEW_SCRIPT.md) | **Multi-platform → one canonical schema** (very Phyllo-native) | Adapter, Factory, Repository, Facade |
| 1 | [01-CREATOR-SEARCH.md](01-CREATOR-SEARCH.md) | Creator Search (public) | Strategy, Repository, Facade |
| 2 | [02-INFLUENCER-VETTING.md](02-INFLUENCER-VETTING.md) | Influencer vetting | Facade, Strategy |
| 3 | [03-SOCIAL-LISTENING.md](03-SOCIAL-LISTENING.md) | Social listening / SoV | Strategy, Observer |
| 4 | [04-VERIFIED-INCOME.md](04-VERIFIED-INCOME.md) | Verified income (consented) | Adapter, Factory, Facade |
| 5 | [05-SOCIAL-KYC.md](05-SOCIAL-KYC.md) | Social KYC / ownership | State, Facade |
| 6 | [06-CAMPAIGN-AND-SCREENING.md](06-CAMPAIGN-AND-SCREENING.md) | Campaign metrics + screening | Facade, Strategy, Observer |
| 7 | [07-WEBHOOK-RELIABLE-DELIVERY.md](07-WEBHOOK-RELIABLE-DELIVERY.md) | Webhook HLD: MAIN + TTL retries + ALERT | RetryPolicy, Queue/DLQ, Facade |

---

## Recommended study order

1. **[ADAPTER_CANONICAL_INTERVIEW_SCRIPT.md](ADAPTER_CANONICAL_INTERVIEW_SCRIPT.md)** — fetch many platforms → normalize (speak + code)  
2. `01` Creator Search → `02` Vetting → `03` Listening → `04` Income → `05` KYC  
3. **`07` Webhooks** — if they ask reliability / retries (Phyllo published this HLD)  
4. `06` Campaign / screening — if time  

---

## Adapter script (what’s inside)

[`ADAPTER_CANONICAL_INTERVIEW_SCRIPT.md`](ADAPTER_CANONICAL_INTERVIEW_SCRIPT.md) is the end-to-end speaking guide for:

- Opening + clarifiers + assumptions  
- Why **Adapter** (not `if platform ==`)  
- Canonical `Profile` / `ContentItem`  
- `PlatformAdapter` + Instagram/YouTube adapters + **Factory** + **SyncOrchestrator** + **Repository**  
- Full Python to type in the interview  
- Edge cases, follow-ups, 60-min timebox, cheat card  

Practice that file if the prompt sounds like: *“normalize Instagram/YouTube into one schema”* or *“how does Phyllo support 25+ platforms?”*

---

## How to practice any file

1. Speak opening → clarifiers → patterns out loud  
2. Draw the diagram from memory  
3. Hand-write the CODE section  
4. Read **Logic explained** (where present)  
5. Answer the follow-up table  

**Website products** are still the most likely ask; **Adapter** and **Webhooks (`07`)** are the strongest eng/infra follow-ons.
