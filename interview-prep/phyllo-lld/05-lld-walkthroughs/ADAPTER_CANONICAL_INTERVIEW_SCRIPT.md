# Phyllo Interview Script — Multi-Platform Adapter → Canonical Data

**Use this as your speaking guide.** Read it out loud once tonight. In the interview, don’t recite word-for-word — use it as the spine of what you say.

**Round:** ~60 min LLD + Python code  
**Problem:** Absorb data from Instagram, YouTube, TikTok, etc. into **one canonical schema**  
**Core pattern:** **Adapter** (+ Factory, Repository, Strategy optional)

---

# PART 0 — First 2 minutes (exact words)

**You say:**

> “Thanks. I’ll treat this as a low-level design round in Python. I’ll clarify requirements, design the classes and APIs, call out the design patterns — especially Adapter for multi-platform normalization — then implement the core adapter flow in code. Does that work?”

**If they give a vague prompt like “design how Phyllo gets data from many platforms”:**

> “Restating: Phyllo needs to pull creator data — profiles, content, maybe income — from platforms like Instagram, YouTube, and TikTok, each with different APIs and JSON shapes, and expose **one normalized schema** to customers. I’ll design the ingestion and normalization layer with platform Adapters, then code the canonical mapping. I’ll keep Connect/OAuth as a boundary and focus on fetch → adapt → store. OK?”

---

# PART 1 — Clarifying questions (say these)

Ask 5–6, then stop.

> “A few clarifiers:
> 1. Are we designing Phyllo’s **internal normalization layer**, or a customer app using Phyllo?
> 2. For v1, which entities — **Profile only**, or Profile + Content, or Income too?
> 3. Which platforms in v1 — say Instagram, YouTube, TikTok?
> 4. Is data **public-only**, **consented**, or both? I’ll assume we already have access tokens where needed.
> 5. Can reads be **eventually consistent** after sync?
> 6. For code, is an **in-memory repository** OK, with Postgres implied in production?”

**If they shrug, lock assumptions:**

> “I’ll assume: Phyllo-internal service, v1 = Profile + Content, three platforms, consented tokens already available, eventual consistency, Python, in-memory repo for the interview.”

Write on board:
```text
Assumptions:
- Platforms: IG, YT, TikTok
- Entities: Profile, ContentItem
- Tokens exist (OAuth out of scope for deep dive)
- Canonical schema is source of truth for APIs
- At-least-once sync jobs OK; upserts idempotent
```

---

# PART 2 — Requirements (say this)

> “Functional requirements:
> - Fetch raw profile and content from each platform
> - Convert raw payloads into a **canonical Profile** and **canonical ContentItem**
> - Upsert into storage keyed by platform + platform-native id
> - Expose read APIs on the canonical model only — customers never see raw Instagram JSON
> - Adding a new platform must not rewrite the core sync service
>
> Non-functional:
> - Extensible for new platforms
> - Idempotent upserts
> - Respect platform rate limits (queue + backoff — I’ll note, not over-build)
> - Multi-tenant isolation by developer/customer id if needed
> - Observable sync status per account”

---

# PART 3 — Why Adapter (say this — critical)

> “Each platform returns different field names and shapes. Instagram might use `follower_count` and `username`. YouTube uses `statistics.subscriberCount` and nested `snippet`. TikTok is different again. If my SyncService has if/else for every platform, it becomes unmaintainable and violates open/closed.
>
> So I’ll use the **Adapter pattern**: each platform has an adapter that speaks that platform’s API dialect and outputs our **canonical model**. The sync orchestrator only depends on the adapter interface.
>
> I’ll also use a **Factory** to pick the adapter by platform key, and a **Repository** so storage can be memory now and Postgres later.”

Draw while talking:

```text
[Platform APIs]
 Instagram | YouTube | TikTok
      \         |        /
   Instagram  YouTube  TikTok
    Adapter   Adapter  Adapter
      \         |        /
       \        |       /
        PlatformAdapter (interface)
                 |
          SyncOrchestrator  (Facade)
                 |
         Canonical models
         Profile / ContentItem
                 |
            Repository
                 |
         InMemory / Postgres
                 |
         Public REST APIs (canonical only)
```

---

# PART 4 — Design patterns (name them explicitly)

Say this list:

> “Patterns I’m using:
> 1. **Adapter** — InstagramAdapter, YouTubeAdapter, TikTokAdapter implement `PlatformAdapter` and map raw → canonical
> 2. **Factory** — `PlatformAdapterFactory.create(platform)` returns the right adapter
> 3. **Repository** — `ProfileRepository` / `ContentRepository` hide persistence
> 4. **Facade** — `SyncOrchestrator` is the single entry for ‘sync this account’
> 5. Optional later: **Strategy** for ranking/scoring on top of canonical data; **Decorator** for caching around adapters”

