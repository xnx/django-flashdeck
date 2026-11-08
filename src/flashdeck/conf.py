"""The app's settings. A site overrides one by setting FLASHDECK_<NAME>."""

from django.conf import settings

DEFAULTS = {
    # New cards introduced to each user per day, across all subjects.
    "NEW_CARDS_PER_DAY": 20,
    # Card images are reduced to fit a square of this size (in pixels) on upload.
    "IMAGE_MAX_SIZE": 1200,
    # The directory, within the site's media storage, that holds card images.
    "UPLOAD_DIR": "flashdeck",
    # The URL (or URL name) to log out at, by POST, for a link on the index; blank
    # for none. Logging in uses Django's LOGIN_URL.
    "LOGOUT_URL": "",
}


def setting(name):
    return getattr(settings, f"FLASHDECK_{name}", DEFAULTS[name])
