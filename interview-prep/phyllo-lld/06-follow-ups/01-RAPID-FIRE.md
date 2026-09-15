# Rapid-Fire Follow-ups — Questions + Answers

Cover with your hand, answer out loud, then check.

---

## Webhooks & events

**Q: Why webhooks instead of polling?**  
A: Push only on change; less load; near-real-time; avoids customers burning rate limits. Polling doesn’t scale with account count.

**Q: At-least-once or exactly-once?**  
A: At-least-once delivery + idempotent consumers (`event_id`). Exactly-once across network boundaries is expensive/fragile.

**Q: Why send IDs not full objects?**  
A: Keep webhooks fast/light; consistent for large datasets; customer bulk-fetches what they need.

**Q: Customer is slow — what happens?**  
A: Timeout counts as failure; retry with backoff; per-subscription concurrency caps so one tenant can’t block others.

**Q: How do you verify authenticity of webhook?**  
A: `X-Phyllo-Signature` = HMAC-SHA256(secret, raw body). Compare with constant-time compare. Optional IP allowlist.

**Q: Out-of-order events?**  
A: Upserts by natural keys; ignore stale via `updated_at`/version; don’t assume total order.

**Q: Dual-write bug (DB updated but event not emitted)?**  
A: Transactional outbox: write row + outbox in same DB txn; relay publishes to queue.

---

## Connect & sync

**Q: SDK event vs webhook?**  
A: SDK for UX immediacy; webhook for reliable backend processing.

**Q: Token expired mid-sync?**  
A: Try refresh; on failure mark `REAUTH_REQUIRED`, pause jobs, notify via webhook.

**Q: How to add a new platform?**  
A: Implement `PlatformConnector` adapter, register config, certification tests in sandbox. Orchestrator unchanged.

**Q: Platform schema changed?**  
A: Version normalizers; keep raw optional; feature-flag connector; don’t break canonical schema (expand-contract).

**Q: Backfill 2 years of videos?**  
A: Cursor checkpoints, low QPS trickle, priority below live incremental, resumable jobs.

**Q: Partial sync failure?**  
A: Per-product status — Identity SYNCED, Income FAILED — don’t block unrelated products.

**Q: Consent revoked / GDPR delete?**  
A: Stop sync immediately; revoke consents; enqueue purge; audit the deletion.

---

## Data & schema

**Q: SQL vs Elasticsearch?**  
A: Postgres source of truth for accounts/content; OpenSearch for creator discovery queries and filters at large scale.

**Q: Index for list content?**  
A: `(account_id, published_at DESC)` plus unique `(account_id, platform_content_id)`.

**Q: How do you dedupe content?**  
A: Natural key upsert on platform content id.

**Q: Cache where?**  
A: Cache profile summaries with TTL in Redis. Never stash raw OAuth tokens in a shared naive cache without encryption/isolation.

---

## Multi-tenant & security

**Q: How prevent developer A reading B’s users?**  
A: `developer_id` on every row; authn via client credentials; authz middleware checks ownership on every query.

**Q: Where do client secrets live?**  
A: Server-side only. Never in mobile/web client. SDK uses short-lived tokens.

**Q: Rate limit 429 handling on Phyllo side when calling Instagram?**  
A: Honor Retry-After; token bucket per platform/account; requeue job; surface lag metrics.

---

## Design process

**Q: Sync vs async Connect response?**  
A: Connect returns when account linked; data sync is async. Don’t block UX on full backfill.

**Q: How would you test without real Instagram?**  
A: Sandbox connectors returning fixtures; recorded OAuth; contract tests per adapter.

**Q: What metrics would you alert on?**  
A: Sync success rate, sync lag p95, webhook delivery success, retry depth, reauth rate, platform 429 rate.
