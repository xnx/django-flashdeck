# django-flashdeck

The django-flashdeck package adds flashcards to a Django site. A card's prompt is text, an image or both, and its answers are typed and marked as right, nearly right or wrong. A card may have several answers, each marked separately, such as the six persons of a conjugated verb. Logged-in users get *spaced repetition*: each card comes back at increasing intervals, timed for just before it would be forgotten. Cards are grouped into *decks* (topics) within *subjects* (such as French or dog breeds), and a subject's decks are written, moved between sites and passed on as *bundles*: a YAML file and its images.

The package needs Django 5.2 or later, and works with or without Wagtail.

## Installation

Add the app and django-modelcluster (which it uses for editing a card's answers inline) to `INSTALLED_APPS`, include its URLs and migrate:

```python
INSTALLED_APPS = [
    ...,
    "modelcluster",
    "flashdeck",
]
```

```python
urlpatterns = [
    ...,
    path("flashcards/", include("flashdeck.urls")),
]
```

Subjects, decks, cards and claimed answers (see "Marking") are edited in Django's admin and, on a Wagtail site, in Wagtail's admin under *Flashcards*. A deck is either public, for anyone to practise, or private, for users with the permission *Can practise private decks* (`flashdeck.practise_private`), which superusers have.

## Settings

| Setting | Default | Meaning |
|---|---|---|
| `FLASHDECK_NEW_CARDS_PER_DAY` | `20` | New cards that each user starts per day, across all subjects |
| `FLASHDECK_IMAGE_MAX_SIZE` | `1200` | The size, in pixels, of the square that uploaded images are reduced to fit |
| `FLASHDECK_UPLOAD_DIR` | `"flashdeck"` | The directory, within the site's media storage, that holds card images |

## Templates and styles

Every page extends `flashdeck/page.html`, which by default is a page of its own. A site overrides it to put the app inside its own pages:

```django
{% extends "base.html" %}
{% block title %}{% block flashdeck_title %}{% endblock %}{% endblock %}
{% block content %}{% block flashdeck_content %}{% endblock %}{% endblock %}
```

The breadcrumb trail starts with `flashdeck/_crumbs_root.html`, which is empty by default; a site can override it to add its own links before *Flashcards*.

The app has its own stylesheet, with no dependence on a CSS framework. Its colours follow the page's text colour and `color-scheme` (light or dark), unless the site sets these custom properties on `.flashdeck`: `--flashdeck-ink`, `--flashdeck-muted`, `--flashdeck-line`, `--flashdeck-surface`, `--flashdeck-input`, `--flashdeck-accent`, `--flashdeck-accent-on`, `--flashdeck-right`, `--flashdeck-nearly` and `--flashdeck-wrong`.

## Marking

An answer is *right* if it matches one of the accepted answers (the model answer and its alternatives), ignoring capitals, runs of white space, typographic apostrophes and quotation marks (’ and '), a space before ; : ! or ? (which French typography puts there), and a final full stop, exclamation mark or question mark. It is *nearly right* if it differs from an accepted answer only in accents, punctuation, or ß, æ and œ written as ss, ae and oe. For a *case-sensitive* subject (such as German, whose nouns have capitals), a difference in capitals also makes an answer nearly right, not right. Anything else is *wrong*. A card is wrong if any of its answers is wrong, otherwise nearly right if any is nearly right, and otherwise right.

After an answer is marked nearly right or wrong, a logged-in user can press *I was right*. The answer is then saved as a *claimed answer*, the card is rescheduled as if it had been right, and the same answer is marked right for that user from then on. Claimed answers are listed in the admin, where accepting one adds it to the card's alternatives, so that it is marked right for everyone; rejecting one stops it being marked right for its user.

## Scheduling

Scheduling uses FSRS, the [Free Spaced Repetition Scheduler](https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm), through the fsrs package. A right answer counts as *Good*, a nearly right one as *Hard* and a wrong one as *Again*, so a card answered wrongly comes back within minutes.

A logged-in user is shown the card most overdue, otherwise a new card (up to `FLASHDECK_NEW_CARDS_PER_DAY`), and otherwise a page saying when the next card is due, with links to start another new card or to practise ahead. A visitor who is not logged in is shown cards from the public decks at random, and nothing is stored.

How often a card comes back is set by the chance of remembering it that FSRS aims for when it next comes back (its *target recall*): 0.9 normally. After answering a card, a logged-in user can choose under *Card options* to see it *More often* (0.95), *Less often* (0.85) or *Rarely* (0.8), which reschedules it at once. The effect compounds: after the second, third and fourth right answers, a card comes back after about 2, 11 and 46 days normally, but after 1, 3 and 8 days (more often), 4, 31 and 174 (less often) or 8, 76 and 525 (rarely). A user can also hide a card, from its question or its result, so that it is never shown again; hiding a card not yet answered does not count towards the day's new cards. Hidden cards, and cards with a changed frequency, are listed at `settings/` (linked from the index), where each choice can be undone.

The app's own pages take the slugs `settings`, `progress` and `reference`, which a subject or deck therefore cannot have.


## Progress

The Progress page (`progress/`, for logged-in users) shows:

- the number of cards answered today, the percentage right and the number of days in a row with at least one answer;
- the answers on each of the last 30 days, as a bar chart split into right, nearly right and wrong (with the same figures as a table);
- for each deck, the cards seen, those *well learnt* (coming back after 21 days or more), those due, and the percentage right over the last 30 days;
- the cards most often missed (answered wrong or nearly right), and, for decks whose cards have labelled answers, the labels most often missed, such as the *nous* form of the subjonctif.

A right answer given after looking at the reference counts as nearly right, as it does for scheduling. The result of each answer also shows a one-line summary of the day.

## Reference

Each subject, deck and *item* has a reference page, generated from the cards:

- a deck's page (`<subject>/<deck>/reference/`) shows the deck's cards as a table, with their answers and notes;
- an item's page (`<subject>/reference/<key>/`) shows the cards that share a key across the subject's decks; for a subject whose decks are the tenses of verbs, keyed by verb, that is one verb in every tense;
- a subject's page (`<subject>/reference/`) lists its decks and an index of its items.

A subject and a deck can also have reference text of their own (rules, tables of endings, exceptions), written in Markdown with tables, which heads its page. Only editors write it, and it is not sanitised. Each page has a search, which narrows the table or index as one types, ignoring accents, capitals and punctuation, and matches every prompt and every accepted answer, so that a form met in a text (*serais*) finds its verb.

On a card, the *Reference* button or ⌘K (Ctrl+K) opens the card's deck reference in a dialog over the card, so that what has been typed is kept; its links open within the dialog, and Esc closes it. Opening it before marking makes a right answer count as nearly right, so that the card comes back sooner.

## Images

Card images are stored with the site's media files, in `<FLASHDECK_UPLOAD_DIR>/<subject>/`, under random names: a file named after its subject (`beagle.jpg`) would give the answer away in the page. Photographs (PNG, JPEG and WebP) are reduced to `FLASHDECK_IMAGE_MAX_SIZE`, turned the right way up and stripped of their metadata (EXIF, XMP and comments), which often names what they show; only their colour profile is kept. SVG images are stored as they are. An SVG file can contain scripts, so only trusted editors should be able to upload one. A replaced image's file is deleted, as is a deleted card's.

The images are not kept in Wagtail's image library, whose files all share one directory, which would make a subject's images hard to move to another site or pass on.

## Bundles

A bundle is a directory, or a zip file, holding `cards.yaml` and the image files that it names:

```yaml
format: flashdeck/1
subject:
  slug: french
  title: French
  language: fr                      # for screen readers and phone keyboards
  characters: à â ç é è ê î ô ù û   # buttons for typing them
  case_sensitive: false
  reference: …                      # Markdown, for the subject's reference page
decks:
- slug: conditionnel
  title: 'Irregular verbs: conditionnel présent'
  public: false
  reference: |-
    The stem of the futur simple with the endings of the imparfait.
  cards:
  - key: etre                       # identifies the card within its deck
    prompt: |-
      être (to be)
      conditionnel présent
    answers:
    - {label: je, text: serais}
    - {label: tu, text: serais}
    # …
    notes: 'Stem: ser- (irregular).'
- slug: animals
  title: Animals
  public: true
  cards:
  - key: dog
    prompt: dog
    answer: le chien                # a single answer
  - key: beagle
    image: images/beagle.jpg
    image_alt: A photograph of a dog
    image_credit: A. Photographer, Wikimedia Commons
    image_licence: CC BY-SA 4.0
    answers:
    - {text: beagle, alternatives: [le beagle]}
```

An answer is either its text, or a mapping with `text` and optionally `label` and `alternatives`. YAML reads an unquoted `yes`, `no`, `on` or `off` as true or false, so answers such as the French pronoun *on* must be quoted; the import stops with a message if one is not.

```bash
python manage.py flashdeck_import decks/french            # or a .zip file
python manage.py flashdeck_import decks/french --update
python manage.py flashdeck_export french french.zip       # or a directory
```

An import adds the subject, decks and cards that the site does not have, matching them by slug and key, and leaves existing ones alone. With `--update`, it also updates existing ones from the bundle. Alternatives accepted on the site are kept, an image already on a card is not replaced, and whether a deck is public is left as it is. An export writes everything about a subject, including edits made in the admin, as a bundle that can be imported elsewhere.

A script that generates a bundle can write its `cards.yaml` with `flashdeck.manifest.dump_manifest(data)`, which needs no Django set-up and puts short lists on one line and text of more than one line in literal blocks.

## Development

The package has its own tests and settings (in `tests/`), independent of any site:

```bash
uv run pytest packages/django-flashdeck
```

The package is kept in the scipython.com repository (`xnx/scipython3`, in `packages/django-flashdeck`) until its licence is decided. Its classifier `Private :: Do Not Upload` makes PyPI refuse an upload until then. `git subtree split --prefix packages/django-flashdeck -b flashdeck-only` makes a branch of its own history, from which it can become a repository of its own.
