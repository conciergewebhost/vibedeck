"""Topics router — master index and per-topic deck listings.

Thin: validates the request and delegates to the topics service.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import get_db
from schemas.topic import TopicDetail, TopicSummary
from services import topics as topics_service

router = APIRouter()


@router.get("", response_model=list[TopicSummary])
def list_topics(db: Session = Depends(get_db)) -> list[TopicSummary]:
    """Master index: all topics with deck counts and top keywords."""
    return topics_service.list_topics(db)


@router.get("/{topic_slug}", response_model=TopicDetail)
def get_topic(topic_slug: str, db: Session = Depends(get_db)) -> TopicDetail:
    """A topic and the decks within it."""
    topic = topics_service.get_topic_with_decks(db, topic_slug)
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic
