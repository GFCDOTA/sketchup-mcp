import unittest
from slugify import slugify

class TestSlugify(unittest.TestCase):
    def test_lowercase(self):
        self.assertEqual(slugify("Hello"), "hello")

    def test_strips_leading_whitespace(self):
        self.assertEqual(slugify("  hello"), "hello")

    def test_strips_trailing_whitespace(self):
        self.assertEqual(slugify("hello  "), "hello")

    def test_collapses_multiple_spaces(self):
        self.assertEqual(slugify("hello  world"), "hello-world")

    def test_required_example(self):
        self.assertEqual(slugify(" Hello World "), "hello-world")

    def test_single_space(self):
        self.assertEqual(slugify("hello world"), "hello-world")

    def test_empty_string(self):
        self.assertEqual(slugify(""), "")

    def test_only_spaces(self):
        self.assertEqual(slugify("   "), "")

    def test_no_spaces(self):
        self.assertEqual(slugify("hello"), "hello")

    def test_already_lowercase(self):
        self.assertEqual(slugify("hello world"), "hello-world")

if __name__ == "__main__":
    unittest.main()
