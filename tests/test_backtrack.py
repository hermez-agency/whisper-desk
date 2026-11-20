"""Corrections said aloud, carried out — and ordinary sentences left alone."""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from . import context  # noqa: F401  (adds src/ to the import path)

from whisper_desk.backtrack import across, apply, cleared, discarded

CORPUS = Path(__file__).resolve().parents[1] / "bench" / "backtrack" / "corpus.tsv"
DISCARD = CORPUS.with_name("discard.tsv")
CLEAR = CORPUS.with_name("clear.tsv")
# Sentences of the corpus the rules still get wrong: the measure counts them,
# the test makes sure the list only ever shrinks.
KNOWN_MISSES = {"fr15", "fr19"}


class CorrectionTest(unittest.TestCase):
    # The sample sentences are dictations: they stay in the language spoken.

    def test_a_weekday_replaces_the_weekday(self):
        self.assertEqual(apply("On se voit mardi, non, plutôt mercredi."), "On se voit mercredi.")

    def test_a_number_replaces_the_number(self):
        self.assertEqual(apply("Let's meet at 2, actually 3."), "Let's meet at 3.")

    def test_the_correction_starts_over_from_the_repeated_word(self):
        self.assertEqual(
            apply("Envoie le dossier à Paul, non, je veux dire à Marie."),
            "Envoie le dossier à Marie.",
        )

    def test_a_strong_marker_replaces_as_many_words(self):
        self.assertEqual(apply("Le chat est noir, non, plutôt gris."), "Le chat est gris.")

    def test_the_determiner_goes_with_the_word_it_announced(self):
        self.assertEqual(
            apply("On déploie en production ce soir, non, plutôt demain."),
            "On déploie en production demain.",
        )

    def test_a_correction_may_open_a_new_sentence(self):
        self.assertEqual(apply("On se voit mardi. Non, plutôt mercredi."), "On se voit mercredi.")

    def test_the_text_after_the_correction_is_kept(self):
        self.assertEqual(
            apply("Le chat est noir, non, plutôt gris. Il dort."),
            "Le chat est gris. Il dort.",
        )

    def test_the_sentences_before_are_left_alone(self):
        self.assertEqual(
            apply("Bonjour. On se voit mardi, non, plutôt mercredi."),
            "Bonjour. On se voit mercredi.",
        )

    def test_or_rather_needs_no_pause(self):
        self.assertEqual(
            apply("Il faut livrer la version 2 ou plutôt la version 3."),
            "Il faut livrer la version 3.",
        )

    def test_two_corrections_in_a_row(self):
        self.assertEqual(
            apply("Je pars lundi, non, plutôt mardi, non, plutôt jeudi."),
            "Je pars jeudi.",
        )


class RestatedTest(unittest.TestCase):
    """A weak marker after a full stop: a number, a day or a month said again."""

    def test_a_number_said_again_after_a_full_stop(self):
        self.assertEqual(apply("Let's meet at 2. Actually 3."), "Let's meet at 3.")

    def test_the_words_after_the_number_are_kept(self):
        self.assertEqual(apply("We need 5 chairs. I mean 6."), "We need 6 chairs.")
        self.assertEqual(apply("Il a 3 ans. Non, 4."), "Il a 4 ans.")

    def test_a_day_said_again(self):
        self.assertEqual(apply("Je pars lundi. Pardon, mardi."), "Je pars mardi.")

    def test_a_question_s_next_sentence_is_its_answer(self):
        text = "Tu viens à 3 h ? Non, à 4 h."
        self.assertEqual(apply(text), text)

    def test_nothing_to_line_up_with_is_no_correction(self):
        for text in ("Tu viens demain. Non, tu restes.", "It costs 5 dollars. Actually, that is cheap."):
            self.assertEqual(apply(text), text)


class AcrossTest(unittest.TestCase):
    """A correction said after the pause that ended its sentence."""

    def test_the_next_sentence_corrects_the_one_before(self):
        self.assertEqual(across("On se voit mardi.", "Non, plutôt mercredi."), "On se voit mercredi.")
        self.assertEqual(across("Let's meet at 2.", "Actually 3."), "Let's meet at 3.")

    def test_what_follows_the_correction_is_kept(self):
        self.assertEqual(
            across("Envoie le dossier à Paul.", "Non, je veux dire à Marie. Merci."),
            "Envoie le dossier à Marie. Merci.",
        )

    def test_the_pause_ends_a_sentence_whisper_left_without_its_full_stop(self):
        self.assertEqual(across("Le train part à 8h", "Pardon, 9h."), "Le train part à 9h.")
        self.assertIsNone(across("Le train part à 8h", "Pardon, je me suis trompé."))

    def test_attend_written_without_its_s(self):
        self.assertEqual(across("On livre lundi.", "Non attend, mardi."), "On livre mardi.")

    def test_a_sentence_that_does_not_open_on_a_correction(self):
        self.assertIsNone(across("On se voit mardi.", "Il faut plutôt mercredi, non, jeudi."))

    def test_an_answer_or_a_new_thought_corrects_nothing(self):
        for previous, sentence in (
            ("Tu viens mardi ?", "Non, je reste."),
            ("Il fait beau.", "Non, je ne viendrai pas."),
            ("Let's meet at 2.", "Actually, I think we should cancel."),
            ("Bonjour.", "Pardon, je n'avais pas vu ton message."),
        ):
            with self.subTest(sentence):
                self.assertIsNone(across(previous, sentence))

    def test_nothing_before_corrects_nothing(self):
        self.assertIsNone(across("", "Non, plutôt mercredi."))