Don’t dump more than that unless asked.

---

# PART 5 — Canonical model (speak + write)

> “Canonical means one internal shape regardless of source platform. Customer APIs and DB talk only to this.”

```python
# Speak while writing:
# "Platform-native ids stay for idempotency; we never lose lineage."

@dataclass
class Profile:
    id: str                 # our internal id
    developer_id: str       # multi-tenant
    platform: str           # instagram | youtube | tiktok
    platform_user_id: str   # native id on that platform
    handle: str
    display_name: str
    bio: str | None
    followers: int
    following: int
    profile_url: str | None
    is_verified: bool
    raw_hash: str           # change detection
    updated_at: datetime

@dataclass
class ContentItem:
    id: str
    profile_id: str
    platform: str
    platform_content_id: str
    content_type: str       # video | image | reel | short | post
    caption: str | None
    published_at: datetime
    likes: int
    comments: int
    views: int
    shares: int
    media_urls: list[str]
    raw_hash: str
```

> “Unique keys for upsert: Profile unique on `(platform, platform_user_id)`. Content unique on `(platform, platform_content_id)` or `(profile_id, platform_content_id)`. That gives idempotent sync.”

---

# PART 6 — Classes (say names, then responsibilities)

> “Here’s the class design:”

| Class | Responsibility |
|-------|----------------|
| `PlatformAdapter` (ABC) | Interface: fetch + to_canonical |
| `InstagramAdapter` | IG API + mapping |
| `YouTubeAdapter` | YT API + mapping |
| `TikTokAdapter` | TT API + mapping |
| `PlatformAdapterFactory` | platform string → adapter instance |
| `SyncOrchestrator` | Facade: sync profile/content for an account |
| `ProfileRepository` | upsert/get profiles |
| `ContentRepository` | upsert/list contents |
| `SyncJob` (optional) | track status per account |

**Interface — speak this:**

> “The adapter contract is the most important part. SyncOrchestrator should never import Instagram SDK types.”

```python
class PlatformAdapter(ABC):
    @abstractmethod
    def fetch_profile(self, access_token: str, external_id: str) -> dict:
        """Return RAW platform payload."""

    @abstractmethod
    def fetch_contents(self, access_token: str, external_id: str, cursor: str | None) -> tuple[list[dict], str | None]:
        """Return RAW items + next cursor."""

    @abstractmethod
    def to_canonical_profile(self, raw: dict, developer_id: str) -> Profile:
        ...

    @abstractmethod
    def to_canonical_content(self, raw: dict, profile_id: str) -> ContentItem:
        ...
```

> “I deliberately split **fetch** and **to_canonical**. Fetch stays IO. Mapping stays pure and unit-testable with fixture JSON.”

---

# PART 7 — APIs (board)

> “Outbound customer APIs only expose canonical data:”

```text
GET  /v1/profiles/{profile_id}
GET  /v1/profiles?platform=instagram&handle=maya
GET  /v1/profiles/{profile_id}/contents?cursor=

POST /internal/sync/accounts/{account_id}   # trigger sync (internal)
```

> “Customers never call Instagram through us in raw form — that’s the product value of normalization.”

---

# PART 8 — Sequence (happy path) — narrate step by step

> “Happy path for syncing one connected Instagram account:
>
> 1. SyncOrchestrator receives `account_id`
> 2. Load account: platform=`instagram`, access_token, external_id, developer_id
> 3. Factory.create(`instagram`) → InstagramAdapter
> 4. adapter.fetch_profile(token, external_id) → raw dict
> 5. adapter.to_canonical_profile(raw, developer_id) → Profile
> 6. profile_repo.upsert(profile)  // idempotent
> 7. Loop: adapter.fetch_contents(... cursor ...) → raw list
> 8. Map each with to_canonical_content → ContentItem
> 9. content_repo.upsert_many(items)
> 10. Update sync status SYNCED; optionally emit event for webhooks
>
> If token expired: mark REAUTH_REQUIRED and stop. If platform returns 429: backoff and retry job.”

Draw numbered arrows on the diagram.

---

# PART 9 — Schema (say briefly)

```text
profiles(
  id PK,
  developer_id,
  platform,
  platform_user_id,
  handle, display_name, bio,
  followers, following,
  raw_hash, updated_at,
  UNIQUE(platform, platform_user_id)
)

content_items(
  id PK,
  profile_id FK,
  platform,
  platform_content_id,
  content_type, caption, published_at,
  likes, comments, views, shares,
  raw_hash,
  UNIQUE(profile_id, platform_content_id)
)

INDEX content_items(profile_id, published_at DESC)
```

