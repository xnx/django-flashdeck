from django.apps import AppConfig


class FlashdeckConfig(AppConfig):
    name = "flashdeck"
    verbose_name = "Flashcards"
    # Set here, so that the app's migrations do not depend on the site's setting.
    default_auto_field = "django.db.models.BigAutoField"
