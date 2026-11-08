import secrets
from pathlib import PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import models, transaction
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel

from .conf import setting
from .images import IMAGE_EXTENSIONS, prepare_image, validate_image
from .marking import Verdict, normalise
from .scheduling import Frequency

# Paths of the app's own pages, which a subject or deck must not take as its slug.
RESERVED_SLUGS = {"settings", "progress", "reference"}


def validate_not_reserved(value):
    if value in RESERVED_SLUGS:
        raise ValidationError(f"“{value}” is the name of one of the app's own pages.")


class Subject(models.Model):
    """Something to learn, such as French or dog breeds, made up of decks."""

    slug = models.SlugField(unique=True, validators=[validate_not_reserved])
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    language = models.CharField(
        max_length=35,
        blank=True,
        help_text="The language of the answers as a code (BCP 47), such as fr or "
        "de, for screen readers and phone keyboards; blank if none.",
    )
    characters = models.CharField(
        max_length=300,
        blank=True,
        help_text="Characters offered as buttons for typing answers, separated by "
        "spaces, such as: é è ê ç",
    )
    case_sensitive = models.BooleanField(
        "case-sensitive",
        default=False,
        help_text="If set, an answer that differs only in capitals is marked nearly "
        "right (for German nouns, for example); otherwise capitals are ignored.",
    )
    position = models.IntegerField(
        default=0, help_text="Subjects are listed in order of this number."
    )

    class Meta:
        ordering = ["position", "title"]

    def __str__(self):
        return self.title

    def character_list(self):
        return self.characters.split()


class Deck(models.Model):
    """A set of cards on one topic within a subject."""

    subject = models.ForeignKey(Subject, related_name="decks", on_delete=models.CASCADE)
    slug = models.SlugField(
        help_text="Unique within the subject.", validators=[validate_not_reserved]
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    is_public = models.BooleanField(
        "public",
        default=False,
        help_text="Anyone can practise a public deck; a private one only users "
        "with the permission “Can practise private decks”.",
    )
    position = models.IntegerField(
        default=0, help_text="Decks are listed in order of this number."
    )

    class Meta:
        ordering = ["subject", "position", "title"]
        constraints = [
            models.UniqueConstraint(
                fields=["subject", "slug"], name="flashdeck_deck_unique_slug"
            )
        ]
        permissions = [("practise_private", "Can practise private decks")]

    def __str__(self):
        return f"{self.subject}: {self.title}"


def card_image_path(card, filename):
    """A random name in the subject's directory, so that the name of the file
    cannot give the answer away."""
    suffix = PurePosixPath(filename).suffix.lower().replace(".jpeg", ".jpg")
    directory = setting("UPLOAD_DIR")
    return f"{directory}/{card.deck.subject.slug}/{secrets.token_hex(8)}{suffix}"


class Card(ClusterableModel):
    """A prompt (text, an image or both) and one or more answers to it."""

    deck = models.ForeignKey(Deck, related_name="cards", on_delete=models.CASCADE)
    key = models.SlugField(
        max_length=100,
        help_text="Identifies the card within its deck, such as in exported bundles.",
    )
    prompt = models.TextField(blank=True)
    image = models.FileField(
        upload_to=card_image_path,
        blank=True,
        validators=[FileExtensionValidator(IMAGE_EXTENSIONS), validate_image],
        help_text="PNG, JPEG, WebP or SVG. Photographs are reduced in size and "
        "their metadata removed.",
    )
    image_alt = models.CharField(
        "image description",
        max_length=300,
        blank=True,
        help_text="For screen readers. It must not give the answer away.",
    )
    image_credit = models.CharField(
        max_length=300, blank=True, help_text="Shown after the card is answered."
    )
    image_licence = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True, help_text="Shown after the card is answered.")
    position = models.IntegerField(
        default=0, help_text="New cards are introduced in order of this number."
    )

    class Meta:
        ordering = ["deck", "position", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["deck", "key"], name="flashdeck_card_unique_key"
            )
        ]

    def __str__(self):
        return " · ".join(self.prompt.split("\n")).strip() or self.key

    def save(self, *args, **kwargs):
        old_image = None
        if self.pk:
            old_image = (
                type(self)
                .objects.filter(pk=self.pk)
                .values_list("image", flat=True)
                .first()
            )
        if self.image and not self.image._committed:
            prepared = prepare_image(self.image.file, self.image.name)
            self.image.save(prepared.name, prepared, save=False)
        super().save(*args, **kwargs)
        if old_image and old_image != self.image.name:
            _delete_file_on_commit(self.image.storage, old_image)


