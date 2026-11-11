"""Importing and exporting bundles in Wagtail's admin (Flashcards → Import and
export), so that a bundle need not be on the server to be imported."""

import tempfile
from pathlib import Path

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import path
from django.views.generic import TemplateView
from wagtail.admin.views.generic.base import WagtailAdminTemplateMixin
from wagtail.admin.viewsets.base import ViewSet

from .bundles import BundleError, export_bundle, import_bundle
from .models import Subject

MAX_UPLOAD = 100 * 1024 * 1024
PERMISSIONS = ["flashdeck.add_card", "flashdeck.change_card"]


class ImportForm(forms.Form):
    bundle = forms.FileField(
        help_text="A zip file holding cards.yaml and the images it names."
    )
    update = forms.BooleanField(
        required=False,
        label="Update what is already on the site",
        help_text="Subjects, decks and cards already here are updated from the "
        "bundle; answers accepted here are kept, images are replaced only if they "
        "have changed, and whether each deck is public is kept. Otherwise they are left alone and only new "
        "ones are added.",
    )

    def clean_bundle(self):
        bundle = self.cleaned_data["bundle"]
        if bundle.size > MAX_UPLOAD:
            raise forms.ValidationError("The file is larger than 100 MB.")
        return bundle


class ExportForm(forms.Form):
    subject = forms.ModelChoiceField(queryset=Subject.objects.all())


class BundlesView(WagtailAdminTemplateMixin, TemplateView):
    page_title = "Import and export"
    header_icon = "upload"
    template_name = "flashdeck/admin/bundles.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.user.has_perms(PERMISSIONS):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        kwargs.setdefault("import_form", ImportForm())
        kwargs.setdefault("export_form", ExportForm())
        return super().get_context_data(**kwargs)

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "export":
            return self.export(request)
        form = ImportForm(request.POST, request.FILES)
        if form.is_valid():
            try:
                counts = self.import_upload(form.cleaned_data)
            except BundleError as error:
                form.add_error("bundle", str(error))
            else:
                summary = ", ".join(f"{n} {what}" for what, n in counts.items())
                messages.success(request, f"Imported: {summary or 'nothing new'}.")
                return redirect(request.path)
        return self.render_to_response(self.get_context_data(import_form=form))

    def import_upload(self, data):
        with tempfile.NamedTemporaryFile(suffix=".zip") as file:
            for chunk in data["bundle"].chunks():
                file.write(chunk)
            file.flush()
            return import_bundle(file.name, update=data["update"])

    def export(self, request):
        form = ExportForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(export_form=form))
        subject = form.cleaned_data["subject"]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / f"{subject.slug}.zip"
            export_bundle(subject, path)
            content = path.read_bytes()
        response = HttpResponse(content, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{subject.slug}.zip"'
        return response


class BundlesViewSet(ViewSet):
    name = "flashdeck_bundles"
    url_prefix = "flashcards/bundles"
    icon = "upload"
    menu_label = "Import and export"

    def get_urlpatterns(self):
        return [path("", BundlesView.as_view(), name="index")]
