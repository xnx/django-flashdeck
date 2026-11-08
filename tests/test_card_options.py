from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from fsrs import Card as FsrsCard
from fsrs import State

from flashdeck.models import CardState, Review, Subject
from flashdeck.scheduling import due_of, schedule
from tests.conftest import make_card
from tests.test_practice import answer, deck_url


def learnt(card, user):
    """A state for a card already in review, last seen ten days ago."""
    now = timezone.now()
    fsrs = FsrsCard(
        card_id=card.pk,
        state=State.Review,
        stability=10.0,
        difficulty=5.0,
        due=now,
        last_review=now - timedelta(days=10),
    ).to_dict()
    return CardState.objects.create(user=user, card=card, due=now, fsrs=fsrs)


def test_a_card_hidden_from_the_result_page_is_not_shown(
    client, user, public_deck, dog
):
    client.force_login(user)
    learnt(dog, user)
    answer(client, public_deck, dog, "chien")
    review = Review.objects.get()
    response = client.post(deck_url(public_deck), {"review": review.pk, "hidden": 1})
    assert response.url == f"{deck_url(public_deck)}?review={review.pk}"
    assert CardState.objects.get().suspended
    assert "will not be shown again" in client.get(response.url).content.decode()

    CardState.objects.update(due=timezone.now())  # due, but hidden
    page = client.get(deck_url(public_deck) + "?ahead=1").content.decode()
    assert "Nothing is due" in page and 'name="card"' not in page
    assert "1 due" not in client.get(reverse("flashdeck:index")).content.decode()

    client.post(deck_url(public_deck), {"review": review.pk, "hidden": 0})
    assert not CardState.objects.get().suspended
    assert f'value="{dog.pk}"' in client.get(deck_url(public_deck)).content.decode()


def test_a_new_card_hidden_from_the_question_page(
    client, user, public_deck, dog, settings
):
    settings.FLASHDECK_NEW_CARDS_PER_DAY = 1
    cat = make_card(public_deck, "cat", "cat", ["le chat"])
    client.force_login(user)
    assert (
        "Never show this card again"
        in client.get(deck_url(public_deck)).content.decode()
    )
    response = client.post(deck_url(public_deck), {"card": dog.pk, "hidden": 1})
    assert response.url == f"{deck_url(public_deck)}?after={dog.pk}&hidden={dog.pk}"
    state = CardState.objects.get()
    assert state.suspended and state.fsrs is None and state.due is None
    # Hiding it did not use up the day's one new card, so the cat comes next.
    page = client.get(response.url).content.decode()
    assert "“dog” will not be shown again" in page
    assert f'name="card" value="{cat.pk}"' in page

    client.post(deck_url(public_deck), {"card": dog.pk, "hidden": 0})
    assert not CardState.objects.exists()  # a new card again
    assert (
        f'name="card" value="{dog.pk}"'
        in client.get(deck_url(public_deck)).content.decode()
    )


def test_frequency_changes_when_a_card_comes_back(client, user, public_deck, dog):
    client.force_login(user)
    learnt(dog, user)
    answer(client, public_deck, dog, "chien")
    review = Review.objects.get()
    normal = CardState.objects.get().due
    page = client.get(f"{deck_url(public_deck)}?review={review.pk}").content.decode()
    assert 'value="normal" class="flashdeck-choice" aria-pressed="true"' in page

    client.post(deck_url(public_deck), {"review": review.pk, "frequency": "rarely"})
    state = CardState.objects.get()
    assert state.frequency == "rarely" and state.due > normal + timedelta(days=10)
    client.post(deck_url(public_deck), {"review": review.pk, "frequency": "more"})
    assert CardState.objects.get().due < normal

    data = {"review": review.pk, "frequency": "never"}
    assert client.post(deck_url(public_deck), data).status_code == 404


def test_the_frequency_is_used_for_later_reviews(db):
    now = timezone.now()
    state = schedule(None, "right", now - timedelta(days=30), 1)
    state = schedule(state, "right", now - timedelta(days=20), 1)
    later = {f: due_of(schedule(state, "right", now, 1, f)) for f in ("more", "rarely")}
    normal = due_of(schedule(state, "right", now, 1))
    assert later["more"] < normal < later["rarely"]


def test_the_card_settings_page(client, user, public_deck, private_deck, dog, etre):
    assert client.get(reverse("flashdeck:settings")).status_code == 404
    client.force_login(user)
    assert (
        "Hidden cards, and"
        not in client.get(reverse("flashdeck:index")).content.decode()
    )
    CardState.objects.create(user=user, card=etre, suspended=True)
    learnt(dog, user)
    CardState.objects.filter(card=dog).update(frequency="less")
    assert (
        "Hidden cards, and" in client.get(reverse("flashdeck:index")).content.decode()
    )

    page = client.get(reverse("flashdeck:settings")).content.decode()
    assert "être (to be) · conditionnel présent" in page
    assert "Animals: less often" in page

    client.post(reverse("flashdeck:settings"), {"card": etre.pk, "hidden": 0})
    client.post(reverse("flashdeck:settings"), {"card": dog.pk, "frequency": "normal"})
    assert list(CardState.objects.values_list("card_id", "frequency")) == [
        (dog.pk, "normal")
    ]


def test_the_app_s_page_names_cannot_be_slugs(db):
    with pytest.raises(ValidationError):
        Subject(slug="settings", title="Settings").full_clean()
