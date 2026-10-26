"""Numbered lists said aloud written as lists."""

from __future__ import annotations

import unittest

from . import context  # noqa: F401  (adds src/ to the import path)

from whisper_desk import lists


class ListTest(unittest.TestCase):
    """Two items numbered in a row make a list."""

    def check(self, said: str, written: str, before: str = "") -> None:
        self.assertEqual(lists.apply(said, before), written)

    def test_numbers_said_with_a_pause(self):
        self.check(
            "J'ai trois choses à acheter, un, des œufs, deux, du lait et trois, du pain.",
            "J'ai trois choses à acheter :\n1. Des œufs\n2. Du lait\n3. Du pain",
        )
        self.check(
            "We need three things: one, eggs. Two, milk. Three, bread.",
            "We need three things:\n1. Eggs\n2. Milk\n3. Bread",
        )

    def test_ordinals(self):
        self.check(
            "Pour demain, premièrement appeler le client, deuxièmement envoyer le devis.",
            "Pour demain :\n1. Appeler le client\n2. Envoyer le devis",
        )
        self.check("Firstly, the tests. Secondly, the docs.", "1. The tests\n2. The docs")
        self.check("Primo, le prix. Secundo, le délai.", "1. Le prix\n2. Le délai")
        self.check("First, the price. Second, the delay.", "1. The price\n2. The delay")

    def test_number_said_before_the_figure(self):
        self.check(
            "Number one, the price. Number two, the delay.", "1. The price\n2. The delay"
        )
        self.check("Numéro un, le prix, numéro deux, le délai.", "1. Le prix\n2. Le délai")

    def test_the_figures_whisper_writes(self):
        self.check(
            "Trois choses : 1. Des œufs, 2. Du lait, 3. Du pain.",
            "Trois choses :\n1. Des œufs\n2. Du lait\n3. Du pain",
        )
        self.check("Steps: 1) build, 2) test.", "Steps:\n1. Build\n2. Test")

    def test_figures_without_a_pause_before_them(self):
        self.check(
            "Ordre du jour 1. Le bilan 2. Le recrutement",
            "Ordre du jour :\n1. Le bilan\n2. Le recrutement",
        )

    def test_numbers_without_a_pause_after_them_need_three_items(self):
        self.check(
            "À acheter, un des œufs, deux du lait, trois du pain.",
            "À acheter :\n1. Des œufs\n2. Du lait\n3. Du pain",
        )
        self.check("Un ami, deux collègues.", "Un ami, deux collègues.")

    def test_what_follows_the_last_item_goes_on_its_own_line(self):
        self.check(
            "Premièrement, appeler le client. Deuxièmement, envoyer le devis. Merci.",
            "1. Appeler le client\n2. Envoyer le devis\nMerci.",
        )

    def test_an_item_keeps_its_question_mark(self):
        self.check("Un, tu viens ? Deux, tu restes ?", "1. Tu viens ?\n2. Tu restes ?")

    def test_a_list_is_written_once(self):
        written = "Trois choses :\n1. Des œufs\n2. Du lait\n3. Du pain\nMerci."
        self.check(written, written)


class ProseTest(unittest.TestCase):
    """Numbers and ordinals in a sentence stay words."""

    def check(self, said: str) -> None:
        self.assertEqual(lists.apply(said), said)

    def test_a_single_item_is_no_list(self):
        self.check("Premièrement, je voudrais vous remercier.")
        self.check("First, let me check the logs.")

    def test_a_count_is_no_list(self):
        self.check("Un, deux, trois, soleil.")
        self.check("One, two, buckle my shoe.")

    def test_numbers_inside_a_sentence(self):
        self.check("J'en veux deux, trois si possible.")
        self.check("No one, two people at most.")
        self.check("Wait a second, first we eat.")
        self.check("Il reste 1,5 kilo, puis 2 litres.")
        self.check("Il en reste un et deux sont cassés.")

    def test_a_list_that_does_not_start_at_one(self):
        self.check("Deux, du lait. Trois, du pain.")


class ContinuationTest(unittest.TestCase):
    """A list inserted already goes on in the next sentence."""

    BEFORE = "Courses :\n1. Des œufs\n2. Du lait"

    def test_the_next_item_takes_the_next_number(self):
        self.assertEqual(lists.apply("Trois, du pain.", self.BEFORE), "\n3. Du pain")
        self.assertEqual(
            lists.apply("Trois, du pain. Quatre, du beurre.", self.BEFORE),
            "\n3. Du pain\n4. Du beurre",
        )

    def test_the_next_number_needs_no_pause(self):
        self.assertEqual(lists.apply("Trois du pain.", self.BEFORE), "\n3. Du pain")

    def test_a_sentence_after_the_list_starts_a_line(self):
        self.assertEqual(lists.apply("Merci.", self.BEFORE), "\nMerci.")

    def test_a_list_after_a_sentence_starts_a_line(self):
        self.assertEqual(
            lists.apply("Un, des œufs. Deux, du lait.", "J'ai des courses à faire."),
            "\n1. Des œufs\n2. Du lait",
        )

    def test_without_a_list_before_nothing_changes(self):
        self.assertEqual(lists.apply("Trois, du pain.", "Bonjour."), "Trois, du pain.")


class PendingTest(unittest.TestCase):
    """A sentence that may open a list waits for the next one."""

    def test_the_first_item_waits_for_the_second(self):
        pending = lists.Pending()
        self.assertIsNone(pending.feed("Un, des œufs.", "Courses :"))
        self.assertEqual(pending.feed("Deux, du lait.", "Courses :"), "\n1. Des œufs\n2. Du lait")
        self.assertEqual(pending.held, [])

    def test_a_sentence_that_opens_nothing_goes_at_once(self):
        self.assertEqual(lists.Pending().feed("Bonjour Marie.", ""), "Bonjour Marie.")

    def test_a_whole_list_goes_at_once(self):
        self.assertEqual(
            lists.Pending().feed("Un, des œufs, deux, du lait.", ""), "1. Des œufs\n2. Du lait"
        )

    def test_a_number_that_may_be_an_article_does_not_wait(self):
        self.assertEqual(lists.Pending().feed("Un ami m'a appelé.", ""), "Un ami m'a appelé.")

    def test_it_waits_for_one_sentence_only(self):
        pending = lists.Pending()
        self.assertIsNone(pending.feed("First, let me check.", ""))
        self.assertEqual(pending.feed("Then we go.", ""), "First, let me check. Then we go.")

    def test_what_is_held_comes_out_as_said(self):
        pending = lists.Pending()
        self.assertIsNone(pending.feed("Premièrement, merci.", ""))
        self.assertEqual(pending.flush(), "Premièrement, merci.")
        self.assertEqual(pending.held, [])


if __name__ == "__main__":
    unittest.main()
