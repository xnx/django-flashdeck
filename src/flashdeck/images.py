"""Card images: checked on upload, reduced in size and stripped of metadata.

Photographs often carry a caption or keywords (in EXIF, XMP or a JPEG comment)
that name what they show, which would give the answer away to anyone who looks
at the file, so only the pixels (and the colour profile) are kept.
"""

import io
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

from .conf import setting

IMAGE_EXTENSIONS = ["png", "jpg", "jpeg", "webp", "svg"]
_FORMATS = {".png": "PNG", ".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}


def validate_image(value):
    """Checks that a newly uploaded image is of the type its extension says.

    An SVG file is only checked for an <svg> element: as it can contain scripts,
    only trusted editors should be able to upload one.
    """
    if getattr(value, "_committed", True):
        return  # already stored, so checked when it was uploaded
    suffix = PurePosixPath(value.name).suffix.lower()
    value.seek(0)
    try:
        if suffix == ".svg":
            head = value.read(4096)
            if isinstance(head, bytes):
                head = head.decode("utf-8", "replace")
            if "<svg" not in head:
                raise ValidationError("This file is not an SVG image.")
            return
        try:
            with Image.open(value) as image:
                found = image.format
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as error:
            raise ValidationError(
                "This file is not an image that can be read."
            ) from error
        if found != _FORMATS.get(suffix):
            raise ValidationError(
                f"This is a {found} image, but its name ends in {suffix}."
            )
    finally:
        value.seek(0)


def prepare_image(file, name: str) -> ContentFile:
    """The image to store: reduced to fit IMAGE_MAX_SIZE, turned the right way up,
    and without metadata. SVG images are stored as they are."""
    suffix = PurePosixPath(name).suffix.lower()
    file.seek(0)
    data = file.read()
    if suffix == ".svg":
        return ContentFile(data, name="image.svg")
    with Image.open(io.BytesIO(data)) as original:
        fmt = original.format
        icc_profile = original.info.get("icc_profile")
        transparency = original.info.get("transparency")
        image = ImageOps.exif_transpose(original)
    image.info = {} if transparency is None else {"transparency": transparency}
    size = setting("IMAGE_MAX_SIZE")
    image.thumbnail((size, size))
    options = {}
    if fmt == "JPEG":
        if image.mode not in ("RGB", "L"):
            image = image.convert("RGB")
            icc_profile = None  # it described the old colour space
        options.update(quality=85, optimize=True)
    elif fmt == "WEBP":
        options.update(quality=85)
    elif fmt == "PNG":
        options.update(optimize=True)
    if icc_profile:
        options["icc_profile"] = icc_profile
    out = io.BytesIO()
    image.save(out, fmt, **options)
    return ContentFile(out.getvalue(), name=f"image{suffix}")