> “I’d also keep an optional `raw_payloads` table for debugging platform schema changes — not required for v1 reads.”

---

# PART 10 — Minute 20 transition to code (exact)

> “Design is enough for v1. Next I’ll code in Python:
> - canonical dataclasses
> - PlatformAdapter interface
> - InstagramAdapter and YouTubeAdapter mappings
> - Factory
> - SyncOrchestrator.sync_profile
> - InMemory ProfileRepository
>
> I’ll stub fetch methods to return sample raw JSON so we can run the mapping. Sound good?”

---

# PART 11 — CODE (write this in the interview)

Speak line-by-line as you type. Comments in the script are for you — don’t over-comment in interview code.

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import hashlib
import json


# ---------- Canonical models ----------

@dataclass
class Profile:
    id: str
    developer_id: str
    platform: str
    platform_user_id: str
    handle: str
    display_name: str
    bio: Optional[str]
    followers: int
    following: int
    is_verified: bool
    raw_hash: str
    updated_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class ContentItem:
    id: str
    profile_id: str
    platform: str
    platform_content_id: str
    content_type: str
    caption: Optional[str]
    published_at: datetime
    likes: int
    comments: int
    views: int
    shares: int
    raw_hash: str


def stable_hash(raw: dict) -> str:
    blob = json.dumps(raw, sort_keys=True, default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def make_id(*parts: str) -> str:
    return ":".join(parts)


# ---------- Adapter interface ----------

class PlatformAdapter(ABC):
    platform: str

    @abstractmethod
    def fetch_profile(self, access_token: str, external_id: str) -> dict:
        ...

    @abstractmethod
    def to_canonical_profile(self, raw: dict, developer_id: str) -> Profile:
        ...

    @abstractmethod
    def fetch_contents(
        self, access_token: str, external_id: str, cursor: Optional[str]
    ) -> tuple[list[dict], Optional[str]]:
        ...

    @abstractmethod
    def to_canonical_content(self, raw: dict, profile_id: str) -> ContentItem:
        ...


# ---------- Concrete adapters ----------

class InstagramAdapter(PlatformAdapter):
    platform = "instagram"

    def fetch_profile(self, access_token: str, external_id: str) -> dict:
        # In interview: stub. In prod: call IG Graph API.
        return {
            "id": external_id,
            "username": "mayamakes",
            "name": "Maya Reyes",
            "biography": "Beauty & Skincare",
            "followers_count": 120000,
            "follows_count": 800,
            "is_verified": False,
        }

    def to_canonical_profile(self, raw: dict, developer_id: str) -> Profile:
        pid = make_id(self.platform, raw["id"])
        return Profile(
            id=pid,
            developer_id=developer_id,
            platform=self.platform,
            platform_user_id=str(raw["id"]),
            handle=raw["username"],
            display_name=raw.get("name") or raw["username"],
            bio=raw.get("biography"),
            followers=int(raw.get("followers_count", 0)),
            following=int(raw.get("follows_count", 0)),
            is_verified=bool(raw.get("is_verified", False)),
            raw_hash=stable_hash(raw),
        )

    def fetch_contents(self, access_token: str, external_id: str, cursor: Optional[str]):
        items = [
            {
                "id": "ig_media_1",
                "caption": "Morning routine",
                "timestamp": "2026-09-01T10:00:00",
                "media_type": "REELS",
                "like_count": 4100,
                "comments_count": 120,
                "view_count": 90000,
            }
        ]
        return items, None

    def to_canonical_content(self, raw: dict, profile_id: str) -> ContentItem:
        ctype = "reel" if raw.get("media_type") == "REELS" else "post"
        return ContentItem(
            id=make_id(self.platform, raw["id"]),
            profile_id=profile_id,
            platform=self.platform,
            platform_content_id=str(raw["id"]),
            content_type=ctype,
            caption=raw.get("caption"),
            published_at=datetime.fromisoformat(raw["timestamp"]),
            likes=int(raw.get("like_count", 0)),
            comments=int(raw.get("comments_count", 0)),
            views=int(raw.get("view_count", 0)),
            shares=int(raw.get("share_count", 0)),
            raw_hash=stable_hash(raw),
        )


class YouTubeAdapter(PlatformAdapter):
    platform = "youtube"

    def fetch_profile(self, access_token: str, external_id: str) -> dict:
        return {
            "id": external_id,
            "snippet": {"title": "MayaTech", "description": "Tutorials"},
            "statistics": {"subscriberCount": "500000", "videoCount": "210"},
        }

    def to_canonical_profile(self, raw: dict, developer_id: str) -> Profile:
        pid = make_id(self.platform, raw["id"])
        snippet = raw.get("snippet", {})
        stats = raw.get("statistics", {})
        return Profile(
            id=pid,
            developer_id=developer_id,
            platform=self.platform,
            platform_user_id=str(raw["id"]),
            handle=snippet.get("title", ""),
            display_name=snippet.get("title", ""),
            bio=snippet.get("description"),
            followers=int(stats.get("subscriberCount", 0)),
            following=0,  # YT has no following in this payload
            is_verified=False,
            raw_hash=stable_hash(raw),
        )

    def fetch_contents(self, access_token: str, external_id: str, cursor: Optional[str]):
        return [], None

    def to_canonical_content(self, raw: dict, profile_id: str) -> ContentItem:
        raise NotImplementedError("demo focuses on profile mapping for YT")


# ---------- Factory ----------

class PlatformAdapterFactory:
    _registry: dict[str, type[PlatformAdapter]] = {
        "instagram": InstagramAdapter,
        "youtube": YouTubeAdapter,
    }

    @classmethod
    def create(cls, platform: str) -> PlatformAdapter:
        try:
            return cls._registry[platform]()
        except KeyError:
            raise ValueError(f"unsupported platform: {platform}")

    @classmethod
    def register(cls, platform: str, adapter_cls: type[PlatformAdapter]) -> None:
        # Speak: "Open/closed — new platform registers here, orchestrator unchanged."
        cls._registry[platform] = adapter_cls


# ---------- Repository ----------

class ProfileRepository(ABC):
    @abstractmethod
    def upsert(self, profile: Profile) -> Profile:
        ...

    @abstractmethod
    def get(self, profile_id: str) -> Optional[Profile]:
        ...


class InMemoryProfileRepository(ProfileRepository):
    def __init__(self):
        self._by_id: dict[str, Profile] = {}
        self._by_native: dict[tuple[str, str], str] = {}

    def upsert(self, profile: Profile) -> Profile:
        key = (profile.platform, profile.platform_user_id)
        existing_id = self._by_native.get(key)
        if existing_id:
            profile.id = existing_id
        self._by_id[profile.id] = profile
        self._by_native[key] = profile.id
        return profile

    def get(self, profile_id: str) -> Optional[Profile]:
        return self._by_id.get(profile_id)


# ---------- Facade / Orchestrator ----------

@dataclass
class ConnectedAccount:
    account_id: str
    developer_id: str
    platform: str
    external_id: str
    access_token: str


class SyncOrchestrator:
    """Facade: one method to sync an account into canonical storage."""

    def __init__(self, profiles: ProfileRepository):
        self.profiles = profiles

    def sync_profile(self, account: ConnectedAccount) -> Profile:
        adapter = PlatformAdapterFactory.create(account.platform)
        raw = adapter.fetch_profile(account.access_token, account.external_id)
        canonical = adapter.to_canonical_profile(raw, account.developer_id)
        return self.profiles.upsert(canonical)


# ---------- Demo / dry-run (narrate) ----------

if __name__ == "__main__":
    repo = InMemoryProfileRepository()
    sync = SyncOrchestrator(repo)

    ig = ConnectedAccount("acc_1", "dev_1", "instagram", "1788", "tok_ig")
    yt = ConnectedAccount("acc_2", "dev_1", "youtube", "UC123", "tok_yt")

    p1 = sync.sync_profile(ig)
    p2 = sync.sync_profile(yt)

    print(p1.platform, p1.handle, p1.followers)  # instagram mayamakes 120000
    print(p2.platform, p2.handle, p2.followers)  # youtube MayaTech 500000

    # Idempotent re-sync
    p1_again = sync.sync_profile(ig)
    assert p1_again.id == p1.id
```

### While coding, say these lines

1. While writing ABC:  
   > “This interface is the Adapter contract.”

2. While writing Instagram vs YouTube mapping:  
   > “Same Profile fields; different raw paths — that’s the whole point.”

3. While writing Factory:  
   > “Adding TikTok is register + new class, not editing SyncOrchestrator.”

4. While writing upsert:  
   > “Natural key platform + platform_user_id makes sync idempotent.”

5. At the end:  
   > “In production, fetch hits real APIs with rate limits; mapping stays pure; repository becomes Postgres.”

---

# PART 12 — Edge cases (after code, speak)

> “Failure modes I’d handle next:
> 1. **Unsupported platform** — Factory raises clear error
> 2. **Schema drift** — Instagram renames a field → only InstagramAdapter changes; add adapter tests with saved fixtures
> 3. **Partial content sync** — page with cursor; save checkpoint cursor on the job
> 4. **429 rate limit** — retry with Retry-After; don’t block other accounts
> 5. **Token expired** — REAUTH_REQUIRED; stop sync
> 6. **Missing fields** — adapters use `.get` with safe defaults; don’t crash the whole job
> 7. **Duplicate webhooks/jobs** — upsert by natural key
> 8. **Consent revoked** — orchestrator refuses sync for that product”

---

# PART 13 — Follow-up Q&A (memorize short answers)

**Q: Adapter vs Facade?**  
> “Adapter translates one platform’s API into our model. Facade is SyncOrchestrator — one simple `sync_profile` over factory + adapter + repo.”

**Q: Why not one giant mapper with if platform ==?**  
> “That violates open/closed. Every new platform edits the same function and increases regression risk.”

**Q: Where does OAuth/Connect fit?**  
> “Upstream. Connect stores tokens and account linkage. This design assumes a ConnectedAccount. I can sketch Connect separately if you want.”

**Q: Public vs consented?**  
> “Same Adapter idea. Public adapters may use different endpoints and no user token; consented adapters use OAuth tokens. Canonical model stays the same — that’s Phyllo’s value.”

**Q: How do you test adapters?**  
> “Golden JSON fixtures per platform → to_canonical_* → assert Profile fields. No live network in unit tests.”

**Q: How do customer APIs stay stable when IG changes?**  
> “Canonical schema is versioned carefully; adapters absorb platform churn.”

**Q: Strategy pattern here?**  
> “Not required for normalization. Strategy appears later for search ranking or authenticity scoring on canonical profiles.”

**Q: Performance?**  
> “Bound concurrency per platform; queue sync jobs; bulk upsert; cache hot canonical profiles in Redis with TTL.”

---

# PART 14 — Closing (exact)

> “To summarize: I designed Phyllo’s multi-platform ingestion around the **Adapter** pattern so Instagram, YouTube, and TikTok each map into one **canonical Profile/Content** model. **Factory** selects the adapter, **SyncOrchestrator** is the **Facade**, and **Repository** stores idempotent upserts by platform native ids. I coded the interface, two adapters, factory, and sync path in Python. Extending to TikTok is a new adapter class plus registry entry — core flow unchanged. Main tradeoff: an extra mapping layer, in exchange for stable APIs and maintainable platform growth.”

Then ask them:
> “Do you want me to extend this to content pagination, or sketch the Connect token side?”

---

# PART 15 — 60-minute clock (stick to this)

| Min | What you say/do |
|-----|-----------------|
| 0–2 | Opening + restate |
| 2–8 | Clarifiers + assumptions |
| 8–12 | Why Adapter + diagram |
| 12–18 | Canonical model + classes + APIs |
| 18–20 | Sequence + schema |
| 20–22 | “I’ll code adapters now” |
| 22–48 | Code (interface → IG → YT → Factory → Repo → Orchestrator → demo) |
| 48–55 | Edge cases + follow-ups |
| 55–60 | Closing summary |

If short on time: skip ContentItem coding; finish Profile path fully.

---

# PART 16 — Cheat card (last look before interview)

**Say:** Adapter → canonical · Factory picks adapter · Facade syncs · Repo upserts  

**Classes:** PlatformAdapter · InstagramAdapter · YouTubeAdapter · Factory · SyncOrchestrator · ProfileRepository  

**Canonical Profile fields:** platform, platform_user_id, handle, followers, …  

**Idempotency:** UNIQUE(platform, platform_user_id)  

**Extensibility line:** “New platform = new Adapter + register, orchestrator unchanged.”  

**Phyllo link:** “This is how Phyllo can expose one schema across 25+ platforms.”  

**Code order:** models → ABC → IG adapter → YT adapter → Factory → Repo → Orchestrator → run demo  

---

# PART 17 — Practice checklist tonight

- [ ] Speak PART 0–3 out loud without reading (2 min)  
- [ ] Draw the diagram from memory  
- [ ] Hand-write Instagram + YouTube `to_canonical_profile`  
- [ ] Hand-write Factory + SyncOrchestrator.sync_profile  
- [ ] Answer “Adapter vs Facade” in 20 seconds  
- [ ] Full mock once with timer (60 min)  

---

**File purpose:** This is the end-to-end speaking script for the **multi-platform → canonical Adapter** question — the most Phyllo-native LLD they can ask from the website’s “one schema across platforms” story.
