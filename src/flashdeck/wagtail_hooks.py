"""Editing in Wagtail's admin, under a Flashcards menu. Wagtail loads this module
itself; on a site without Wagtail it is never imported."""

from django import forms
from wagtail.admin.panels import FieldPanel, InlinePanel, MultiFieldPanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet, SnippetViewSetGroup

from .models import Card, ClaimedAnswer, Deck, Subject
from .wagtail_views import BundlesViewSet


class SubjectViewSet(SnippetViewSet):
    model = Subject
    icon = "folder-open-inverse"
    list_display = ["title", "slug", "language", "position"]
    panels = [
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("language"),
        FieldPanel("characters"),
        FieldPanel("case_sensitive"),
        FieldPanel("position"),
    ]


class DeckViewSet(SnippetViewSet):
    model = Deck
    icon = "folder-inverse"
    list_display = ["title", "subject", "is_public", "position"]
    list_filter = ["subject", "is_public"]
    panels = [
        FieldPanel("subject"),
        FieldPanel("title"),
        FieldPanel("slug"),
        FieldPanel("description"),
        FieldPanel("is_public"),
        FieldPanel("position"),
    ]


class CardViewSet(SnippetViewSet):
    model = Card
    icon = "doc-full"
    list_display = ["__str__", "deck", "key"]
    list_filter = ["deck"]
    search_fields = ["prompt", "key"]
    search_backend_name = None  # search with the database, not Wagtail's index
    panels = [
        FieldPanel("deck"),
        FieldPanel("key"),
        FieldPanel("prompt"),
        MultiFieldPanel(
            [
                FieldPanel("image"),
                FieldPanel("image_alt"),
                FieldPanel("image_credit"),
                FieldPanel("image_licence"),
            ],
            heading="Image",
        ),
        InlinePanel(
            "answers",
            label="Answer",
            min_num=1,
            panels=[
                FieldPanel("label"),
                FieldPanel("text"),
                FieldPanel("alternatives", widget=forms.Textarea(attrs={"rows": 2})),
            ],
        ),
        FieldPanel("notes"),
        FieldPanel("position"),
    ]


class ClaimedAnswerViewSet(SnippetViewSet):
    model = ClaimedAnswer
    icon = "help"
    menu_label = "Claimed answers"
    list_display = ["text", "answer", "user", "status", "created"]
    list_filter = ["status"]
    panels = [
        FieldPanel("answer", read_only=True),
        FieldPanel("text", read_only=True),
        FieldPanel("user", read_only=True),
        FieldPanel(
            "status",
            help_text="Accepting an answer marks it right for everyone, by adding it "
            "to the card's other answers.",
        ),
    ]


class FlashcardsGroup(SnippetViewSetGroup):
    menu_label = "Flashcards"
    menu_icon = "tasks"
    menu_name = "flashdeck"
    items = (
        SubjectViewSet,
        DeckViewSet,
        CardViewSet,
        ClaimedAnswerViewSet,
        BundlesViewSet,
    )


register_snippet(FlashcardsGroup)
