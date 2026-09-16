# Interview Script — Phyllo Reliable Webhook Delivery (HLD → LLD + Code)

**Source:** Phyllo eng design — “How We Made It Reliable and Fault-Tolerant” (webhook system)  
**Why it can be asked:** They published this architecture; HR said products/website, but eng blogs are fair game — especially “design our webhook delivery.”  
**Round:** ~60 min LLD + Python  
**Patterns:** Queue / delayed retry · Strategy (RetryPolicy) · Facade (WebhookDispatcher) · Repository (optional delivery log)

Blog: https://www.getphyllo.com/post/building-a-distributed-webhook-system

---

## PART 0 — Opening (say)

> “I’ll design a reliable webhook delivery system like Phyllo’s: publish events to developers’ HTTPS endpoints, treat 5xx and timeouts as failures, retry with staged backoff using TTL delay queues that dead-letter back to MAIN, and after retries are exhausted route to an ALERT queue. I’ll implement the consumer decision logic and retry routing in Python.”

**Restate from their diagram:**

> “Restating the HLD: PUBLISH → MAIN QUEUE → consumer SEND WEBHOOK. On failure, increment `x-retry`, if retry ≤ 3 publish to RETRY QUEUE 1/2/3 with TTL 5 min / 60 min / 6 hours; when TTL expires, DLQ returns the message to MAIN. If retries exceeded → ALERT QUEUE for email/alerts. Success → END. OK if I LLD that and code the consumer + routing?”

---

## PART 1 — Clarifiers (ask)

> “1. At-least-once delivery OK?  
> 2. Failure = 5xx **or** timeout beyond N seconds — same as your blog?  
> 3. Payload = event ids (light) vs full objects?  
> 4. HMAC signature required?  
> 5. Per-tenant concurrency limits?  
> 6. In-memory simulation of queues OK for interview (real system = RabbitMQ/ActiveMQ)?”

**Assume if shrug:**

> “At-least-once, failure = non-2xx or timeout, light JSON payload, HMAC, in-memory queues simulating TTL/DLQ, Python.”

Board:
```text
Assumptions:
- At-least-once + idempotent event_id on customer side
- Fail: timeout OR status >= 500 (also treat 429 as retryable)
- Retries: 3 delay stages then ALERT
- TTL: 5m → 60m → 6h then back to MAIN via DLQ
```

---

## PART 2 — Requirements (say)

> “Functional: enqueue webhook, deliver HTTP POST, retry with backoff, alert on exhaustion, sign payload.  
> Non-functional: don’t block forever on slow customers, durable retries, observable retry count, multi-tenant fairness (mention).”

---

## PART 3 — Draw their HLD (say while drawing)

```text
                    PUBLISH WEBHOOK
                          |
                          v
              +------------------------+
              |   RabbitMQ Exchange    |
              |  MAIN QUEUE <----------+-- DLQ from retry queues
              |  RETRY1 TTL=5m  DLQ=MAIN
              |  RETRY2 TTL=60m DLQ=MAIN
              |  RETRY3 TTL=6h  DLQ=MAIN
              |  ALERT QUEUE           |
              +------------------------+
                          |
                     consume MAIN
                          v
                   SEND WEBHOOK
                     /       \
                 success     fail
                   |           |
                  END     retry++ ; set header x-retry
                               |
                        retry <= 3 ?
                        /          \
                      yes           no
                       |             |
                 publish to      ALERT QUEUE
                 RETRY1/2/3      (email/alerts)
                 by retry count
```

> “The clever part is: retry queues **don’t** call HTTP. They only **delay**. TTL expiry + dead-letter **re-injects into MAIN**, so one consumer path always does SEND WEBHOOK.”

---

## PART 4 — Patterns (say)

> “**RetryPolicy Strategy** — maps retry count → which delay queue / TTL.  
> **Facade** — WebhookDispatcher / consumer loop.  
> **Queue + DLQ** — infrastructure pattern for delayed retry (RabbitMQ TTL + DLX).  
> Optional **Repository** — persist delivery attempts for audit.  
> Optional **Circuit breaker** later per tenant URL.”

---

## PART 5 — Classes

| Class | Role |
|-------|------|
| `WebhookMessage` | payload + headers including `x-retry` |
| `HttpWebhookClient` | POST with timeout; returns success/fail |
| `SignatureService` | HMAC-SHA256 |
| `RetryPolicy` | retry→queue name + TTL seconds |
| `QueueBroker` | MAIN / RETRY1/2/3 / ALERT; simulate TTL release to MAIN |
| `WebhookConsumer` | take MAIN → send → route on failure |

