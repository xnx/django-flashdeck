from django.urls import path

from . import views

app_name = "flashdeck"

urlpatterns = [
    path("", views.index, name="index"),
    path("<slug:subject>/", views.practise, name="subject"),
    path("<slug:subject>/<slug:deck>/", views.practise, name="deck"),
]
