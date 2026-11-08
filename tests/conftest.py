import pytest
from django.contrib.auth import get_user_model

from flashdeck.models import Answer, Card, Deck, Subject


@pytest.fixture(autouse=True)
def _media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


def make_card(deck, key, prompt, answers, **fields):
    """A card; each answer is a text, or a (label, text, alternatives) tuple."""
    card = Card.objects.create(deck=deck, key=key, prompt=prompt, **fields)
    for sort_order, answer in enumerate(answers):
        label, text, alternatives = (
            ("", answer, "") if isinstance(answer, str) else answer
        )
        Answer.objects.create(
            card=card,
            label=label,
            text=text,
            alternatives=alternatives,
            sort_order=sort_order,
        )
    return card


@pytest.fixture
def french(db):
    return Subject.objects.create(
        slug="french", title="French", language="fr", characters="é è ç"
    )


@pytest.fixture
def public_deck(french):
    return Deck.objects.create(
        subject=french, slug="animals", title="Animals", is_public=True
    )


@pytest.fixture
def private_deck(french):
    return Deck.objects.create(subject=french, slug="verbs", title="Verbs")


@pytest.fixture
def dog(public_deck):
    return make_card(public_deck, "dog", "dog", [("", "le chien", "chien")])


@pytest.fixture
def etre(private_deck):
    return make_card(
        private_deck,
        "etre",
        "être (to be)\nconditionnel présent",
        [("je", "serais", ""), ("nous", "serions", "")],
    )


@pytest.fixture
def user(db):
    return get_user_model().objects.create_superuser("christian", password="pw")


@pytest.fixture
def other_user(db):
    return get_user_model().objects.create_user("visitor", password="pw")
