from django.db.models import Count, Q
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
    set_frequency,
    set_hidden,
    visible_decks,
)
from .scheduling import Frequency

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
    has_settings = False
    if request.user.is_authenticated:
        due = dict(
            CardState.objects.filter(
                user=request.user,
                due__lte=timezone.now(),
                suspended=False,
                card__deck__in=[deck.pk for deck in decks],
            )
            .values_list("card__deck")
            .annotate(n=Count("pk"))
        )
        has_settings = _changed_states(request.user).exists()
    subjects = {}
    for deck in decks:
        deck.due = due.get(deck.pk, 0)
        subject = subjects.setdefault(deck.subject_id, deck.subject)
        if not hasattr(subject, "deck_list"):
            subject.deck_list, subject.due = [], 0
        subject.deck_list.append(deck)
        subject.due += deck.due
    return render(
        request,
        "flashdeck/index.html",
        {"subjects": subjects.values(), "has_settings": has_settings},
    )


def _changed_states(user):
    """The user's cards that are hidden or come back more or less often."""
    return CardState.objects.filter(user=user).filter(
        Q(suspended=True) | ~Q(frequency=Frequency.NORMAL)
    )


@require_http_methods(["GET", "POST"])
def card_settings(request):
    """The cards that the user has hidden, or asked to see more or less often, with
    buttons to undo each choice."""
    if not request.user.is_authenticated:
        raise Http404("Log in to see your card settings")
    if request.method == "POST":
        card = get_object_or_404(
            Card.objects.filter(deck__in=visible_decks(request.user)),
            pk=_int(request.POST.get("card")),
        )
        if request.POST.get("hidden") == "0":
            set_hidden(request.user, card, False)
        if request.POST.get("frequency") == Frequency.NORMAL:
            set_frequency(request.user, card, Frequency.NORMAL)
        return redirect(request.path)
    states = list(
        _changed_states(request.user)
        .filter(card__deck__in=visible_decks(request.user))
        .select_related("card__deck__subject")
        .order_by(
            "card__deck__subject__position",
            "card__deck__position",
            "card__position",
            "card_id",
        )
    )
    return render(
        request,
        "flashdeck/settings.html",
        {
            "hidden": [s for s in states if s.suspended],
            "changed": [s for s in states if not s.suspended],
        },
    )


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
        "logged_in": request.user.is_authenticated,
    }
    if request.method == "POST":
        if "claim" in request.POST:
            return _claim(request, cards)
        if "hidden" in request.POST or "frequency" in request.POST:
            return _card_option(request, cards)
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
    if request.user.is_authenticated:
        # The card just hidden from the question page, to offer an Undo.
        context["hidden_card"] = cards.filter(
            pk=_int(request.GET.get("hidden")),
            states__user=request.user,
            states__suspended=True,
        ).first()
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


def _card_option(request, cards):
    """Hides a card, shows it again, or changes how often it comes back: from the
    result page (with the review) or from the question page (with the card)."""
    if not request.user.is_authenticated:
        raise Http404("Log in to change how a card is shown")
    review = None
    if "review" in request.POST:
        review = get_object_or_404(
            Review.objects.select_related("card"),
            pk=_int(request.POST.get("review")),
            user=request.user,
            card__in=cards,
        )
        card = review.card
    else:
        card = get_object_or_404(cards, pk=_int(request.POST.get("card")))
    if "frequency" in request.POST:
        if request.POST["frequency"] not in Frequency.values:
            raise Http404("No such frequency")
        set_frequency(request.user, card, request.POST["frequency"])
    if "hidden" in request.POST:
        hidden = request.POST["hidden"] == "1"
        set_hidden(request.user, card, hidden)
    if review is not None:
        return redirect(f"{request.path}?review={review.pk}")
    hidden_query = f"&hidden={card.pk}" if request.POST.get("hidden") == "1" else ""
    return redirect(f"{request.path}?after={card.pk}{hidden_query}")


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
    state = None
    if review is not None:
        state = CardState.objects.filter(user=review.user, card=card).first()
    context.update(
        card=card,
        rows=rows,
        verdict=Verdict(verdict),
        review=review,
        state=state,
        frequencies=Frequency.choices,
        has_labels=any(row["label"] for row in rows),
    )
    return render(request, "flashdeck/result.html", context)


def _nothing_due(request, context, cards):
    context["has_cards"] = cards.exists()
    if not request.user.is_authenticated:
        return render(request, "flashdeck/nothing_due.html", context)
    states = CardState.objects.filter(
        user=request.user, card__in=cards, suspended=False
    ).exclude(due=None)
    context.update(
        next_due=states.order_by("due").values_list("due", flat=True).first(),
        new_left=cards.exclude(states__user=request.user).exists(),
        quota_reached=new_cards_left(request.user) <= 0,
    )
    return render(request, "flashdeck/nothing_due.html", context)
