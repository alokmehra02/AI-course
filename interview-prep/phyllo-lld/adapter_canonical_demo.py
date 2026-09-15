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

