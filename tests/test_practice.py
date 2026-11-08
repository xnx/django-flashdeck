from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from flashdeck.models import CardState, ClaimedAnswer, Review
from tests.conftest import make_card


def deck_url(deck):
    return reverse("flashdeck:deck", args=[deck.subject.slug, deck.slug])


def answer(client, deck, card, *texts):
    data = {"card": card.pk}
    for a, text in zip(card.answers.all(), texts, strict=True):
        data[f"answer-{a.pk}"] = text
    return client.post(deck_url(deck), data)


def test_visitors_see_only_public_decks(client, dog, etre, public_deck, private_deck):
    page = client.get(reverse("flashdeck:index")).content.decode()
    assert "Animals" in page and "Verbs" not in page
    assert client.get(deck_url(private_deck)).status_code == 404
    page = client.get(reverse("flashdeck:subject", args=["french"])).content.decode()
    assert f'name="card" value="{dog.pk}"' in page


def test_a_user_with_the_permission_sees_private_decks(
    client, user, etre, private_deck
):
    client.force_login(user)
    assert "Verbs" in client.get(reverse("flashdeck:index")).content.decode()
    page = client.get(deck_url(private_deck)).content.decode()
    assert "conditionnel présent" in page
    assert 'lang="fr"' in page and 'data-flashdeck-insert="é"' in page


def test_a_visitor_s_answer_is_marked_but_not_stored(client, dog, public_deck):
    response = answer(client, public_deck, dog, "Chien.")
    assert response.status_code == 200
    page = response.content.decode()
    assert "Right" in page and "I was right" not in page
    assert not Review.objects.exists() and not CardState.objects.exists()


def test_each_answer_on_a_card_is_marked(client, user, etre, private_deck):
    client.force_login(user)
    response = answer(client, private_deck, etre, "serais", "serons")
    review = Review.objects.get()
    assert response.url == f"{deck_url(private_deck)}?review={review.pk}"
    assert review.verdict == "wrong"
    assert [r["verdict"] for r in review.results] == ["right", "wrong"]
    page = client.get(response.url).content.decode()
    assert "serions" in page and page.count("I was right") == 1
    state = CardState.objects.get()
    assert state.due < timezone.now() + timedelta(minutes=2)  # wrong: back soon


def test_a_nearly_right_answer_counts_as_a_weak_pass(client, user, etre, private_deck):
    client.force_login(user)
    answer(client, private_deck, etre, "serais", "serîons")
    assert Review.objects.get().verdict == "nearly"
    assert "Nearly right" in client.get(answer_url(private_deck)).content.decode()


def answer_url(deck):
    return f"{deck_url(deck)}?review={Review.objects.latest('created').pk}"


def test_claiming_an_answer_remembers_it_for_that_user(
    client, user, other_user, dog, public_deck
):
    client.force_login(user)
    answer(client, public_deck, dog, "un chien")
    review = Review.objects.get()
    wrong_due = CardState.objects.get().due
    response = client.post(
        deck_url(public_deck), {"review": review.pk, "claim": dog.answers.get().pk}
    )
    assert response.status_code == 302
    review.refresh_from_db()
    assert review.verdict == "right"
    assert review.results[0]["verdict"] == "claimed"
    assert CardState.objects.get().due > wrong_due  # rescheduled as right
    claimed = ClaimedAnswer.objects.get()
    assert (claimed.text, claimed.status, claimed.user) == ("un chien", "pending", user)

    # Right for this user from now on, but not for anyone else...
    answer(client, public_deck, dog, "Un chien")
    assert Review.objects.latest("created").verdict == "right"
    client.force_login(other_user)
    answer(client, public_deck, dog, "un chien")
    assert Review.objects.latest("created").verdict == "wrong"

    # ...until it is accepted.
    claimed.status = ClaimedAnswer.Status.ACCEPTED
    claimed.save()
    assert dog.answers.get().accepted() == ["le chien", "chien", "un chien"]
    answer(client, public_deck, dog, "un chien")
    assert Review.objects.latest("created").verdict == "right"


def test_only_wrong_answers_can_be_claimed(client, user, dog, public_deck):
    client.force_login(user)
    answer(client, public_deck, dog, "chien")
    review = Review.objects.get()
    data = {"review": review.pk, "claim": dog.answers.get().pk}
    assert client.post(deck_url(public_deck), data).status_code == 404
    client.logout()
    assert client.post(deck_url(public_deck), data).status_code == 404


def test_due_cards_come_before_new_ones(client, user, public_deck, dog):
    cat = make_card(public_deck, "cat", "cat", ["le chat"])
    client.force_login(user)
    CardState.objects.create(user=user, card=cat, due=timezone.now(), fsrs={})
    page = client.get(deck_url(public_deck)).content.decode()
    assert f'name="card" value="{cat.pk}"' in page


@pytest.mark.parametrize("more", [False, True])
def test_new_cards_are_limited_per_day(client, user, public_deck, dog, settings, more):
    settings.FLASHDECK_NEW_CARDS_PER_DAY = 1
    make_card(public_deck, "cat", "cat", ["le chat"])
    client.force_login(user)
    answer(client, public_deck, dog, "chien")
    url = deck_url(public_deck) + ("?more=1" if more else "")
    page = client.get(url).content.decode()
    if more:
        assert "cat" in page and 'name="card"' in page
    else:
        assert "Nothing is due" in page and "Start a new card" in page


def test_a_bad_card_number_is_not_found(client, public_deck, dog):
    assert client.post(deck_url(public_deck), {"card": "x"}).status_code == 404
