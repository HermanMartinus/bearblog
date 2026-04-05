from django.test import SimpleTestCase
from blogs.utils import sanitize_html
class TestSanitization(SimpleTestCase):
    def test_sanitize_html_allows_mega_iframe(self):
        html = '<iframe src="https://mega.nz/embed/abc#key" width="640" height="360" allowfullscreen></iframe>'
        sanitized = sanitize_html(html)
        self.assertIn('<iframe', sanitized)
        self.assertIn('mega.nz/embed/abc#key', sanitized)

    def test_sanitize_html_blocks_arbitrary_iframe(self):
        html = '<iframe src="https://example.com/embed"></iframe>'
        sanitized = sanitize_html(html)
        self.assertNotIn('<iframe', sanitized)
        self.assertNotIn('example.com/embed', sanitized)
