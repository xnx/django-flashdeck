"""Bundles: a subject's decks and cards, with their images, as a directory or zip
file holding cards.yaml and the image files it names. Bundles are how decks are
written, generated, moved between sites and passed on; the README describes the
format.
"""

import io
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

import yaml
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.validators import validate_slug
from django.db import transaction

from .manifest import FORMAT, MANIFEST, dump_manifest
from .marking import normalise
from .models import RESERVED_SLUGS, Answer, Card, Deck, Subject


class BundleError(Exception):
    pass


class _Source:
    """Reads files from a bundle directory or zip file."""

    def __init__(self, path):
        self.path = Path(path)
        self.zip = None
        self.prefix = PurePosixPath()
        if self.path.is_file():
            if not zipfile.is_zipfile(self.path):
                raise BundleError(f"{self.path} is neither a directory nor a zip file.")
            self.zip = zipfile.ZipFile(self.path)
            # Allow the bundle to be one directory down, as when a directory is
            # zipped as a whole.
            manifests = [
                PurePosixPath(n)
                for n in self.zip.namelist()
                if PurePosixPath(n).name == MANIFEST
            ]
            if not manifests:
                raise BundleError(f"There is no {MANIFEST} in {self.path}.")
            self.prefix = min(manifests, key=lambda p: len(p.parts)).parent
        elif not self.path.is_dir():
            raise BundleError(f"There is no bundle at {self.path}.")

    def read(self, name):
        path = PurePosixPath(str(name))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise BundleError(f"{name!r} is not a path within the bundle.")
        try:
            if self.zip:
                return self.zip.read(str(self.prefix / path))
            return self.path.joinpath(*path.parts).read_bytes()
        except (KeyError, FileNotFoundError, IsADirectoryError) as error:
            raise BundleError(f"{name} is not in the bundle.") from error

    def close(self):
        if self.zip:
            self.zip.close()


def import_bundle(path, *, update=False):
    """Imports a bundle, adding the subject, decks and cards that are not on the
    site (matched by slug and by key). With `update`, existing ones are updated
    too, except that answers accepted on the site are kept, images already on a
    card are not replaced, and whether a deck is public is left as it is. Returns
    counts of what was done."""
    source = _Source(path)
    try:
        try:
            data = yaml.safe_load(source.read(MANIFEST))
        except yaml.YAMLError as error:
            raise BundleError(f"{MANIFEST} is not valid YAML: {error}") from error
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            raise BundleError(f"{MANIFEST} must start with “format: {FORMAT}”.")
        with transaction.atomic():
            return _import(data, source, update)
    finally:
        source.close()


def _import(data, source, update):
    counts = Counter()
    fields = _mapping(data.get("subject"), "subject")
    slug = _slug(fields.get("slug"), "subject", page_name=True)
    characters = fields.get("characters") or ""
    if isinstance(characters, list):
        characters = " ".join(_text(c, "subject characters") for c in characters)
    values = {
        "title": _text(fields.get("title"), "subject title", required=True),
        "description": _text(fields.get("description"), "subject description"),
        "language": _text(fields.get("language"), "subject language"),
        "characters": _text(characters, "subject characters"),
        "case_sensitive": bool(fields.get("case_sensitive", False)),
    }
    subject, created = Subject.objects.get_or_create(slug=slug, defaults=values)
    _count(counts, "subject", created, update, subject, values)

    for position, deck_data in enumerate(data.get("decks") or []):
        deck_data = _mapping(deck_data, f"deck {position + 1}")
        slug = _slug(deck_data.get("slug"), f"deck {position + 1}", page_name=True)
        where = f"deck {slug}"
        values = {
            "title": _text(deck_data.get("title"), f"{where}: title", required=True),
            "description": _text(deck_data.get("description"), f"{where}: description"),
            "is_public": bool(deck_data.get("public", False)),
            "position": position,
        }
        deck, created = Deck.objects.get_or_create(
            subject=subject, slug=slug, defaults=values
        )
        # Whether a deck is public is for the site to decide, so an update leaves
        # it as it is.
        values.pop("is_public")
        _count(counts, "deck", created, update, deck, values)
        for card_position, card_data in enumerate(deck_data.get("cards") or []):
            _import_card(deck, card_data, card_position, source, update, counts)
    return counts


def _count(counts, kind, created, update, obj, values):
    if created:
        counts[f"{kind}s created"] += 1
    elif update:
        for name, value in values.items():
            setattr(obj, name, value)
        obj.save()
        counts[f"{kind}s updated"] += 1


