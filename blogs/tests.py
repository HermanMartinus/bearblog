from django.test import TestCase
from django.utils.safestring import SafeString

from blogs.templatetags.custom_tags import safe_title, plain_title


class SafeTitleTests(TestCase):
    def test_plain_text_unchanged(self):
        result = safe_title("Hello World")
        self.assertEqual(result, "Hello World")

    def test_italic(self):
        result = safe_title("Review of *The Great Gatsby*")
        self.assertEqual(result, "Review of <i>The Great Gatsby</i>")

    def test_bold(self):
        result = safe_title("A **Bold** Statement")
        self.assertEqual(result, "A <b>Bold</b> Statement")

    def test_bold_and_italic(self):
        result = safe_title("**Bold** and *italic*")
        self.assertEqual(result, "<b>Bold</b> and <i>italic</i>")

    def test_nbsp(self):
        result = safe_title("Hello&nbsp;World")
        self.assertEqual(result, "Hello\u00a0World")

    def test_returns_mark_safe(self):
        result = safe_title("*italic*")
        self.assertIsInstance(result, SafeString)

    def test_html_escaped(self):
        result = safe_title("<script>alert(1)</script>")
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_html_tags_not_allowed(self):
        result = safe_title("<b>bold</b> and <a href='x'>link</a>")
        self.assertNotIn("<a ", result)
        # The <b> in the output should be escaped, not raw HTML
        self.assertIn("&lt;b&gt;", result)

    def test_mixed_formatting_and_xss(self):
        result = safe_title('*italic* <script>alert("xss")</script>')
        self.assertIn("<i>italic</i>", result)
        self.assertNotIn("<script>", result)

    def test_multiple_italic_segments(self):
        result = safe_title("*one* and *two*")
        self.assertEqual(result, "<i>one</i> and <i>two</i>")

    def test_asterisk_without_pair_unchanged(self):
        result = safe_title("rating: 5*")
        # Single asterisk with no closing match stays as-is
        self.assertIn("5*", result)

    def test_empty_string(self):
        result = safe_title("")
        self.assertEqual(result, "")

    def test_ampersand_escaped(self):
        result = safe_title("Tom & Jerry")
        self.assertIn("&amp;", result)


class PlainTitleTests(TestCase):
    def test_plain_text_unchanged(self):
        self.assertEqual(plain_title("Hello World"), "Hello World")

    def test_strips_single_asterisks(self):
        self.assertEqual(plain_title("Review of *The Great Gatsby*"), "Review of The Great Gatsby")

    def test_strips_double_asterisks(self):
        self.assertEqual(plain_title("A **Bold** Statement"), "A Bold Statement")

    def test_strips_nbsp(self):
        self.assertEqual(plain_title("Hello&nbsp;World"), "Hello World")

    def test_mixed(self):
        self.assertEqual(plain_title("**Bold** and *italic*&nbsp;text"), "Bold and italic text")

    def test_empty_string(self):
        self.assertEqual(plain_title(""), "")

    def test_no_formatting(self):
        self.assertEqual(plain_title("Just a normal title"), "Just a normal title")

    def test_returns_plain_string(self):
        result = plain_title("*italic*")
        self.assertNotIsInstance(result, SafeString)
