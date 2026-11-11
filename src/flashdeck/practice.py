"""Choosing the next card, marking and recording answers, claims, and each user's
choices of which cards to hide and how often the others come back."""

from collections import defaultdict
from datetime import datetime, time

from django.db import transaction
from django.utils import timezone

from .conf import setting
from .marking import Verdict, combine, mark
from .models import Answer, CardState, ClaimedAnswer, Deck, Review
from .scheduling import Frequency, due_of, effective_verdict, schedule

NEW_CARD_ORDER = [
    "deck__subject__position",
    "deck__position",
    "deck_id",
    "position",
    "id",
]


def visible_decks(user):
    """The decks that a user may practise."""
    decks = Deck.objects.select_related("subject")
    if not user.has_perm("flashdeck.practise_private"):
        decks = decks.filter(is_public=True)
    return decks


def new_cards_left(user):
    """How many more new cards the user may start today."""
    midnight = timezone.make_aware(datetime.combine(timezone.localdate(), time.min))
    # A card hidden before it was ever answered has no FSRS state, and was not
    # started.
    started = CardState.objects.filter(
        user=user, created__gte=midnight, fsrs__isnull=False
    ).count()
    return setting("NEW_CARDS_PER_DAY") - started


def next_card(user, cards, *, after=None, ahead=False, more=False):
    """The card to show next from `cards`, or None if nothing is due.

    A visitor who is not logged in gets a random card. A user gets the card most
    overdue; failing that, a new card (up to NEW_CARDS_PER_DAY, or beyond it with
    `more`); failing that, with `ahead`, the card due soonest. Cards the user has
    hidden are never shown. The card just shown (`after`) is not shown again
    straight away unless it is the only choice.
    """
    if not user.is_authenticated:
        pool = cards.exclude(pk=after) if after else cards
        return pool.order_by("?").first() or cards.first()
    states = CardState.objects.filter(
        user=user, card__in=cards, suspended=False
    ).select_related("card__deck__subject")
    due = states.filter(due__lte=timezone.now()).order_by("due")
    state = _first(due, card_id=after)
    if state:
        return state.card
    if more or new_cards_left(user) > 0:
        new = cards.exclude(states__user=user).order_by(*NEW_CARD_ORDER)
        card = _first(new.select_related("deck__subject"), pk=after)
        if card:
            return card
    if ahead:
        state = _first(states.exclude(due=None).order_by("due"), card_id=after)
        if state:
            return state.card
    return None


def _first(queryset, **exclude):
    """The first in the queryset other than the excluded one, if there is one."""
    if any(value is not None for value in exclude.values()):
        found = queryset.exclude(**exclude).first()
        if found:
            return found
    return queryset.first()


def mark_card(card, answers, given, user):
    """Marks the answers given (a dictionary from Answer id to text).

    Returns the results, one for each answer, and the verdict on the card. A user's
    claimed answers that have not been rejected are marked right for that user.
    """
    claimed = defaultdict(list)
    if user.is_authenticated:
        for answer_id, text in ClaimedAnswer.objects.filter(
            user=user, answer__in=answers, status=ClaimedAnswer.Status.PENDING
        ).values_list("answer_id", "text"):
            claimed[answer_id].append(text)
    case_sensitive = card.deck.subject.case_sensitive
    results = []
    for answer in answers:
        text = given.get(answer.pk, "").strip()
        result = mark(
            text, answer.accepted() + claimed[answer.pk], case_sensitive=case_sensitive
        )
        results.append(
            {
                "answer": answer.pk,
                "given": text,
                "verdict": result.verdict.value,
                "expected": result.expected,
            }
        )
    return results, combine(r["verdict"] for r in results)


@transaction.atomic
def record_review(user, card, results, verdict, looked_up=False):
    """Saves a marked answer and reschedules the card (as if nearly right if the
    user looked at the reference first and was right)."""
    now = timezone.now()
    state = CardState.objects.select_for_update().filter(user=user, card=card).first()
    if state is None:
        state = CardState(user=user, card=card)
    before = state.fsrs
    after = schedule(
        before, effective_verdict(verdict, looked_up), now, card.pk, state.frequency
    )
    state.fsrs = after
    state.due = due_of(after)
    state.save()
    return Review.objects.create(
        user=user,
        card=card,
        created=now,
        verdict=verdict,
        results=results,
        state_before=before,
        looked_up=looked_up,
    )


class ClaimError(Exception):
    pass


@transaction.atomic
def claim(review, answer_id):
    """Records the user's claim that their answer was right after all.

    The answer is saved as a ClaimedAnswer, the review is marked again, and, if it
    is the user's latest review of the card, the card is rescheduled as if the
    review had been marked that way to begin with.
    """
    review = Review.objects.select_for_update().get(pk=review.pk)
    entry = next((r for r in review.results if r["answer"] == answer_id), None)
    if (
        entry is None
        or entry["verdict"] not in (Verdict.NEARLY, Verdict.WRONG)
        or not entry["given"]
    ):
        raise ClaimError("Only an answer marked wrong or nearly right can be claimed.")
    try:
        answer = Answer.objects.get(pk=answer_id, card_id=review.card_id)
    except Answer.DoesNotExist as error:
        raise ClaimError("The answer no longer exists.") from error
    claimed, created = ClaimedAnswer.objects.get_or_create(
        answer=answer, user=review.user, text=entry["given"]
    )
    if not created and claimed.status == ClaimedAnswer.Status.REJECTED:
        claimed.status = ClaimedAnswer.Status.PENDING
        claimed.save(update_fields=["status"])
    entry["verdict"] = Verdict.CLAIMED.value
    review.verdict = combine(r["verdict"] for r in review.results)
    review.save(update_fields=["results", "verdict"])
    latest = (
        Review.objects.filter(user=review.user, card_id=review.card_id)
        .values_list("pk", flat=True)
        .first()
    )
    if latest == review.pk:
        state = CardState.objects.select_for_update().get(
            user=review.user, card_id=review.card_id
        )
        _reschedule(state)
        state.save(update_fields=["fsrs", "due"])
    return claimed


def _reschedule(state):
    """Schedules the card again from the user's latest review of it, as if that
    review had been marked as it is now, with the card's present frequency.
    Returns whether there was a review to do it from."""
    review = Review.objects.filter(user_id=state.user_id, card_id=state.card_id).first()
    if review is None:
        return False
    state.fsrs = schedule(
        review.state_before,
        effective_verdict(review.verdict, review.looked_up),
        review.created,
        state.card_id,
        state.frequency,
    )
    state.due = due_of(state.fsrs)
    return True


@transaction.atomic
def set_hidden(user, card, hidden):
    """Hides a card from a user (it is never shown in practice), or shows it again."""
    state = CardState.objects.select_for_update().filter(user=user, card=card).first()
    if hidden:
        if state is None:
            CardState.objects.create(user=user, card=card, suspended=True)
        elif not state.suspended:
            state.suspended = True
            state.save(update_fields=["suspended"])
    elif state is not None and state.suspended:
        if state.fsrs is None:
            state.delete()  # never answered, so it is a new card again
        else:
            state.suspended = False
            state.save(update_fields=["suspended"])


@transaction.atomic
def set_frequency(user, card, frequency):
    """Sets how often a card that the user has answered comes back, and schedules
    it again at once."""
    frequency = Frequency(frequency)
    state = CardState.objects.select_for_update().filter(user=user, card=card).first()
    if state is None or state.fsrs is None:
        return
    state.frequency = frequency
    _reschedule(state)
    state.save(update_fields=["frequency", "fsrs", "due"])
