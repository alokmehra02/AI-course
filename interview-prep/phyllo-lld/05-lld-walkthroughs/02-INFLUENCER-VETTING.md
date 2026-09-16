# Interview Script — Influencer Vetting (Public)

**Website:** Screen creator history, audience authenticity, brand-safety risk before a brand signs.  
**Round:** ~60 min LLD + Python  
**Patterns:** Facade · Strategy · (optional Template Method)

---

## PART 0 — Opening (say)

> “I’ll design Phyllo’s Influencer Vetting report API: pull public profile/content signals, run authenticity and brand-safety checks as Strategies, and return APPROVE / REVIEW / REJECT. Then I’ll code VettingService in Python.”

**Restate:**

> “Before contract, a brand wants a report: engagement quality, authenticity score, safety flags with evidence, and a recommendation. Public data for v1; consented metrics can plug in later. OK?”

---

## PART 1 — Clarifiers (ask)

> “1. Phyllo vetting product or customer app?  
> 2. Public only for v1, or also consented audience?  
> 3. Sync report in interview vs async job in prod?  
> 4. Which blocked categories matter — hate, scam, alcohol, etc.?  
> 5. How much content history — last N posts?”

**Assume:**

> “Phyllo API, public v1, compute inline for interview / async in prod, last N contents provided as input, heuristic scorers.”

---

## PART 2 — Requirements (say)

> “Functional: create report by handle/platform, score authenticity, scan brand safety, recommend, fetch report by id.  
> Non-functional: pluggable scorers, explainable flags with evidence content ids, multi-tenant developer_id if needed.”

---

## PART 3 — Design + patterns (say)

> “**Facade:** VettingService is one entry — callers don’t wire scorers.  
> **Strategy:** AuthenticityScorer and BrandSafetyScanner are replaceable (heuristic today, ML tomorrow).  
> Optional **Template Method:** load → analyze → recommend → save.”

Diagram:
```text
POST /vetting/reports
        ↓
  VettingService (Facade)
     ├─ AuthenticityScorer (Strategy)
     ├─ BrandSafetyScanner (Strategy)
     └─ ReportStore
```

**Entities:** `ContentItem`, `SafetyFlag`, `VettingReport`  
**API:**
```text
POST /v1/vetting/reports
GET  /v1/vetting/reports/{id}
```

**Flow:**
1. Create report PENDING  
2. If no content → FAILED / NO_CONTENT  
3. Compute engagement rate  
4. Strategy authenticity score  
5. Strategy safety scan → flags  
6. Recommend APPROVE/REVIEW/REJECT  
7. Mark READY  

---

## PART 4 — Transition to code (say)

> “I’ll code models, BrandSafetyScanner, AuthenticityScorer, and VettingService.create_report with recommendation logic.”

---

## PART 5 — CODE

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class ReportStatus(str, Enum):
    PENDING = "PENDING"
    READY = "READY"
    FAILED = "FAILED"


@dataclass
class ContentItem:
    id: str
    text: str
    likes: int
    comments: int
    views: int


@dataclass
class SafetyFlag:
    code: str
    severity: str  # low|medium|high
    evidence_content_id: str


@dataclass
class VettingReport:
    id: str
    handle: str
    platform: str
    status: ReportStatus
    authenticity_score: float = 0.0
    safety_flags: list[SafetyFlag] = field(default_factory=list)
    engagement_rate: float = 0.0
    recommendation: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


class BrandSafetyScanner:
    """Strategy-like policy pack."""
    RISK_KEYWORDS = {"hate": "high", "scam": "high", "alcohol": "medium"}

    def scan(self, contents: list[ContentItem], blocked: list[str]) -> list[SafetyFlag]:
        flags: list[SafetyFlag] = []
        blocked_set = set(blocked)
        for item in contents:
            text = item.text.lower()
            for word, severity in self.RISK_KEYWORDS.items():
                if word in text and (not blocked_set or word in blocked_set):
                    flags.append(SafetyFlag(word, severity, item.id))
        return flags


class AuthenticityScorer:
    """Strategy: heuristic now, ML later."""

    def score(self, followers: int, avg_likes: float, engagement_rate: float) -> float:
        if followers <= 0:
            return 0.0
        expected = avg_likes / followers
        gap = abs(expected - engagement_rate)
        raw = 1.0 - min(gap * 10, 1.0)
        if engagement_rate > 0.25 and followers > 50_000:
            raw *= 0.7  # suspiciously high
        return round(max(0.0, min(raw, 1.0)), 3)


class VettingService:
    def __init__(self, scanner: BrandSafetyScanner, scorer: AuthenticityScorer):
        self.scanner = scanner
        self.scorer = scorer
        self._reports: dict[str, VettingReport] = {}

    def create_report(
        self,
        handle: str,
        platform: str,
        followers: int,
        contents: list[ContentItem],
        blocked_categories: Optional[list[str]] = None,
    ) -> VettingReport:
        report = VettingReport(str(uuid.uuid4()), handle, platform, ReportStatus.PENDING)
        self._reports[report.id] = report

        if not contents:
            report.status = ReportStatus.FAILED
            report.recommendation = "NO_CONTENT"
            return report

        avg_likes = sum(c.likes for c in contents) / len(contents)
        interactions = sum(c.likes + c.comments for c in contents)
        views = sum(c.views for c in contents) or 1
        engagement_rate = interactions / views

        flags = self.scanner.scan(contents, blocked_categories or [])
        auth = self.scorer.score(followers, avg_likes, engagement_rate)

        report.authenticity_score = auth
        report.safety_flags = flags
        report.engagement_rate = round(engagement_rate, 4)
        report.status = ReportStatus.READY
        report.recommendation = self._recommend(auth, flags)
        return report

    def get_report(self, report_id: str) -> Optional[VettingReport]:
        return self._reports.get(report_id)

    def _recommend(self, auth: float, flags: list[SafetyFlag]) -> str:
        if any(f.severity == "high" for f in flags):
            return "REJECT"
        if auth < 0.5 or flags:
            return "REVIEW"
        return "APPROVE"


