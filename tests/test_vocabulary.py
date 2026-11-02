"""Personal dictionary: the words a corrected dictation teaches the vocabulary."""

from __future__ import annotations

import unittest

from . import context  # noqa: F401  (adds src/ to the import path)

from whisper_desk import vocabulary


def learned(before: str, after: str) -> list[str]:
    return vocabulary.learned(before, after)


class LearnedTest(unittest.TestCase):
    """A name, jargon, a word misheard: learned."""

    def test_a_name_heard_as_several_words(self):
        self.assertEqual(learned("Envoie le devis à animal link.", "Envoie le devis à Animalink."),
                         ["Animalink"])
        self.assertEqual(learned("On déploie sur cube et Netis demain.",
                                 "On déploie sur Kubernetes demain."), ["Kubernetes"])

    def test_a_name_given_its_capital(self):
        self.assertEqual(learned("Je vois hermez demain.", "Je vois Hermez demain."), ["Hermez"])

    def test_a_name_spelt_at_the_start_of_a_sentence(self):
        self.assertEqual(learned("Hermes is working on it.", "Hermez is working on it."), ["Hermez"])

    def test_a_word_misheard_as_another(self):
        self.assertEqual(learned("Merci pour les ripos GitHub.", "Merci pour les repos GitHub."),
                         ["repos"])

    def test_jargon_keeps_its_signs(self):
        self.assertEqual(learned("Use node JS.", "Use Node.js."), ["Node.js"])
        self.assertEqual(learned("installe faster whisper", "installe faster-whisper"),
                         ["faster-whisper"])
        self.assertEqual(learned("en C plus plus", "en C++"), ["C++"])

    def test_a_name_Whisper_left_out(self):
        self.assertEqual(learned("On lance le demain.", "On lance le Dokploy demain."), ["Dokploy"])

    def test_the_names_of_a_sentence_rewritten(self):
        self.assertEqual(learned("Je parle à salva demain matin pour le point.",
                                 "Demain, j'appelle Hermez pour faire le point sur le budget."),
                         ["Hermez"])

    def test_without_its_elision_or_possessive(self):
        self.assertEqual(learned("Le devis d'animal link.", "Le devis d'Animalink."), ["Animalink"])
        self.assertEqual(learned("D'animal link, rien.", "D'Animalink, rien."), ["Animalink"])
        self.assertEqual(learned("The animal links quote.", "The Animalink's quote."), ["Animalink"])

    def test_each_word_once(self):
        self.assertEqual(learned("animal link et animal link", "Animalink et Animalink"),
                         ["Animalink"])


class NotLearnedTest(unittest.TestCase):
    """Grammar, a word left out, a capital at the start of a sentence: nothing."""

    def assertNothing(self, before: str, after: str) -> None:
        self.assertEqual(learned(before, after), [])

    def test_an_agreement_or_a_tense(self):
        self.assertNothing("Il mange des pommes.", "Ils mangent des pommes.")
        self.assertNothing("Elle parlait au client.", "Elle parlais au client.")

    def test_short_words_and_accents(self):
        self.assertNothing("Il a fini.", "Il à fini.")
        self.assertNothing("Il a des pommes.", "Il a les pommes.")

    def test_an_elision(self):
        self.assertNothing("Their going home.", "They're going home.")

    def test_a_short_word_corrected(self):
        self.assertNothing("I has a meeting at noon.", "I have a meeting at noon.")
        self.assertNothing("The results was good.", "The results were good.")

    def test_the_user_changing_their_mind(self):
        self.assertNothing("On se voit demain matin.", "On se voit demain après-midi.")

    def test_an_ordinary_word_left_out(self):
        self.assertNothing("le chat dort", "le petit chat dort")

    def test_a_capital_or_a_mark_at_the_start(self):
        self.assertNothing("bonjour tout le monde", "Bonjour tout le monde.")
        self.assertNothing("c'est fait. merci", "C'est fait. Merci")

    def test_nothing_changed(self):
        self.assertNothing("Rien à corriger.", "Rien à corriger.")


class MergeTest(unittest.TestCase):
    def test_added_at_the_end(self):
        self.assertEqual(vocabulary.merge("Animalink, pull request", ["Kubernetes"]),
                         ("Animalink, pull request, Kubernetes", ["Kubernetes"]))

    def test_an_empty_vocabulary(self):
        self.assertEqual(vocabulary.merge("", ["Hermez", "Ponos"]),
                         ("Hermez, Ponos", ["Hermez", "Ponos"]))

    def test_a_word_already_there_in_another_case_is_not_added(self):
        self.assertEqual(vocabulary.merge("animalink", ["Animalink"]), ("animalink", []))

    def test_learn_saves_only_what_is_new(self):
        config = {"model": {"vocabulary": "Hermez"}}
        saved: list[dict] = []
        added = vocabulary.learn("Je vois hermez et Pono.", "Je vois Hermez et Ponos.",
                                 config, saved.append)
        self.assertEqual(added, ["Ponos"])
        self.assertEqual(saved, [{"model": {"vocabulary": "Hermez, Ponos"}}])
        self.assertEqual(config["model"]["vocabulary"], "Hermez, Ponos")

    def test_learn_writes_nothing_when_nothing_is_new(self):
        saved: list[dict] = []
        vocabulary.learn("Il mange.", "Ils mangent.", {"model": {"vocabulary": ""}}, saved.append)
        self.assertEqual(saved, [])


if __name__ == "__main__":
    unittest.main()
