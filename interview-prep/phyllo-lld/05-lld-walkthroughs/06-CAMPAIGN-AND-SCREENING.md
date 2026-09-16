# Interview Script — Campaign Measurement + Social Screening

Two shorter Phyllo website products. Same speak → design → code shape; slightly less depth.

---

# A) Campaign Intelligence / Measurement

**Website:** Measure delivered reach and engagement across campaign creators.  
**Patterns:** Facade · Repository  
**Public + optional consented** (story reach/saves later)

## Opening (say)

> “I’ll design campaign measurement: attach creators to a campaign, track posts in a window, aggregate delivered reach and engagement — not follower count as ROI. Code the metrics aggregator.”

## Clarifiers

> “Attribution by creator list + date window? Tracking codes? Consented private metrics in v1?”

**Assume:** creator list + posts already collected; public metrics; aggregate API.

## Design

```text
Campaign → CampaignCreator[] → TrackedPost[] → CampaignService.metrics()
API: POST /campaigns | POST /campaigns/{id}/creators | GET /campaigns/{id}/metrics
```

**Say:** “Phyllo’s point: follower count is not ROI; delivered reach/engagement is. Consented adds story reach/saves/demographics later.”

## CODE

```python
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class TrackedPost:
    creator_id: str
    reach: int
    likes: int
    comments: int
    shares: int


@dataclass
class Campaign:
    id: str
    name: str
    creator_ids: list[str] = field(default_factory=list)
    posts: list[TrackedPost] = field(default_factory=list)


class CampaignService:
    def __init__(self):
        self._campaigns: dict[str, Campaign] = {}

    def create(self, campaign_id: str, name: str) -> Campaign:
        c = Campaign(campaign_id, name)
        self._campaigns[campaign_id] = c
        return c

    def add_creator(self, campaign_id: str, creator_id: str) -> None:
        self._campaigns[campaign_id].creator_ids.append(creator_id)

    def add_post(self, campaign_id: str, post: TrackedPost) -> None:
        camp = self._campaigns[campaign_id]
        if camp.creator_ids and post.creator_id not in camp.creator_ids:
            raise ValueError("creator not in campaign")
        camp.posts.append(post)

    def metrics(self, campaign_id: str) -> dict:
        posts = self._campaigns[campaign_id].posts
        if not posts:
            return {"reach": 0, "engagement": 0, "per_creator": {}}
        per_creator: dict[str, dict] = {}
        total_reach = 0
        total_eng = 0
        for p in posts:
            eng = p.likes + p.comments + p.shares
            total_reach += p.reach
            total_eng += eng
            bucket = per_creator.setdefault(p.creator_id, {"reach": 0, "engagement": 0})
            bucket["reach"] += p.reach
            bucket["engagement"] += eng
        return {"reach": total_reach, "engagement": total_eng, "per_creator": per_creator}


if __name__ == "__main__":
    svc = CampaignService()
    svc.create("cmp1", "Launch")
    svc.add_creator("cmp1", "c1")
    svc.add_post("cmp1", TrackedPost("c1", 10000, 500, 40, 10))
    m = svc.metrics("cmp1")
    assert m["reach"] == 10000 and m["engagement"] == 550
```

## Close (say)

> “Campaign Facade aggregates delivered reach/engagement per creator; followers are not the metric.”

---

# B) Social Screening / Continuous Monitoring

**Website:** Applicant footprint risk, adverse content, optional re-screen alerts.  
**Patterns:** Strategy · Observer · Facade

## Opening (say)

> “I’ll design social screening: scan public posts with a RiskStrategy, produce signals, and optionally notify Observers on a monitoring schedule.”

## Clarifiers

> “One-time vs continuous? Severity policy pack? Who is alerted?”

**Assume:** one-time scan coded; monitoring = same scanner on schedule + Observer.

## Design