class LeftAloneTest(unittest.TestCase):
    def test_without_a_pause_the_marker_is_a_word_of_the_sentence(self):
        for text in ("C'est plutôt une bonne nouvelle.", "I actually think so."):
            self.assertEqual(apply(text), text)

    def test_an_answer_is_not_a_correction(self):
        for text in ("Tu viens ? Non, je reste.", "Pardon, je n'avais pas vu."):
            self.assertEqual(apply(text), text)

    def test_a_weak_marker_needs_something_to_line_up_with(self):
        text = "Il a dit non, et il est parti."
        self.assertEqual(apply(text), text)

    def test_an_empty_text_stays_empty(self):
        self.assertEqual(apply(""), "")


class DiscardedTest(unittest.TestCase):
    """"Efface ça" said after a pause: the daemon erases the sentence before it."""

    def test_the_command_alone(self):
        for sentence in ("Efface ça.", "Scratch that.", "Delete that!", "Effacez cela.",
                         "Supprime la dernière phrase.", "Delete the last sentence."):
            with self.subTest(sentence):
                self.assertEqual(discarded(sentence), "")

    def test_a_word_before_it(self):
        self.assertEqual(discarded("Non, efface ça."), "")
        self.assertEqual(discarded("Oops, scratch that."), "")

    def test_what_follows_is_the_sentence_meant(self):
        self.assertEqual(discarded("Scratch that. Hi Mary."), "Hi Mary.")

    def test_after_a_comma_it_opens_its_sentence(self):
        self.assertEqual(discarded("Efface ça, le chien dort."), "Le chien dort.")

    def test_spellings_whisper_writes(self):
        self.assertEqual(discarded("Éface-ça."), "")
        self.assertEqual(discarded("Suprime ça."), "")

    def test_a_command_about_something_else(self):
        for sentence in ("Efface ça du tableau.", "Delete that file.", "Scratch that itch.",
                         "Delete that?", "Il faut effacer ça.", "Efface le tableau."):
            with self.subTest(sentence):
                self.assertIsNone(discarded(sentence))


class DiscardInsideTest(unittest.TestCase):
    """The command and the sentence it drops, in one transcription."""

    def test_the_sentence_before_goes(self):
        self.assertEqual(
            apply("Rendez-vous à 3 heures. Efface ça. Rendez-vous à 4 heures."),
            "Rendez-vous à 4 heures.",
        )

    def test_after_a_comma_its_own_sentence_goes(self):
        self.assertEqual(apply("Hello. Lunch at noon, scratch that."), "Hello.")

    def test_nothing_left(self):
        self.assertEqual(apply("Lunch at noon. Scratch that."), "")

    def test_what_follows_a_comma_opens_a_sentence(self):
        self.assertEqual(apply("Hello. Scratch that, let's meet Thursday."), "Let's meet Thursday.")

    def test_between_two_commas_it_replaces(self):
        self.assertEqual(apply("See you Tuesday, scratch that, Wednesday."), "See you Wednesday.")

    def test_a_word_before_it_is_no_sentence(self):
        """The daemon's case: the command opens the transcription, the sentence is typed."""
        self.assertEqual(apply("Non, efface ça."), "Non, efface ça.")
        self.assertEqual(apply("Bonjour. Non, efface ça."), "")

    def test_the_command_alone_is_left_to_the_daemon(self):
        self.assertEqual(apply("Efface ça."), "Efface ça.")


