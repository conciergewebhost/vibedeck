"""Topics service — master index and per-topic deck listings."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import Topic
from schemas.deck import DeckListItem
from schemas.topic import TopicDetail, TopicSummary

# How many keywords to surface per topic on the master index.
_TOP_KEYWORDS = 5


def _deck_list_item(deck) -> DeckListItem:
    return DeckListItem(
        slug=deck.slug,
        title=deck.title,
        author=deck.author,
        description=deck.description,
        theme=deck.theme,
        keywords=[k.value for k in deck.keywords],
        card_count=deck.card_count,
    )


def list_topics(db: Session) -> list[TopicSummary]:
    """All topics with deck counts and their most common keywords."""
    topics = db.scalars(select(Topic).order_by(Topic.display_name)).all()
    summaries: list[TopicSummary] = []
    for topic in topics:
        counts: dict[str, int] = {}
        for deck in topic.decks:
            for kw in deck.keywords:
                counts[kw.value] = counts.get(kw.value, 0) + 1
        # Most frequent first, ties broken alphabetically for stable output.
        top = [
            value
            for value, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[
                :_TOP_KEYWORDS
            ]
        ]
        summaries.append(
            TopicSummary(
                slug=topic.slug,
                display_name=topic.display_name,
                description=topic.description,
                theme=topic.theme,
                deck_count=len(topic.decks),
                top_keywords=top,
            )
        )
    return summaries


def get_topic_with_decks(db: Session, slug: str) -> TopicDetail | None:
    """A topic and its decks, or None if the topic does not exist."""
    topic = db.scalar(select(Topic).where(Topic.slug == slug))
    if topic is None:
        return None
    decks = [
        _deck_list_item(d) for d in sorted(topic.decks, key=lambda d: d.title.lower())
    ]
    return TopicDetail(
        slug=topic.slug,
        display_name=topic.display_name,
        description=topic.description,
        theme=topic.theme,
        decks=decks,
    )
