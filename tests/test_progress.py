from datetime import datetime, time, timedelta

from django.urls import reverse
from django.utils import timezone

from flashdeck import stats
from flashdeck.models import CardState, Review
from tests.test_card_options import learnt
from tests.test_practice import answer, deck_url


def noon(days_ago):
    day = timezone.localdate() - timedelta(days=days_ago)
    return timezone.make_aware(datetime.combine(day, time(12)))


def review(user, card, verdict, days_ago=0, looked_up=False, results=None):
    return Review.objects.create(
        user=user,
        card=card,
        created=noon(days_ago),
        verdict=verdict,
        looked_up=looked_up,
        results=results or [],
    )


def test_daily_counts_and_days_in_a_row(user, dog):
    review(user, dog, "right")
    review(user, dog, "right", looked_up=True)  # counts as nearly right
    review(user, dog, "claimed")
    review(user, dog, "wrong", days_ago=1)
    review(user, dog, "nearly", days_ago=2)
    review(user, dog, "right", days_ago=5)
    days = stats.daily(user)
    assert len(days) == 30 and days[-1].date == timezone.localdate()
    assert (days[-1].right, days[-1].nearly, days[-1].wrong) == (2, 1, 0)
    assert days[-2].wrong == 1 and days[-6].right == 1 and days[-4].total == 0
    assert stats.days_in_a_row(user) == 3
    tally, in_a_row = stats.today(user)
    assert (tally.total, tally.percent_right, in_a_row) == (3, 67, 3)


def test_days_in_a_row_count_from_yesterday_until_today_s_first_answer(user, dog):
    review(user, dog, "right", days_ago=1)
    review(user, dog, "right", days_ago=2)
    assert stats.days_in_a_row(user) == 2


def test_deck_progress(user, public_deck, dog):
    from tests.conftest import make_card

    cat = make_card(public_deck, "cat", "cat", ["le chat"])
    make_card(public_deck, "cow", "cow", ["la vache"])
    learnt(dog, user)  # last seen 10 days ago, due now
    state = learnt(cat, user)
    state.fsrs["due"] = (timezone.now() + timedelta(days=30)).isoformat()
    state.due = timezone.now() + timedelta(days=30)
    state.save()
    review(user, dog, "right")
    review(user, cat, "wrong")
    (row,) = stats.decks(user, [public_deck])
    assert (row.cards, row.seen, row.due, row.well_learnt) == (3, 2, 1, 1)
    assert row.recent.percent_right == 50
    CardState.objects.filter(card=dog).update(suspended=True)
    (row,) = stats.decks(user, [public_deck])
    assert (row.due, row.hidden) == (0, 1)


def test_the_most_missed_cards_and_answers(user, private_deck, etre, dog):
    je, nous = etre.answers.all()

    def conjugated(je_verdict, nous_verdict):
        return [
            {"answer": je.pk, "given": "", "verdict": je_verdict, "expected": ""},
            {"answer": nous.pk, "given": "", "verdict": nous_verdict, "expected": ""},
        ]

    for _ in range(5):
        review(user, etre, "wrong", results=conjugated("right", "wrong"))
    review(user, dog, "wrong")
    review(user, dog, "right")
    cards = stats.most_missed_cards(user, [private_deck, dog.deck])
    assert [(card, m.missed, m.total) for card, m in cards] == [
        (etre, 5, 5),
        (dog, 1, 2),
    ]
    answers = stats.most_missed_answers(user, [private_deck])
    assert [(label, m.percent, m.total) for _, label, m in answers] == [
        ("nous", 100, 5)
    ]


def test_the_progress_page(client, user, public_deck, dog):
    assert client.get(reverse("flashdeck:progress")).status_code == 404
    client.force_login(user)
    review(user, dog, "right")
    review(user, dog, "wrong", days_ago=1)
    page = client.get(reverse("flashdeck:progress")).content.decode()
    today = timezone.localdate()
    assert f'aria-label="{today.day} {today:%B}: 1 answered (1 right, 0 nearly' in page
    assert "<strong>1</strong> answered today" in page
    assert "<strong>2</strong> days in a row" in page
    assert "Animals" in page and "50% of 2" in page
    assert "missed 1 time out of 2" in page


def test_each_result_shows_the_day_so_far(client, user, public_deck, dog):
    client.force_login(user)
    response = answer(client, public_deck, dog, "chien")
    page = client.get(response.url).content.decode()
    assert "Today: 1 answered, 100% right." in page
    assert reverse("flashdeck:progress") in page
    assert (
        reverse("flashdeck:progress")
        in client.get(reverse("flashdeck:index")).content.decode()
    )


def test_an_answer_given_after_looking_it_up_comes_back_sooner(
    client, user, public_deck, dog
):
    client.force_login(user)
    learnt(dog, user)
    page = client.get(deck_url(public_deck)).content.decode()
    assert 'name="looked_up" value="0"' in page and "data-flashdeck-reference" in page
    answer(client, public_deck, dog, "chien")
    without = CardState.objects.get().due
    CardState.objects.all().delete()
    Review.objects.all().delete()
    learnt(dog, user)
    client.post(
        deck_url(public_deck),
        {"card": dog.pk, f"answer-{dog.answers.get().pk}": "chien", "looked_up": "1"},
    )
    review = Review.objects.get()
    assert review.looked_up and review.verdict == "right"
    assert CardState.objects.get().due < without
    page = client.get(f"{deck_url(public_deck)}?review={review.pk}").content.decode()
    assert "You looked at the reference first" in page
