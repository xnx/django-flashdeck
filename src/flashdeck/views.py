from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .marking import Verdict
from .models import Card, CardState, Review, Subject
from .practice import (
    ClaimError,
    claim,
    mark_card,
    new_cards_left,
    next_card,
    record_review,
    visible_decks,
)

MAX_ANSWER_LENGTH = 500


def _int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def index(request):
    """The subjects and decks the user may practise, with the number of cards due."""
    decks = list(visible_decks(request.user).annotate(card_count=Count("cards")))
    due = {}
    if request.user.is_authenticated:
        due = dict(
            CardState.objects.filter(
                user=request.user,
                due__lte=timezone.now(),
                card__deck__in=[deck.pk for deck in decks],
            )
            .values_list("card__deck")
            .annotate(n=Count("pk"))
        )
    subjects = {}
    for deck in decks:
        deck.due = due.get(deck.pk, 0)
        subject = subjects.setdefault(deck.subject_id, deck.subject)
        if not hasattr(subject, "deck_list"):
            subject.deck_list, subject.due = [], 0
        subject.deck_list.append(deck)
        subject.due += deck.due
    return render(request, "flashdeck/index.html", {"subjects": subjects.values()})


@require_http_methods(["GET", "POST"])
def practise(request, subject, deck=None):
    """Practise a subject (all its decks) or one deck: shows the next card, marks
    the answers given, and shows the result."""
    subject = get_object_or_404(Subject, slug=subject)
    decks = visible_decks(request.user).filter(subject=subject)
    if deck is not None:
        deck = get_object_or_404(decks, slug=deck)
        decks = decks.filter(pk=deck.pk)
    elif not decks.exists():
        raise Http404("No decks")
    cards = Card.objects.filter(deck__in=decks)
    context = {
        "subject": subject,
        "deck": deck,
        "scope_url": request.path,
        "characters": subject.character_list(),
        "show_deck": deck is None,
    }
    if request.method == "POST":
        if "claim" in request.POST:
            return _claim(request, cards)
        return _answer(request, cards, context)

    review_id = _int(request.GET.get("review"))
    if review_id is not None and request.user.is_authenticated:
        review = get_object_or_404(
            Review.objects.select_related("card__deck__subject"),
            pk=review_id,
            user=request.user,
            card__in=cards,
        )
        return _result(
            request, context, review.card, review.results, review.verdict, review
        )

    after = _int(request.GET.get("after"))
    card = next_card(
        request.user,
        cards,
        after=after,
        ahead="ahead" in request.GET,
        more="more" in request.GET,
    )
    if card is None:
        return _nothing_due(request, context, cards)
    context.update(card=card, answers=card.answers.all())
    return render(request, "flashdeck/question.html", context)


def _answer(request, cards, context):
    card = get_object_or_404(
        cards.select_related("deck__subject"), pk=_int(request.POST.get("card"))
    )
    answers = list(card.answers.all())
    given = {
        a.pk: request.POST.get(f"answer-{a.pk}", "")[:MAX_ANSWER_LENGTH]
        for a in answers
    }
    results, verdict = mark_card(card, answers, given, request.user)
    if request.user.is_authenticated:
        review = record_review(request.user, card, results, verdict)
        return redirect(f"{request.path}?review={review.pk}")
    return _result(request, context, card, results, verdict, None)


def _claim(request, cards):
    if not request.user.is_authenticated:
        raise Http404("Log in to claim an answer")
    review = get_object_or_404(
        Review,
        pk=_int(request.POST.get("review")),
        user=request.user,
        card__in=cards,
    )
    try:
        claim(review, _int(request.POST.get("claim")))
    except ClaimError as error:
        raise Http404(str(error)) from error
    return redirect(f"{request.path}?review={review.pk}")


def _result(request, context, card, results, verdict, review):
    answers = {a.pk: a for a in card.answers.all()}
    rows = []
    for result in results:
        answer = answers.get(result["answer"])
        rows.append(
            {
                **result,
                "label": answer.label if answer else "",
                "verdict_label": Verdict(result["verdict"]).label,
                "can_claim": review is not None
                and answer is not None
                and result["given"] != ""
                and result["verdict"] in (Verdict.NEARLY, Verdict.WRONG),
            }
        )
    due = None
    if review is not None:
        due = (
            CardState.objects.filter(user=review.user, card=card)
            .values_list("due", flat=True)
            .first()
        )
    context.update(
        card=card,
        rows=rows,
        verdict=Verdict(verdict),
        review=review,
        due=due,
        has_labels=any(row["label"] for row in rows),
    )
    return render(request, "flashdeck/result.html", context)


def _nothing_due(request, context, cards):
    context["has_cards"] = cards.exists()
    if not request.user.is_authenticated:
        return render(request, "flashdeck/nothing_due.html", context)
    states = CardState.objects.filter(user=request.user, card__in=cards)
    context.update(
        next_due=states.order_by("due").values_list("due", flat=True).first(),
        new_left=cards.exclude(states__user=request.user).exists(),
        quota_reached=new_cards_left(request.user) <= 0,
    )
    return render(request, "flashdeck/nothing_due.html", context)
