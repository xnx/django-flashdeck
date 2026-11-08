"""The bundle format's manifest, cards.yaml. This module needs no Django set-up, so
that scripts which generate bundles can use it."""

import yaml

FORMAT = "flashdeck/1"
MANIFEST = "cards.yaml"


class _Dumper(yaml.SafeDumper):
    """Writes text of more than one line as a literal block (|-)."""


def _represent_text(dumper, text):
    style = "|" if "\n" in text else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", text, style=style)


_Dumper.add_representer(str, _represent_text)


def dump_manifest(data):
    """The text of cards.yaml for a bundle's data, written to be easy to read and
    edit: short lists and mappings on one line, and text of more than one line as
    a literal block."""
    return yaml.dump(
        data,
        Dumper=_Dumper,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=None,
        width=88,
    )
