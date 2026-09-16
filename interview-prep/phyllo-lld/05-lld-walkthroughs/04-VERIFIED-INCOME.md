# Interview Script — Verified Income (Consented)

**Website:** Ad revenue, sponsorships, subscriptions, affiliates in one verified statement.  
**Round:** ~60 min LLD + Python  
**Patterns:** Adapter · Factory · Facade · Repository

---

## PART 0 — Opening (say)

> “I’ll design Phyllo Verified Income: after a creator consents, we normalize platform earnings through Adapters into one transaction ledger and expose a monthly summary. Self-reported income is not verification. Then I’ll code consent, upsert, and summarize.”

**Restate:**

> “Creator connects accounts, we sync income transactions from YouTube/TikTok/etc., store canonical transactions, and return total USD plus breakdown by category and account. OK?”

---

## PART 1 — Clarifiers (ask)

> “1. Categories in v1 — ads, sponsorship, subs, affiliates?  
> 2. Multi-currency — store original + amount_usd?  
> 3. Summary on-read vs materialized monthly statements?  
> 4. Are platform tokens already available from Connect?  
> 5. In-memory OK for interview?”

**Assume:**

> “Four categories, amount_usd provided/normalized, on-read aggregate, Connect already done, Python in-memory.”

---

## PART 2 — Requirements (say)

> “Functional: grant income consent, ingest/normalize txns, idempotent upsert, summarize by date range.  
> Non-functional: consent enforced, platform schema isolated in Adapters, auditability later.”

---

## PART 3 — Design + patterns (say)

> “**Adapter:** each platform’s payout JSON → canonical IncomeTransaction.  
> **Factory:** pick adapter by platform.  
> **Facade:** IncomeService.  
> **Repository:** txn upsert by (account_id, platform_txn_id).”

Diagram:
```text
Connect (tokens+consent)
        ↓
Platform raw txns → TxnAdapter (IG/YT/...) → IncomeTransaction
        ↓
IncomeService.add_transaction (consent check + upsert)
        ↓
IncomeService.summarize(user, from, to)
```

**Must say:**

> “No consent → PermissionError. Verification means platform-sourced with consent, not follower-based estimates.”

**Entities:** `IncomeTransaction`, `IncomeSummary`  
**API:**
```text
POST /v1/accounts/{id}/income/consent
POST /internal/income/sync/{account_id}
GET  /v1/users/{id}/income/summary?from&to
GET  /v1/users/{id}/income/transactions?from&to
```

---

## PART 4 — Transition to code (say)

> “I’ll code canonical txn, YoutubeTxnAdapter, IncomeService with consent + summarize. Fetch can be stubbed.”

---

## PART 5 — CODE

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from enum import Enum


class IncomeCategory(str, Enum):
    AD_REVENUE = "AD_REVENUE"
    SPONSORSHIP = "SPONSORSHIP"
    SUBSCRIPTION = "SUBSCRIPTION"
    AFFILIATE = "AFFILIATE"


@dataclass
class IncomeTransaction:
    user_id: str
    account_id: str
    platform_txn_id: str
    category: IncomeCategory
    amount: float
    currency: str
    amount_usd: float
    occurred_on: date


@dataclass
class IncomeSummary:
    user_id: str
    start: date
    end: date
    total_usd: float
    by_category: dict[str, float]
    by_platform_account: dict[str, float]


class TxnAdapter(ABC):
    @abstractmethod
    def to_canonical(self, user_id: str, account_id: str, raw: dict) -> IncomeTransaction:
        ...


class YoutubeTxnAdapter(TxnAdapter):
    def to_canonical(self, user_id: str, account_id: str, raw: dict) -> IncomeTransaction:
        return IncomeTransaction(
            user_id=user_id,
            account_id=account_id,
            platform_txn_id=str(raw["id"]),
            category=IncomeCategory.AD_REVENUE,
            amount=float(raw["amount"]),
            currency=raw.get("currency", "USD"),
            amount_usd=float(raw["amount_usd"]),
            occurred_on=date.fromisoformat(raw["date"]),
        )


class TikTokTxnAdapter(TxnAdapter):
    def to_canonical(self, user_id: str, account_id: str, raw: dict) -> IncomeTransaction:
        return IncomeTransaction(
            user_id=user_id,
            account_id=account_id,
            platform_txn_id=str(raw["txn_id"]),
            category=IncomeCategory.SUBSCRIPTION,
            amount=float(raw["gross"]),
            currency=raw.get("ccy", "USD"),
            amount_usd=float(raw["gross_usd"]),
            occurred_on=date.fromisoformat(raw["occurred_on"]),
        )


class TxnAdapterFactory:
    _map = {"youtube": YoutubeTxnAdapter, "tiktok": TikTokTxnAdapter}

    @classmethod
    def create(cls, platform: str) -> TxnAdapter:
        if platform not in cls._map:
            raise ValueError(f"unsupported platform: {platform}")
        return cls._map[platform]()


