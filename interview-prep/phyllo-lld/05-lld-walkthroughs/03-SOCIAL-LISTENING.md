# Interview Script — Social Listening (Public)

**Website:** Brand/keyword mentions across platforms with sentiment and share of voice.  
**Round:** ~60 min LLD + Python  
**Patterns:** Strategy · Observer · Repository

---

## PART 0 — Opening (say)

> “I’ll design Phyllo Social Listening: ingest mentions for a keyword watch, dedupe, classify sentiment with a Strategy, compute share of voice, and notify alert Observers. Then I’ll code the ingest and SoV path.”

**Restate:**

> “A brand creates a watch on keywords/competitors. We collect matching public posts/comments, label sentiment, aggregate share of voice, and alert on negative spikes. OK?”

---

## PART 1 — Clarifiers (ask)

> “1. Real-time stream or micro-batch every few minutes?  
> 2. Platforms in v1?  
> 3. Sentiment: simple rules OK for interview?  
> 4. Alerts on negative only or threshold rules?  
> 5. Dedup key — platform + post_id?”

**Assume:**

> “Micro-batch OK, multi-platform mentions already normalized into Mention input, keyword sentiment Strategy, Observer alerts on negative, dedupe by (platform, post_id).”

---

## PART 2 — Requirements (say)

> “Functional: create watch, ingest mention, dedupe, classify, list mentions, share of voice, alert subscribers.  
> Non-functional: pluggable classifier, no double-count duplicates, multi-tenant watches.”

---

## PART 3 — Design + patterns (say)

> “**Strategy:** SentimentStrategy — KeywordSentiment today, model later.  
> **Observer:** AlertObserver list — Slack/email/webhook without editing ingest.  
> **Repository:** mention store (in-memory now).”

Diagram:
```text
MentionIngest → Deduper → SentimentStrategy → MentionRepo
                                ↓
                         AlertObservers (Observer)
ShareOfVoice ← aggregate by brand for watch_id
```

**Entities:** `Watch`, `Mention`, `Alert`  
**API:**
```text
POST /v1/watches
POST /v1/watches/{id}/mentions      # or internal ingest
GET  /v1/watches/{id}/mentions
GET  /v1/watches/{id}/share-of-voice?brands=
```

**Flow:**
1. Ingest mention  
2. If seen (platform, post_id) → skip  
3. Classify sentiment  
4. Store  
5. Notify observers  
6. SoV = brand_count / total for watch  

---

## PART 4 — Transition to code (say)

> “I’ll code Mention, SentimentStrategy, Observer, ListeningService.ingest and share_of_voice.”

---

## PART 5 — CODE

```python
from __future__ import annotations
from abc import ABC, abstractmethod
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


class NegativeAlerter(AlertObserver):
    def __init__(self):
        self.alerts: list[Mention] = []

    def on_mention(self, mention: Mention) -> None:
        if mention.sentiment == "negative":
            self.alerts.append(mention)


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

    def list_mentions(self, watch_id: str) -> list[Mention]:
        return [m for m in self._mentions if m.watch_id == watch_id]

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


if __name__ == "__main__":
    alerter = NegativeAlerter()
    svc = ListeningService(KeywordSentiment())
    svc.subscribe(alerter)
    m1 = Mention("instagram", "p1", "w1", "I love BrandA", "BrandA", "", datetime.utcnow())
    m2 = Mention("instagram", "p2", "w1", "BrandB is the worst", "BrandB", "", datetime.utcnow())
    m2_dup = Mention("instagram", "p2", "w1", "BrandB is the worst", "BrandB", "", datetime.utcnow())
    assert svc.ingest(m1) is True
    assert svc.ingest(m2) is True
    assert svc.ingest(m2_dup) is False
    sov = svc.share_of_voice("w1", ["BrandA", "BrandB"])
    assert sov["BrandA"] == 0.5
    assert len(alerter.alerts) == 1
```

### Say while coding

> “Dedupe before classify so we don’t double-count SoV.”  
> “Sentiment is Strategy.”  
> “Observers get notified after store — loose coupling for alerts.”  
> “SoV is brand share within the watch’s matched mentions.”

---

## PART 6 — Edge cases (say)

> “Duplicate post → ingest returns False.  
> Empty watch → SoV all zeros.  
> Multilingual → later Strategy.  
> Stream vs batch: same service; ingestion source changes.  
> Alert noise: threshold Observer (e.g. 5 negatives / 10 min).”

---

## PART 7 — Follow-ups

| Q | Say |
|---|-----|
| Listening vs monitoring? | Monitoring = item-level respond; listening = aggregate SoV/sentiment/trends |
| Why Observer? | Add webhook alerter without editing ingest |
| Scale? | Partition by watch_id; queue ingest workers |

---

## PART 8 — Close (say)

> “Designed Social Listening with Strategy sentiment, Observer alerts, and deduped mention storage, plus share-of-voice aggregation. Coded ingest + SoV + negative alerter.”

---

## Timebox

| Min | Do |
|-----|-----|
| 0–8 | Clarify |
| 8–20 | Design |
| 20–50 | Code |
| 50–60 | Edges + close |