```text
ScreeningCase → fetch public posts → RiskStrategy.scan → RiskSignal[]
Continuous: scheduler → rescan → Observer.on_new_signals
API: POST /screening/cases | GET /screening/cases/{id} | POST /.../monitor
```

## CODE

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    READY = "READY"
    FAILED = "FAILED"


@dataclass
class PublicPost:
    id: str
    text: str


@dataclass
class RiskSignal:
    code: str
    post_id: str
    severity: str


@dataclass
class ScreeningCase:
    id: str
    applicant_id: str
    status: CaseStatus = CaseStatus.OPEN
    signals: list[RiskSignal] = field(default_factory=list)
    monitored: bool = False
    updated_at: datetime = field(default_factory=datetime.utcnow)


class RiskStrategy(ABC):
    @abstractmethod
    def scan(self, posts: list[PublicPost]) -> list[RiskSignal]:
        ...


class KeywordRiskStrategy(RiskStrategy):
    RULES = {"violence": "high", "fraud": "high", "drugs": "medium"}

    def scan(self, posts: list[PublicPost]) -> list[RiskSignal]:
        out: list[RiskSignal] = []
        for p in posts:
            lower = p.text.lower()
            for word, severity in self.RULES.items():
                if word in lower:
                    out.append(RiskSignal(word, p.id, severity))
        return out


class AlertObserver(ABC):
    @abstractmethod
    def on_new_signals(self, case_id: str, signals: list[RiskSignal]) -> None:
        ...


class MemoryAlerter(AlertObserver):
    def __init__(self):
        self.events: list[tuple[str, list[RiskSignal]]] = []

    def on_new_signals(self, case_id: str, signals: list[RiskSignal]) -> None:
        if signals:
            self.events.append((case_id, signals))


class ScreeningService:
    def __init__(self, risk: RiskStrategy):
        self.risk = risk
        self._cases: dict[str, ScreeningCase] = {}
        self._observers: list[AlertObserver] = []

    def subscribe(self, obs: AlertObserver) -> None:
        self._observers.append(obs)

    def create_case(self, case_id: str, applicant_id: str) -> ScreeningCase:
        case = ScreeningCase(case_id, applicant_id)
        self._cases[case_id] = case
        return case

    def run_scan(self, case_id: str, posts: list[PublicPost]) -> ScreeningCase:
        case = self._cases[case_id]
        if not posts:
            case.status = CaseStatus.FAILED
            return case
        new_signals = self.risk.scan(posts)
        # continuous: only alert on newly seen post_ids
        existing = {(s.code, s.post_id) for s in case.signals}
        fresh = [s for s in new_signals if (s.code, s.post_id) not in existing]
        case.signals.extend(fresh)
        case.status = CaseStatus.READY
        case.updated_at = datetime.utcnow()
        if case.monitored and fresh:
            for obs in self._observers:
                obs.on_new_signals(case_id, fresh)
        return case

    def enable_monitoring(self, case_id: str) -> None:
        self._cases[case_id].monitored = True


if __name__ == "__main__":
    alerter = MemoryAlerter()
    svc = ScreeningService(KeywordRiskStrategy())
    svc.subscribe(alerter)
    svc.create_case("s1", "a1")
    svc.enable_monitoring("s1")
    svc.run_scan("s1", [PublicPost("p1", "possible fraud scheme")])
    assert svc._cases["s1"].signals[0].code == "fraud"
    assert len(alerter.events) == 1
```

### Say while coding

> “Risk rules are Strategy.”  
> “Monitoring reuses scan; Observer only fires on fresh signals.”  
> “Empty posts → FAILED.”

## Close (say)

> “Screening is Strategy-based risk scan with optional Observer-driven continuous monitoring — same scanner, scheduled replay.”

---

## Timebox (either product)

| Min | Do |
|-----|-----|
| 0–8 | Clarify |
| 8–18 | Design |
| 18–45 | Code core |
| 45–60 | Edges + close |
