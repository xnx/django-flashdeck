"""Marking typed answers as right, nearly right or wrong.

An answer is *right* if it matches an accepted answer once both are normalised (see
`normalise`), and *nearly right* if it differs from one only in accents, capitals
or punctuation (see `loosen`). Nothing else is forgiven.
"""

import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from django.db import models


class Verdict(models.TextChoices):
    RIGHT = "right", "Right"
    NEARLY = "nearly", "Nearly right"
    WRONG = "wrong", "Wrong"
    # Marked nearly right or wrong, then claimed as right by the user.
    CLAIMED = "claimed", "Claimed as right"


# Typographic variants that one keyboard produces and another does not.
_EQUIVALENTS = str.maketrans(
    {
        "’": "'",  # right single quotation mark, the French apostrophe
        "‘": "'",  # left single quotation mark
        "ʼ": "'",  # modifier letter apostrophe
        "“": '"',  # left double quotation mark
        "”": '"',  # right double quotation mark
        " ": " ",  # no-break space
        " ": " ",  # narrow no-break space, before ; : ! ? in French
        "‑": "-",  # non-breaking hyphen
    }
)
_SPACE_BEFORE_PUNCTUATION = re.compile(r"\s+([;:!?])")
_LETTERS_SPELT_OUT = str.maketrans(
    {"ß": "ss", "ẞ": "ss", "æ": "ae", "Æ": "ae", "œ": "oe", "Œ": "oe"}
)


def normalise(text: str, *, case_sensitive: bool = False) -> str:
    """The form of an answer that is compared for a right mark.

    Differences in Unicode composition, typographic apostrophes and quotation
    marks, runs of white space, a space before ; : ! or ? (which French typography
    puts there), and a final full stop, exclamation mark or question mark are all
    ignored, as are capitals unless `case_sensitive` is set.
    """
    text = unicodedata.normalize("NFC", text).translate(_EQUIVALENTS)
    text = " ".join(text.split())
    text = _SPACE_BEFORE_PUNCTUATION.sub(r"\1", text)
    text = text.rstrip(".!?").rstrip()
    # lower(), not casefold(), which would turn ß into ss.
    return text if case_sensitive else text.lower()


def loosen(text: str) -> str:
    """The form of an answer that is compared for a nearly-right mark.

    As `normalise`, but also without accents, capitals or punctuation (each mark
    of punctuation counts as a space), and with ß, æ and œ spelt out.
    """
    text = normalise(text).translate(_LETTERS_SPELT_OUT)
    text = "".join(
        c for c in unicodedata.normalize("NFD", text) if not unicodedata.combining(c)
    )
    text = "".join(c if c.isalnum() or c.isspace() else " " for c in text)
    return " ".join(text.split())


@dataclass(frozen=True)
class Mark:
    verdict: Verdict
    # The accepted answer that was matched or nearly matched, or else the first
    # (the model answer).
    expected: str


def mark(given: str, accepted: Sequence[str], *, case_sensitive: bool = False) -> Mark:
    """Marks one answer against the answers accepted for it."""
    if not accepted:
        raise ValueError("No accepted answers")
    strict = normalise(given, case_sensitive=case_sensitive)
    if not strict:
        return Mark(Verdict.WRONG, accepted[0])
    for form in accepted:
        if normalise(form, case_sensitive=case_sensitive) == strict:
            return Mark(Verdict.RIGHT, form)
    loose = loosen(given)
    if loose:
        for form in accepted:
            if loosen(form) == loose:
                return Mark(Verdict.NEARLY, form)
    return Mark(Verdict.WRONG, accepted[0])


def combine(verdicts: Iterable[str]) -> Verdict:
    """The verdict on a card from the verdicts on its answers: wrong if any is
    wrong, otherwise nearly right if any is nearly right, otherwise right."""
    verdicts = set(verdicts)
    if Verdict.WRONG in verdicts:
        return Verdict.WRONG
    if Verdict.NEARLY in verdicts:
        return Verdict.NEARLY
    return Verdict.RIGHT