class IncomeService:
    def __init__(self):
        self._txns: dict[tuple[str, str], IncomeTransaction] = {}
        self._consent: set[str] = set()

    def grant_consent(self, account_id: str) -> None:
        self._consent.add(account_id)

    def ingest_raw(self, user_id: str, account_id: str, platform: str, raw: dict) -> None:
        adapter = TxnAdapterFactory.create(platform)
        txn = adapter.to_canonical(user_id, account_id, raw)
        self.add_transaction(txn)

    def add_transaction(self, txn: IncomeTransaction) -> None:
        if txn.account_id not in self._consent:
            raise PermissionError("income consent required")
        self._txns[(txn.account_id, txn.platform_txn_id)] = txn  # idempotent

    def summarize(self, user_id: str, start: date, end: date) -> IncomeSummary:
        by_cat: dict[str, float] = defaultdict(float)
        by_acct: dict[str, float] = defaultdict(float)
        total = 0.0
        for txn in self._txns.values():
            if txn.user_id != user_id:
                continue
            if not (start <= txn.occurred_on <= end):
                continue
            total += txn.amount_usd
            by_cat[txn.category.value] += txn.amount_usd
            by_acct[txn.account_id] += txn.amount_usd
        return IncomeSummary(user_id, start, end, round(total, 2), dict(by_cat), dict(by_acct))


if __name__ == "__main__":
    svc = IncomeService()
    svc.grant_consent("acc_yt")
    svc.ingest_raw(
        "user_1",
        "acc_yt",
        "youtube",
        {"id": "t1", "amount": 100.0, "currency": "USD", "amount_usd": 100.0, "date": "2026-09-01"},
    )
    svc.ingest_raw(  # duplicate id → upsert
        "user_1",
        "acc_yt",
        "youtube",
        {"id": "t1", "amount": 100.0, "currency": "USD", "amount_usd": 100.0, "date": "2026-09-01"},
    )
    summary = svc.summarize("user_1", date(2026, 9, 1), date(2026, 9, 30))
    assert summary.total_usd == 100.0
    try:
        svc.add_transaction(
            IncomeTransaction("user_1", "acc_no", "x", IncomeCategory.AD_REVENUE, 1, "USD", 1, date(2026, 9, 2))
        )
        raise AssertionError("should need consent")
    except PermissionError:
        pass
```

### Say while coding

> “Adapter isolates YouTube vs TikTok field names.”  
> “Factory picks adapter — orchestrator stays clean.”  
> “Consent gate before write.”  
> “Upsert key account_id + platform_txn_id.”

---

## PART 5B — Logic explained (say this if they ask “how does verify / summarize work?”)

### Why Adapter on income?

YouTube raw might look like:
```json
{"id": "t1", "amount": 100, "amount_usd": 100, "date": "2026-09-01"}
```
TikTok might look like:
```json
{"txn_id": "t9", "gross": 40, "gross_usd": 40, "occurred_on": "2026-09-02"}
```

> “Same canonical `IncomeTransaction`, different field paths. Adapters absorb that. IncomeService never branches on platform strings for mapping.”

### Consent gate

```text
grant_consent(account_id) → add to allow-set
add_transaction / ingest_raw:
  if account_id not in allow-set → PermissionError
```

> “Verified income is **consented**. Without grant, we refuse writes. That’s the product difference vs estimating income from followers.”

### Idempotent upsert

```text
key = (account_id, platform_txn_id)
self._txns[key] = txn   # insert or overwrite
```

> “Sync jobs and webhooks retry. Same payout id twice must not double-count in summarize. Natural key = platform’s transaction id scoped to the connected account.”

### `ingest_raw` vs `add_transaction`

```text
ingest_raw(platform, raw)
  → Factory.create(platform)
  → adapter.to_canonical(...)
  → add_transaction(canonical)
```

> “Fetch/IO can live outside; mapping is pure; service enforces consent + storage.”

### `summarize` math

```text
for each stored txn:
  if txn.user_id != requested user: skip
  if occurred_on not in [start, end]: skip
  total_usd += amount_usd
  by_category[category] += amount_usd
  by_account[account_id] += amount_usd
```

**Example:**
- Sep 1: YouTube ads +$100  
- Sep 2: TikTok subs +$40 (after consent on that account)  
- Summary Sep 1–30 → `total_usd=140`, by_category `{AD_REVENUE:100, SUBSCRIPTION:40}`

> “We aggregate **amount_usd** so multi-currency doesn’t break totals. Original `amount`+`currency` stay on the txn for audit.”

### On-read vs materialized statements

> “This summarize is **on-read** — simple and always fresh when late txns arrive. If a user has millions of txns, I’d materialize monthly snapshots and invalidate on ingest.”

### What “verified” means (say clearly)

> “Verified ≠ predicted from follower count. Verified = platform-sourced ledger rows collected after explicit consent, normalized, and summed.”

---

## PART 6 — Edge cases (say)

> “Consent revoked → remove from set + stop sync + optionally purge.  
> Late txn → summarize on-read picks it up.  
> FX: store amount_usd from FX service at ingest.  
> Fintech audit: log who read summary.”

---

## PART 7 — Follow-ups

| Q | Say |
|---|-----|
| Why Adapter here? | Same as Phyllo core — platforms differ, API doesn’t |
| Materialize statements? | On-read until volume hurts; then monthly snapshot table |
| Sponsorship not in API? | Some streams may be manual/consented docs — call out as extension |

---

## PART 8 — Close (say)

> “Verified Income uses Adapter+Factory into a consented ledger and a Facade summarize API. Coded consent, idempotent upsert, and category breakdown — platform-sourced, not self-reported.”

---

## Timebox

| Min | Do |
|-----|-----|
| 0–8 | Clarify |
| 8–20 | Design |
| 20–50 | Code |
| 50–60 | Edges + close |
