import json
import os
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
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


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class DiscoverCSRFTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.staff_user = User.objects.create_user(username='staffuser', password='pass', is_staff=True)
        self.regular_user = User.objects.create_user(username='regularuser', password='pass')

        self.blog_owner = User.objects.create_user(username='blogowner', password='pass')
        self.blog = Blog.objects.create(
            user=self.blog_owner,
            title='Test Blog',
            subdomain='testblog',
            reviewed=True,
            hidden=False,
        )
        self.post = Post.objects.create(
            blog=self.blog,
            uid='disc1',
            title='Discoverable Post',
            slug='discoverable-post',
            published_date=timezone.now(),
            publish=True,
            make_discoverable=True,
            content='x' * 200,
        )

    # --- Admin action tests ---

    def test_staff_post_without_csrf_token_is_rejected(self):
        """Staff POST without CSRF token should be rejected with 403."""
        self.client.login(username='staffuser', password='pass')
        response = self.client.post(
            '/discover/',
            {'hide-post': self.post.pk},
            enforce_csrf_checks=True,
        )
        self.assertEqual(response.status_code, 403)
        self.post.refresh_from_db()
        self.assertFalse(self.post.hidden)

    def _post_with_csrf(self, url, data):
        """POST with a valid CSRF token via cookie + form field."""
        self.client.get(url)  # sets csrftoken cookie
        token = self.client.cookies['csrftoken'].value
        data['csrfmiddlewaretoken'] = token
        return self.client.post(url, data)

    def test_staff_post_with_csrf_token_succeeds(self):
        """Staff POST with valid CSRF token should hide the post."""
        self.client.login(username='staffuser', password='pass')
        response = self._post_with_csrf('/discover/', {'hide-post': self.post.pk})
        self.assertEqual(response.status_code, 200)
        self.post.refresh_from_db()
        self.assertTrue(self.post.hidden)

    def test_non_staff_post_does_not_execute_admin_action(self):
        """Non-staff user POST should not execute admin actions."""
        self.client.login(username='regularuser', password='pass')
        self._post_with_csrf('/discover/', {'hide-post': self.post.pk})
        self.post.refresh_from_db()
        self.assertFalse(self.post.hidden)

    # --- User hide list tests ---

    def test_hide_adds_subdomain_to_hide_list(self):
        """Authenticated user can hide a blog from their discover feed."""
        self.client.login(username='regularuser', password='pass')
        self._post_with_csrf('/discover/', {'subdomain': 'testblog', 'action': 'hide'})
        self.regular_user.settings.refresh_from_db()
        self.assertIn('testblog', self.regular_user.settings.discovery_hide_list)

    def test_unhide_removes_subdomain_from_hide_list(self):
        """Authenticated user can unhide a blog from their discover feed."""
        self.regular_user.settings.discovery_hide_list = ['testblog']
        self.regular_user.settings.save()

        self.client.login(username='regularuser', password='pass')
        self._post_with_csrf('/discover/', {'subdomain': 'testblog', 'action': 'unhide'})
        self.regular_user.settings.refresh_from_db()
        self.assertNotIn('testblog', self.regular_user.settings.discovery_hide_list)


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver', 'STAFF_API_KEY': 'test-key'})
class StaffApiBlogReviewTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='bloguser', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='Test Blog',
            subdomain='testblog-review',
            reviewed=False,
            permanent_ignore=False,
            flagged=False,
            to_review=False,
            content='A' * 250,
        )
        # Backdate created_date to satisfy >1 day filter
        Blog.objects.filter(pk=self.blog.pk).update(
            created_date=timezone.now() - timezone.timedelta(days=3)
        )
        self.blog.refresh_from_db()

        self.post = Post.objects.create(
            blog=self.blog,
            uid='rev1',
            title='Test Post',
            slug='test-post',
            published_date=timezone.now(),
            content='B' * 500,
        )
        self.auth = {'HTTP_X_API_KEY': 'test-key'}

    # --- GET /staff-api/unreviewed-blogs/ ---

    def test_blogs_list_requires_auth(self):
        response = self.client.get('/staff-api/unreviewed-blogs/')
        self.assertEqual(response.status_code, 401)

    def test_blogs_list_returns_unreviewed(self):
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        subdomains = [b['subdomain'] for b in data['blogs']]
        self.assertIn('testblog-review', subdomains)

    def test_blogs_list_excludes_reviewed(self):
        self.blog.reviewed = True
        self.blog.save()
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertNotIn('testblog-review', subdomains)

    def test_blogs_list_excludes_flagged(self):
        self.blog.flagged = True
        self.blog.save()
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertNotIn('testblog-review', subdomains)

    def test_blogs_list_excludes_permanent_ignore(self):
        self.blog.permanent_ignore = True
        self.blog.save()
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertNotIn('testblog-review', subdomains)

    def test_blogs_list_excludes_inactive_user(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertNotIn('testblog-review', subdomains)

    def test_blogs_list_excludes_to_review(self):
        self.blog.to_review = True
        self.blog.save()
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertNotIn('testblog-review', subdomains)

    def test_blogs_list_excludes_too_new(self):
        Blog.objects.filter(pk=self.blog.pk).update(created_date=timezone.now())
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertNotIn('testblog-review', subdomains)

    def test_blogs_list_excludes_empty_short_content_no_link(self):
        self.post.delete()
        self.blog.content = 'Short'
        self.blog.save()
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertNotIn('testblog-review', subdomains)

    def test_blogs_list_includes_empty_with_link(self):
        self.post.delete()
        self.blog.content = 'Visit http://example.com'
        self.blog.save()
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        self.assertIn('testblog-review', subdomains)

    def test_blogs_list_includes_posts_preview(self):
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        blog_entry = [b for b in response.json()['blogs'] if b['subdomain'] == 'testblog-review'][0]
        self.assertIn('posts', blog_entry)
        self.assertEqual(len(blog_entry['posts']), 1)
        # Content should be truncated to 300 chars
        self.assertLessEqual(len(blog_entry['posts'][0]['content']), 300)

    def test_blogs_list_ordered_by_created_date(self):
        user2 = User.objects.create_user(username='bloguser2', password='pass')
        blog2 = Blog.objects.create(
            user=user2, title='Older Blog', subdomain='older-blog',
            reviewed=False, permanent_ignore=False, flagged=False,
            to_review=False, content='A' * 250,
        )
        Post.objects.create(
            blog=blog2, uid='rev2', title='Older Post', slug='older-post',
            published_date=timezone.now(), content='C' * 500,
        )
        # Backdate after post creation (Post.save triggers blog.save)
        Blog.objects.filter(pk=blog2.pk).update(
            created_date=timezone.now() - timezone.timedelta(days=10)
        )
        response = self.client.get('/staff-api/unreviewed-blogs/', **self.auth)
        subdomains = [b['subdomain'] for b in response.json()['blogs']]
        idx_older = subdomains.index('older-blog')
        idx_newer = subdomains.index('testblog-review')
        self.assertLess(idx_older, idx_newer)

    # --- PATCH /staff-api/blog/<subdomain>/ with is_active ---

    def test_patch_blog_deactivate_user(self):
        response = self.client.patch(
            '/staff-api/blog/testblog-review/',
            json.dumps({'is_active': False}),
            content_type='application/json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.is_active)

    def test_patch_blog_activate_user(self):
        self.user.is_active = False
        self.user.save()
        response = self.client.patch(
            '/staff-api/blog/testblog-review/',
            json.dumps({'is_active': True}),
            content_type='application/json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    # --- PATCH /staff-api/blog/<subdomain>/ with ignored_date ---

    def test_patch_blog_set_ignored_date(self):
        response = self.client.patch(
            '/staff-api/blog/testblog-review/',
            json.dumps({'ignored_date': timezone.now().isoformat()}),
            content_type='application/json',
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.blog.refresh_from_db()
        self.assertIsNotNone(self.blog.ignored_date)