---

## PART 6 — Transition to code (say)

> “I won’t stand up real RabbitMQ. I’ll simulate MAIN, three delay queues, ALERT, and a `tick()` that moves expired retry messages back to MAIN — same control flow as your HLD. Then code SEND → success/fail → retry routing.”

---

## PART 7 — CODE

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
import hashlib
import hmac
import json
import time
import uuid


# ---------- Models ----------

class QueueName(str, Enum):
    MAIN = "MAIN"
    RETRY_1 = "RETRY_1"
    RETRY_2 = "RETRY_2"
    RETRY_3 = "RETRY_3"
    ALERT = "ALERT"


@dataclass
class WebhookMessage:
    event_id: str
    event_type: str
    url: str
    body: dict
    secret: str
    x_retry: int = 0  # header x-retry
    available_at: datetime = field(default_factory=datetime.utcnow)

    def to_bytes(self) -> bytes:
        return json.dumps(self.body, sort_keys=True).encode()


@dataclass
class SendResult:
    ok: bool
    status_code: Optional[int] = None
    error: Optional[str] = None


# ---------- Signature ----------

class SignatureService:
    def sign(self, secret: str, body: bytes) -> str:
        return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


# ---------- HTTP client (stub for interview) ----------

class HttpWebhookClient:
    """In interview: stub behaviors. In prod: real HTTPS with timeout."""

    def __init__(self, timeout_sec: float = 5.0):
        self.timeout_sec = timeout_sec
        # test hooks
        self.fail_urls: set[str] = set()

    def send(self, msg: WebhookMessage, signature: str) -> SendResult:
        # Simulate timeout / 5xx for configured URLs
        if msg.url in self.fail_urls:
            return SendResult(False, status_code=500, error="upstream_5xx")
        # Success path
        return SendResult(True, status_code=200)


# ---------- Retry policy (Strategy) — matches Phyllo diagram ----------

class RetryPolicy:
    """
    After failure, x-retry becomes 1,2,3 → delay queues.
    TTLs: 5 min, 60 min, 6 hours (diagram: 5 mins / 60 mins / 6 hours).
    If x-retry would exceed 3 → ALERT.
    """

    TTL_SEC = {
        1: 5 * 60,
        2: 60 * 60,
        3: 6 * 60 * 60,
    }
    QUEUE_FOR_RETRY = {
        1: QueueName.RETRY_1,
        2: QueueName.RETRY_2,
        3: QueueName.RETRY_3,
    }
    MAX_RETRY = 3

    def next_queue(self, new_retry_count: int) -> QueueName:
        if new_retry_count > self.MAX_RETRY:
            return QueueName.ALERT
        return self.QUEUE_FOR_RETRY[new_retry_count]

    def ttl_for(self, new_retry_count: int) -> Optional[int]:
        return self.TTL_SEC.get(new_retry_count)


# ---------- Broker simulation (TTL + DLQ back to MAIN) ----------

@dataclass
class QueuedItem:
    msg: WebhookMessage
    release_at: datetime  # when delay expires → MAIN


class InMemoryBroker:
    """
    Simulates:
      RETRY queues hold messages until TTL
      dead-letter → MAIN
    """

    def __init__(self):
        self.main: list[WebhookMessage] = []
        self.retry: dict[QueueName, list[QueuedItem]] = {
            QueueName.RETRY_1: [],
            QueueName.RETRY_2: [],
            QueueName.RETRY_3: [],
        }
        self.alert: list[WebhookMessage] = []

    def publish_main(self, msg: WebhookMessage) -> None:
        msg.available_at = datetime.utcnow()
        self.main.append(msg)

    def publish_retry(self, msg: WebhookMessage, queue: QueueName, ttl_sec: int, now: Optional[datetime] = None) -> None:
        now = now or datetime.utcnow()
        self.retry[queue].append(QueuedItem(msg, now + timedelta(seconds=ttl_sec)))

    def publish_alert(self, msg: WebhookMessage) -> None:
        self.alert.append(msg)

    def tick(self, now: Optional[datetime] = None) -> int:
        """Move expired retry messages back to MAIN (DLQ behavior)."""
        now = now or datetime.utcnow()
        moved = 0
        for q in (QueueName.RETRY_1, QueueName.RETRY_2, QueueName.RETRY_3):
            remain: list[QueuedItem] = []
            for item in self.retry[q]:
                if item.release_at <= now:
                    self.main.append(item.msg)
                    moved += 1
                else:
                    remain.append(item)
            self.retry[q] = remain
        return moved

    def consume_main(self) -> Optional[WebhookMessage]:
        if not self.main:
            return None
        return self.main.pop(0)


