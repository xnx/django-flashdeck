"""The app's settings. A site overrides one by setting FLASHDECK_<NAME>."""

from django.conf import settings

DEFAULTS = {
    # New cards introduced to each user per day, across all subjects.
    "NEW_CARDS_PER_DAY": 20,
    # Card images are reduced to fit a square of this size (in pixels) on upload.
    "IMAGE_MAX_SIZE": 1200,
    # The directory, within the site's media storage, that holds card images.
    "UPLOAD_DIR": "flashdeck",
}


def setting(name):
    return getattr(settings, f"FLASHDECK_{name}", DEFAULTS[name])
