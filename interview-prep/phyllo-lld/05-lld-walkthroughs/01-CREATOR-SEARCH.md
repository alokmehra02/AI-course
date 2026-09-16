# Interview Script — Creator Search (Public)

**Website:** Find creators across 470M+ profiles by niche, audience, location, growth.  
**Round:** ~60 min LLD + Python  
**Patterns:** Strategy · Repository · Facade

Use as a speaking spine. Don’t recite robotically.

---

## PART 0 — Opening (say)

> “I’ll clarify the Phyllo Creator Search product, design entities and APIs, use Strategy for ranking and Repository for storage, then implement search in Python.”

**Restate:**

> “Restating: brands need to search a large creator index by filters like platform, niche, location, followers, engagement, and growth, and get a ranked list. Public data — no creator connect required. OK?”

---

## PART 1 — Clarifiers (ask)

> “1. Phyllo search API or an app on top of Phyllo?  
> 2. Filters in v1 — niche, country, followers, engagement, growth?  
> 3. Ranking factors you care about most?  
> 4. Cursor pagination OK?  
> 5. Index freshness — minutes/hours lag OK?  
> 6. In-memory for interview code, OpenSearch in prod?”

**Assume if shrug:**

> “Phyllo-internal search API, public profiles, filters as above, BalancedRanker v1, cursor later, eventual index freshness, Python + in-memory repo.”

Board:
```text
Assumptions: public search | IG/YT/TikTok docs | ranked top-N | in-memory now / OpenSearch later
```

---

## PART 2 — Requirements (say)

> “Functional: filter creators, score/rank, return top N with scores.  
> Non-functional: extensible ranker, fast filters at scale in prod, multi-tenant if needed, stable API.”

---

## PART 3 — Design + patterns (say)

> “I’ll keep ingestion out of deep scope and focus on query path. Profiles already canonical in the index.  
> Patterns: **Strategy** for RankingStrategy so I can swap EngagementFirst vs Balanced without touching the service; **Repository** so memory becomes OpenSearch later; **Facade** CreatorSearchService is the API entry.”

Diagram:
```text
Client → CreatorSearchService (Facade)
              ├─ CreatorRepository.list/search
              └─ RankingStrategy.score
                    ├─ BalancedRanker
                    └─ EngagementFirstRanker
```

**Entities:** `Creator`, `SearchFilters`, `SearchResult`  
**API:** `POST /v1/creator-search`  
**Flow:** validate filters → load/match candidates → Strategy.score → sort desc → limit → return

**Prod note (say once):**

> “Interview uses linear scan. Production: OpenSearch/Elasticsearch with same filter fields; Repository hides that.”

---

## PART 4 — Schema / index doc (board)

```text
creator_docs: id, platform, handle, niches[], country,
followers, engagement_rate, growth_30d, authenticity_score, indexed_at
```

---

## PART 5 — Transition to code (say)

> “I’ll code Creator, SearchFilters, RankingStrategy, BalancedRanker, InMemoryCreatorRepository, and CreatorSearchService.search.”

---

## PART 6 — CODE

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


class CreatorRepository(ABC):
    @abstractmethod
    def list_all(self) -> list[Creator]:
        ...


class InMemoryCreatorRepository(CreatorRepository):
    def __init__(self, creators: list[Creator]):
        self._creators = creators

    def list_all(self) -> list[Creator]:
        return list(self._creators)


class RankingStrategy(ABC):
    @abstractmethod
    def score(self, creator: Creator, filters: SearchFilters) -> float:
        ...


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
    def __init__(self, repo: CreatorRepository, ranker: RankingStrategy):
        self.repo = repo
        self.ranker = ranker

    def search(self, filters: SearchFilters, limit: int = 20) -> list[SearchResult]:
        if limit <= 0:
            return []
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
        if not (f.min_followers <= c.followers <= f.max_followers):
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
    out = svc.search(SearchFilters(niches=["beauty"], countries=["US"], min_followers=10_000))
    assert out[0].creator.handle == "maya"
```

### Say while coding

> “Repository first so storage is swappable.”  
> “RankingStrategy is Strategy — service depends on interface.”  
> “Filter then score — don’t score everyone if filters kill them.”  
> “Linear scan is interview-only; OpenSearch in production.”

---

## PART 7 — Edge cases (say)

> “Empty filters → still rank all (or require one filter).  
> No matches → empty list.  
> limit <= 0 → empty.  
> New ranker → inject EngagementFirstRanker, no service edit.  
> Cursor pagination in prod via search_after, not deep offset.”

---

## PART 8 — Follow-ups

| Q | Say |
|---|-----|
| Why Strategy? | Open/closed — new ranker without editing SearchService |
| 470M scale? | OpenSearch behind same Repository |
| Freshness? | Async indexer from profile pipeline; search is eventually consistent |
| Personalization? | Later Strategy that takes brand context |

---

## PART 9 — Close (say)

> “Designed Phyllo Creator Search with Facade service, Repository for index storage, and Strategy ranking. Coded filter + BalancedRanker + top-N. Production swaps in-memory for OpenSearch without changing the API.”

---

## Timebox

| Min | Do |
|-----|-----|
| 0–8 | Clarify + requirements |
| 8–20 | Patterns, entities, API, flow |
| 20–50 | Code |
| 50–60 | Edges + close |
