import markdown
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter
def flashdeck_markdown(text):
    """Reference text written in Markdown (with tables), as HTML. Only editors
    write it, and they are trusted, so it is not sanitised."""
    html = markdown.markdown(text, extensions=["tables", "sane_lists"])
    return mark_safe(html)  # noqa: S308
