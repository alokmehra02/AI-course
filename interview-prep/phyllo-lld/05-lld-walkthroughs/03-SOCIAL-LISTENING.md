# Walkthrough — Social Listening (Public)

Website: mentions, sentiment, share of voice across 25+ platforms.

## Clarify

- Keyword/brand watches per customer  
- Near-real-time vs batch? Assume minutes OK  
- Dedup by (platform, post_id)  

## Design

**Entities:** Watch, Mention, Alert  

**API:**

```text
POST /v1/watches
GET  /v1/watches/{id}/mentions
GET  /v1/watches/{id}/share-of-voice
```

**Flow:** ingest -> dedupe -> classify sentiment -> store -> SoV aggregate -> alert observers  

**Patterns:**

- Strategy: sentiment classifier  
- Observer: alert subscribers  
- Repository: mention store  

## Code to write

```python
from __future__ import annotations
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Mention:
    platform: str
    post_id: str
    watch_id: str
    text: str
    brand: str
    sentiment: str
    created_at: datetime


class SentimentStrategy(ABC):
    @abstractmethod
    def label(self, text: str) -> str:
        ...


class KeywordSentiment(SentimentStrategy):
    def label(self, text: str) -> str:
        t = text.lower()
        if any(w in t for w in ("love", "great", "awesome")):
            return "positive"
        if any(w in t for w in ("hate", "scam", "worst")):
            return "negative"
        return "neutral"


class AlertObserver(ABC):
    @abstractmethod
    def on_mention(self, mention: Mention) -> None:
        ...


class PrintAlerter(AlertObserver):
    def on_mention(self, mention: Mention) -> None:
        if mention.sentiment == "negative":
            print(f"ALERT {mention.brand}: {mention.text[:80]}")


class ListeningService:
    def __init__(self, classifier: SentimentStrategy):
        self.classifier = classifier
        self._seen: set[tuple[str, str]] = set()
        self._mentions: list[Mention] = []
        self._observers: list[AlertObserver] = []

    def subscribe(self, obs: AlertObserver) -> None:
        self._observers.append(obs)

    def ingest(self, mention: Mention) -> bool:
        key = (mention.platform, mention.post_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        mention.sentiment = self.classifier.label(mention.text)
        self._mentions.append(mention)
        for obs in self._observers:
            obs.on_mention(mention)
        return True

    def share_of_voice(self, watch_id: str, brands: list[str]) -> dict[str, float]:
        counts: dict[str, int] = defaultdict(int)
        total = 0
        for m in self._mentions:
            if m.watch_id != watch_id or m.brand not in brands:
                continue
            counts[m.brand] += 1
            total += 1
        if total == 0:
            return {b: 0.0 for b in brands}
        return {b: round(counts[b] / total, 4) for b in brands}
```

## Say this

> "Classifier is Strategy. Alerts use Observer so I can add webhook/email without touching ingest."
