"""Canonical reader URLs — the ONLY place URL shape is decided.

Server edition: /u/{owner.handle}/{topic.slug}/{deck.slug} (per-user
spaces). Standalone: flat /{topic.slug}/{deck.slug} (one owner, no
ambiguity). Everything that emits a deck or topic URL — list endpoints,
UploadResult, CLI output — must call these instead of assembling paths,
so flipping an instance's edition flips every URL it serves.

Callers must have the owner relationship loaded (joinedload) or accept a
lazy load; both Deck and Topic carry owner relationships.
"""

from config import settings
from models import Deck, Topic


def topic_url(topic: Topic) -> str:
    if settings.user_spaces_enabled:
        return f"/u/{topic.owner.handle}/{topic.slug}"
    return f"/{topic.slug}"


def deck_url(deck: Deck) -> str:
    if settings.user_spaces_enabled:
        return f"/u/{deck.owner.handle}/{deck.topic.slug}/{deck.slug}"
    return f"/{deck.topic.slug}/{deck.slug}"
