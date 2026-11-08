import pytest
from django.urls import reverse

from flashdeck.models import Deck
from tests.conftest import make_card

PRESENT = [("je", "suis", ""), ("tu", "es", ""), ("nous", "sommes", "")]


@pytest.fixture
def verbs(french, private_deck, etre):
    """Two decks of verbs, keyed by verb: the conditionnel (private_deck) and the
    présent, each with être; the présent also has avoir."""
    private_deck.title = "Irregular verbs: conditionnel présent"
    private_deck.reference = "| je | -ais |\n|----|------|\n| tu | -ais |"
    private_deck.save()
    present = Deck.objects.create(
        subject=french, slug="present", title="Irregular verbs: présent", position=-1
    )
    make_card(present, "etre", "être (to be)\nprésent", PRESENT, notes="Irregular.")
    make_card(present, "avoir", "avoir (to have)\nprésent", [("j’", "ai", "")])
    return present


def url(name, *args):
    return reverse(f"flashdeck:{name}", args=args)


def test_the_subject_reference(client, user, verbs):
    client.force_login(user)
    page = client.get(url("subject_reference", "french")).content.decode()
    assert page.index(">avoir (to have)<") < page.index(">être (to be)<")
    assert 'data-search="etre to be present / suis / je suis /' in page
    assert url("deck_reference", "french", "present") in page
    assert "<html" in page and "flashdeck-crumbs" in page


def test_the_deck_reference(client, user, verbs):
    client.force_login(user)
    page = client.get(url("deck_reference", "french", "verbs")).content.decode()
    assert "<table>\n<thead>\n<tr>\n<th>je</th>" in page  # the Markdown, as HTML
    assert '<span class="flashdeck-muted">nous </span><strong>serions</strong>' in page
    page = client.get(url("deck_reference", "french", "present")).content.decode()
    assert '<span class="flashdeck-muted">j’</span><strong>ai</strong>' in page
    assert "--flashdeck-rows: 2" in page  # three persons in two columns


def test_an_item_in_every_deck(client, user, verbs):
    client.force_login(user)
    page = client.get(url("item_reference", "french", "etre")).content.decode()
    assert "<h1>être (to be)</h1>" in page
    # In deck order, without the "Irregular verbs: " that every title shares.
    assert page.index(">présent</a></h2>") < page.index(
        ">conditionnel présent</a></h2>"
    )
    assert "<strong>sommes</strong>" in page and "Irregular." in page
    assert client.get(url("item_reference", "french", "nothing")).status_code == 404


def test_a_fragment_for_the_dialog(client, user, verbs):
    client.force_login(user)
    page = client.get(
        url("deck_reference", "french", "present") + "?fragment=1"
    ).content.decode()
    assert "<html" not in page and "flashdeck-crumbs" not in page
    assert "data-flashdeck-search" in page and "data-flashdeck-ref" in page


def test_visitors_see_only_the_public_decks(client, verbs, dog):
    page = client.get(url("subject_reference", "french")).content.decode()
    assert "Animals" in page and "Irregular verbs" not in page
    response = client.get(url("deck_reference", "french", "present"))
    assert response.status_code == 404
    assert client.get(url("item_reference", "french", "etre")).status_code == 404
