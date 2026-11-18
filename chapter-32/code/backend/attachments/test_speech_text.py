from django.test import SimpleTestCase

from attachments.speech_text import split_for_speech, to_speakable


class SpeakableTests(SimpleTestCase):
    def test_markdown_marks_are_not_read_aloud(self):
        md = "## Plan\n\n- **First** item\n- second `item`\n\n1. one\n2. two\n\n> quoted"
        self.assertEqual(to_speakable(md), "Plan\n\nFirst item\nsecond item\n\none\ntwo\n\nquoted")

    def test_links_keep_their_label_and_urls_become_a_phrase(self):
        self.assertEqual(to_speakable("See [the docs](https://example.com/very/long/path?x=1)."), "See the docs.")
        self.assertEqual(to_speakable("Visit https://example.com/a/b now"), "Visit a link now")

    def test_code_blocks_are_announced_not_spelled_out(self):
        text = to_speakable("Run this:\n```python\nprint('hi')\n```\nThen stop.")
        self.assertIn("code omitted", text)
        self.assertNotIn("print", text)

    def test_plain_text_is_unchanged(self):
        self.assertEqual(to_speakable("Just a sentence."), "Just a sentence.")


class SplitTests(SimpleTestCase):
    def test_short_text_is_one_part_and_empty_is_none(self):
        self.assertEqual(split_for_speech("Hello."), ["Hello."])
        self.assertEqual(split_for_speech(""), [])

    def test_long_text_is_cut_at_sentence_ends_within_the_limit(self):
        text = " ".join(f"This is sentence number {i}." for i in range(200))
        parts = split_for_speech(text, max_chars=300)
        self.assertGreater(len(parts), 5)
        self.assertTrue(all(len(p) <= 300 for p in parts))
        self.assertTrue(all(p.endswith(".") for p in parts))
        self.assertEqual(" ".join(parts).split(), text.split())  # nothing lost, nothing repeated

    def test_one_enormous_sentence_is_still_cut(self):
        parts = split_for_speech("word " * 500, max_chars=100)
        self.assertTrue(all(len(p) <= 100 for p in parts))
        self.assertEqual(" ".join(parts).split(), ("word " * 500).split())
