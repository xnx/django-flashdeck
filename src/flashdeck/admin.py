"""Editing in Django's admin. (On a Wagtail site, wagtail_hooks.py also adds the
same models to Wagtail's admin, as snippets.)"""

from django.contrib import admin

from .models import Answer, Card, ClaimedAnswer, Deck, Subject


@admin.register(Subject)
class SubjectAdmin(admin.ModelAdmin):
    list_display = ["title", "slug", "language", "position"]
    prepopulated_fields = {"slug": ["title"]}


@admin.register(Deck)
class DeckAdmin(admin.ModelAdmin):
    list_display = ["title", "subject", "is_public", "position"]
    list_filter = ["subject", "is_public"]
    prepopulated_fields = {"slug": ["title"]}


class AnswerInline(admin.TabularInline):
    model = Answer
    fields = ["label", "text", "alternatives"]
    extra = 1


@admin.register(Card)
class CardAdmin(admin.ModelAdmin):
    list_display = ["__str__", "deck", "key"]
    list_filter = ["deck__subject", "deck"]
    search_fields = ["prompt", "key"]
    inlines = [AnswerInline]

    def save_formset(self, request, form, formset, change):
        super().save_formset(request, form, formset, change)
        # Keep the answers in the order in which they appear on the form.
        kept = [
            f.instance
            for f in formset.forms
            if f.instance.pk and f not in formset.deleted_forms
        ]
        for sort_order, answer in enumerate(kept):
            if answer.sort_order != sort_order:
                answer.sort_order = sort_order
                answer.save(update_fields=["sort_order"])


@admin.register(ClaimedAnswer)
class ClaimedAnswerAdmin(admin.ModelAdmin):
    list_display = ["text", "answer", "user", "status", "created"]
    list_filter = ["status"]
    fields = ["answer", "user", "text", "status", "created"]
    readonly_fields = ["answer", "user", "text", "created"]
    actions = ["accept", "reject"]

    def has_add_permission(self, request):
        return False

    @admin.action(description="Accept: mark these answers right for everyone")
    def accept(self, request, queryset):
        for claimed in queryset.select_related("answer__card__deck__subject"):
            claimed.status = ClaimedAnswer.Status.ACCEPTED
            claimed.save()

    @admin.action(description="Reject")
    def reject(self, request, queryset):
        queryset.update(status=ClaimedAnswer.Status.REJECTED)
