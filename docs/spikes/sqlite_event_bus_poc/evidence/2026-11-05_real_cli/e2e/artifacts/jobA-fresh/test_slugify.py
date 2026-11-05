import unittest
from slugify import slugify


class TestSlugify(unittest.TestCase):

    def test_example(self):
        self.assertEqual(slugify(" Hello World "), "hello-world")

    def test_lowercase(self):
        self.assertEqual(slugify("UPPER"), "upper")

    def test_mixed_case(self):
        self.assertEqual(slugify("CamelCase"), "camelcase")

    def test_strips_leading_whitespace(self):
        self.assertEqual(slugify("   hello"), "hello")

    def test_strips_trailing_whitespace(self):
        self.assertEqual(slugify("hello   "), "hello")

    def test_strips_both_ends(self):
        self.assertEqual(slugify("  hello  "), "hello")

    def test_single_space_between_words(self):
        self.assertEqual(slugify("foo bar"), "foo-bar")

    def test_multiple_spaces_become_single_hyphen(self):
        self.assertEqual(slugify("foo   bar"), "foo-bar")

    def test_many_words(self):
        self.assertEqual(slugify("one two three"), "one-two-three")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "")

    def test_only_spaces(self):
        self.assertEqual(slugify("   "), "")

    def test_single_word(self):
        self.assertEqual(slugify("hello"), "hello")

    def test_already_lowercase(self):
        self.assertEqual(slugify("hello world"), "hello-world")

    def test_leading_trailing_spaces_with_internal_runs(self):
        self.assertEqual(slugify("  Hello   World  "), "hello-world")


if __name__ == "__main__":
    unittest.main()