@receiver(post_delete, sender=Card)
def _delete_card_image(sender, instance, **kwargs):
    if instance.image:
        _delete_file_on_commit(instance.image.storage, instance.image.name)


def _delete_file_on_commit(storage, name):
    transaction.on_commit(lambda: storage.delete(name))


class Answer(models.Model):
    """One of a card's answers, each marked separately: a vocabulary card has one,
    a conjugation table six (labelled je, tu, …)."""

    card = ParentalKey(Card, related_name="answers", on_delete=models.CASCADE)
    label = models.CharField(
        max_length=100, blank=True, help_text="Shown before the answer box."
    )
    text = models.CharField("answer", max_length=500)
    alternatives = models.TextField(
        blank=True, help_text="Other answers that are marked right, one per line."
    )
    sort_order = models.IntegerField(null=True, blank=True, editable=False)

    # Used by Wagtail's InlinePanel to keep the answers in order.
    sort_order_field = "sort_order"

    class Meta:
        ordering = ["sort_order", "id"]

    def __str__(self):
        return f"{self.card} ({self.label})" if self.label else str(self.card)

    def accepted(self):
        """Every answer marked right, the model answer first."""
        lines = (line.strip() for line in self.alternatives.splitlines())
        return [self.text, *(line for line in lines if line)]

    def add_alternative(self, text):
        """Adds an answer to those marked right, unless it already is one."""
        case_sensitive = self.card.deck.subject.case_sensitive
        form = normalise(text, case_sensitive=case_sensitive)
        if any(
            normalise(a, case_sensitive=case_sensitive) == form for a in self.accepted()
        ):
            return False
        self.alternatives = "\n".join([*self.accepted()[1:], text.strip()])
        self.save(update_fields=["alternatives"])
        return True


class CardState(models.Model):
    """One user's progress with one card: its spaced-repetition (FSRS) state, and
    the user's choices of how often it comes back and whether it is hidden.

    A card hidden before it was ever answered has a state with no FSRS state and
    no due date; showing it again deletes the state, so that it is new again.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="flashdeck_states",
        on_delete=models.CASCADE,
    )
    card = models.ForeignKey(Card, related_name="states", on_delete=models.CASCADE)
    due = models.DateTimeField(null=True, blank=True, db_index=True)
    fsrs = models.JSONField(null=True, blank=True)
    suspended = models.BooleanField(
        "hidden", default=False, help_text="Never shown in practice."
    )
    frequency = models.CharField(
        max_length=10, choices=Frequency.choices, default=Frequency.NORMAL
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "card"], name="flashdeck_cardstate_unique"
            )
        ]

    def __str__(self):
        return f"{self.user}: {self.card}"


class Review(models.Model):
    """One answer to a card by a user, as marked."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="flashdeck_reviews",
        on_delete=models.CASCADE,
    )
    card = models.ForeignKey(Card, related_name="reviews", on_delete=models.CASCADE)
    created = models.DateTimeField(default=timezone.now, db_index=True)
    verdict = models.CharField(max_length=10, choices=Verdict.choices)
    # One entry per answer: {"answer": id, "given": text, "verdict": verdict,
    # "expected": the accepted answer compared with}.
    results = models.JSONField(default=list)
    # The card's FSRS state before this review (None for a new card), so that it
    # can be rescheduled if the user claims that an answer was right.
    state_before = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-created", "-id"]

    def __str__(self):
        return f"{self.user}: {self.card} ({self.get_verdict_display()})"


class ClaimedAnswer(models.Model):
    """An answer that a user said was right, although it matched none of the
    accepted answers. It is marked right for that user from then on; accepting it
    adds it to the answers marked right for everyone."""

    class Status(models.TextChoices):
        PENDING = "pending", "To review"
        ACCEPTED = "accepted", "Accepted"
        REJECTED = "rejected", "Rejected"

    answer = models.ForeignKey(Answer, related_name="claims", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="flashdeck_claims",
        on_delete=models.CASCADE,
    )
    text = models.CharField("claimed answer", max_length=500)
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        constraints = [
            models.UniqueConstraint(
                fields=["answer", "user", "text"], name="flashdeck_claim_unique"
            )
        ]

    def __str__(self):
        return self.text

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.status == self.Status.ACCEPTED:
            self.answer.add_alternative(self.text)
