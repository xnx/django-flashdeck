"""Spaced repetition with FSRS (the Free Spaced Repetition Scheduler).

A right answer is rated Good, a nearly right one Hard and a wrong one Again. The
state of each card for each user is kept as the dictionary that the fsrs package
reads and writes.
"""

from datetime import UTC, datetime

from fsrs import Card as FsrsCard
from fsrs import Rating, Scheduler

from .marking import Verdict

_scheduler = Scheduler()

RATINGS = {
    Verdict.RIGHT: Rating.Good,
    Verdict.CLAIMED: Rating.Good,
    Verdict.NEARLY: Rating.Hard,
    Verdict.WRONG: Rating.Again,
}


def schedule(state: dict | None, verdict: str, when: datetime, card_id: int) -> dict:
    """The state after a review at `when`, from the state before it (None for a
    card not seen before)."""
    when = when.astimezone(UTC)  # fsrs accepts only datetime.UTC
    card = FsrsCard.from_dict(state) if state else FsrsCard(card_id=card_id, due=when)
    card, _ = _scheduler.review_card(card, RATINGS[Verdict(verdict)], when)
    return card.to_dict()


def due_of(state: dict) -> datetime:
    return datetime.fromisoformat(state["due"])
