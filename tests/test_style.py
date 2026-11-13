"""Writing styles: the final full stop held back, the opening capitals dropped."""

from __future__ import annotations

import unittest

from . import context  # noqa: F401  (adds src/ to the import path)

from whisper_desk import style


class ResolveTest(unittest.TestCase):
    def test_the_configured_style(self):
        self.assertEqual(style.resolve({"model": {"style": "casual"}}), "casual")
        self.assertEqual(style.resolve({"model": {"style": "Very casual"}}), "very_casual")

    def test_formal_by_default_and_for_an_unknown_style(self):
        self.assertEqual(style.resolve({"model": {}}), "formal")
        self.assertEqual(style.resolve({"model": {"style": "excited"}}), "formal")


class HoldFullStopTest(unittest.TestCase):
    def check(self, text: str, kept: str, held: str) -> None:
        self.assertEqual(style.hold_full_stop(text), (kept, held))

    def test_the_final_full_stop_is_held(self):
        self.check("On se voit demain.", "On se voit demain", ".")
        self.check("Ça marche. On se voit demain.", "Ça marche. On se voit demain", ".")

    def test_other_marks_stay(self):
        self.check("On se voit demain ?", "On se voit demain ?", "")
        self.check("Great!", "Great!", "")
        self.check("Je ne sais pas…", "Je ne sais pas…", "")
        self.check("I don't know...", "I don't know...", "")
        self.check("Les courses :\n1. Des œufs", "Les courses :\n1. Des œufs", "")

    def test_a_full_stop_that_belongs_to_its_word_stays(self):
        self.check("Des pommes, des poires, etc.", "Des pommes, des poires, etc.", "")
        self.check("Signé J.", "Signé J.", "")
        self.check("Ask Mr.", "Ask Mr.", "")
        self.check("Like this, e.g.", "Like this, e.g.", "")

    def test_a_lone_mark_stays(self):
        self.check(".", ".", "")


class RejoinTest(unittest.TestCase):
    def test_the_held_full_stop_opens_the_next_sentence(self):
        self.assertEqual(style.rejoin(".", "Merci"), ". Merci")
        self.assertEqual(style.rejoin(".", "\n1. Des œufs"), ".\n1. Des œufs")

    def test_a_sentence_opening_on_a_mark_replaces_it(self):
        self.assertEqual(style.rejoin(".", ", et toi"), ", et toi")
        self.assertEqual(style.rejoin(".", "?"), "?")

    def test_nothing_held(self):
        self.assertEqual(style.rejoin("", "Merci"), "Merci")


class LowerStartsTest(unittest.TestCase):
    def check(self, text: str, written: str, keep: set[str] = frozenset()) -> None:
        self.assertEqual(style.lower_starts(text, keep), written)

    def test_each_sentence_opens_on_a_small_letter(self):
        self.check("Ça marche. On se voit demain ! Tu viens ?",
                   "ça marche. on se voit demain ! tu viens ?")
        self.check("Sounds good… See you.", "sounds good… see you.")

    def test_after_a_line_break_and_a_list_number(self):
        self.check("Les courses :\n1. Des œufs\n2. Du lait\nMerci.",
                   "les courses :\n1. des œufs\n2. du lait\nmerci.")

    def test_after_an_opening_quote_or_bracket(self):
        self.check("Il a dit. « Bonjour. » (Puis rien.)", "il a dit. « bonjour. » (puis rien.)")

    def test_capitals_inside_a_sentence_stay(self):
        self.check("On part à Paris avec Marie.", "on part à Paris avec Marie.")

    def test_acronyms_mixed_case_and_i_stay(self):
        self.check("OK. GitHub is down. I'm on it. I think so.",
                   "OK. GitHub is down. I'm on it. I think so.")

    def test_names_of_the_vocabulary_stay(self):
        self.check("Opoil est en ligne. Merci.", "Opoil est en ligne. merci.", {"Opoil"})

    def test_after_an_abbreviation_or_an_initial(self):
        self.check("Voir M. Dupont.", "voir M. Dupont.")
        self.check("Signé J. Martin.", "signé J. Martin.")


class NamesTest(unittest.TestCase):
    def test_vocabulary_and_replacement_spellings(self):
        config = {
            "model": {"vocabulary": "Animalink, Kubernetes, pull request, Hermez agency"},
            "replacements": {"alarmor": "Ollama", "mac os": "macOS", "off": ""},
        }
        self.assertEqual(
            style.names(config), {"Animalink", "Kubernetes", "Hermez", "Ollama"}
        )


if __name__ == "__main__":
    unittest.main()