# ---------- Consumer (core of the HLD flowchart) ----------

class WebhookConsumer:
    def __init__(
        self,
        broker: InMemoryBroker,
        client: HttpWebhookClient,
        signer: SignatureService,
        policy: RetryPolicy,
    ):
        self.broker = broker
        self.client = client
        self.signer = signer
        self.policy = policy
        self.attempts: list[dict] = []  # audit log for interview

    def process_one(self) -> bool:
        """
        Pull from MAIN → SEND WEBHOOK → success END / fail route.
        Returns False if MAIN empty.
        """
        msg = self.broker.consume_main()
        if msg is None:
            return False

        body = msg.to_bytes()
        signature = self.signer.sign(msg.secret, body)
        result = self.client.send(msg, signature)

        self.attempts.append(
            {
                "event_id": msg.event_id,
                "x_retry": msg.x_retry,
                "ok": result.ok,
                "status": result.status_code,
            }
        )

        if result.ok:
            return True  # END

        # FAILURE: 5xx or timeout (client encoded as ok=False)
        msg.x_retry += 1  # RETRY COUNT ++ ; header x-retry
        queue = self.policy.next_queue(msg.x_retry)

        if queue == QueueName.ALERT:
            self.broker.publish_alert(msg)
        else:
            ttl = self.policy.ttl_for(msg.x_retry)
            assert ttl is not None
            self.broker.publish_retry(msg, queue, ttl)
        return True


# ---------- Publisher API (entry) ----------

class WebhookPublisher:
    def __init__(self, broker: InMemoryBroker):
        self.broker = broker

    def publish(self, url: str, secret: str, event_type: str, body: dict) -> str:
        event_id = str(uuid.uuid4())
        msg = WebhookMessage(
            event_id=event_id,
            event_type=event_type,
            url=url,
            body={**body, "event_id": event_id, "event_type": event_type},
            secret=secret,
            x_retry=0,
        )
        self.broker.publish_main(msg)
        return event_id


# ---------- Demo matching the diagram ----------

if __name__ == "__main__":
    broker = InMemoryBroker()
    client = HttpWebhookClient(timeout_sec=5)
    consumer = WebhookConsumer(broker, client, SignatureService(), RetryPolicy())
    publisher = WebhookPublisher(broker)

    # Happy path
    eid_ok = publisher.publish(
        "https://good.example/hooks",
        "sec",
        "CONTENTS.UPDATED",
        {"account_id": "acc_1", "items": ["c1"]},
    )
    assert consumer.process_one() is True
    assert broker.main == [] and broker.alert == []

    # Failure path → RETRY_1 (x-retry becomes 1, TTL 5m)
    client.fail_urls.add("https://bad.example/hooks")
    eid_bad = publisher.publish(
        "https://bad.example/hooks",
        "sec",
        "ACCOUNTS.CONNECTED",
        {"account_id": "acc_2"},
    )
    assert consumer.process_one() is True
    assert len(broker.retry[QueueName.RETRY_1]) == 1
    assert broker.retry[QueueName.RETRY_1][0].msg.x_retry == 1

    # Simulate TTL expiry → DLQ to MAIN
    future = datetime.utcnow() + timedelta(minutes=6)
    assert broker.tick(now=future) == 1
    assert len(broker.main) == 1

    # Fail again → RETRY_2 (x-retry == 2)
    assert consumer.process_one() is True
    assert len(broker.retry[QueueName.RETRY_2]) == 1
    assert broker.retry[QueueName.RETRY_2][0].msg.x_retry == 2

    # Fail through retry 3 then ALERT
    broker.tick(now=datetime.utcnow() + timedelta(hours=2))
    consumer.process_one()  # → RETRY_3 (x-retry=3)
    assert len(broker.retry[QueueName.RETRY_3]) == 1
    broker.tick(now=datetime.utcnow() + timedelta(hours=7))
    consumer.process_one()  # → ALERT (x-retry=4 > 3)
    assert len(broker.alert) == 1
    assert broker.alert[0].event_id == eid_bad
    print("ok", eid_ok, "alerted", eid_bad)
