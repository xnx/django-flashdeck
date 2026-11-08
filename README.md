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
decks:
- slug: conditionnel
  title: 'Irregular verbs: conditionnel présent'
  public: false
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

An import adds the subject, decks and cards that the site does not have, matching them by slug and key, and leaves existing ones alone. With `--update`, it also updates existing ones from the bundle. Alternatives accepted on the site are kept, and an image already on a card is not replaced. An export writes everything about a subject, including edits made in the admin, as a bundle that can be imported elsewhere.

A script that generates a bundle can write its `cards.yaml` with `flashdeck.manifest.dump_manifest(data)`, which needs no Django set-up and puts short lists on one line and text of more than one line in literal blocks.

## Development

The package has its own tests and settings (in `tests/`), independent of any site:

```bash
uv run pytest packages/django-flashdeck
```

The package is kept in the scipython.com repository (`xnx/scipython3`, in `packages/django-flashdeck`) until its licence is decided. Its classifier `Private :: Do Not Upload` makes PyPI refuse an upload until then. `git subtree split --prefix packages/django-flashdeck -b flashdeck-only` makes a branch of its own history, from which it can become a repository of its own.