if __name__ == "__main__":
    svc = VettingService(BrandSafetyScanner(), AuthenticityScorer())
    contents = [
        ContentItem("c1", "Love this routine", 4000, 100, 80000),
        ContentItem("c2", "avoid this scam", 50, 20, 1000),
    ]
    r = svc.create_report("maya", "instagram", 120_000, contents, ["scam", "hate"])
    assert r.recommendation in {"REJECT", "REVIEW"}
    assert any(f.code == "scam" for f in r.safety_flags)
```

### Say while coding

> “VettingService is Facade.”  
> “Scorer and scanner are Strategies injected in constructor.”  
> “Every safety flag keeps evidence_content_id for explainability.”  
> “In prod this returns PENDING and a worker fills READY.”

---

## PART 5B — Logic explained (say this if they ask “how do scores / recommend work?”)

### End-to-end compute path

```text
contents empty? → FAILED / NO_CONTENT
else:
  engagement_rate = (sum likes+comments) / sum(views)
  authenticity     = AuthenticityScorer(...)
  safety_flags     = BrandSafetyScanner(...)
  recommendation   = rules on (auth, flags)
  status           = READY
```

### Engagement rate

```text
engagement_rate = total_interactions / total_views
total_interactions = Σ (likes + comments)
```
- Views `or 1` avoids divide-by-zero.  
- Interview simplification: we use views as the denominator; brands may prefer followers or impressions — say that out loud.

> “This is a rough quality signal for the content set we scanned — not a platform-official ER.”

### `BrandSafetyScanner.scan`

```text
for each post text (lowercased):
  for each risk keyword → severity:
    if keyword in text AND (no blocked filter OR keyword in blocked_categories):
      emit SafetyFlag(code, severity, evidence_content_id=post.id)
```

- **Keyword → severity map** is a stand-in for a policy pack / classifier.  
- `blocked_categories` lets a beauty brand care about `alcohol` while another brand might not pass that list.  
- If `blocked` is empty, we flag any matched risk keyword (demo behavior).  
- **evidence_content_id** makes the report explainable — “rejected because post c2 contained scam.”

> “In production this Strategy becomes an ML/moderation service; the Facade stays the same.”

### `AuthenticityScorer.score`

Goal: return **0..1** — higher = more believable audience/engagement.

```text
expected = avg_likes / followers
gap = |expected - engagement_rate|
raw = 1.0 - min(gap * 10, 1.0)
if engagement_rate > 0.25 and followers > 50_000: raw *= 0.7
return clamp(raw, 0..1)
```

**What this means in words:**

1. **expected** ≈ “if likes were spread across followers, what ER-like ratio do we see?”  
2. Compare to the **observed engagement_rate** from the content sample.  
3. Large **gap** → suspicious → score drops (`gap * 10` scales sensitivity; gap ≥ 0.1 → score floor path).  
4. Extra penalty: **very high ER (>25%) on a large account (>50k)** often looks inflated → multiply by 0.7.  
5. Clamp to `[0, 1]`.

> “This is a **heuristic Strategy**, not a paper-grade fake-follower model. I’m showing a pluggable authenticity signal brands can threshold on.”

**Worked intuition:**
- Healthy creator: likes/followers roughly consistent with content ER → small gap → score near 1.  
- Bought followers: high followers, weak likes → big gap → low score.  
- Engagement pods / weird spikes: high ER on big account → penalty.

### `_recommend` decision table

| Condition | Result | Why |
|-----------|--------|-----|
| Any flag with `severity == "high"` | **REJECT** | Hard brand-safety fail |
| `authenticity < 0.5` | **REVIEW** | Audience looks shaky — human check |
| Any flags (even medium) | **REVIEW** | Soft risk — don’t auto-approve |
| Else | **APPROVE** | Clear enough for v1 automation |

> “Reject is reserved for high-severity safety. Authenticity problems usually need human REVIEW, not silent reject — false positives hurt creator marketplace products.”

### Why Strategies instead of if/else in the service?

> “Beauty brand vs alcohol brand want different safety packs. ML authenticity replaces heuristic later. Constructor injection keeps VettingService stable.”

---

## PART 6 — Edge cases (say)

> “No content → FAILED.  
> High severity flag → REJECT.  
> Low authenticity alone → REVIEW.  
> Async: API returns report_id immediately; poll GET.  
> Consented audience later = extra Strategy input, same Facade.”

---

## PART 7 — Follow-ups

| Q | Say |
|---|-----|
| Fake followers? | Authenticity Strategy from engagement plausibility; not magic ML in interview |
| Facade vs God class? | Delegates to strategies; doesn’t own platform fetch details |
| Why not one function? | Can’t swap safety policy per brand category cleanly |

---

## PART 8 — Close (say)

> “Built Influencer Vetting as a Facade over authenticity and brand-safety Strategies, returning an explainable report with APPROVE/REVIEW/REJECT. Coded create_report end-to-end; production would run analyze async.”

---

## Timebox

| Min | Do |
|-----|-----|
| 0–8 | Clarify |
| 8–20 | Design + patterns |
| 20–50 | Code |
| 50–60 | Edges + close |
