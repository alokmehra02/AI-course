# Walkthrough — Influencer Vetting (Public)

Website: screen creator history, audience authenticity, brand-safety risk before signing.

## 1-hour plan

- Design report flow  
- Code Facade + Strategy scorers  
- Cover empty content + REJECT/REVIEW/APPROVE  

## Clarify

- Public content for v1; consented extras optional later  
- Sync report in interview; async job in prod  
- Brand categories / blocked topics as input  

## Design

**Entities:** VettingRequest, ContentItem, SafetyFlag, VettingReport  

**API:**

```text
POST /v1/vetting/reports
GET  /v1/vetting/reports/{id}
```

**Flow:** load profile/contents -> authenticity Strategy -> safety Strategy -> recommend -> save  

**Patterns:**

- Facade: VettingService  
- Strategy: AuthenticityScorer, BrandSafetyScanner  
- Template Method (optional): load -> analyze -> recommend -> save  

## Code to write

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
    severity: str
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
    def score(self, followers: int, avg_likes: float, engagement_rate: float) -> float:
        if followers <= 0:
            return 0.0
        expected = avg_likes / followers
        gap = abs(expected - engagement_rate)
        raw = 1.0 - min(gap * 10, 1.0)
        if engagement_rate > 0.25 and followers > 50_000:
            raw *= 0.7
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

    def _recommend(self, auth: float, flags: list[SafetyFlag]) -> str:
        if any(f.severity == "high" for f in flags):
            return "REJECT"
        if auth < 0.5 or flags:
            return "REVIEW"
        return "APPROVE"
```

## Say this

> "VettingService is a Facade. Scorer and scanner are Strategies I can replace with ML later."

## Follow-ups

- Async: return PENDING, worker fills READY  
- Evidence links for each flag  
- Consented audience metrics as later Strategy input  
