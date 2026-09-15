# Walkthrough — Verified Income (Consented)

Website: ad revenue, sponsorships, subscriptions, affiliates in one verified statement.

## Clarify

- Consented accounts only  
- Store original currency + amount_usd  
- Idempotent upsert on (account_id, platform_txn_id)  

## Design

**Entities:** IncomeTransaction, IncomeSummary  

**API:**

```text
GET /v1/users/{id}/income/summary?from&to
GET /v1/users/{id}/income/transactions
```

**Flow:** consent -> Adapter normalizes platform txns -> upsert -> summarize  

**Patterns:**

- Adapter: platform txn -> canonical IncomeTransaction  
- Facade: IncomeService  
- Repository: txn store  
- Factory: pick adapter by platform  

## Code to write

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
            platform_txn_id=raw["id"],
            category=IncomeCategory.AD_REVENUE,
            amount=float(raw["amount"]),
            currency=raw.get("currency", "USD"),
            amount_usd=float(raw["amount_usd"]),
            occurred_on=date.fromisoformat(raw["date"]),
        )


class IncomeService:
    def __init__(self):
        self._txns: dict[tuple[str, str], IncomeTransaction] = {}
        self._consent: set[str] = set()

    def grant_consent(self, account_id: str) -> None:
        self._consent.add(account_id)

    def add_transaction(self, txn: IncomeTransaction) -> None:
        if txn.account_id not in self._consent:
            raise PermissionError("income consent required")
        self._txns[(txn.account_id, txn.platform_txn_id)] = txn

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
```

## Say this

> "Self-reported income is not verified. Consent gate + Adapter normalization + idempotent upsert."
