import io

import pytest
import yaml
from django.core.management import call_command
from PIL import Image

from flashdeck.bundles import BundleError, export_bundle, import_bundle
from flashdeck.models import Card, Subject

BUNDLE = {
    "format": "flashdeck/1",
    "subject": {
        "slug": "french",
        "title": "French",
        "language": "fr",
        "characters": ["é", "è", "ç"],
    },
    "decks": [
        {
            "slug": "conditionnel",
            "title": "Irregular verbs: conditionnel présent",
            "cards": [
                {
                    "key": "etre",
                    "prompt": "être (to be)\nconditionnel présent",
                    "answers": [
                        {"label": "je", "text": "serais"},
                        {"label": "nous", "text": "serions"},
                    ],
                    "notes": "Stem: ser-",
                }
            ],
        },
        {
            "slug": "animals",
            "title": "Animals",
            "public": True,
            "cards": [
                {"key": "dog", "prompt": "dog", "answer": "le chien"},
                {
                    "key": "beagle",
                    "image": "images/beagle.png",
                    "image_alt": "A photograph of a dog",
                    "image_credit": "A. Photographer",
                    "image_licence": "CC BY-SA 4.0",
                    "answers": [{"text": "beagle", "alternatives": ["le beagle"]}],
                },
            ],
        },
    ],
}


def png():
    out = io.BytesIO()
    Image.new("RGB", (40, 30), "tan").save(out, "PNG")
    return out.getvalue()


def write_bundle(path, data=BUNDLE, images=True):
    path.mkdir(parents=True, exist_ok=True)
    (path / "cards.yaml").write_text(yaml.safe_dump(data, allow_unicode=True))
    if images:
        (path / "images").mkdir(exist_ok=True)
        (path / "images" / "beagle.png").write_bytes(png())
    return path


def test_a_bundle_is_imported(db, tmp_path):
    counts = import_bundle(write_bundle(tmp_path / "french"))
    assert counts == {"subjects created": 1, "decks created": 2, "cards created": 3}
    subject = Subject.objects.get()
    assert subject.characters == "é è ç" and subject.language == "fr"
    etre = Card.objects.get(key="etre")
    assert [(a.label, a.text) for a in etre.answers.all()] == [
        ("je", "serais"),
        ("nous", "serions"),
    ]
    assert not etre.deck.is_public
    beagle = Card.objects.get(key="beagle")
    assert beagle.image.name.startswith("flashdeck/french/")
    assert beagle.answers.get().accepted() == ["beagle", "le beagle"]


def test_importing_again_changes_nothing_unless_asked(db, tmp_path):
    path = write_bundle(tmp_path / "french")
    import_bundle(path)
    answer = Card.objects.get(key="dog").answers.get()
    answer.add_alternative("chien")  # accepted on the site

    assert import_bundle(path) == {"cards unchanged": 3}

    data = yaml.safe_load((path / "cards.yaml").read_text())
    data["decks"][0]["cards"][0]["answers"].pop()  # nous
    data["decks"][1]["cards"][0]["prompt"] = "the dog"
    write_bundle(path, data, images=False)
    image = Card.objects.get(key="beagle").image.name
    counts = import_bundle(path, update=True)
    assert counts["cards updated"] == 3
    assert Card.objects.get(key="etre").answers.count() == 1
    dog = Card.objects.get(key="dog")
    assert dog.prompt == "the dog"
    assert dog.answers.get().accepted() == ["le chien", "chien"]
    assert Card.objects.get(key="beagle").image.name == image


def test_an_exported_bundle_can_be_imported_again(db, tmp_path):
    import_bundle(write_bundle(tmp_path / "french"))
    Card.objects.get(key="dog").answers.get().add_alternative("chien")
    assert export_bundle(Subject.objects.get(), tmp_path / "out.zip") == 3
    Subject.objects.all().delete()

    counts = import_bundle(tmp_path / "out.zip")
    assert counts["cards created"] == 3
    assert Card.objects.get(key="dog").answers.get().accepted() == ["le chien", "chien"]
    beagle = Card.objects.get(key="beagle")
    assert (beagle.image_credit, beagle.image_licence) == (
        "A. Photographer",
        "CC BY-SA 4.0",
    )
    with beagle.image.open("rb") as image:
        assert Image.open(image).size == (40, 30)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda d: d.pop("format"), "format: flashdeck/1"),
        (lambda d: d["decks"][1]["cards"][0].update(answer=True), "quotation marks"),
        (lambda d: d["decks"][1]["cards"][1].update(image="../x.png"), "not a path"),
        (lambda d: d["decks"][1]["cards"][1].update(image="images/x.png"), "not in"),
        (lambda d: d["decks"][0]["cards"][0].pop("answers"), "at least one answer"),
        (lambda d: d["decks"][0]["cards"][0].update(key="être"), "must be letters"),
    ],
)
def test_mistakes_in_a_bundle_are_reported(db, tmp_path, change, message):
    data = yaml.safe_load(yaml.safe_dump(BUNDLE))
    change(data)
    with pytest.raises(BundleError, match=message):
        import_bundle(write_bundle(tmp_path / "french", data))
    assert not Subject.objects.exists()


def test_the_commands(db, tmp_path, capsys):
    call_command("flashdeck_import", str(write_bundle(tmp_path / "french")))
    assert "3 cards created" in capsys.readouterr().out
    call_command("flashdeck_export", "french", str(tmp_path / "out"))
    assert "3 cards written" in capsys.readouterr().out
    assert (tmp_path / "out" / "images" / "animals").is_dir()
