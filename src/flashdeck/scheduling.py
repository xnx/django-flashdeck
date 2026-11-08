"""Spaced repetition with FSRS (the Free Spaced Repetition Scheduler).

A right answer is rated Good, a nearly right one Hard and a wrong one Again. The
state of each card for each user is kept as the dictionary that the fsrs package
reads and writes.

How often a card comes back is set by the chance of remembering it that FSRS aims
for when it next comes back (its *target recall*). A lower target lengthens every
interval, and the effect compounds: after the second, third and fourth right
answers, a card comes back after about 2, 11 and 46 days normally, but after 1, 3
and 8 (more often), 4, 31 and 174 (less often) or 8, 76 and 525 (rarely).
"""

from datetime import UTC, datetime

from django.db import models
from fsrs import Card as FsrsCard
from fsrs import Rating, Scheduler

from .marking import Verdict


class Frequency(models.TextChoices):
    MORE = "more", "More often"
    NORMAL = "normal", "Normally"
    LESS = "less", "Less often"
    RARELY = "rarely", "Rarely"


TARGET_RECALL = {
    Frequency.MORE: 0.95,
    Frequency.NORMAL: 0.9,
    Frequency.LESS: 0.85,
    Frequency.RARELY: 0.8,
}
_schedulers = {
    frequency: Scheduler(desired_retention=recall)
    for frequency, recall in TARGET_RECALL.items()
}

RATINGS = {
    Verdict.RIGHT: Rating.Good,
    Verdict.CLAIMED: Rating.Good,
    Verdict.NEARLY: Rating.Hard,
    Verdict.WRONG: Rating.Again,
}


def schedule(
    state: dict | None,
    verdict: str,
    when: datetime,
    card_id: int,
    frequency: str = Frequency.NORMAL,
) -> dict:
    """The state after a review at `when`, from the state before it (None for a
    card not seen before)."""
    when = when.astimezone(UTC)  # fsrs accepts only datetime.UTC
    card = FsrsCard.from_dict(state) if state else FsrsCard(card_id=card_id, due=when)
    scheduler = _schedulers[Frequency(frequency)]
    card, _ = scheduler.review_card(card, RATINGS[Verdict(verdict)], when)
    return card.to_dict()


def due_of(state: dict) -> datetime:
    return datetime.fromisoformat(state["due"])
