# Walkthrough — Campaign Measurement + Social Screening

Two shorter website products. Use if interviewer picks these.

---

## A) Campaign intelligence

**Goal:** measure delivered reach/engagement across campaign creators (not follower count).

**Entities:** Campaign, CampaignCreator, TrackedPost, MetricsSnapshot  

**API:**

```text
POST /v1/campaigns
POST /v1/campaigns/{id}/creators
GET  /v1/campaigns/{id}/metrics
```

**Patterns:** Facade + Repository  

**Code sketch:**

```python
from dataclasses import dataclass


@dataclass
class TrackedPost:
    creator_id: str
    reach: int
    likes: int
    comments: int
    shares: int


class CampaignService:
    def metrics(self, posts: list[TrackedPost]) -> dict:
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
        return {
            "reach": total_reach,
            "engagement": total_eng,
            "per_creator": per_creator,
        }
```

**Say:** Consented data can add story reach/saves later; public metrics are the baseline.

---

## B) Social screening / continuous monitoring

**Goal:** flag adverse/risk content on an applicant footprint; optional re-scan.

**Entities:** ScreeningCase, RiskSignal, MonitoringSchedule  

**Patterns:** Strategy (risk rules) + Observer (alerts)  

**Code sketch:**

```python
from dataclasses import dataclass


@dataclass
class PublicPost:
    id: str
    text: str


@dataclass
class RiskSignal:
    code: str
    post_id: str
    severity: str


class RiskStrategy:
    RULES = {"violence": "high", "fraud": "high", "drugs": "medium"}

    def scan(self, posts: list[PublicPost]) -> list[RiskSignal]:
        out: list[RiskSignal] = []
        for p in posts:
            lower = p.text.lower()
            for word, severity in self.RULES.items():
                if word in lower:
                    out.append(RiskSignal(word, p.id, severity))
        return out
```

**Say:** One-time screen vs continuous monitoring = same scanner on a schedule + Observer alerts.