def _import_card(deck, data, position, source, update, counts):
    data = _mapping(data, f"deck {deck.slug}: card {position + 1}")
    key = _slug(data.get("key"), f"deck {deck.slug}: card {position + 1}")
    where = f"deck {deck.slug}: card {key}"
    answers = _answers(data, where)
    card = Card.objects.filter(deck=deck, key=key).first()
    if card is not None and not update:
        counts["cards unchanged"] += 1
        return
    new = card is None
    if new:
        card = Card(deck=deck, key=key)
    card.prompt = _text(data.get("prompt"), f"{where}: prompt")
    card.notes = _text(data.get("notes"), f"{where}: notes")
    card.image_alt = _text(data.get("image_alt"), f"{where}: image_alt")
    card.image_credit = _text(data.get("image_credit"), f"{where}: image_credit")
    card.image_licence = _text(data.get("image_licence"), f"{where}: image_licence")
    card.position = position
    image = data.get("image")
    if image and not card.image:
        card.image = File(
            io.BytesIO(source.read(image)), name=PurePosixPath(image).name
        )
    if not card.prompt and not card.image:
        raise BundleError(f"{where}: a card needs a prompt, an image or both.")
    try:
        card.full_clean(exclude=["deck"])
    except ValidationError as error:
        raise BundleError(f"{where}: {'; '.join(error.messages)}") from error
    card.save()

    existing = [] if new else list(card.answers.all())
    for sort_order, values in enumerate(answers):
        if sort_order < len(existing):
            answer = existing[sort_order]
            kept = answer.accepted()[1:]
        else:
            answer, kept = Answer(card=card), []
        answer.label = values["label"]
        answer.text = values["text"]
        answer.alternatives = "\n".join(
            _distinct(values["alternatives"] + kept, exclude=values["text"])
        )
        answer.sort_order = sort_order
        answer.save()
    for answer in existing[len(answers) :]:
        answer.delete()
    counts["cards created" if new else "cards updated"] += 1


def _distinct(forms, exclude):
    seen = {normalise(exclude)}
    out = []
    for form in forms:
        key = normalise(form)
        if key not in seen:
            seen.add(key)
            out.append(form)
    return out


def _answers(data, where):
    raw = data.get("answers")
    if raw is None and "answer" in data:
        raw = [data["answer"]]
    if not isinstance(raw, list) or not raw:
        raise BundleError(f"{where}: a card needs at least one answer.")
    answers = []
    for item in raw:
        if not isinstance(item, dict):
            item = {"text": item}
        alternatives = item.get("alternatives") or []
        if not isinstance(alternatives, list):
            alternatives = [alternatives]
        answers.append(
            {
                "label": _text(item.get("label"), f"{where}: label"),
                "text": _text(item.get("text"), f"{where}: answer", required=True),
                "alternatives": [
                    t
                    for t in (_text(a, f"{where}: alternative") for a in alternatives)
                    if t
                ],
            }
        )
    return answers


def _mapping(value, where):
    if not isinstance(value, dict):
        raise BundleError(f"{where}: expected a mapping of names to values.")
    return value


def _slug(value, where, *, page_name=False):
    """A slug or key; a subject's or deck's slug (`page_name`), which is part of
    its page's address, must not be the name of one of the app's own pages."""
    value = _text(value, f"{where}: slug or key", required=True)
    try:
        validate_slug(value)
    except ValidationError as error:
        raise BundleError(
            f"{where}: {value!r} must be letters, numbers, hyphens and underscores."
        ) from error
    if page_name and value in RESERVED_SLUGS:
        raise BundleError(f"{where}: {value!r} is the name of one of the app's pages.")
    return value


def _text(value, where, *, required=False):
    """A YAML value as text. YAML reads an unquoted yes, no, on or off as true or
    false, which is never meant here (on is a French pronoun)."""
    if isinstance(value, bool):
        raise BundleError(f"{where}: put {str(value).lower()!r} in quotation marks.")
    text = "" if value is None else str(value).strip()
    if required and not text:
        raise BundleError(f"{where}: missing.")
    return text


def export_bundle(subject, path):
    """Writes a subject's decks and cards, with their images, as a bundle: a zip
    file if `path` ends in .zip, otherwise a directory. Returns the number of
    cards."""
    path = Path(path)
    files = {}
    decks = []
    count = 0
    for deck in subject.decks.all():
        cards = []
        for card in deck.cards.prefetch_related("answers"):
            entry = {"key": card.key}
            if card.prompt:
                entry["prompt"] = card.prompt
            if card.image:
                name = f"images/{deck.slug}/{card.key}{PurePosixPath(card.image.name).suffix}"
                with card.image.open("rb") as image:
                    files[name] = image.read()
                entry["image"] = name
                for field in ("image_alt", "image_credit", "image_licence"):
                    if getattr(card, field):
                        entry[field] = getattr(card, field)
            entry["answers"] = [_export_answer(a) for a in card.answers.all()]
            if card.notes:
                entry["notes"] = card.notes
            cards.append(entry)
            count += 1
        deck_entry = {"slug": deck.slug, "title": deck.title}
        if deck.description:
            deck_entry["description"] = deck.description
        deck_entry["public"] = deck.is_public
        deck_entry["cards"] = cards
        decks.append(deck_entry)
    subject_entry = {"slug": subject.slug, "title": subject.title}
    for field in ("description", "language", "characters"):
        if getattr(subject, field):
            subject_entry[field] = getattr(subject, field)
    if subject.case_sensitive:
        subject_entry["case_sensitive"] = True
    manifest = dump_manifest(
        {"format": FORMAT, "subject": subject_entry, "decks": decks}
    )
    if path.suffix == ".zip":
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
            bundle.writestr(MANIFEST, manifest)
            for name, content in files.items():
                bundle.writestr(name, content)
    else:
        path.mkdir(parents=True, exist_ok=True)
        (path / MANIFEST).write_text(manifest, encoding="utf-8")
        for name, content in files.items():
            target = path.joinpath(*PurePosixPath(name).parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    return count


def _export_answer(answer):
    alternatives = answer.accepted()[1:]
    if not answer.label and not alternatives:
        return answer.text
    entry = {}
    if answer.label:
        entry["label"] = answer.label
    entry["text"] = answer.text
    if alternatives:
        entry["alternatives"] = alternatives
    return entry
