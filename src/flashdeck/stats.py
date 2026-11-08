"""Scores: each user's progress, from the reviews and card states already stored.

A review counts as *right* if it was marked right (or claimed as right) without
looking at the reference; a right answer that was looked up counts as *nearly*
right, as it does for scheduling.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, time, timedelta

from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from .marking import Verdict
from .models import Answer, Card, CardState, Review

RIGHT = Q(verdict__in=[Verdict.RIGHT, Verdict.CLAIMED], looked_up=False)
NEARLY = Q(verdict=Verdict.NEARLY) | Q(
    verdict__in=[Verdict.RIGHT, Verdict.CLAIMED], looked_up=True
)
WRONG = Q(verdict=Verdict.WRONG)
# A card is *well learnt* once it comes back after this many days or more (the
# "mature" of Anki).
WELL_LEARNT_DAYS = 21
CHART_DAYS = 30
MOST_MISSED = 10


@dataclass
class Tally:
    right: int = 0
    nearly: int = 0
    wrong: int = 0

    @property
    def total(self):
        return self.right + self.nearly + self.wrong

    @property
    def percent_right(self):
        return round(100 * self.right / self.total) if self.total else None


@dataclass
class Day(Tally):
    date: datetime | None = None

    def bar_height(self, most):
        """The height of the day's bar, as a percentage of the busiest day's."""
        return round(100 * self.total / most, 1) if most else 0


def _start_of(day):
    return timezone.make_aware(datetime.combine(day, time.min))


def _by_day(reviews):
    return reviews.annotate(
        day=TruncDate("created", tzinfo=timezone.get_current_timezone())
    ).values("day")


def daily(user, days=CHART_DAYS):
    """A Day for each of the last `days` days, today last."""
    today = timezone.localdate()
    first = today - timedelta(days=days - 1)
    rows = (
        _by_day(Review.objects.filter(user=user, created__gte=_start_of(first)))
        .annotate(
            right=Count("pk", filter=RIGHT),
            nearly=Count("pk", filter=NEARLY),
            wrong=Count("pk", filter=WRONG),
        )
        .order_by()
    )
    found = {row["day"]: row for row in rows}
    out = []
    for i in range(days):
        date = first + timedelta(days=i)
        row = found.get(date, {})
        out.append(
            Day(
                date=date,
                right=row.get("right", 0),
                nearly=row.get("nearly", 0),
                wrong=row.get("wrong", 0),
            )
        )
    return out


def days_in_a_row(user):
    """The number of days up to today (or yesterday, if there have been no answers
    yet today) on each of which the user answered at least one card."""
    days = set(
        _by_day(Review.objects.filter(user=user))
        .values_list("day", flat=True)
        .distinct()
        .order_by()
    )
    day = timezone.localdate()
    if day not in days:
        day -= timedelta(days=1)
    count = 0
    while day in days:
        count += 1
        day -= timedelta(days=1)
    return count


def today(user):
    """Today's Tally, and the number of days in a row."""
    counts = Review.objects.filter(
        user=user, created__gte=_start_of(timezone.localdate())
    ).aggregate(
        right=Count("pk", filter=RIGHT),
        nearly=Count("pk", filter=NEARLY),
        wrong=Count("pk", filter=WRONG),
    )
    return Tally(**counts), days_in_a_row(user)


@dataclass
class DeckProgress:
    deck: object
    cards: int = 0
    seen: int = 0
    well_learnt: int = 0
    due: int = 0
    hidden: int = 0
    recent: Tally | None = None


def decks(user, deck_list):
    """A DeckProgress for each deck: cards seen, well learnt, due and hidden, and
    the answers of the last CHART_DAYS days."""
    now = timezone.now()
    progress = {deck.pk: DeckProgress(deck=deck) for deck in deck_list}
    for deck_id, n in (
        Card.objects.filter(deck__in=deck_list)
        .values_list("deck")
        .annotate(n=Count("pk"))
        .order_by()
    ):
        progress[deck_id].cards = n
    states = CardState.objects.filter(user=user, card__deck__in=deck_list)
    for deck_id, fsrs, due, suspended in states.values_list(
        "card__deck", "fsrs", "due", "suspended"
    ):
        row = progress[deck_id]
        if suspended:
            row.hidden += 1
        if fsrs is None:
            continue
        row.seen += 1
        if not suspended and due is not None and due <= now:
            row.due += 1
        if _interval_days(fsrs) >= WELL_LEARNT_DAYS:
            row.well_learnt += 1
    recent = (
        Review.objects.filter(
            user=user,
            card__deck__in=deck_list,
            created__gte=now - timedelta(days=CHART_DAYS),
        )
        .values("card__deck")
        .annotate(
            right=Count("pk", filter=RIGHT),
            nearly=Count("pk", filter=NEARLY),
            wrong=Count("pk", filter=WRONG),
        )
        .order_by()
    )
    for row in recent:
        deck_id = row.pop("card__deck")
        progress[deck_id].recent = Tally(**row)
    return list(progress.values())


def _interval_days(fsrs):
    if not fsrs.get("last_review"):
        return 0
    last = datetime.fromisoformat(fsrs["last_review"])
    return (datetime.fromisoformat(fsrs["due"]) - last) / timedelta(days=1)


@dataclass
class Missed:
    missed: int
    total: int

    @property
    def percent(self):
        return round(100 * self.missed / self.total)


def most_missed_cards(user, deck_list, limit=MOST_MISSED):
    """The cards most often answered wrong or nearly right, with their counts."""
    rows = (
        Review.objects.filter(user=user, card__deck__in=deck_list)
        .values("card")
        .annotate(missed=Count("pk", filter=NEARLY | WRONG), total=Count("pk"))
        .filter(missed__gt=0)
        .order_by("-missed", "-total")[:limit]
    )
    cards = Card.objects.select_related("deck__subject").in_bulk(
        [row["card"] for row in rows]
    )
    return [(cards[row["card"]], Missed(row["missed"], row["total"])) for row in rows]


def most_missed_answers(user, deck_list, limit=MOST_MISSED, at_least=5):
    """For decks whose cards have labelled answers (such as the persons of a
    verb), the labels most often answered wrong or nearly right, as a share of the
    answers given for them (at least `at_least`). Answers given after looking at
    the reference are left out."""
    tallies = defaultdict(lambda: [0, 0])
    reviews = Review.objects.filter(
        user=user, card__deck__in=deck_list, looked_up=False
    ).values_list("results", flat=True)
    answers = {}
    for results in reviews.iterator():
        for result in results:
            answers.setdefault(result["answer"], None)
    for pk, label, deck_id in Answer.objects.filter(pk__in=list(answers)).values_list(
        "pk", "label", "card__deck"
    ):
        if label:
            answers[pk] = (deck_id, label)
    for results in reviews.iterator():
        for result in results:
            key = answers.get(result["answer"])
            if key is None:
                continue
            tally = tallies[key]
            tally[1] += 1
            if result["verdict"] in (Verdict.NEARLY, Verdict.WRONG):
                tally[0] += 1
    decks_by_pk = {deck.pk: deck for deck in deck_list}
    rows = [
        (decks_by_pk[deck_id], label, Missed(missed, total))
        for (deck_id, label), (missed, total) in tallies.items()
        if missed and total >= at_least
    ]
    rows.sort(key=lambda row: (-row[2].percent, -row[2].total))
    return rows[:limit]
