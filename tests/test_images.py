import io
from pathlib import Path

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from flashdeck.images import prepare_image, validate_image
from flashdeck.models import Card

SVG = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"><title>Resistor</title></svg>'


def jpeg_with_caption(size=(3000, 2000)):
    image = Image.new("RGB", size, "tan")
    exif = Image.Exif()
    exif[0x010E] = "Beagle"  # ImageDescription
    out = io.BytesIO()
    image.save(out, "JPEG", exif=exif, comment="A beagle")
    return out.getvalue()


def png_with_caption():
    info = PngInfo()
    info.add_text("Description", "Beagle")
    out = io.BytesIO()
    Image.new("RGBA", (50, 40), (10, 20, 30, 128)).save(out, "PNG", pnginfo=info)
    return out.getvalue()


def test_photographs_are_reduced_and_lose_their_metadata():
    prepared = prepare_image(io.BytesIO(jpeg_with_caption()), "beagle.jpg")
    with Image.open(io.BytesIO(prepared.read())) as image:
        assert image.size == (1200, 800)
        assert not image.getexif()
        assert "comment" not in image.info


def test_png_text_is_removed_and_transparency_kept():
    prepared = prepare_image(io.BytesIO(png_with_caption()), "beagle.png")
    with Image.open(io.BytesIO(prepared.read())) as image:
        assert "Description" not in image.info
        assert image.mode == "RGBA"


def test_svg_images_are_kept_as_they_are():
    assert prepare_image(io.BytesIO(SVG), "resistor.svg").read() == SVG


@pytest.mark.parametrize(
    ("name", "content"),
    [("notes.png", b"not an image"), ("beagle.png", None), ("drawing.svg", b"<html>")],
)
def test_files_that_are_not_what_their_names_say_are_rejected(name, content):
    if content is None:
        content = jpeg_with_caption((20, 20))  # a JPEG called .png
    card = Card(image=SimpleUploadedFile(name, content))
    with pytest.raises(ValidationError):
        validate_image(card.image)


def test_an_uploaded_image_gets_a_random_name_in_its_subject(
    public_deck, settings, django_capture_on_commit_callbacks
):
    card = Card(deck=public_deck, key="beagle", prompt="Which breed?")
    card.image = SimpleUploadedFile("beagle.jpg", jpeg_with_caption())
    card.full_clean()
    card.save()
    name = Path(card.image.name)
    assert name.parent == Path("flashdeck/french")
    assert "beagle" not in name.name and name.suffix == ".jpg"
    first = Path(settings.MEDIA_ROOT) / card.image.name
    assert first.exists()

    # Replacing the image, or deleting the card, deletes the file.
    with django_capture_on_commit_callbacks(execute=True):
        card.image = SimpleUploadedFile("resistor.svg", SVG)
        card.save()
    assert not first.exists()
    second = Path(settings.MEDIA_ROOT) / card.image.name
    with django_capture_on_commit_callbacks(execute=True):
        card.delete()
    assert not second.exists()
