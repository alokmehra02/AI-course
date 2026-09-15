# Deep Follow-ups — Longer Answers

Use when interviewer says “go deeper.”

---

## 1) Design the Sync worker lease so two workers don’t process one job

```
sync_jobs.locked_until, locked_by
Worker:
  UPDATE sync_jobs
  SET locked_until = now()+lease, locked_by = worker_id, status='IN_PROGRESS'
  WHERE id=? AND (locked_until IS NULL OR locked_until < now()) AND status in (...)
  -- check rowcount == 1
Process; on success mark SYNCED; on fail schedule retry
Heartbeat extends lease for long fetches
```

---

## 2) Transactional outbox (exactly how)

Same Postgres transaction:
1. Upsert `content_items`
2. Insert `outbox(event_id, type, payload, created_at)`

Relay process:
- Poll outbox / listen
- Publish to queue
- Mark published

Prevents “DB wrote but webhook never queued.”

---

## 3) Per-tenant fairness algorithm

- Each subscription has `in_flight` counter in Redis  
- Worker only pulls if `in_flight < cap`  
- Slow endpoint → fills its own cap, others continue  
- Optional: move chronic offenders to isolation queue  

---

## 4) Canonical schema versioning

- `schema_version` on normalized documents  
- Writers emit v2 while readers still accept v1  
- Expand → migrate → contract  
- Never silently change field meaning  

---

## 5) Idempotent webhook receiver (customer side)

```python
def handle(event_id, payload):
    if redis.set(f"evt:{event_id}", "1", nx=True, ex=86400):
        queue.publish(payload)
    return 200
```

Always 200 after accept; duplicate event_id ignored.

---

## 6) Connect token security

- Store only hash of SDK token  
- Bind to user_id + developer_id + products  
- Short TTL  
- One-time or rotating refresh policy if stolen  

---

## 7) When you’d pick Kafka vs Redis Streams vs Cloud Tasks

| Tool | Use |
|------|-----|
| Cloud Tasks / SQS | Delayed retries, per-job execution (sync jobs, webhook retries) |
| Pub/Sub / Kafka | High-throughput fanout of change events |
| Redis Streams | Lighter internal pipelines if already Redis-heavy |

Say: “I’d pick based on delay support, fanout, and ops familiarity — for Phyllo-like retries, task queues with ETA are convenient.”
