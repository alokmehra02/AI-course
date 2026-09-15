# Phyllo LLD + Code Interview — Single Study File (1 Hour)

**For:** Aalok | **Language:** Python | **Source:** [getphyllo.com](https://www.getphyllo.com/) products  
**Round length:** ~60 minutes = design + working Python for the core logic

HR: use case from website/products. Expect **design first, then code** (classes + key methods). Not leetcode puzzles.

---

## 0. 1-hour timebox (follow this exactly)

| Min | What you do | Output |
|-----|-------------|--------|
| 0–2 | Restate problem + confirm LLD+code in Python | Alignment |
| 2–8 | Clarifying Qs + assumptions + scope v1 | Requirements list |
| 8–20 | Entities, APIs, schema, flow + **name 2–3 design patterns** | Design |
| 20–25 | Confirm: “I’ll code X using Strategy/Adapter/…” | Scope lock |
| 25–50 | Write Python showing those patterns (see §6 + §6B) | Code |
| 50–55 | Walk code + edge cases + why that pattern | Dry run |
| 55–60 | Summary + their questions | Close |

**Rule:** Design lean so you have **25–30 min for code**. Name patterns while designing — don’t wait until the end.

**What they usually want coded (pick one when you offer):**
1. Core service + Strategy/scorer plugs  
2. Platform **Adapter** + normalize  
3. Ranking / aggregation with Strategy  
4. Repo interface + in-memory impl (**Repository**)  

Say at minute 20:
> “Design is enough for v1. I’ll code the core path in Python using Adapter for platforms and Strategy for scoring — models + service, skip FastAPI boilerplate unless you want it.”
---

## 1. What Phyllo is (45 seconds)

> “Phyllo gives apps public and consented social data across 25+ platforms through one API. Public: search, profile analytics, content, social listening — no login. Consented: verified income, real audience, private performance — creator connects. Customers build influencer marketing, creator tools, KYC, screening, fintech on it.”

| Public | Consented |
|--------|-----------|
| Creator Search | Verified income |
| Profile Analytics | Audience truth |
| Content | Private performance |
| Social Listening | Publish / in-app analytics |

---

## 2. Website products → LLD asks (prepare these)

### Top 5 (code-ready in this file)

1. Creator Search  
2. Influencer Vetting  
3. Social Listening  
4. Verified Income  
5. Social KYC  

Also possible: Campaign measurement, Social screening, Profile analytics, Competitor intel, Publish.

| Website product | LLD prompt |
|-----------------|------------|
| Creator search | Search creators by niche, location, audience, growth |
| Influencer vetting | Screen history, authenticity, brand safety → report |
| Social listening | Mentions + sentiment + share of voice |
| Campaign intelligence | Measure reach/engagement across campaign creators |
| Profile analytics | Audience + engagement + content for a handle |
| Social screening | Applicant footprint risk + optional monitoring |
| Social KYC | Prove account ownership + case report |
| Verified income | Aggregate consented earnings by stream |
| Competitor intelligence | Rival content cadence, SoV, overlap |
| Cross-platform publish | Post to all connected accounts |

---

## 3. What to say

### Opening
> “I’ll clarify scope, design entities/APIs/flow with the key design patterns, then implement the core logic in Python.”

### Clarifiers (ask ~5)
1. Phyllo API product vs app on Phyllo?  
2. Public, consented, or both?  
3. Platforms in v1?  
4. Scale ballpark?  
5. Sync response vs async job + poll?  
6. For code: in-memory OK, or sketch against repo interfaces?

### Assumptions
> “Python 3, clear classes, in-memory store for the interview, Postgres/Redis in real system, eventual consistency for analytics, multi-tenant customer_id on records.”

### Closing
> “Designed the product with Adapter for platforms, Strategy for scoring, and Repository for storage. Coded the core path with those patterns, plus consent/dedupe edge cases. In production the same interfaces swap to Postgres and async workers.”

### Pattern one-liner (say during design, ~min 12)
> “I’ll use **Adapter** so Instagram/YouTube map into one schema, **Strategy** so ranking/authenticity/sentiment are swappable, and **Repository** so the service doesn’t care if storage is memory or Postgres.”

---

## 4. Design template (8–20 min only)

1. Restate  
2. Actors  
3. Requirements (F + NF)  
4. Entities  
5. 3–5 APIs  
6. Tables (short)  
7. Sequence (happy path)  
8. **Patterns:** name 2–3 + where they sit in the diagram  
9. “Coding next: ____ (will show Pattern X in code)”

---

## 4B. Design patterns for Phyllo LLD (must know)

Don’t dump 20 patterns. Use **2–3 per problem** and show them in code.

### Pattern cheat map (product → patterns)

| Phyllo product | Patterns to name | Why |
|----------------|------------------|-----|
| Creator Search | **Strategy** (ranking), **Repository** | Swap rankers; hide index/DB |
| Influencer Vetting | **Strategy** (scorers), **Facade** (VettingService), **Template Method** (report pipeline) | Pluggable checks; one entry API |
| Social Listening | **Strategy** (classifier), **Observer** (alerts), Repository | Swap sentiment; notify on rule hit |
| Profile / Content / Income sync | **Adapter** / **Gateway**, **Factory**, Repository | Each platform looks different |
| Verified Income | **Adapter** (txn normalize), Facade (IncomeService) | One summary API over many sources |
| Social KYC | **State**, Facade | Case OPEN→VERIFIED/FAILED |
| Cross-platform Publish | **Adapter**, **Facade**, optional **Command** | One publish call → many platforms |
| Screening / monitoring | Strategy (risk rules), Observer (alerts) | Pluggable policies + notifications |
| All multi-tenant APIs | **Repository** + DI (constructor inject) | Testable; swap infra |

### The 8 patterns — what / when / say / code shape

#### 1) Adapter (a.k.a. Wrapper) — #1 for Phyllo
**What:** Convert Instagram/YouTube/TikTok payloads → canonical `Profile` / `Content` / `IncomeTransaction`.  
**When:** Any multi-platform product.  
**Say:** “New platform = new adapter; domain service stays unchanged.”

```python
from abc import ABC, abstractmethod

class PlatformAdapter(ABC):
    @abstractmethod
    def fetch_profile(self, handle: str) -> dict: ...
    @abstractmethod
    def to_canonical_profile(self, raw: dict) -> "Profile": ...

class InstagramAdapter(PlatformAdapter):
    def fetch_profile(self, handle: str) -> dict:
        return {"username": handle, "follower_count": 120_000}  # fake API

    def to_canonical_profile(self, raw: dict) -> "Profile":
        return Profile(
            platform="instagram",
            handle=raw["username"],
            followers=raw["follower_count"],
        )

class YouTubeAdapter(PlatformAdapter):
    def fetch_profile(self, handle: str) -> dict:
        return {"snippet": {"title": handle}, "statistics": {"subscriberCount": "500000"}}

    def to_canonical_profile(self, raw: dict) -> "Profile":
        return Profile(
            platform="youtube",
            handle=raw["snippet"]["title"],
            followers=int(raw["statistics"]["subscriberCount"]),
        )
```

#### 2) Strategy — #1 for scoring / ranking / sentiment / risk
**What:** Family of algorithms behind one interface; pick at runtime.  
**When:** Search ranking, authenticity, brand safety, sentiment, risk rules.  
**Say:** “Ranking is a Strategy — I can ship RelevanceRanker today and MLRanker later without touching SearchService.”

```python
class RankingStrategy(ABC):
    @abstractmethod
    def score(self, creator: "Creator", filters: "SearchFilters") -> float: ...

class EngagementFirstRanker(RankingStrategy):
    def score(self, creator, filters) -> float:
        return creator.engagement_rate * 100 + creator.growth_30d * 50

class BalancedRanker(RankingStrategy):
    def score(self, creator, filters) -> float:
        niche = 1.0 if set(filters.niches) & set(creator.niches) else 0.0
        return 0.4 * niche + 0.3 * creator.engagement_rate + 0.3 * creator.authenticity_score

class CreatorSearchService:
    def __init__(self, repo: "CreatorRepository", ranker: RankingStrategy):
        self.repo = repo
        self.ranker = ranker  # injected Strategy
```

#### 3) Repository
**What:** Persistence interface; service talks to repo, not dict/SQL.  
**When:** Always in LLD+code.  
**Say:** “In-memory repo for interview; same interface → Postgres in prod.”

```python
class CreatorRepository(ABC):
    @abstractmethod
    def list_all(self) -> list["Creator"]: ...
    @abstractmethod
    def upsert(self, creator: "Creator") -> None: ...

class InMemoryCreatorRepository(CreatorRepository):
    def __init__(self):
        self._items: dict[str, Creator] = {}

    def list_all(self) -> list[Creator]:
        return list(self._items.values())

    def upsert(self, creator: Creator) -> None:
        self._items[creator.id] = creator
```

#### 4) Factory
**What:** Central place to create the right adapter/strategy from a key.  
**When:** `platform == "instagram"` → `InstagramAdapter`.  
**Say:** “Factory keeps if/else out of the service.”

```python
class PlatformAdapterFactory:
    _registry = {
        "instagram": InstagramAdapter,
        "youtube": YouTubeAdapter,
    }

    @classmethod
    def create(cls, platform: str) -> PlatformAdapter:
        try:
            return cls._registry[platform]()
        except KeyError:
            raise ValueError(f"unsupported platform: {platform}")
```

#### 5) Facade
**What:** One simple API over several subsystems (fetch + score + scan + save).  
**When:** VettingService, IncomeService, PublishService, KycService.  
**Say:** “VettingService is a Facade — callers don’t wire scorers themselves.”

#### 6) Template Method
**What:** Fixed pipeline steps; subclasses/hooks customize one step.  
**When:** Vetting/screening report pipeline: load → analyze → recommend → save.  
**Say:** “Report flow is fixed; analysis step is pluggable.”

```python
class ReportPipeline(ABC):
    def run(self, request) -> "VettingReport":
        data = self.load(request)          # fixed order
        analysis = self.analyze(data)      # hook
        report = self.recommend(analysis)  # fixed
        return self.save(report)

    @abstractmethod
    def analyze(self, data): ...
```

#### 7) State
**What:** Behavior depends on case/report status transitions.  
**When:** KYC case, vetting report PENDING→READY, screening monitoring.  
**Say:** “Invalid transitions are rejected — OPEN can go VERIFIED, not the reverse without a new case.”

```python
ALLOWED = {
    CaseStatus.OPEN: {CaseStatus.VERIFIED, CaseStatus.FAILED, CaseStatus.NEEDS_REVIEW},
    CaseStatus.NEEDS_REVIEW: {CaseStatus.VERIFIED, CaseStatus.FAILED},
}
```

#### 8) Observer (lightweight)
**What:** On event (new mention / new risk flag), notify subscribers (alerts, webhooks).  
**When:** Listening alerts, continuous monitoring.  
**Say:** “Watchers subscribe; ingest publishes events — loose coupling.”

```python
class AlertObserver(ABC):
    @abstractmethod
    def on_mention(self, mention: "Mention") -> None: ...

class ListeningService:
    def __init__(self):
        self._observers: list[AlertObserver] = []

    def subscribe(self, obs: AlertObserver) -> None:
        self._observers.append(obs)

    def ingest(self, mention: "Mention") -> None:
        # ... store ...
        for obs in self._observers:
            obs.on_mention(mention)
```

### Patterns to mention only if asked
- **Singleton** — avoid unless config; say “prefer DI”  
- **Decorator** — caching/rate-limit wrapper around adapter  
- **Command** — enqueue `PublishCommand` / `ScreenCommand`  
- **Builder** — complex search filter / report construction  

### How many patterns in 1 hour?
- Design phase: name **2 or 3**  
- Code phase: implement **at least 1 interface** (Strategy or Adapter) + Repository  
- Closing: repeat the 2–3 names  

---

## 5. Short product designs (don’t overbuild)

### 5.1 Creator Search
- Ingest → normalize → index  
- `POST /v1/creator-search` with filters + cursor  
- Rank: niche match + engagement + growth  
- **Patterns:** Strategy (ranker), Repository  
- **Code:** filter + Strategy.score + top N  

### 5.2 Influencer Vetting
- Resolve profile → contents → authenticity + safety → `VettingReport`  
- `POST /v1/vetting/reports` → maybe async `report_id`  
- **Patterns:** Facade (VettingService), Strategy (scorer/scanner), Template Method (pipeline)  
- **Code:** `create_report()` + scorers  

### 5.3 Social Listening
- Watch keywords → ingest mentions → dedupe → sentiment → SoV  
- **Patterns:** Strategy (classifier), Observer (alerts), Repository  
- **Code:** `ingest_mention()` + `share_of_voice()`  

### 5.4 Verified Income
- Consent → sync txns → upsert → monthly summary by category  
- **Patterns:** Adapter (platform txns), Facade (IncomeService), Repository  
- **Code:** `summarize_income()`  

### 5.5 Social KYC
- Claim handles → connect/prove → match → report  
- **Patterns:** State (case status), Facade (KycService)  
- **Code:** `verify_case()` status transition  

### 5.6 Campaign metrics
- Campaign + creators + posts → aggregate reach/engagement  
- **Patterns:** Facade, Repository  
- **Code:** `campaign_metrics()`  

### 5.7 Profile analytics
- `GET profile/contents` — cache optional  
- **Patterns:** Adapter + Factory (per platform), optional Decorator (Redis cache)  
- **Code:** normalize platform payload → `Profile`  

### 5.8 Screening
- Pull public activity → risk flags → report; monitor = reschedule  
- **Patterns:** Strategy (risk rules), Observer (alerts)  
- **Code:** `scan_contents_for_risk()`  

### 5.9 Publish
- **Patterns:** Adapter per platform, Facade `PublishService`, Factory to resolve adapters  

---

## 6. CODE BANK — practice writing these by hand

In the interview you’ll write **one** of these fully. Practice all five once.

Style rules they like:
- Type hints  
- Dataclasses  
- **Show patterns in code** (ABC/Protocol for Strategy or Adapter + Repository)  
- Pure logic first (no Flask/FastAPI noise unless asked)  
- Explicit edge cases (empty list, missing consent, duplicates)  
- Small `InMemoryRepo` is fine  

**While coding, say the pattern name once:**
> “RankingStrategy is Strategy pattern — SearchService depends on the interface, not a concrete ranker.”

---

### CODE A — Creator Search with Strategy + Repository

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Creator:
    id: str
    platform: str
    handle: str
    niches: list[str]
    country: str
    followers: int
    engagement_rate: float
    growth_30d: float
    authenticity_score: float = 0.8


@dataclass
class SearchFilters:
    platforms: list[str] = field(default_factory=list)
    niches: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    min_followers: int = 0
    max_followers: int = 10**12
    min_engagement: float = 0.0
    min_growth: float = 0.0


@dataclass
class SearchResult:
    creator: Creator
    score: float


# --- Repository pattern ---
class CreatorRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[Creator]: ...


class InMemoryCreatorRepository(CreatorRepository):
    def __init__(self, creators: list[Creator]):
        self._creators = creators

    def list_all(self) -> list[Creator]:
        return list(self._creators)


# --- Strategy pattern ---
class RankingStrategy(ABC):
    @abstractmethod
    def score(self, creator: Creator, filters: SearchFilters) -> float: ...


class BalancedRanker(RankingStrategy):
    def score(self, creator: Creator, filters: SearchFilters) -> float:
        niche_bonus = 0.0
        if filters.niches:
            overlap = len(set(filters.niches) & set(creator.niches))
            niche_bonus = overlap / len(filters.niches)
        return (
            0.40 * niche_bonus
            + 0.25 * min(creator.engagement_rate / 0.10, 1.0)
            + 0.20 * min(max(creator.growth_30d, 0.0) / 0.20, 1.0)
            + 0.15 * creator.authenticity_score
        )


class EngagementFirstRanker(RankingStrategy):
    def score(self, creator: Creator, filters: SearchFilters) -> float:
        return creator.engagement_rate * 100 + creator.growth_30d * 50


class CreatorSearchService:
    """Facade over repo + ranker."""

    def __init__(self, repo: CreatorRepository, ranker: RankingStrategy):
        self.repo = repo
        self.ranker = ranker

    def search(self, filters: SearchFilters, limit: int = 20) -> list[SearchResult]:
        matched: list[SearchResult] = []
        for c in self.repo.list_all():
            if not self._matches(c, filters):
                continue
            matched.append(SearchResult(c, self.ranker.score(c, filters)))
        matched.sort(key=lambda r: r.score, reverse=True)
        return matched[:limit]

    def _matches(self, c: Creator, f: SearchFilters) -> bool:
        if f.platforms and c.platform not in f.platforms:
            return False
        if f.countries and c.country not in f.countries:
            return False
        if c.followers < f.min_followers or c.followers > f.max_followers:
            return False
        if c.engagement_rate < f.min_engagement or c.growth_30d < f.min_growth:
            return False
        if f.niches and not set(f.niches).intersection(c.niches):
            return False
        return True


if __name__ == "__main__":
    data = [
        Creator("1", "instagram", "maya", ["beauty"], "US", 120_000, 0.047, 0.08, 0.91),
        Creator("2", "instagram", "joe", ["fitness"], "US", 500_000, 0.01, 0.02, 0.4),
    ]
    svc = CreatorSearchService(InMemoryCreatorRepository(data), BalancedRanker())
    results = svc.search(SearchFilters(niches=["beauty"], countries=["US"], min_followers=10_000))
    assert results[0].creator.handle == "maya"
```

**Narrate:** Strategy = swap `BalancedRanker` / `EngagementFirstRanker`. Repository = swap memory / OpenSearch later. Service is a thin Facade.

---

### CODE A2 — Adapter + Factory (profile normalize — use with analytics/income)

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Profile:
    platform: str
    handle: str
    followers: int


class PlatformAdapter(ABC):
    @abstractmethod
    def to_canonical(self, raw: dict) -> Profile: ...


class InstagramAdapter(PlatformAdapter):
    def to_canonical(self, raw: dict) -> Profile:
        return Profile("instagram", raw["username"], int(raw["follower_count"]))


class YouTubeAdapter(PlatformAdapter):
    def to_canonical(self, raw: dict) -> Profile:
        return Profile(
            "youtube",
            raw["snippet"]["title"],
            int(raw["statistics"]["subscriberCount"]),
        )


class PlatformAdapterFactory:
    _map = {"instagram": InstagramAdapter, "youtube": YouTubeAdapter}

    @classmethod
    def create(cls, platform: str) -> PlatformAdapter:
        if platform not in cls._map:
            raise ValueError(f"unsupported: {platform}")
        return cls._map[platform]()


def normalize_profile(platform: str, raw: dict) -> Profile:
    return PlatformAdapterFactory.create(platform).to_canonical(raw)
```

**Narrate:** Adapter isolates platform JSON quirks; Factory picks adapter — core product code never branches on platform strings everywhere.

---

### CODE B — Influencer Vetting (Facade + Strategy)

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
    # Strategy-like policy — say "BrandSafetyStrategy interface in fuller design"
    RISK_KEYWORDS = {
        "hate": "high",
        "scam": "high",
        "alcohol": "medium",
    }

    def scan(self, contents: list[ContentItem], blocked_categories: list[str]) -> list[SafetyFlag]:
        flags: list[SafetyFlag] = []
        blocked = set(blocked_categories)
        for item in contents:
            text = item.text.lower()
            for word, severity in self.RISK_KEYWORDS.items():
                if word in text and (word in blocked or not blocked):
                    flags.append(SafetyFlag(word, severity, item.id))
        return flags


class AuthenticityScorer:
    """Strategy: authenticity algorithm (swap heuristic vs ML later)."""

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
    """Facade: one entry point over fetch inputs + strategies + report persistence."""

    def __init__(self, scanner: BrandSafetyScanner, scorer: AuthenticityScorer):
        self.scanner = scanner  # Strategy
        self.scorer = scorer    # Strategy
        self._reports: dict[str, VettingReport] = {}

    def create_report(
        self,
        handle: str,
        platform: str,
        followers: int,
        contents: list[ContentItem],
        blocked_categories: Optional[list[str]] = None,
    ) -> VettingReport:
        report_id = str(uuid.uuid4())
        report = VettingReport(report_id, handle, platform, ReportStatus.PENDING)
        self._reports[report_id] = report

        if not contents:
            report.status = ReportStatus.FAILED
            report.recommendation = "NO_CONTENT"
            return report

        total_interactions = sum(c.likes + c.comments for c in contents)
        avg_likes = sum(c.likes for c in contents) / len(contents)
        views = sum(c.views for c in contents) or 1
        engagement_rate = total_interactions / views

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
        if auth < 0.5:
            return "REVIEW"
        if flags:
            return "REVIEW"
        return "APPROVE"
```

**Narrate:** Facade = `VettingService`. Strategy = scorer + scanner injected. Template Method if you extract `load → analyze → recommend → save`.

---

### CODE C — Social Listening (Strategy classifier + optional Observer)

```python
from __future__ import annotations
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Mention:
    platform: str
    post_id: str
    watch_id: str
    text: str
    brand: str
    sentiment: str  # positive|neutral|negative
    created_at: datetime


class ListeningService:
    def __init__(self):
        self._seen: set[tuple[str, str]] = set()  # (platform, post_id)
        self._mentions: list[Mention] = []

    def ingest(self, mention: Mention) -> bool:
        """Return True if stored, False if duplicate."""
        key = (mention.platform, mention.post_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        mention.sentiment = self.classify(mention.text)
        self._mentions.append(mention)
        return True

    def classify(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ("love", "great", "awesome")):
            return "positive"
        if any(w in t for w in ("hate", "scam", "worst")):
            return "negative"
        return "neutral"

    def share_of_voice(self, watch_id: str, brands: list[str]) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        total = 0
        for m in self._mentions:
            if m.watch_id != watch_id:
                continue
            if m.brand not in brands:
                continue
            counts[m.brand] += 1
            total += 1
        if total == 0:
            return {b: 0.0 for b in brands}
        return {b: round(counts[b] / total, 4) for b in brands}
```

---

### CODE D — Verified Income aggregation

```python
from __future__ import annotations
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


class IncomeService:
    def __init__(self):
        self._txns: dict[tuple[str, str], IncomeTransaction] = {}
        # key: (account_id, platform_txn_id)
        self._consent: set[str] = set()  # account_ids with INCOME consent

    def grant_consent(self, account_id: str) -> None:
        self._consent.add(account_id)

    def add_transaction(self, txn: IncomeTransaction) -> None:
        if txn.account_id not in self._consent:
            raise PermissionError("income consent required")
        key = (txn.account_id, txn.platform_txn_id)
        self._txns[key] = txn  # idempotent upsert

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
        return IncomeSummary(
            user_id=user_id,
            start=start,
            end=end,
            total_usd=round(total, 2),
            by_category=dict(by_cat),
            by_platform_account=dict(by_acct),
        )
```

**Must say while coding:** consent gate + upsert by platform txn id + USD normalized field.

---

### CODE E — Social KYC verify (State + Facade)

```python
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CaseStatus(str, Enum):
    OPEN = "OPEN"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"


# State pattern (lightweight): allowed transitions
ALLOWED_TRANSITIONS = {
    CaseStatus.OPEN: {CaseStatus.VERIFIED, CaseStatus.FAILED, CaseStatus.NEEDS_REVIEW},
    CaseStatus.NEEDS_REVIEW: {CaseStatus.VERIFIED, CaseStatus.FAILED},
    CaseStatus.VERIFIED: set(),
    CaseStatus.FAILED: set(),
}


@dataclass
class ClaimedAccount:
    platform: str
    handle: str


@dataclass
class ConnectedAccount:
    platform: str
    handle: str
    external_account_id: str
    connected_at: datetime


@dataclass
class VerificationCase:
    id: str
    applicant_id: str
    claims: list[ClaimedAccount] = field(default_factory=list)
    proofs: list[ConnectedAccount] = field(default_factory=list)
    status: CaseStatus = CaseStatus.OPEN
    verified_at: Optional[datetime] = None
    notes: str = ""


class KycService:
    def __init__(self):
        self._cases: dict[str, VerificationCase] = {}

    def create_case(self, case_id: str, applicant_id: str, claims: list[ClaimedAccount]) -> VerificationCase:
        case = VerificationCase(case_id, applicant_id, claims=claims)
        self._cases[case_id] = case
        return case

    def attach_proof(self, case_id: str, proof: ConnectedAccount) -> VerificationCase:
        case = self._cases[case_id]
        case.proofs.append(proof)
        return self.evaluate(case_id)

    def evaluate(self, case_id: str) -> VerificationCase:
        case = self._cases[case_id]
        if not case.claims:
            return self._transition(case, CaseStatus.FAILED, "no claims")

        proof_keys = {(p.platform, p.handle.lower()) for p in case.proofs}
        matched = sum(
            1 for claim in case.claims
            if (claim.platform, claim.handle.lower()) in proof_keys
        )

        if matched == len(case.claims):
            case.verified_at = datetime.utcnow()
            return self._transition(case, CaseStatus.VERIFIED, "all claimed accounts connected")
        if matched == 0:
            return self._transition(case, CaseStatus.FAILED, "no overlapping ownership proof")
        return self._transition(case, CaseStatus.NEEDS_REVIEW, f"partial match {matched}/{len(case.claims)}")

    def _transition(self, case: VerificationCase, new_status: CaseStatus, notes: str) -> VerificationCase:
        allowed = ALLOWED_TRANSITIONS.get(case.status, set())
        if new_status != case.status and new_status not in allowed:
            raise ValueError(f"illegal transition {case.status} → {new_status}")
        case.status = new_status
        case.notes = notes
        return case
```

**Narrate:** Facade = `KycService`. State = explicit allowed transitions so you don’t silently jump FAILED → VERIFIED.

---

## 7. If they ask for API handlers too (keep tiny)

```python
# optional — only if they insist on HTTP layer
from fastapi import FastAPI, HTTPException
app = FastAPI()
search_service = CreatorSearchService([])  # injected

@app.post("/v1/creator-search")
def creator_search(body: dict):
    filters = SearchFilters(
        platforms=body.get("filters", {}).get("platforms", []),
        niches=body.get("filters", {}).get("niches", []),
        countries=body.get("filters", {}).get("location", []),
        min_followers=body.get("filters", {}).get("followers", {}).get("min", 0),
        max_followers=body.get("filters", {}).get("followers", {}).get("max", 10**12),
    )
    results = search_service.search(filters, limit=body.get("limit", 20))
    return {
        "items": [
            {"handle": r.creator.handle, "score": r.score, "followers": r.creator.followers}
            for r in results
        ]
    }
```

Prefer business logic over framework unless they ask.

---

## 8. Coding follow-ups (expect these while you type)

| They ask | You do / say |
|----------|----------------|
| “Handle duplicates” | Show set/dict upsert key |
| “What if empty content?” | Return FAILED / empty summary safely |
| “Consent revoked” | Raise / skip consented paths |
| “This is O(N) for search” | “Interview store is linear; prod = OpenSearch behind same Repository” |
| “Make scorer extensible” | Point at **Strategy** interface |
| “Add Instagram + TikTok” | **Adapter** + **Factory** — no service rewrite |
| “Why not if/else on platform?” | “That becomes unmaintainable; Adapter localizes platform churn” |
| “Add tests” | 2–3 asserts for happy + edge |
| “Thread safety?” | “In-memory demo isn’t; prod uses DB unique constraints + row locks” |

---

## 8B. Pattern follow-ups (they often ask these)

| Q | A |
|---|---|
| Why Strategy over if/else for ranking? | Open/closed — new ranker without editing SearchService |
| Adapter vs Facade? | Adapter = translate one platform API → our model. Facade = simplify many steps into one service API |
| Where is Factory? | `PlatformAdapterFactory.create("instagram")` |
| Repository vs just using a list? | Service depends on interface; swap memory/Postgres/OpenSearch |
| Is VettingService a God class? | No — Facade that delegates to Strategy collaborators |
| State vs status enum? | Enum fields + allowed transitions; reject illegal moves |
| Observer vs calling alert() inline? | Observers let you add Slack/email/webhook without editing ingest |
| Over-engineering? | “Only 2–3 patterns that remove real branching — not patterns for show” |

---

## 9. Product follow-ups (design)

| Q | A |
|---|---|
| Public vs consented? | Search/listening/screening public; income/KYC/private metrics consented |
| One schema across platforms? | **Adapter** → canonical models |
| Fake followers? | Authenticity **Strategy** + REVIEW path |
| Campaign ROI? | Delivered reach/engagement, not follower count |
| KYC proof? | Connected account via official login; **State** on case |

---

## 10. Pick-from-website line

> “I’ll design **Influencer Vetting** with Facade + Strategy scorers, then code `VettingService.create_report` in Python.”

Backups: **Creator Search** (Strategy + Repository — cleanest) · **Verified Income** (Adapter + Facade) · **Social Listening**.

---

## 11. Night-before drill (90 min)

- [ ] Rehearse 1-hour timebox once  
- [ ] Memorize pattern map in §4B (product → 2–3 patterns)  
- [ ] Hand-write **Creator Search** with Strategy + Repository  
- [ ] Hand-write **Adapter + Factory** normalize once  
- [ ] Hand-write **Vetting create_report** (Facade + Strategy)  
- [ ] Practice 30-sec answer: Adapter vs Facade vs Strategy  
- [ ] One full mock: 20 min design (incl. patterns) + 25 min code  

---

## 12. Day-of card

**60 min = 20 design (incl. patterns) + 30 code + 10 wrap**

**Always name 2–3:** Adapter · Strategy · Repository (add Facade/State/Observer when they fit)

**Code offer:** ABC interface + service + in-memory repo  

**Top code picks:** Search · Vetting · Income · Listening · KYC  

**Line to say:** “New platform = new Adapter; new ranker = new Strategy; storage behind Repository.”

**Prod disclaimer (once):** “In-memory for interview; same interfaces → Postgres/OpenSearch + async workers.”