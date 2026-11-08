from django.core.management.base import BaseCommand, CommandError

from flashdeck.bundles import BundleError, import_bundle


class Command(BaseCommand):
    help = (
        "Imports a bundle of flashcards: a directory or zip file holding cards.yaml "
        "and its images. Cards not on the site are added; existing ones are left "
        "alone unless --update is given."
    )

    def add_arguments(self, parser):
        parser.add_argument("bundle", help="The bundle's directory or zip file.")
        parser.add_argument(
            "--update",
            action="store_true",
            help="Also update existing subjects, decks and cards from the bundle. "
            "Answers accepted on the site are kept, images already on a card are not "
            "replaced, and whether a deck is public is left as it is.",
        )

    def handle(self, bundle, update, **options):
        try:
            counts = import_bundle(bundle, update=update)
        except BundleError as error:
            raise CommandError(str(error)) from error
        summary = ", ".join(f"{n} {what}" for what, n in counts.items())
        self.stdout.write(summary or "Nothing to import.")
