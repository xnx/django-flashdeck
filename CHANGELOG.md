# Changelog

## 0.1.0 (11 November 2026)

The first release, from the app that runs at https://scipython.com/apps/flashcards/.

- Subjects, decks and cards, edited in Django's admin and, on a Wagtail site, in Wagtail's.
- Typed answers marked right, nearly right (a difference only in accents, capitals or punctuation) or wrong; cards with several labelled answers; characters to type as buttons.
- Spaced repetition (FSRS) for logged-in users, with cards hidden or shown more or less often; random cards from the public decks, with nothing stored, for visitors.
- Answers claimed as right by a user, reviewed in the admin.
- A Progress page, and reference pages generated from the cards, with a search and a dialog that opens from a card.
- Card images reduced in size and stripped of metadata, under random names.
- Bundles (`cards.yaml` and its images) imported and exported with management commands or, on a Wagtail site, in the admin.