class ClearedTest(unittest.TestCase):
    """"Efface tout" said after a pause: the daemon erases the whole dictation."""

    def test_the_command_alone(self):
        for sentence in ("Efface tout.", "Efface tout ça.", "Supprime tout.", "Effacez tout !",
                         "Efface toute la dictée.", "Efface tout le texte.",
                         "Scratch all that.", "Delete everything.", "Erase it all.",
                         "Delete all of this.", "Clear everything."):
            with self.subTest(sentence):
                self.assertEqual(cleared(sentence), "")

    def test_starting_over_said_with_it(self):
        for sentence in ("Efface tout et recommence.", "On efface tout et on recommence.",
                         "Scratch all that and start over.", "Delete everything, and start again."):
            with self.subTest(sentence):
                self.assertEqual(cleared(sentence), "")

    def test_a_word_before_it(self):
        self.assertEqual(cleared("Non, efface tout."), "")
        self.assertEqual(cleared("Oops, scratch all that."), "")

    def test_what_follows_is_the_text_meant(self):
        self.assertEqual(cleared("Efface tout. Bonjour Marie."), "Bonjour Marie.")
        self.assertEqual(cleared("Scratch all that, hi Mary."), "Hi Mary.")

    def test_spellings_whisper_writes(self):
        for sentence in ("Éface tout.", "Suprime-tout.", "Fasse tout.", "Et fasse tout ça !",
                         "Oop et face tout !", "On efface toutes et on recommence."):
            with self.subTest(sentence):
                self.assertEqual(cleared(sentence), "")

    def test_a_sound_alike_only_as_a_whole_sentence(self):
        for sentence in ("Qu'il fasse tout.", "Fasse tout ce qu'il peut.", "Face tout le monde.",
                         "Et face à tout."):
            with self.subTest(sentence):
                self.assertIsNone(cleared(sentence))
        self.assertEqual(apply("Bonjour. Fasse tout."), "Bonjour. Fasse tout.")

    def test_a_command_about_something_else(self):
        for sentence in ("Efface tout le tableau.", "Delete everything in the folder.",
                         "Delete everything?", "Il faut tout effacer.", "Tu as tout effacé ?",
                         "On efface tout et on recommence le projet demain.",
                         "Clear all that snow from the path.", "Efface ça."):
            with self.subTest(sentence):
                self.assertIsNone(cleared(sentence))

    def test_scratch_that_is_no_clearing(self):
        self.assertIsNone(cleared("Scratch that."))
        self.assertIsNone(discarded("Scratch all that."))
        self.assertIsNone(discarded("Efface tout."))


class ClearInsideTest(unittest.TestCase):
    """"Efface tout" and what it takes back, in one transcription."""

    def test_what_was_said_before_goes(self):
        self.assertEqual(
            apply("Bonjour Marc. On se voit mardi. Efface tout. Bonjour Marie."),
            "Efface tout. Bonjour Marie.",
        )

    def test_the_command_stays_for_the_daemon(self):
        """The sentences typed before this transcription go too: the daemon's job."""
        self.assertEqual(apply("Efface tout."), "Efface tout.")
        self.assertEqual(apply("Hello. Scratch all that."), "Scratch all that.")

    def test_after_a_comma(self):
        self.assertEqual(apply("Hi Mark, scratch all that, hi Mary."),
                         "scratch all that, hi Mary.")

    def test_the_last_one_said_counts(self):
        self.assertEqual(apply("A. Efface tout. B. Scratch all that. C."), "Scratch all that. C.")

    def test_a_sentence_about_something_else_stays(self):
        text = "Le tableau est plein. Efface tout le tableau."
        self.assertEqual(apply(text), text)

    def test_not_when_discarding_is_off(self):
        text = "Bonjour. Efface tout."
        self.assertEqual(apply(text, discard=False), text)


class CorpusTest(unittest.TestCase):
    """The sentences of the measure, written out, give the expected text."""

    def test_the_corpus(self):
        with CORPUS.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in rows:
            if row["id"] in KNOWN_MISSES:
                continue
            with self.subTest(row["id"]):
                self.assertEqual(apply(row["spoken"]), row["expected"])

    def test_the_discard_corpus(self):
        with DISCARD.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in rows:
            with self.subTest(row["id"]):
                rest = discarded(row["second"])
                at_cursor = row["first"] + " " + row["second"] if rest is None else rest
                self.assertEqual(at_cursor, row["expected"])

    def test_the_clear_corpus(self):
        with CLEAR.open(encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in rows:
            with self.subTest(row["id"]):
                rest = cleared(row["third"])
                said = " ".join((row["first"], row["second"], row["third"]))
                self.assertEqual(said if rest is None else rest, row["expected"])

    def test_the_known_misses_are_still_missed(self):
        """A rule that fixes one of them: take it off the list."""
        with CORPUS.open(encoding="utf-8") as handle:
            rows = {row["id"]: row for row in csv.DictReader(handle, delimiter="\t")}
        for name in KNOWN_MISSES:
            with self.subTest(name):
                self.assertNotEqual(apply(rows[name]["spoken"]), rows[name]["expected"])


if __name__ == "__main__":
    unittest.main()