```

### Say while coding

> “MAIN is the only place that sends HTTP.”  
> “On fail: x-retry++, route to RETRY1/2/3 or ALERT — same as the flowchart.”  
> “Retry queues only delay; tick() is TTL+DLQ back to MAIN.”  
> “HMAC signature header would be X-Phyllo-Signature in production.”

---

## PART 8 — Logic explained (say if they dig into the HLD)

### What counts as failure?

> “Per Phyllo: developer endpoint returns **5xx**, or takes **longer than allowed seconds**. In code, `SendResult.ok=False` covers both. I’d also retry **429** with Retry-After if asked.”

### Why not sleep() inside the consumer?

> “Sleeping ties up workers. TTL delay queues free consumers. That’s why RETRY queues exist.”

### Retry count vs attempts

```text
First MAIN attempt:     x-retry = 0
Fail → publish RETRY1:  x-retry = 1  (delay 5m)  → back MAIN
Fail → publish RETRY2:  x-retry = 2  (delay 60m) → back MAIN
Fail → publish RETRY3:  x-retry = 3  (delay 6h)  → back MAIN
Fail → ALERT:           x-retry = 4  (> 3)
```

> “So you get **4 send attempts** max (1 initial + 3 delayed), then alert. Matches RETRY COUNT <= 3 publish retry, else ALERT.”

### TTL + Dead Letter → MAIN

> “Retry queue has **no consumers that POST**. Message sits until TTL. Broker dead-letters to MAIN. Consumer always uses one code path: send webhook.”

### Why staged 5m / 60m / 6h?

> “Exponential-ish backoff covering short blips, deploy windows, and longer outages — Phyllo’s blog says this covers ~99% of developer endpoint failures before alerting.”

### Success path

> “2xx within timeout → END. Don’t increment retry. Optionally ack/delete message (in RabbitMQ terms).”

### Security (always mention)

> “Sign body with HMAC-SHA256 and send `X-Phyllo-Signature`. Publish source IPs for allowlists. TLS 1.2+.”

### Customer side (product literacy)

> “Customer should verify signature, return 200 quickly, process async. Slow handlers cause **your** timeout → our retry — bad for both.”

### At-least-once

> “Retries mean duplicates possible. Customers dedupe on `event_id`.”

---

## PART 9 — Edge cases (say)

> “Poison URL always 500 → eventually ALERT, don’t block MAIN forever (per-tenant concurrency caps).  
> Partial network errors → retry.  
> 4xx (except 429) → often don’t retry (bad URL / auth) — call out as policy choice.  
> Replay from ALERT after customer fixes endpoint.  
> Persist attempts table for support debugging.”

---

## PART 10 — Follow-ups

| Q | Say |
|---|-----|
| Why MAIN + delay queues instead of one delayed retry field? | Separates delay from send; classic RabbitMQ TTL/DLX pattern; scales consumers on MAIN only |
| Exactly-once? | No — at-least-once + idempotent event_id |
| Fairness? | Cap in-flight per destination URL/subscription |
| ActiveMQ vs RabbitMQ? | Same idea — Phyllo blog used ActiveMQ TTL/DLQ; diagram shows RabbitMQ |
| Where does publish come from? | Sync/outbox when profile/content updates — IDs in payload |
| How do you test TTL in interview? | `tick(now=future)` to simulate expiry |

---

## PART 11 — Close (say)

> “I implemented Phyllo’s reliable webhook HLD: MAIN consumer sends HTTP; failures bump `x-retry` and route to TTL delay queues 5m/60m/6h that dead-letter back to MAIN; after retries exceed three, ALERT for email. HMAC signs payloads; delivery is at-least-once. The in-memory broker mirrors RabbitMQ TTL+DLQ so the control flow matches your diagram.”

---

## Timebox

| Min | Do |
|-----|-----|
| 0–8 | Clarify + restate HLD |
| 8–20 | Redraw diagram + patterns + failure definition |
| 20–48 | Code broker + consumer + retry policy + demo |
| 48–60 | Logic explained + follow-ups + close |

---

## Cheat card

**Fail** = 5xx or timeout  
**Path** = MAIN → send → fail → x-retry++ → RETRY1/2/3 or ALERT  
**Delay** = 5m / 60m / 6h then DLQ → MAIN  
**Say** = “Retry queues delay only; MAIN always sends.”  
**Code order** = Message → RetryPolicy → Broker(tick) → Consumer.process_one → demo fail/TTL/alert  
