"""Topics service — master index and per-topic deck listings.

Topics are owner-scoped (per-user spaces). The flat lookups here resolve
ONLY unambiguous matches — canonical in standalone (single owner), legacy
redirect support in the server edition; the owner-scoped variants are the
canonical resolvers for /u/{handle}/{topic} pages.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Topic, User
from schemas.deck import DeckListItem
from schemas.topic import TopicDetail, TopicSummary
from services.urls import deck_url, topic_url

# How many keywords to surface per topic on the master index.
_TOP_KEYWORDS = 5


def _is_listable(deck) -> bool:
    """Whether a deck belongs in public listings: public visibility only
    (unlisted stays reachable by direct link but unlisted), and not
    quarantined by moderation."""
    return deck.visibility == "public" and deck.moderation_status == "approved"


def _deck_list_item(deck) -> DeckListItem:
    return DeckListItem(
        slug=deck.slug,
        title=deck.title,
        author=deck.author,
        description=deck.description,
        theme=deck.theme,
        keywords=[k.value for k in deck.keywords],
        card_count=deck.card_count,
        url=deck_url(deck),
    )


def _summarize(topic: Topic) -> TopicSummary | None:
    """A TopicSummary for the index, or None if nothing in it is listable."""
    visible = [d for d in topic.decks if _is_listable(d)]
    if not visible:  # topics with no listable decks stay off the index
        return None
    counts: dict[str, int] = {}
    for deck in visible:
        for kw in deck.keywords:
            counts[kw.value] = counts.get(kw.value, 0) + 1
    # Most frequent first, ties broken alphabetically for stable output.
    top = [
        value
        for value, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[
            :_TOP_KEYWORDS
        ]
    ]
    return TopicSummary(
        slug=topic.slug,
        display_name=topic.display_name,
        description=topic.description,
        theme=topic.theme,
        deck_count=len(visible),
        top_keywords=top,
        url=topic_url(topic),
        owner_handle=topic.owner.handle if topic.owner else None,
    )


def list_topics(db: Session) -> list[TopicSummary]:
    """All topics (across owners) with deck counts and common keywords."""
    topics = db.scalars(select(Topic).order_by(Topic.display_name)).all()
    return [s for t in topics if (s := _summarize(t)) is not None]


def _topic_detail(topic: Topic) -> TopicDetail:
    decks = [
        _deck_list_item(d)
        for d in sorted(topic.decks, key=lambda d: d.title.lower())
        if _is_listable(d)
    ]
    return TopicDetail(
        slug=topic.slug,
        display_name=topic.display_name,
        description=topic.description,
        theme=topic.theme,
        decks=decks,
        url=topic_url(topic),
        owner_handle=topic.owner.handle if topic.owner else None,
    )


def get_topic_with_decks(db: Session, slug: str) -> TopicDetail | None:
    """A topic and its decks by FLAT slug — only when exactly one owner has
    it; ambiguous or missing slugs yield None."""
    matches = db.scalars(
        select(Topic).where(Topic.slug == slug).limit(2)
    ).all()
    if len(matches) != 1:
        return None
    return _topic_detail(matches[0])


def get_topic_for_owner(db: Session, handle: str, slug: str) -> TopicDetail | None:
    """A topic and its decks in one owner's namespace (/u/{handle}/{slug})."""
    topic = db.scalar(
        select(Topic)
        .join(User, Topic.owner_id == User.id)
        .where(User.handle == handle, Topic.slug == slug)
    )
    if topic is None:
        return None
    return _topic_detail(topic)


def list_topics_for_owner(db: Session, handle: str) -> list[TopicSummary]:
    """One owner's topics, for their /u/{handle} author page."""
    topics = db.scalars(
        select(Topic)
        .join(User, Topic.owner_id == User.id)
        .where(User.handle == handle)
        .order_by(Topic.display_name)
    ).all()
    return [s for t in topics if (s := _summarize(t)) is not None]
