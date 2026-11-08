from django.urls import path

from . import views

app_name = "flashdeck"

urlpatterns = [
    path("", views.index, name="index"),
    # Before the subjects, whose slugs cannot be "settings" (see RESERVED_SLUGS).
    path("settings/", views.card_settings, name="settings"),
    path("<slug:subject>/", views.practise, name="subject"),
    path("<slug:subject>/<slug:deck>/", views.practise, name="deck"),
]
