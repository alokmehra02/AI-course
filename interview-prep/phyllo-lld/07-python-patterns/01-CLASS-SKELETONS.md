# Python Class Skeletons (Board-Ready)

Copy patterns, don’t memorize every line.

---

## Enums & models

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

class Product(str, Enum):
    IDENTITY = "IDENTITY"
    ENGAGEMENT = "ENGAGEMENT"
    INCOME = "INCOME"

class AccountStatus(str, Enum):
    PENDING = "PENDING"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    SYNCING = "SYNCING"
    READY = "READY"
    REAUTH_REQUIRED = "REAUTH_REQUIRED"
    DISCONNECTED = "DISCONNECTED"
    FAILED = "FAILED"

class SyncStatus(str, Enum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    SYNCED = "SYNCED"
    FAILED = "FAILED"
    PARTIAL = "PARTIAL"

@dataclass
class Account:
    id: str
    user_id: str
    platform: str
    status: AccountStatus
    external_account_id: str | None

@dataclass
class ContentItem:
    id: str
    account_id: str
    platform_content_id: str
    published_at: datetime
    metrics: dict
    content_hash: str
```

---

## Platform adapter

```python
@dataclass
class OAuthTokens:
    access_token: str
    refresh_token: str | None
    expires_at: datetime

@dataclass
class FetchPage:
    items: list[dict]
    next_cursor: str | None

class PlatformConnector(ABC):
    @abstractmethod
    def exchange_code(self, code: str) -> OAuthTokens: ...

    @abstractmethod
    def refresh(self, tokens: OAuthTokens) -> OAuthTokens: ...

    @abstractmethod
    def fetch_profile(self, tokens: OAuthTokens) -> dict: ...

    @abstractmethod
    def fetch_content(self, tokens: OAuthTokens, cursor: str | None) -> FetchPage: ...

class InstagramConnector(PlatformConnector):
    ...
```

---

## Sync orchestrator

```python
class SyncOrchestrator:
    def __init__(self, connectors: dict[str, PlatformConnector], jobs, repo, queue):
        self.connectors = connectors
        self.jobs = jobs
        self.repo = repo
        self.queue = queue

    def enqueue_initial(self, account_id: str, products: list[Product]) -> None:
        for p in products:
            job_id = self.jobs.create(account_id, p)
            self.queue.publish("sync.fetch", {"job_id": job_id})

    def process_fetch_job(self, job_id: str) -> None:
        job = self.jobs.lease(job_id)
        account = self.repo.get_account(job.account_id)
        connector = self.connectors[account.platform]
        tokens = self.repo.get_tokens(account.id)
        # fetch → normalize → upsert → emit outbox event
```

---

## Webhook signing + retry

```python
import hmac, hashlib

def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

def verify(secret: str, body: bytes, header: str) -> bool:
    expected = sign(secret, body)
    return hmac.compare_digest(expected, header)

class RetryPolicy:
    DELAYS = [300, 3600, 21600]  # 5m, 60m, 360m

    def next_delay(self, retry_count: int) -> int | None:
        if retry_count >= len(self.DELAYS):
            return None
        return self.DELAYS[retry_count]
```

---

## Rate limiter sketch

```python
class RateLimiter:
    def allow(self, key: str, limit: int, window_sec: int) -> bool:
        # Redis INCR + EXPIRE, or token bucket Lua
        ...
```
