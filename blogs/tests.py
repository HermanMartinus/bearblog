import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from django.utils.safestring import SafeString

from blogs.models import Blog, Post, Stylesheet
from blogs.templatetags.custom_tags import apply_filters, safe_title, plain_title


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


class ApplyFiltersExcludeTagTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='testuser', password='pass')
        self.blog = Blog.objects.create(user=self.user, title='Test Blog', subdomain='test-exclude')
        now = timezone.now()

        self.post_python = Post.objects.create(
            blog=self.blog, uid='p1', title='Python Basics', slug='python-basics',
            published_date=now, content='content',
            all_tags=json.dumps(['python', 'tutorial']),
        )
        self.post_django = Post.objects.create(
            blog=self.blog, uid='p2', title='Django Guide', slug='django-guide',
            published_date=now, content='content',
            all_tags=json.dumps(['python', 'django']),
        )
        self.post_personal = Post.objects.create(
            blog=self.blog, uid='p3', title='My Day', slug='my-day',
            published_date=now, content='content',
            all_tags=json.dumps(['personal']),
        )
        self.post_draft = Post.objects.create(
            blog=self.blog, uid='p4', title='Draft Ideas', slug='draft-ideas',
            published_date=now, content='content',
            all_tags=json.dumps(['personal', 'draft']),
        )
        self.all_posts = self.blog.posts.filter(publish=True)

    def test_exclude_single_tag(self):
        result = apply_filters(self.all_posts, tag='-personal')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Python Basics', 'Django Guide'})

    def test_exclude_multiple_tags(self):
        result = apply_filters(self.all_posts, tag='-personal,-tutorial')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Django Guide'})

    def test_include_and_exclude(self):
        result = apply_filters(self.all_posts, tag='python,-tutorial')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Django Guide'})

    def test_exclude_only_keeps_non_matching(self):
        result = apply_filters(self.all_posts, tag='-draft')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Python Basics', 'Django Guide', 'My Day'})

    def test_bare_dash_ignored(self):
        result = apply_filters(self.all_posts, tag='-')
        self.assertEqual(len(result), 4)
