"""Reference pages, generated from the cards: a deck's cards as a table, and a
subject's *items*, each being the cards that share a key across its decks (for
verbs, each verb in every tense)."""

import os
from dataclasses import dataclass, field

from .marking import loosen
from .models import Card


@dataclass
class Form:
    """One answer as shown in a reference: its label, its text, and the other
    answers that are also right."""

    label: str
    text: str
    alternatives: list

    @property
    def prefix(self):
        """The label, with a space after it unless it ends in an apostrophe (j’)."""
        if not self.label:
            return ""
        return self.label if self.label[-1] in "’'" else f"{self.label} "


def forms(card):
    return [
        Form(a.label, a.text, a.accepted()[1:])
        for a in card.answers.all()  # prefetched
    ]


def rows(card):
    """Rows of the forms grid: two columns, filled downwards, so that a verb's six
    persons read je, tu, il down the first and nous, vous, ils down the second."""
    return (len(card.answers.all()) + 1) // 2


def search_text(cards):
    """The text that the search box matches, in the folded form that both it and
    flashdeck.js compare (see marking.loosen): every prompt and answer."""
    parts = []
    for card in cards:
        parts.append(card.prompt)
        for answer in card.answers.all():
            parts.extend(answer.accepted())
            if answer.label:
                parts.append(f"{answer.label} {answer.text}")
    return " / ".join(loosen(part) for part in parts if part)


def name(card):
    """A card's name in a reference: the first line of its prompt, or its key."""
    return card.prompt.split("\n")[0].strip() or card.key


@dataclass
class Item:
    key: str
    name: str
    cards: list = field(default_factory=list)

    @property
    def search(self):
        return search_text(self.cards)


def cards_in(decks):
    return (
        Card.objects.filter(deck__in=decks)
        .select_related("deck__subject")
        .prefetch_related("answers")
        .order_by("deck__position", "deck__title", "deck_id", "position", "id")
    )


def items(decks):
    """The subject's items, in alphabetical order of name (ignoring accents)."""
    found = {}
    for card in cards_in(decks):
        item = found.setdefault(card.key, Item(card.key, name(card)))
        item.cards.append(card)
    return sorted(found.values(), key=lambda item: loosen(item.name))


def short_titles(decks):
    """Deck titles without the part they all share up to a colon, such as
    "Irregular verbs: ", which repeats on an item's page."""
    titles = {deck.pk: deck.title for deck in decks}
    if len(titles) > 1:
        common = os.path.commonprefix(list(titles.values()))
        cut = common.rfind(": ")
        if cut > 0:
            return {pk: title[cut + 2 :] for pk, title in titles.items()}
    return titles
