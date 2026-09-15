# Walkthrough — Creator Search (Public)

Website: find creators across 470M+ profiles by niche, audience, location, growth.

## 1-hour plan

- 0-20: design  
- 20-50: code Strategy + Repository  
- 50-60: edge cases + summary  

## Clarify

- Public data only? Yes for v1.  
- Filters in v1: platform, niche, country, followers, engagement, growth.  
- In-memory OK for interview; OpenSearch in prod.  

## Design

**Entities:** Creator, SearchFilters, SearchResult  

**API:**

```text
POST /v1/creator-search
```

**Flow:** filters -> match -> Strategy.score -> sort -> limit  

**Patterns:**

- Strategy: RankingStrategy  
- Repository: CreatorRepository  
- Facade: CreatorSearchService  

## Code to write

```python
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


class CreatorSearchService:
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
        if not (f.min_followers <= c.followers <= f.max_followers):
            return False
        if c.engagement_rate < f.min_engagement or c.growth_30d < f.min_growth:
            return False
        if f.niches and not set(f.niches).intersection(c.niches):
            return False
        return True
```

## Say this

> "Strategy lets me swap rankers. Repository hides OpenSearch vs memory. Linear scan is interview-only."

## Follow-ups

- Cursor pagination in prod (`search_after`)  
- Index freshness  
- New ranker without editing the service  
