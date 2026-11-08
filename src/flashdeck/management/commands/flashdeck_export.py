from django.core.management.base import BaseCommand, CommandError

from flashdeck.bundles import export_bundle
from flashdeck.models import Subject


class Command(BaseCommand):
    help = (
        "Exports a subject's decks and cards, with their images, as a bundle: a zip "
        "file if the name ends in .zip, otherwise a directory."
    )

    def add_arguments(self, parser):
        parser.add_argument("subject", help="The subject's slug.")
        parser.add_argument("bundle", help="The directory or zip file to write.")

    def handle(self, subject, bundle, **options):
        try:
            subject = Subject.objects.get(slug=subject)
        except Subject.DoesNotExist as error:
            raise CommandError(f"There is no subject {subject!r}.") from error
        count = export_bundle(subject, bundle)
        self.stdout.write(f"{count} cards written to {bundle}.")
