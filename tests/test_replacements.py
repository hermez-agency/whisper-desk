"""Replacements: a spelling Whisper keeps writing swapped for the one meant."""

from __future__ import annotations

import unittest

from . import context  # noqa: F401  (adds src/ to the import path)

from whisper_desk import replacements
from whisper_desk.replacements import Replacements

TABLE = {
    "mac os": "macOS",
    "mac os x": "Mac OS X",
    "animal link": "Animalink",
    "dock ploy": "Dokploy",
    "lori": "Laurie",
    "don't": "do not",
    "can": "CAN",
}


def replace(text: str) -> str:
    return replacements.apply(text, TABLE)


class MatchTest(unittest.TestCase):
    """Whole words, whatever their case and their spacing."""

    def test_the_spelling_is_written_as_saved(self):
        self.assertEqual(replace("Je suis sous Mac OS depuis hier."),
                         "Je suis sous macOS depuis hier.")

    def test_case_and_hyphen_do_not_matter(self):
        self.assertEqual(replace("le devis d'animal-link"), "le devis d'Animalink")
        self.assertEqual(replace("DOCK  PLOY tourne"), "Dokploy tourne")

    def test_every_occurrence_is_replaced(self):
        self.assertEqual(replace("Lori et lori."), "Laurie et Laurie.")

    def test_the_longest_entry_wins(self):
        self.assertEqual(replace("Still on mac os x."), "Still on Mac OS X.")

    def test_punctuation_around_is_kept(self):
        self.assertEqual(replace("Ask Lori, then « dock ploy »!"),
                         "Ask Laurie, then « Dokploy »!")

    def test_a_possessive_stays(self):
        self.assertEqual(replace("animal link's site"), "Animalink's site")

    def test_never_inside_a_word(self):
        self.assertEqual(replace("Loris and canal, I can't."), "Loris and canal, I can't.")

    def test_not_across_a_full_stop(self):
        self.assertEqual(replace("Animal. Link."), "Animal. Link.")

    def test_a_contraction_is_one_word(self):
        self.assertEqual(replace("I don’t know."), "I do not know.")


class CaseTest(unittest.TestCase):
    def test_a_lowercase_spelling_takes_the_sentence_capital(self):
        self.assertEqual(replace("Don't go."), "Do not go.")

    def test_a_spelling_with_its_own_case_keeps_it(self):
        self.assertEqual(replace("Mac OS is out."), "macOS is out.")
        self.assertEqual(replace("the can bus"), "the CAN bus")


class TableTest(unittest.TestCase):
    def test_no_entry_leaves_the_text_alone(self):
        self.assertIsNone(Replacements({}).pattern)
        self.assertEqual(replacements.apply("Mac OS", {}), "Mac OS")

    def test_an_empty_spelling_switches_an_entry_off(self):
        self.assertEqual(replacements.apply("mac os", {"mac os": " "}), "mac os")

    def test_an_entry_without_a_word_is_ignored(self):
        self.assertIsNone(Replacements({"...": "x"}).pattern)

    def test_a_value_that_is_no_string_is_ignored(self):
        with self.assertLogs("whisper-desk.replacements", "WARNING"):
            table = Replacements({"mac os": 3, "lori": "Laurie"})
        self.assertEqual(table.apply("mac os, lori"), "mac os, Laurie")

    def test_regex_characters_are_plain_text(self):
        self.assertEqual(replacements.apply("c plus plus", {"c plus plus": "C++"}), "C++")
        self.assertEqual(replacements.apply("a.b axb", {"a b": "x"}), "a.b axb")

    def test_the_key_folds_case_spacing_and_apostrophes(self):
        self.assertEqual(replacements.misspelling_key("  Mac,  OS "), "mac os")
        self.assertEqual(replacements.misspelling_key("Don’t"), "don't")


if __name__ == "__main__":
    unittest.main()
