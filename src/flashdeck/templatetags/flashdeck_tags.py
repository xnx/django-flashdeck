from urllib.parse import urlsplit

import markdown
from django import template
from django.conf import settings
from django.shortcuts import resolve_url
from django.urls import NoReverseMatch, Resolver404, resolve
from django.utils.safestring import mark_safe

from ..conf import setting

register = template.Library()


@register.filter
def flashdeck_markdown(text):
    """Reference text written in Markdown (with tables), as HTML. Only editors
    write it, and they are trusted, so it is not sanitised."""
    html = markdown.markdown(text, extensions=["tables", "sane_lists"])
    return mark_safe(html)  # noqa: S308


def url_if_routed(url):
    """The URL (or URL name) as a path, if the site has a page there."""
    if not url:
        return None
    try:
        path = resolve_url(url)
        resolve(urlsplit(path).path)
    except (NoReverseMatch, Resolver404):
        return None
    return path


@register.inclusion_tag("flashdeck/_account.html", takes_context=True)
def flashdeck_account(context):
    """At the top of each page: Log in (to the site's LOGIN_URL, and back), or the
    user's name and Log out (at FLASHDECK_LOGOUT_URL)."""
    request = getattr(context, "request", None)
    if request is None:
        return {}
    user = request.user
    return {
        "show": True,
        "logged_in": user.is_authenticated,
        "user_name": user.is_authenticated
        and (user.get_short_name() or user.get_username()),
        "login_url": url_if_routed(settings.LOGIN_URL),
        "logout_url": url_if_routed(setting("LOGOUT_URL")),
        "next": request.get_full_path(),
        "csrf_token": context.get("csrf_token"),
    }
