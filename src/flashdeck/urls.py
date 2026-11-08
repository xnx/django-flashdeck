from django.urls import path

from . import views

app_name = "flashdeck"

urlpatterns = [
    path("", views.index, name="index"),
    # Before the subjects, whose slugs cannot be "settings" or "progress" (see
    # RESERVED_SLUGS).
    path("settings/", views.card_settings, name="settings"),
    path("progress/", views.progress, name="progress"),
    path("<slug:subject>/", views.practise, name="subject"),
    # Before the decks, whose slugs cannot be "reference".
    path(
        "<slug:subject>/reference/",
        views.subject_reference,
        name="subject_reference",
    ),
    path(
        "<slug:subject>/reference/<slug:key>/",
        views.item_reference,
        name="item_reference",
    ),
    path("<slug:subject>/<slug:deck>/", views.practise, name="deck"),
    path(
        "<slug:subject>/<slug:deck>/reference/",
        views.deck_reference,
        name="deck_reference",
    ),
]
