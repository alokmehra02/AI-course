# Assumptions Cheat Sheet

When interviewer is vague, state these and move on.

---

## Default assumptions pack

1. Designing **Phyllo-like backend**, not customer UI  
2. Language/design: **Python** services (FastAPI-style)  
3. Storage: **Postgres** + **Redis** + **task queue**  
4. Delivery: **at-least-once** webhooks  
5. Consistency: **eventual** for synced data reads  
6. V1 platforms: **2–3** major ones via adapters  
7. Security: OAuth tokens encrypted; HMAC webhooks; server-side API secrets  
8. Multi-tenant: every row keyed by `developer_id`  
9. Consent revoke stops sync immediately  
10. Sandbox fixtures exist for connectors  

---

## Say it as one breath

> “I’ll assume a Phyllo-style backend in Python with Postgres, Redis, and a task queue; at-least-once ID-based webhooks; eventual consistency for sync; and adapter-based connectors for a few platforms in v1.”
