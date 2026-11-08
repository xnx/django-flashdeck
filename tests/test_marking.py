from flashdeck.marking import Verdict, combine, mark


def test_typography_and_final_punctuation_are_ignored():
    accepted = ["Vous ne pensez pas que je devrais m’inquiéter."]
    given = "vous ne pensez pas  que je devrais m'inquiéter"
    assert mark(given, accepted).verdict == Verdict.RIGHT
    assert mark("Ça va?", ["Ça va ?"]).verdict == Verdict.RIGHT
    assert mark("ça va ?", ["Ça va ?"]).verdict == Verdict.RIGHT


def test_a_difference_only_in_accents_is_nearly_right():
    result = mark("etre", ["être"])
    assert result.verdict == Verdict.NEARLY
    assert result.expected == "être"


def test_a_difference_only_in_punctuation_is_nearly_right():
    assert mark("peut etre", ["peut-être"]).verdict == Verdict.NEARLY
    assert mark("j ai", ["j’ai"]).verdict == Verdict.NEARLY


def test_capitals_are_ignored_unless_the_subject_is_case_sensitive():
    assert mark("der hund", ["der Hund"]).verdict == Verdict.RIGHT
    assert mark("der hund", ["der Hund"], case_sensitive=True).verdict == Verdict.NEARLY


def test_sharp_s_is_nearly_ss():
    assert mark("Straße", ["Straße"], case_sensitive=True).verdict == Verdict.RIGHT
    assert mark("Strasse", ["Straße"], case_sensitive=True).verdict == Verdict.NEARLY


def test_wrong_and_empty_answers_show_the_model_answer():
    result = mark("serai", ["serais", "serais-je"])
    assert result.verdict == Verdict.WRONG
    assert result.expected == "serais"
    assert mark("", ["serais"]).verdict == Verdict.WRONG
    assert mark(" ?", ["serais"]).verdict == Verdict.WRONG


def test_alternatives_are_marked_right():
    result = mark("suis allée", ["suis allé", "suis allée", "suis allé(e)"])
    assert result.verdict == Verdict.RIGHT
    assert result.expected == "suis allée"


def test_the_verdict_on_a_card():
    assert combine(["right", "nearly", "right"]) == Verdict.NEARLY
    assert combine(["right", "nearly", "wrong"]) == Verdict.WRONG
    assert combine(["right", "claimed"]) == Verdict.RIGHT
