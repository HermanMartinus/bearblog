import json
import os
from unittest import mock
from zoneinfo import ZoneInfo

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from django.utils.safestring import SafeString

from blogs.models import Blog, Post, Stylesheet
from blogs.templatetags.custom_tags import apply_filters, safe_title, plain_title, markdown, markdown_renderer, replace_inline_latex, escape_currency, fix_links, clean, element_replacement, excluding_pre


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


class PostListTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='testuser', password='pass')

        # Blog with tagged posts for tag filtering tests
        self.tag_blog = Blog.objects.create(user=self.user, title='Tag Blog', subdomain='test-tags')
        now = timezone.now()
        self.post_python = Post.objects.create(
            blog=self.tag_blog, uid='p1', title='Python Basics', slug='python-basics',
            published_date=now, content='content',
            all_tags=json.dumps(['python', 'tutorial']),
        )
        self.post_django = Post.objects.create(
            blog=self.tag_blog, uid='p2', title='Django Guide', slug='django-guide',
            published_date=now, content='content',
            all_tags=json.dumps(['python', 'django']),
        )
        self.post_personal = Post.objects.create(
            blog=self.tag_blog, uid='p3', title='My Day', slug='my-day',
            published_date=now, content='content',
            all_tags=json.dumps(['personal']),
        )
        self.post_draft = Post.objects.create(
            blog=self.tag_blog, uid='p4', title='Draft Ideas', slug='draft-ideas',
            published_date=now, content='content',
            all_tags=json.dumps(['personal', 'draft']),
        )
        self.tag_posts = self.tag_blog.posts.filter(publish=True)

        # Blog with dated posts for date range tests
        self.date_blog = Blog.objects.create(user=self.user, title='Date Blog', subdomain='test-dates')
        self.post_jan = Post.objects.create(
            blog=self.date_blog, uid='d1', title='January Post', slug='jan-post',
            published_date=timezone.datetime(2024, 1, 15, tzinfo=ZoneInfo('UTC')),
            content='content',
        )
        self.post_jun = Post.objects.create(
            blog=self.date_blog, uid='d2', title='June Post', slug='jun-post',
            published_date=timezone.datetime(2024, 6, 15, tzinfo=ZoneInfo('UTC')),
            content='content',
        )
        self.post_dec = Post.objects.create(
            blog=self.date_blog, uid='d3', title='December Post', slug='dec-post',
            published_date=timezone.datetime(2024, 12, 31, 23, 59, tzinfo=ZoneInfo('UTC')),
            content='content',
        )
        self.date_posts = self.date_blog.posts.filter(publish=True)

    # --- Tag filtering ---

    def test_exclude_single_tag(self):
        result = apply_filters(self.tag_posts, tag='-personal')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Python Basics', 'Django Guide'})

    def test_exclude_multiple_tags(self):
        result = apply_filters(self.tag_posts, tag='-personal,-tutorial')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Django Guide'})

    def test_include_and_exclude(self):
        result = apply_filters(self.tag_posts, tag='python,-tutorial')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Django Guide'})

    def test_exclude_only_keeps_non_matching(self):
        result = apply_filters(self.tag_posts, tag='-draft')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'Python Basics', 'Django Guide', 'My Day'})

    def test_bare_dash_ignored(self):
        result = apply_filters(self.tag_posts, tag='-')
        self.assertEqual(len(result), 4)

    # --- Date range ---

    def test_from_date_only(self):
        result = apply_filters(self.date_posts, from_date='2024-06-01')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'June Post', 'December Post'})

    def test_to_date_only(self):
        result = apply_filters(self.date_posts, to_date='2024-06-30')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'January Post', 'June Post'})

    def test_from_and_to_date(self):
        result = apply_filters(self.date_posts, from_date='2024-02-01', to_date='2024-11-30')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'June Post'})

    def test_to_date_inclusive_of_full_day(self):
        """to:2024-12-31 should include a post at 23:59 on that day."""
        result = apply_filters(self.date_posts, to_date='2024-12-31')
        titles = {p.title for p in result}
        self.assertIn('December Post', titles)

    def test_invalid_date_ignored(self):
        """Malformed dates should be silently ignored, returning all posts."""
        result = apply_filters(self.date_posts, from_date='not-a-date')
        self.assertEqual(len(list(result)), 3)

    def test_date_range_with_tag(self):
        """Date range should compose with tag filtering."""
        self.post_jun.all_tags = json.dumps(['python'])
        self.post_jun.save()
        result = apply_filters(self.date_posts, tag='python', from_date='2024-01-01', to_date='2024-12-31')
        titles = {p.title for p in result}
        self.assertEqual(titles, {'June Post'})


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class PostListDataTagsTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='datatagsuser', password='pass')
        self.blog = Blog.objects.create(user=self.user, title='Tags Blog', subdomain='tags-blog')

    def test_post_with_tags_has_data_tags_attribute(self):
        Post.objects.create(
            blog=self.blog, uid='dt1', title='Tagged', slug='tagged',
            published_date=timezone.now(), content='x',
            all_tags=json.dumps(['alpha', 'beta']),
        )
        response = self.client.get('/blog/', SERVER_NAME='tags-blog.testserver')
        self.assertIn('data-tags="alpha,beta"', response.content.decode())

    def test_post_without_tags_has_empty_data_tags(self):
        Post.objects.create(
            blog=self.blog, uid='dt2', title='Untagged', slug='untagged',
            published_date=timezone.now(), content='x',
        )
        response = self.client.get('/blog/', SERVER_NAME='tags-blog.testserver')
        self.assertIn('data-tags=""', response.content.decode())


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


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class DiscoverRandomFeedTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='randomuser', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='Random Blog',
            subdomain='randomblog',
            reviewed=True,
            hidden=False,
        )
        for i in range(3):
            Post.objects.create(
                blog=self.blog,
                uid=f'rand{i}',
                title=f'Random Post {i}',
                slug=f'random-post-{i}',
                published_date=timezone.now(),
                publish=True,
                make_discoverable=True,
                content='x' * 200,
            )

    def test_random_feed_returns_200(self):
        response = self.client.get('/discover/?random=true')
        self.assertEqual(response.status_code, 200)

    def test_random_feed_contains_posts(self):
        response = self.client.get('/discover/?random=true')
        self.assertEqual(len(response.context['posts']), 3)

    def test_random_context_variable_set(self):
        response = self.client.get('/discover/?random=true')
        self.assertTrue(response.context['random'])

    def test_random_not_set_on_default(self):
        response = self.client.get('/discover/')
        self.assertFalse(response.context.get('random'))

    def test_random_tab_in_nav(self):
        response = self.client.get('/discover/?random=true')
        content = response.content.decode()
        self.assertIn('<b><a href="/discover/?random=true">Random</a></b>', content)

    def test_random_tab_not_bold_on_trending(self):
        response = self.client.get('/discover/')
        content = response.content.decode()
        self.assertIn('<a href="/discover/?random=true">Random</a>', content)
        self.assertNotIn('<b><a href="/discover/?random=true">Random</a></b>', content)

    def test_random_shows_more_link(self):
        response = self.client.get('/discover/?random=true')
        content = response.content.decode()
        self.assertIn('More random posts', content)
        self.assertNotIn('Next', content)
        self.assertNotIn('Previous', content)


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


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class DiscoverFeedMarkdownTests(TestCase):
    """Verify the discover feed uses the full markdown renderer (not bare mistune)."""

    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='feedmduser', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='Feed MD Blog',
            subdomain='feedmd',
            reviewed=True,
            hidden=False,
        )

    def _make_post(self, content):
        """Create a discoverable post with the given content (padded to 100+ chars)."""
        # Pad content to meet the 100-char minimum length filter
        padded = content + '\n\n' + ('x' * 150)
        post = Post.objects.create(
            blog=self.blog,
            uid=f'fmd-{Post.objects.count()}',
            title='Test Post',
            slug=f'test-post-{Post.objects.count()}',
            published_date=timezone.now(),
            publish=True,
            make_discoverable=True,
            content=padded,
        )
        return post

    def _get_feed_content(self):
        response = self.client.get('/discover/feed/')
        self.assertEqual(response.status_code, 200)
        return response.content.decode()

    def test_typographic_replacements(self):
        """(c) should render as copyright symbol."""
        self._make_post('Copyright (c) 2024')
        content = self._get_feed_content()
        self.assertIn('©', content)
        self.assertNotIn('(c)', content)

    def test_heading_ids(self):
        """Headings should get slugified IDs from the custom renderer."""
        self._make_post('## My Heading')
        content = self._get_feed_content()
        self.assertIn('id=my-heading', content)

    def test_duplicate_heading_ids(self):
        """Duplicate headings should get suffixed IDs."""
        self._make_post('## My Heading\n## My Heading\n## My Heading')
        content = self._get_feed_content()
        self.assertIn('id=my-heading', content)
        self.assertIn('id=my-heading-1', content)
        self.assertIn('id=my-heading-2', content)

    def test_code_highlighting(self):
        """Fenced code blocks should get Pygments syntax highlighting."""
        self._make_post('```python\nprint("hello")\n```')
        content = self._get_feed_content()
        self.assertIn('class="highlight"', content)

    def test_template_variable_replacement(self):
        """{{ post_published_date }} should be replaced with the actual date."""
        self._make_post('Published on {{ post_published_date }}')
        content = self._get_feed_content()
        self.assertNotIn('{{ post_published_date }}', content)


class ScriptTagTests(TestCase):
    """Verify that <script> blocks are not corrupted by markdown text processing."""

    def test_inline_script_no_br(self):
        """Backslash-n in inline script should NOT be converted to <br>."""
        content = r'text <script>var msg = "hi\nthere";</script>'
        result = markdown_renderer(content)
        self.assertNotIn('<br>', result)
        self.assertIn(r'\n', result)

    def test_inline_script_no_typographic_replacements(self):
        """(c) inside inline script should NOT become a copyright symbol."""
        content = 'text <script>var x = "(c) 2024";</script>'
        result = markdown_renderer(content)
        self.assertNotIn('\u00a9', result)
        self.assertIn('(c)', result)

    def test_block_script_preserved(self):
        """Block-level script content should be preserved as-is."""
        content = '<script>\nvar x = "(c)";\nvar y = "hello\\nworld";\n</script>'
        result = markdown_renderer(content)
        self.assertIn('(c)', result)
        self.assertNotIn('\u00a9', result)
        self.assertNotIn('<br>', result)

    def test_script_with_surrounding_markdown(self):
        """Script blocks should not break surrounding markdown rendering."""
        content = '# Hello\n\ntext <script>var x = 1;</script>\n\n**bold**'
        result = markdown_renderer(content)
        self.assertIn('<h1', result)
        self.assertIn('<strong>bold</strong>', result)
        self.assertIn('<script>var x = 1;</script>', result)

    def test_multiple_scripts(self):
        """Multiple script blocks should all be protected."""
        content = 'a <script>var x = "(c)";</script> b <script>var y = "hi\\nthere";</script>'
        result = markdown_renderer(content)
        self.assertNotIn('\u00a9', result)
        self.assertNotIn('<br>', result)

    def test_script_in_fenced_code_block_not_extracted(self):
        """Script tags inside fenced code blocks should render as code, not be extracted."""
        content = '```html\n<div>\n    <script>alert("test\\n");</script>\n</div>\n```'
        result = markdown_renderer(content)
        self.assertNotIn('BEAR_SCRIPT', result)
        self.assertIn('alert', result)

    def test_many_code_blocks_no_corruption(self):
        """10+ code blocks should not suffer placeholder substring collision."""
        blocks = []
        for i in range(12):
            lang = 'python' if i % 2 == 0 else ''
            blocks.append(f'```{lang}\nblock_content_{i}\n```')
        content = '\n\nsome text\n\n'.join(blocks)
        result = markdown_renderer(content)
        for i in range(12):
            self.assertIn(f'block_content_{i}', result)
        self.assertNotIn('BEAR_CODE', result)

    def test_script_template_variables_replaced(self):
        """{{ blog_title }} and {{ post_title }} inside <script> should be replaced."""
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        user = User.objects.create_user(username='scriptvar', password='pass')
        blog = Blog.objects.create(user=user, title='My Blog', subdomain='scriptvar')
        user.settings.upgraded = True
        user.settings.save()
        post = Post.objects.create(
            blog=blog,
            uid='sv-1',
            title='My Post',
            slug='my-post',
            published_date=timezone.now(),
            publish=True,
            content='placeholder',
        )
        content = '<script>var title = "{{ blog_title }}"; var post = "{{ post_title }}";</script>'
        result = markdown(content, blog=blog, post=post)
        self.assertNotIn('{{ blog_title }}', result)
        self.assertNotIn('{{ post_title }}', result)
        self.assertIn('My Blog', result)
        self.assertIn('My Post', result)


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class ContentTypeTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='ctype_user', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='CT Blog',
            subdomain='ctblog',
        )
        self.post = Post.objects.create(
            blog=self.blog,
            uid='ct1',
            title='CT Post',
            slug='ct-post',
            published_date=timezone.now(),
            content='Test content',
        )

    # --- ping() ---

    def test_ping_valid_returns_text_plain(self):
        self.blog.domain = 'example.com'
        self.blog.save()
        from django.core.cache import cache
        cache.delete('domain_map')
        response = self.client.get('/ping/', {'domain': 'example.com'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    def test_ping_invalid_returns_text_plain(self):
        response = self.client.get('/ping/', {'domain': 'nonexistent.com'})
        self.assertEqual(response.status_code, 422)
        self.assertIn('text/plain', response['Content-Type'])

    def test_ping_missing_domain_returns_text_plain(self):
        response = self.client.get('/ping/')
        self.assertEqual(response.status_code, 422)
        self.assertIn('text/plain', response['Content-Type'])

    # --- upvote() ---

    def test_upvote_success_returns_text_plain(self):
        response = self.client.post('/upvote/', {'uid': 'ct1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    def test_upvote_forbidden_returns_text_plain(self):
        response = self.client.post('/upvote/', {})
        self.assertEqual(response.status_code, 403)
        self.assertIn('text/plain', response['Content-Type'])

    # --- hit() ---

    def test_hit_forbidden_returns_text_plain(self):
        response = self.client.get('/hit/')
        self.assertEqual(response.status_code, 403)
        self.assertIn('text/plain', response['Content-Type'])

    @mock.patch('blogs.views.analytics.get_country', return_value={'country_name': 'Test'})
    @mock.patch.dict(os.environ, {'SALT': 'test-salt'})
    def test_hit_success_returns_text_plain(self, mock_country):
        response = self.client.get('/hit/', {
            'blog': 'ctblog',
            'score': '100',
            'token': '/',
        }, HTTP_USER_AGENT='Mozilla/5.0')
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    # --- email_subscribe() ---

    def test_email_subscribe_dodgy_returns_text_plain(self):
        response = self.client.post('/email-subscribe/', {})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    def test_email_subscribe_bad_email_returns_text_plain(self):
        response = self.client.post(
            '/email-subscribe/',
            {'confirm': '829389c2a9f0402b8a3600e52f2ad4e1', 'email': 'not-an-email'},
            SERVER_NAME='ctblog.testserver',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    def test_email_subscribe_success_returns_text_plain(self):
        response = self.client.post(
            '/email-subscribe/',
            {'confirm': '829389c2a9f0402b8a3600e52f2ad4e1', 'email': 'test@example.com'},
            SERVER_NAME='ctblog.testserver',
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    # --- upload_image() ---

    @mock.patch('blogs.views.media.upload_files', return_value=['https://example.com/test.png'])
    def test_upload_image_success_returns_json(self, mock_upload):
        self.user.settings.upgraded = True
        self.user.settings.save()
        self.client.login(username='ctype_user', password='pass')
        from django.core.files.uploadedfile import SimpleUploadedFile
        f = SimpleUploadedFile('test.png', b'\x89PNG', content_type='image/png')
        response = self.client.post('/ctblog/dashboard/upload-image/', {'file': f})
        self.assertEqual(response.status_code, 200)
        self.assertIn('application/json', response['Content-Type'])

    def test_upload_image_failure_returns_text_plain(self):
        self.client.login(username='ctype_user', password='pass')
        response = self.client.post('/ctblog/dashboard/upload-image/')
        self.assertEqual(response.status_code, 400)
        self.assertIn('text/plain', response['Content-Type'])

    # --- email_list() export-txt ---

    def test_email_list_export_txt_returns_text_plain(self):
        self.user.settings.upgraded = True
        self.user.settings.save()
        self.client.login(username='ctype_user', password='pass')
        response = self.client.get('/ctblog/dashboard/email-list/', {'export-txt': '1'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/plain', response['Content-Type'])

    # --- settings() export ---

    def _get_export(self):
        self.client.login(username='ctype_user', password='pass')
        return self.client.get('/ctblog/dashboard/settings/', {'export-md': 'true'})

    def _read_zip(self, response):
        import zipfile, io
        return zipfile.ZipFile(io.BytesIO(response.content))

    def test_export_returns_zip(self):
        response = self._get_export()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')

    def test_export_zip_contains_md_file(self):
        response = self._get_export()
        zf = self._read_zip(response)
        self.assertIn('ct-post.md', zf.namelist())

    def test_export_frontmatter_contains_title(self):
        response = self._get_export()
        zf = self._read_zip(response)
        content = zf.read('ct-post.md').decode('utf-8')
        self.assertIn('title: CT Post', content)

    def test_export_contains_content_after_frontmatter(self):
        response = self._get_export()
        zf = self._read_zip(response)
        content = zf.read('ct-post.md').decode('utf-8')
        self.assertIn('Test content', content)

    def test_export_excludes_sensitive_fields(self):
        response = self._get_export()
        zf = self._read_zip(response)
        content = zf.read('ct-post.md').decode('utf-8')
        self.assertNotIn('upvotes', content)
        self.assertNotIn('shadow_votes', content)
        self.assertNotIn('hidden', content)
        self.assertNotIn('score', content)

    def test_export_duplicate_slugs_get_suffix(self):
        Post.objects.create(
            blog=self.blog, uid='ct2', title='CT Post Dupe',
            slug='ct-post', published_date=timezone.now(), content='Dupe',
        )
        response = self._get_export()
        zf = self._read_zip(response)
        names = zf.namelist()
        self.assertIn('ct-post.md', names)
        self.assertIn('ct-post-2.md', names)

    def test_export_optional_fields_omitted_when_empty(self):
        response = self._get_export()
        zf = self._read_zip(response)
        content = zf.read('ct-post.md').decode('utf-8')
        self.assertNotIn('alias:', content)

    def test_export_tags_comma_separated(self):
        self.post.all_tags = '["python", "django"]'
        self.post.save()
        response = self._get_export()
        zf = self._read_zip(response)
        content = zf.read('ct-post.md').decode('utf-8')
        self.assertIn('tags: django, python', content)


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class ResolveAddressTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='resolveuser', password='pass')
        self.blog = Blog.objects.create(user=self.user, title='Resolve Blog', subdomain='myblog')

    @mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
    def test_main_site_returns_none(self):
        from blogs.views.blog import resolve_address
        request = self.client.get('/').wsgi_request
        request.META['HTTP_HOST'] = 'testserver'
        request.META['SERVER_NAME'] = 'testserver'
        self.assertIsNone(resolve_address(request))

    @mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
    def test_subdomain_returns_blog(self):
        response = self.client.get('/', SERVER_NAME='myblog.testserver')
        self.assertEqual(response.status_code, 200)

    @mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
    def test_nonexistent_subdomain_returns_404(self):
        response = self.client.get('/', SERVER_NAME='nosuchblog.testserver')
        self.assertEqual(response.status_code, 404)

    @mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
    def test_feed_with_subdomain(self):
        response = self.client.get('/feed/', SERVER_NAME='myblog.testserver')
        self.assertEqual(response.status_code, 200)

    @mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
    def test_robots_with_subdomain(self):
        response = self.client.get('/robots.txt', SERVER_NAME='myblog.testserver')
        self.assertEqual(response.status_code, 200)


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class FeedTagTitleTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='feedtag_user', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='Feed Tag Blog',
            subdomain='feedtagblog',
        )
        self.post = Post.objects.create(
            blog=self.blog,
            uid='ft1',
            title='Tagged Post',
            slug='tagged-post',
            published_date=timezone.now(),
            publish=True,
            content='Some content',
            all_tags=json.dumps(['news']),
        )

    def test_atom_feed_title_without_tag(self):
        response = self.client.get('/feed/', SERVER_NAME='feedtagblog.testserver')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('<title>Feed Tag Blog</title>', content)

    def test_atom_feed_title_with_tag(self):
        response = self.client.get('/feed/?q=news', SERVER_NAME='feedtagblog.testserver')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('<title>Feed Tag Blog - news</title>', content)

    def test_rss_feed_title_with_tag(self):
        response = self.client.get('/rss/', {'q': 'news'}, SERVER_NAME='feedtagblog.testserver')
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('<title>Feed Tag Blog - news</title>', content)


class InlineLatexTests(TestCase):
    """Tests for replace_inline_latex and currency vs math rendering."""

    def test_currency_pair_does_not_break_markdown_links(self):
        text = 'are [Bazqux](https://bazqux.com/), which is $30/year, and [Feedbin](https://feedbin.com/), which is $50/year.'
        result = markdown_renderer(escape_currency(replace_inline_latex(text)))
        self.assertIn('Feedbin</a>', result)
        self.assertIn('Bazqux</a>', result)

    def test_math_starting_with_digit_preserved(self):
        text = r'approximately $3 \times 10^8$ m/s.'
        result = markdown_renderer(escape_currency(replace_inline_latex(text)))
        self.assertIn('math', result)

    def test_currency_and_math_together(self):
        text = r'$c$ is the speed of light (approximately $3 \times 10^8$ m/s). It costs $30/year and $50/year.'
        result = markdown_renderer(escape_currency(replace_inline_latex(text)))
        self.assertIn('math', result)
        self.assertNotIn('30/year', result.split('math')[0] if 'math' in result else '')
        self.assertIn('$30', result)
        self.assertIn('$50', result)

    def test_simple_inline_math_preserved(self):
        text = '$E=mc^2$'
        result = markdown_renderer(replace_inline_latex(text))
        self.assertIn('math', result)

    def test_variable_math_preserved(self):
        text = '$E$ is the energy'
        result = markdown_renderer(replace_inline_latex(text))
        self.assertIn('math', result)

    def test_old_double_dollar_inline_converted(self):
        text = '$$E=mc^2$$'
        result = markdown_renderer(replace_inline_latex(text))
        self.assertIn('math', result)

    def test_single_currency_no_pair(self):
        text = 'It costs $50.'
        result = replace_inline_latex(text)
        self.assertIn('$50', result)
        self.assertNotIn('\\$', result)

    def test_dollar_not_escaped_in_code_block(self):
        text = '```sql\nPREPARE my_query (integer) AS\nSELECT * FROM foo WHERE bar IS NOT DISTINCT FROM $1;\n\nEXECUTE my_query(1);\n```'
        result = markdown(text)
        self.assertNotIn('\\$', result)

    def test_double_dollar_not_removed_in_code_block(self):
        text = "```\n$$ some latex shouldn't render here $$\n```"
        result = markdown(text)
        self.assertNotIn('math', result)
        self.assertIn('$$', result)

    def test_7th_renders_as_latex(self):
        text = r'This should render as 7^th^: $7^\text{th}$'
        result = markdown_renderer(escape_currency(replace_inline_latex(text)))
        self.assertIn('math', result)

    def test_already_escaped_currency_not_double_escaped(self):
        text = r'$20 is good money, but \$50 is not.'
        result = escape_currency(text)
        self.assertNotIn('\\\\$', result)

    def test_decimal_latex_preserved(self):
        text = '$3.14$'
        result = markdown_renderer(escape_currency(replace_inline_latex(text)))
        self.assertIn('math', result)


class FaviconSvgTests(TestCase):
    """Verify the SVG favicon supports dark mode via prefers-color-scheme."""

    def test_favicon_svg_uses_current_color(self):
        svg_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'favicon.svg')
        with open(svg_path) as f:
            content = f.read()
        self.assertIn('currentColor', content)

    def test_favicon_svg_has_dark_mode_media_query(self):
        svg_path = os.path.join(os.path.dirname(__file__), '..', 'static', 'favicon.svg')
        with open(svg_path) as f:
            content = f.read()
        self.assertIn('prefers-color-scheme:dark', content)


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class FaviconViewTests(TestCase):
    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='favuser', password='pass')
        self.blog = Blog.objects.create(user=self.user, title='Fav Blog', subdomain='favblog')

    def test_base_template_has_svg_favicon(self):
        """The main site base template should reference favicon.svg."""
        response = self.client.get('/discover/')
        content = response.content.decode()
        self.assertIn('favicon.svg', content)
        self.assertIn('image/svg+xml', content)

    def test_favicon_ico_redirects_to_ico(self):
        response = self.client.get('/favicon.ico', SERVER_NAME='favblog.testserver')
        self.assertEqual(response.status_code, 301)
        self.assertIn('/static/favicon.ico', response['Location'])

    def test_apple_touch_icon_redirects_to_png(self):
        response = self.client.get('/apple-touch-icon.png', SERVER_NAME='favblog.testserver')
        self.assertEqual(response.status_code, 301)
        self.assertIn('/static/favicon.png', response['Location'])

    def test_favicon_fallback_redirects_to_svg(self):
        response = self.client.get('/favicons/site.webmanifest', SERVER_NAME='favblog.testserver')
        self.assertEqual(response.status_code, 301)
        self.assertIn('/static/favicon.svg', response['Location'])


class HeadingTests(TestCase):
    """Tests for MyRenderer.heading() -- slug IDs, duplicates, levels."""

    def test_h1_with_id(self):
        result = markdown_renderer('# Title')
        self.assertIn('<h1 id=title>Title</h1>', result)

    def test_h2_slugified_id(self):
        result = markdown_renderer('## Hello World')
        self.assertIn('<h2 id=hello-world>Hello World</h2>', result)

    def test_h3(self):
        result = markdown_renderer('### Sub')
        self.assertIn('<h3 id=sub>Sub</h3>', result)

    def test_h6(self):
        result = markdown_renderer('###### Deep')
        self.assertIn('<h6 id=deep>Deep</h6>', result)

    def test_duplicate_ids_suffixed(self):
        result = markdown_renderer('## Intro\n## Intro\n## Intro')
        self.assertIn('id=intro', result)
        self.assertIn('id=intro-1', result)
        self.assertIn('id=intro-2', result)

    def test_ids_reset_between_calls(self):
        r1 = markdown_renderer('## Test')
        r2 = markdown_renderer('## Test')
        self.assertEqual(r1, r2)

    def test_ampersand_stripped_from_slug(self):
        result = markdown_renderer('## Rock & Roll')
        self.assertIn('id=rock-roll', result)

    def test_numeric_heading(self):
        result = markdown_renderer('## 42 is the answer')
        self.assertIn('id=42-is-the-answer', result)

    def test_heading_with_bold(self):
        result = markdown_renderer('## **Bold** heading')
        self.assertIn('<strong>Bold</strong>', result)
        self.assertIn('id=strongboldstrong-heading', result)

    def test_heading_with_inline_code(self):
        result = markdown_renderer('## Using `code` in heading')
        self.assertIn('<code>code</code>', result)
        self.assertIn('id=using-codecodecode-in-heading', result)

    def test_empty_heading(self):
        result = markdown_renderer('## ')
        self.assertIn('<h2 id=></h2>', result)

    def test_multiple_levels(self):
        result = markdown_renderer('# H1\n## H2\n### H3')
        self.assertIn('<h1 id=h1>', result)
        self.assertIn('<h2 id=h2>', result)
        self.assertIn('<h3 id=h3>', result)


class LinkTests(TestCase):
    """Tests for MyRenderer.link() -- normal, tab:, title attribute."""

    def test_normal_link(self):
        result = markdown_renderer('[Google](https://google.com)')
        self.assertIn("href='https://google.com'", result)
        self.assertNotIn('target', result)

    def test_tab_prefix_opens_new_tab(self):
        result = markdown_renderer('[Google](tab:https://google.com)')
        self.assertIn("target='_blank'", result)
        self.assertNotIn('tab:', result)

    def test_link_with_title(self):
        result = markdown_renderer('[Google](https://google.com "Search")')
        self.assertIn("title='Search'", result)

    def test_tab_link_with_title(self):
        result = markdown_renderer('[Google](tab:https://google.com "Search")')
        self.assertIn("target='_blank'", result)
        self.assertIn("title='Search'", result)

    def test_title_apostrophe_escaped(self):
        result = markdown_renderer('[Test](https://example.com "it\'s a test")')
        self.assertIn("it&apos;s a test", result)

    def test_link_text_preserved(self):
        result = markdown_renderer('[Click Here](https://example.com)')
        self.assertIn('>Click Here</a>', result)


class TypographicReplacementTests(TestCase):
    """Tests for typographic_replacements() via markdown_renderer()."""

    def test_copyright_lowercase(self):
        result = markdown_renderer('Copyright (c) 2024')
        self.assertIn('©', result)
        self.assertNotIn('(c)', result)

    def test_copyright_uppercase(self):
        result = markdown_renderer('Copyright (C) 2024')
        self.assertIn('©', result)

    def test_registered_lowercase(self):
        result = markdown_renderer('Brand (r)')
        self.assertIn('®', result)

    def test_registered_uppercase(self):
        result = markdown_renderer('Brand (R)')
        self.assertIn('®', result)

    def test_trademark_lowercase(self):
        result = markdown_renderer('Product (tm)')
        self.assertIn('™', result)

    def test_trademark_uppercase(self):
        result = markdown_renderer('Product (TM)')
        self.assertIn('™', result)

    def test_phonogram_lowercase(self):
        result = markdown_renderer('Sound (p) 2024')
        self.assertIn('℗', result)

    def test_phonogram_uppercase(self):
        result = markdown_renderer('Sound (P) 2024')
        self.assertIn('℗', result)

    def test_plus_minus(self):
        result = markdown_renderer('5+-2')
        self.assertIn('±', result)

    def test_backslash_n_becomes_br(self):
        result = markdown_renderer('hello\\nworld')
        self.assertIn('<br>', result)


class TrailingBackslashTests(TestCase):
    """Tests for standalone backslash -> <br> in text() method."""

    def test_standalone_backslash_paragraph(self):
        result = markdown_renderer('line1\n\n\\\\\n\nline2')
        self.assertIn('<br>', result)

    def test_markdown_hard_break(self):
        result = markdown_renderer('line1\\\\\nline2')
        self.assertIn('<br>', result)
        self.assertIn('line2', result)

    def test_double_backslash_becomes_br(self):
        result = markdown_renderer('hello \\\\ world')
        self.assertIn('<br>', result)


class HTMLPassthroughTests(TestCase):
    """Tests for inline_html() / block_html() with escape=False."""

    def test_block_html_passthrough(self):
        result = markdown_renderer('<div class="custom">hello</div>')
        self.assertIn('<div class="custom">hello</div>', result)

    def test_inline_html_passthrough(self):
        result = markdown_renderer('This has <span class="red">inline</span> HTML')
        self.assertIn('<span class="red">inline</span>', result)

    def test_nested_html_preserved(self):
        result = markdown_renderer('<div><p>nested</p></div>')
        self.assertIn('<div><p>nested</p></div>', result)


class RendererInlineMathTests(TestCase):
    """Tests for MyRenderer.inline_math() -- LaTeX to MathML."""

    def test_inline_math_renders_mathml(self):
        result = markdown_renderer('$x^2 + y^2 = z^2$')
        self.assertIn('math', result)
        self.assertIn('xmlns', result)

    def test_space_before_closing_dollar_renders_math(self):
        result = markdown_renderer('$text $')
        self.assertIn('math', result)
        self.assertIn('xmlns', result)

    def test_single_variable_renders(self):
        result = markdown_renderer('$E$ is energy')
        self.assertIn('math', result)


class RendererBlockMathTests(TestCase):
    """Tests for MyRenderer.block_math() -- display=block."""

    def test_block_math_display_block(self):
        result = markdown_renderer('$$\nE=mc^2\n$$')
        self.assertIn('display="block"', result)
        self.assertNotIn('display="inline"', result)

    def test_block_math_has_mathml_namespace(self):
        result = markdown_renderer('$$\nE=mc^2\n$$')
        self.assertIn('xmlns="http://www.w3.org/1998/Math/MathML"', result)


class CodeBlockTests(TestCase):
    """Tests for MyRenderer.block_code() -- Pygments highlighting."""

    def test_python_highlighting(self):
        result = markdown_renderer('```python\nprint("hello")\n```')
        self.assertIn('class="highlight"', result)
        self.assertIn('print', result)

    def test_no_language_fallback(self):
        result = markdown_renderer('```\nplain text\n```')
        self.assertIn('class="highlight"', result)
        self.assertIn('plain text', result)

    def test_invalid_language_fallback(self):
        result = markdown_renderer('```nonexistentlang\nsome code\n```')
        self.assertIn('class="highlight"', result)
        self.assertIn('some code', result)

    def test_tilde_fenced_code_block(self):
        result = markdown_renderer('~~~\ncode here\n~~~')
        self.assertIn('class="highlight"', result)
        self.assertIn('code here', result)

    def test_explicit_text_language(self):
        result = markdown_renderer('```text\nplain content\n```')
        self.assertIn('class="highlight"', result)


class IndentCodeDisabledTests(TestCase):
    """Tests that 8-space indentation does NOT create code blocks."""

    def test_eight_space_indent_no_code_block(self):
        result = markdown_renderer('        indented text')
        self.assertNotIn('<code>', result)
        self.assertNotIn('<pre>', result)
        self.assertIn('indented text', result)


class FixLinksTests(TestCase):
    """Tests for fix_links() -- parentheses escaping in URLs."""

    def test_escapes_parentheses_in_url(self):
        text = '[Wiki](https://en.wikipedia.org/wiki/Python_(programming_language))'
        result = fix_links(text)
        self.assertIn('%28', result)
        self.assertIn('%29', result)

    def test_normal_link_unchanged(self):
        text = '[Google](https://google.com)'
        result = fix_links(text)
        self.assertEqual(result, text)

    def test_tab_prefix_with_parentheses(self):
        text = '[Wiki](tab:https://en.wikipedia.org/wiki/Foo_(bar))'
        result = fix_links(text)
        self.assertIn('tab:', result)
        self.assertIn('%28', result)

    def test_no_parentheses_unchanged(self):
        text = '[test](https://example.com/path)'
        result = fix_links(text)
        self.assertEqual(result, text)

    def test_fix_then_render(self):
        text = '[Wiki](https://en.wikipedia.org/wiki/Python_(programming_language))'
        fixed = fix_links(text)
        result = markdown_renderer(fixed)
        self.assertIn('href=', result)
        self.assertIn('Wiki</a>', result)


class ReplaceInlineLatexDirectTests(TestCase):
    """Tests for replace_inline_latex() directly."""

    def test_double_dollar_converted(self):
        result = replace_inline_latex('$$x^2$$')
        self.assertEqual(result, '$x^2$')

    def test_currency_pair_escaped(self):
        result = escape_currency('$30/year and $50/year')
        self.assertIn('\\$30', result)
        self.assertIn('\\$50', result)

    def test_single_currency_no_pair(self):
        result = replace_inline_latex('costs $50.')
        self.assertIn('$50', result)
        self.assertNotIn('\\$', result)

    def test_multiline_block_math_unchanged(self):
        text = '$$\nE=mc^2\n$$'
        result = replace_inline_latex(text)
        self.assertEqual(result, text)

    def test_multiple_currency_pairs(self):
        result = escape_currency('between $10 and $20 or $30')
        self.assertIn('\\$10', result)
        self.assertIn('\\$20', result)


class StrikethroughPluginTests(TestCase):
    """Tests for ~~strikethrough~~ plugin."""

    def test_strikethrough(self):
        result = markdown_renderer('~~deleted~~')
        self.assertIn('<del>deleted</del>', result)

    def test_strikethrough_in_bold(self):
        result = markdown_renderer('**~~deleted~~**')
        self.assertIn('<strong><del>deleted</del></strong>', result)


class FootnotePluginTests(TestCase):
    """Tests for footnotes plugin."""

    def test_footnote_reference_and_definition(self):
        result = markdown_renderer('Text[^1]\n\n[^1]: Footnote content')
        self.assertIn('footnote-ref', result)
        self.assertIn('Footnote content', result)
        self.assertIn('class="footnotes"', result)

    def test_multiple_footnotes(self):
        result = markdown_renderer('First[^1] and second[^2]\n\n[^1]: Note one\n[^2]: Note two')
        self.assertIn('fn-1', result)
        self.assertIn('fn-2', result)
        self.assertIn('Note one', result)
        self.assertIn('Note two', result)


class TablePluginTests(TestCase):
    """Tests for markdown table plugin."""

    def test_basic_table(self):
        result = markdown_renderer('| a | b |\n| - | - |\n| 1 | 2 |')
        self.assertIn('<table>', result)
        self.assertIn('<th>a</th>', result)
        self.assertIn('<td>1</td>', result)

    def test_table_alignment(self):
        result = markdown_renderer('| Left | Center | Right |\n| :--- | :---: | ---: |\n| L | C | R |')
        self.assertIn('text-align:left', result)
        self.assertIn('text-align:center', result)
        self.assertIn('text-align:right', result)


class SuperscriptSubscriptPluginTests(TestCase):
    """Tests for ^superscript^ and ~subscript~ plugins."""

    def test_superscript(self):
        result = markdown_renderer('x^2^')
        self.assertIn('<sup>2</sup>', result)

    def test_subscript(self):
        result = markdown_renderer('H~2~O')
        self.assertIn('<sub>2</sub>', result)


class MarkPluginTests(TestCase):
    """Tests for ==mark== plugin."""

    def test_mark(self):
        result = markdown_renderer('==highlighted==')
        self.assertIn('<mark>highlighted</mark>', result)


class TaskListPluginTests(TestCase):
    """Tests for task list plugin."""

    def test_checked_task(self):
        result = markdown_renderer('- [x] Done')
        self.assertIn('checked', result)
        self.assertIn('task-list-item', result)

    def test_unchecked_task(self):
        result = markdown_renderer('- [ ] Todo')
        self.assertIn('type="checkbox"', result)
        # The 'checked' attribute should not be standalone (only in checked items)
        self.assertNotIn('checked/', result)

    def test_mixed_task_and_regular(self):
        result = markdown_renderer('- [x] Done\n- [ ] Not done\n- Regular item')
        self.assertIn('checked', result)
        self.assertIn('Regular item', result)
        self.assertEqual(result.count('class="task-list-item"'), 2)


class AbbreviationPluginTests(TestCase):
    """Tests for abbreviation plugin."""

    def test_abbreviation(self):
        result = markdown_renderer('*[HTML]: Hyper Text Markup Language\n\nThe HTML specification')
        self.assertIn('<abbr title="Hyper Text Markup Language">HTML</abbr>', result)


class AdmonitionPluginTests(TestCase):
    """Tests for RST admonition directive plugin."""

    def test_note_admonition(self):
        result = markdown_renderer('.. note::\n   This is a note')
        self.assertIn('admonition', result)
        self.assertIn('note', result)
        self.assertIn('This is a note', result)

    def test_warning_admonition(self):
        result = markdown_renderer('.. warning::\n   Be careful!')
        self.assertIn('admonition', result)
        self.assertIn('warning', result)

    def test_tip_admonition(self):
        result = markdown_renderer('.. tip::\n   A helpful tip')
        self.assertIn('admonition', result)
        self.assertIn('tip', result)

    def test_admonition_with_title(self):
        result = markdown_renderer('.. note:: Important Note\n   This is critical')
        self.assertIn('Important Note', result)


class CleanSecurityTests(TestCase):
    """Tests for the clean() security filter."""

    def test_removes_script_tags(self):
        result = clean('<p>hello</p><script>alert(1)</script><p>world</p>')
        self.assertNotIn('<script>', result)
        self.assertIn('<p>hello</p>', result)
        self.assertIn('<p>world</p>', result)

    def test_removes_script_case_insensitive(self):
        result = clean('<SCRIPT>alert(1)</SCRIPT>')
        self.assertNotIn('alert', result)

    def test_removes_script_with_attributes(self):
        result = clean('<script type="text/javascript">alert(1)</script>')
        self.assertNotIn('alert', result)

    def test_removes_multiline_script(self):
        result = clean('<script>\nvar x = 1;\n</script>')
        self.assertNotIn('var x', result)

    def test_removes_onclick_double_quotes(self):
        result = clean('<div onclick="alert(1)">text</div>')
        self.assertNotIn('onclick', result)
        self.assertIn('text', result)

    def test_removes_onclick_single_quotes(self):
        result = clean("<div onclick='alert(1)'>text</div>")
        self.assertNotIn('onclick', result)

    def test_removes_onerror(self):
        result = clean('<img onerror="alert(1)" src="x.png">')
        self.assertNotIn('onerror', result)

    def test_removes_onmouseover(self):
        result = clean('<div onmouseover="alert(1)">text</div>')
        self.assertNotIn('onmouseover', result)

    def test_removes_javascript_url_href(self):
        result = clean('<a href="javascript:alert(1)">click</a>')
        self.assertNotIn('javascript:', result)

    def test_removes_javascript_url_src(self):
        result = clean('<img src="javascript:alert(1)">')
        self.assertNotIn('javascript:', result)

    def test_removes_javascript_case_insensitive(self):
        result = clean('<a href="JAVASCRIPT:alert(1)">x</a>')
        self.assertNotIn('JAVASCRIPT:', result)

    def test_removes_object_tag(self):
        result = clean('<object data="x">text</object>')
        self.assertNotIn('<object', result)
        self.assertNotIn('</object>', result)

    def test_removes_embed_tag(self):
        result = clean('<embed src="x">')
        self.assertNotIn('<embed', result)

    def test_removes_form_tag(self):
        result = clean('<form action="x"></form>')
        self.assertNotIn('<form', result)

    def test_removes_input_tag(self):
        result = clean('<input type="text" value="hello">')
        self.assertNotIn('<input', result)

    def test_removes_button_tag(self):
        result = clean('<button>Click</button>')
        self.assertNotIn('<button', result)
        self.assertNotIn('</button>', result)

    def test_iframe_youtube_whitelisted(self):
        result = clean('<iframe src="https://www.youtube.com/embed/123"></iframe>')
        self.assertIn('<iframe', result)

    def test_iframe_vimeo_whitelisted(self):
        result = clean('<iframe src="https://player.vimeo.com/123"></iframe>')
        self.assertIn('<iframe', result)

    def test_iframe_spotify_whitelisted(self):
        result = clean('<iframe src="https://open.spotify.com/embed/track/123"></iframe>')
        self.assertIn('<iframe', result)

    def test_iframe_google_docs_whitelisted(self):
        result = clean('<iframe src="https://docs.google.com/doc/embed"></iframe>')
        self.assertIn('<iframe', result)

    def test_iframe_evil_domain_removed(self):
        result = clean('<iframe src="https://evil.com/page"></iframe>')
        self.assertNotIn('<iframe', result)

    def test_preserves_normal_html(self):
        html = '<p>hello <b>world</b></p>'
        result = clean(html)
        self.assertEqual(result, html)


class ScriptCodeProtectionTests(TestCase):
    """Tests for script/code placeholder extraction in markdown_renderer()."""

    def test_script_in_backtick_code_not_extracted(self):
        result = markdown_renderer('```html\n<script>alert(1)</script>\n```')
        self.assertNotIn('BEAR_SCRIPT', result)
        self.assertIn('alert', result)

    def test_script_in_tilde_code_not_extracted(self):
        result = markdown_renderer('~~~html\n<script>alert(1)</script>\n~~~')
        self.assertNotIn('BEAR_SCRIPT', result)
        self.assertIn('alert', result)

    def test_script_outside_code_preserved(self):
        result = markdown_renderer('```\ncode\n```\n\n<script>var x=1;</script>')
        self.assertIn('<script>var x=1;</script>', result)

    def test_many_code_blocks_no_collision(self):
        blocks = [f'```\nblock_content_{i}\n```' for i in range(12)]
        content = '\n\nsome text\n\n'.join(blocks)
        result = markdown_renderer(content)
        for i in range(12):
            self.assertIn(f'block_content_{i}', result)
        self.assertNotIn('BEAR_CODE', result)


class CombinedRenderingTests(TestCase):
    """Tests for interactions between multiple rendering features."""

    def test_bold_italic_combined(self):
        result = markdown_renderer('***bold italic***')
        self.assertIn('<strong>', result)
        self.assertIn('<em>', result)

    def test_inline_code_preserved(self):
        result = markdown_renderer('Use `print()` function')
        self.assertIn('<code>print()</code>', result)

    def test_blockquote(self):
        result = markdown_renderer('> This is a quote')
        self.assertIn('<blockquote>', result)

    def test_horizontal_rule(self):
        result = markdown_renderer('---')
        self.assertIn('<hr', result)

    def test_image(self):
        result = markdown_renderer('![alt text](https://example.com/image.png)')
        self.assertIn('src="https://example.com/image.png"', result)
        self.assertIn('alt="alt text"', result)

    def test_empty_content(self):
        result = markdown_renderer('')
        self.assertEqual(result, '')

    def test_ordered_list(self):
        result = markdown_renderer('1. First\n2. Second\n3. Third')
        self.assertIn('<ol>', result)
        self.assertIn('<li>First</li>', result)
        self.assertIn('<li>Third</li>', result)

    def test_unordered_list(self):
        result = markdown_renderer('- Alpha\n- Beta\n- Gamma')
        self.assertIn('<ul>', result)
        self.assertIn('<li>Alpha</li>', result)


class ElementReplacementTests(TestCase):
    """Regression tests for template variable injection via element_replacement()."""

    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='elrepuser', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='My Test Blog',
            subdomain='elrep',
            meta_description='A blog about testing',
        )
        self.post = Post.objects.create(
            blog=self.blog,
            uid='er1',
            title='Test Post',
            slug='test-post',
            published_date=timezone.now(),
            publish=True,
            content='Hello world',
            meta_description='A test post',
        )

    def test_blog_title_replaced(self):
        result = element_replacement('Title: {{ blog_title }}', self.blog)
        self.assertNotIn('{{ blog_title }}', result)
        self.assertIn('My Test Blog', result)

    def test_blog_description_replaced(self):
        result = element_replacement('Desc: {{ blog_description }}', self.blog)
        self.assertNotIn('{{ blog_description }}', result)
        self.assertIn('A blog about testing', result)

    def test_post_title_replaced(self):
        result = element_replacement('Post: {{ post_title }}', self.blog, post=self.post)
        self.assertNotIn('{{ post_title }}', result)
        self.assertIn('Test Post', result)

    def test_post_description_replaced(self):
        result = element_replacement('Desc: {{ post_description }}', self.blog, post=self.post)
        self.assertNotIn('{{ post_description }}', result)
        self.assertIn('A test post', result)

    def test_post_published_date_replaced(self):
        result = element_replacement('Date: {{ post_published_date }}', self.blog, post=self.post)
        self.assertNotIn('{{ post_published_date }}', result)

    def test_post_link_replaced(self):
        result = element_replacement('Link: {{ post_link }}', self.blog, post=self.post)
        self.assertNotIn('{{ post_link }}', result)
        self.assertIn('test-post', result)

    def test_blog_link_replaced(self):
        result = element_replacement('Link: {{ blog_link }}', self.blog)
        self.assertNotIn('{{ blog_link }}', result)

    def test_blog_title_html_escaped(self):
        """Blog title with HTML should be escaped to prevent XSS."""
        self.blog.title = '<script>alert(1)</script>'
        self.blog.save()
        result = element_replacement('{{ blog_title }}', self.blog)
        self.assertNotIn('<script>', result)
        self.assertIn('&lt;script&gt;', result)

    def test_blog_description_html_escaped(self):
        """Blog description with HTML should be escaped."""
        self.blog.meta_description = '<img onerror=alert(1)>'
        self.blog.save()
        result = element_replacement('{{ blog_description }}', self.blog)
        self.assertNotIn('<img', result)
        self.assertIn('&lt;img', result)

    def test_post_description_html_escaped(self):
        """Post description with HTML should be escaped."""
        self.post.meta_description = '<b>bold</b>'
        self.post.save()
        result = element_replacement('{{ post_description }}', self.blog, post=self.post)
        self.assertNotIn('<b>', result)
        self.assertIn('&lt;b&gt;', result)

    def test_post_variables_not_replaced_without_post(self):
        """Post-specific variables should remain if no post is provided."""
        result = element_replacement('{{ post_title }}', self.blog)
        self.assertIn('{{ post_title }}', result)

    def test_multiple_variables_in_same_markup(self):
        result = element_replacement(
            '{{ blog_title }} - {{ blog_description }}',
            self.blog,
        )
        self.assertIn('My Test Blog', result)
        self.assertIn('A blog about testing', result)

    def test_email_signup_stripped_for_free_users(self):
        result = element_replacement('{{ email-signup }}', self.blog)
        self.assertNotIn('{{ email-signup }}', result)

    def test_email_signup_underscore_stripped_for_free_users(self):
        result = element_replacement('{{ email_signup }}', self.blog)
        self.assertNotIn('{{ email_signup }}', result)

    def test_email_signup_rendered_for_upgraded_users(self):
        self.user.settings.upgraded = True
        self.user.settings.save()
        result = element_replacement('{{ email-signup }}', self.blog)
        self.assertNotIn('{{ email-signup }}', result)
        # Should contain the subscribe form snippet
        self.assertIn('email', result.lower())

    def test_tags_replaced(self):
        self.post.all_tags = json.dumps(['python', 'django'])
        self.post.save()
        result = element_replacement('{{ tags }}', self.blog)
        self.assertNotIn('{{ tags }}', result)

    def test_blog_created_date_replaced(self):
        result = element_replacement('{{ blog_created_date }}', self.blog)
        self.assertNotIn('{{ blog_created_date }}', result)

    def test_blog_last_modified_replaced(self):
        result = element_replacement('{{ blog_last_modified }}', self.blog)
        self.assertNotIn('{{ blog_last_modified }}', result)

    def test_blog_last_posted_replaced_when_set(self):
        """blog_last_posted should be replaced with time since last posted."""
        self.blog.last_posted = timezone.now()
        self.blog.save()
        result = element_replacement('{{ blog_last_posted }}', self.blog)
        self.assertNotIn('{{ blog_last_posted }}', result)

    def test_blog_last_posted_empty_when_none(self):
        """blog_last_posted should be empty string when blog has no last_posted."""
        empty_blog = Blog.objects.create(user=self.user, title='Empty', subdomain='empty-blog')
        result = element_replacement('X{{ blog_last_posted }}Y', empty_blog)
        self.assertNotIn('{{ blog_last_posted }}', result)
        self.assertIn('XY', result)


class NextPreviousPostTests(TestCase):
    """Regression tests for {{ next_post }} and {{ previous_post }} replacement."""

    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='navuser', password='pass')
        self.blog = Blog.objects.create(user=self.user, title='Nav Blog', subdomain='nav')
        now = timezone.now()
        self.post1 = Post.objects.create(
            blog=self.blog, uid='nav1', title='First', slug='first',
            published_date=now - timezone.timedelta(days=2), publish=True, content='c',
        )
        self.post2 = Post.objects.create(
            blog=self.blog, uid='nav2', title='Second', slug='second',
            published_date=now - timezone.timedelta(days=1), publish=True, content='c',
        )
        self.post3 = Post.objects.create(
            blog=self.blog, uid='nav3', title='Third', slug='third',
            published_date=now, publish=True, content='c',
        )

    def test_next_post_link(self):
        result = element_replacement('{{ next_post }}', self.blog, post=self.post1)
        self.assertIn('href="/second"', result)
        self.assertIn('class="next-post"', result)

    def test_previous_post_link(self):
        result = element_replacement('{{ previous_post }}', self.blog, post=self.post3)
        self.assertIn('href="/second"', result)
        self.assertIn('class="previous-post"', result)

    def test_next_post_empty_for_latest(self):
        result = element_replacement('X{{ next_post }}Y', self.blog, post=self.post3)
        self.assertNotIn('next-post', result)
        self.assertIn('XY', result)

    def test_previous_post_empty_for_oldest(self):
        result = element_replacement('X{{ previous_post }}Y', self.blog, post=self.post1)
        self.assertNotIn('previous-post', result)
        self.assertIn('XY', result)

    def test_middle_post_has_both(self):
        result = element_replacement(
            '{{ previous_post }} {{ next_post }}', self.blog, post=self.post2,
        )
        self.assertIn('previous-post', result)
        self.assertIn('next-post', result)

    def test_next_post_title_escaped(self):
        """Post titles with special chars in nav links should be escaped."""
        self.post2.title = 'Post "with" <quotes>'
        self.post2.save()
        result = element_replacement('{{ next_post }}', self.blog, post=self.post1)
        self.assertNotIn('<quotes>', result)


class PostListDirectiveTests(TestCase):
    """Regression tests for {{ posts ... }} directive parsing in element_replacement()."""

    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='plduser', password='pass')
        self.blog = Blog.objects.create(user=self.user, title='PLD Blog', subdomain='pld')
        now = timezone.now()
        self.post_a = Post.objects.create(
            blog=self.blog, uid='pld1', title='Alpha', slug='alpha',
            published_date=now - timezone.timedelta(days=3), publish=True, content='alpha content',
            all_tags=json.dumps(['tech']),
        )
        self.post_b = Post.objects.create(
            blog=self.blog, uid='pld2', title='Beta', slug='beta',
            published_date=now - timezone.timedelta(days=2), publish=True, content='beta content',
            all_tags=json.dumps(['tech', 'python']),
        )
        self.post_c = Post.objects.create(
            blog=self.blog, uid='pld3', title='Gamma', slug='gamma',
            published_date=now - timezone.timedelta(days=1), publish=True, content='gamma content',
            all_tags=json.dumps(['personal']),
        )

    def test_basic_posts_directive(self):
        """{{ posts }} should render a list of all published posts."""
        result = element_replacement('{{ posts }}', self.blog)
        self.assertNotIn('{{ posts }}', result)
        self.assertIn('Alpha', result)
        self.assertIn('Beta', result)
        self.assertIn('Gamma', result)

    def test_posts_with_tag_filter(self):
        result = element_replacement('{{ posts tag:tech }}', self.blog)
        self.assertIn('Alpha', result)
        self.assertIn('Beta', result)
        self.assertNotIn('Gamma', result)

    def test_posts_with_exclude_tag(self):
        result = element_replacement('{{ posts tag:-personal }}', self.blog)
        self.assertIn('Alpha', result)
        self.assertIn('Beta', result)
        self.assertNotIn('Gamma', result)

    def test_posts_with_limit(self):
        result = element_replacement('{{ posts limit:1 }}', self.blog)
        # Default order is desc, so Gamma (most recent) should appear
        self.assertIn('Gamma', result)
        self.assertNotIn('Alpha', result)

    def test_posts_with_order_asc(self):
        result = element_replacement('{{ posts order:asc limit:1 }}', self.blog)
        # Ascending order, oldest first
        self.assertIn('Alpha', result)
        self.assertNotIn('Gamma', result)

    def test_posts_with_multiple_params(self):
        # tag must come last since its regex is greedy and captures trailing text
        result = element_replacement('{{ posts limit:1 order:asc tag:tech }}', self.blog)
        self.assertIn('Alpha', result)
        self.assertNotIn('Beta', result)

    def test_posts_excludes_drafts(self):
        """Unpublished posts should not appear in {{ posts }}."""
        self.post_b.publish = False
        self.post_b.save()
        result = element_replacement('{{ posts }}', self.blog)
        self.assertNotIn('Beta', result)
        self.assertIn('Alpha', result)

    def test_posts_excludes_pages(self):
        """Pages (is_page=True) should not appear in {{ posts }}."""
        self.post_b.is_page = True
        self.post_b.save()
        result = element_replacement('{{ posts }}', self.blog)
        self.assertNotIn('Beta', result)
        self.assertIn('Alpha', result)

    def test_posts_directive_with_surrounding_content(self):
        """The directive should only replace the {{ posts ... }} part."""
        result = element_replacement('<p>Before</p>{{ posts }}<p>After</p>', self.blog)
        self.assertIn('<p>Before</p>', result)
        self.assertIn('<p>After</p>', result)
        self.assertIn('Alpha', result)

    def test_multiple_posts_directives(self):
        """Multiple {{ posts }} directives in the same content should all be replaced."""
        result = element_replacement('{{ posts tag:tech }}---{{ posts tag:personal }}', self.blog)
        self.assertNotIn('{{ posts', result)

    def test_posts_with_extra_whitespace(self):
        """Whitespace variations in the directive should still work."""
        result = element_replacement('{{  posts  }}', self.blog)
        self.assertNotIn('{{', result)
        self.assertIn('Alpha', result)

    def test_posts_content_only_on_pages(self):
        """content:True should only render full content when post context is a page."""
        page = Post.objects.create(
            blog=self.blog, uid='page1', title='My Page', slug='my-page',
            published_date=timezone.now(), publish=True, content='page content',
            is_page=True,
        )
        result = element_replacement('{{ posts content:True }}', self.blog, post=page)
        # Should include post content since context post is a page
        self.assertIn('alpha content', result)

    def test_posts_content_ignored_on_regular_posts(self):
        """content:True should NOT render full content when context post is not a page."""
        regular = self.post_a
        result = element_replacement('{{ posts content:True }}', self.blog, post=regular)
        # Content should NOT be rendered since context post is not a page
        self.assertNotIn('beta content', result)


class ExcludingPreTests(TestCase):
    """Regression tests for excluding_pre() -- variables inside code blocks should NOT be replaced."""

    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='expreuser', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='ExPre Blog',
            subdomain='expre',
        )
        self.post = Post.objects.create(
            blog=self.blog, uid='ep1', title='EP Post', slug='ep-post',
            published_date=timezone.now(), publish=True, content='x',
        )

    def test_variable_outside_pre_replaced(self):
        result = excluding_pre('<p>{{ blog_title }}</p>', self.blog)
        self.assertIn('ExPre Blog', result)

    def test_variable_inside_pre_not_replaced(self):
        """Template variables inside <pre> blocks should be left as-is."""
        result = excluding_pre(
            '<pre>{{ blog_title }}</pre>',
            self.blog,
        )
        self.assertIn('{{ blog_title }}', result)
        self.assertNotIn('ExPre Blog', result)

    def test_variable_inside_code_not_replaced(self):
        """Template variables inside <code> blocks should be left as-is."""
        result = excluding_pre(
            '<code>{{ blog_title }}</code>',
            self.blog,
        )
        self.assertIn('{{ blog_title }}', result)
        self.assertNotIn('ExPre Blog', result)

    def test_mixed_pre_and_regular(self):
        """Variables outside pre should be replaced, inside pre should not."""
        markup = '<p>{{ blog_title }}</p><pre>{{ blog_title }}</pre>'
        result = excluding_pre(markup, self.blog)
        self.assertIn('ExPre Blog', result)
        # The pre block should still contain the raw variable
        self.assertIn('<pre>{{ blog_title }}</pre>', result)

    def test_posts_directive_inside_code_not_replaced(self):
        """{{ posts }} inside a code block should not be replaced with a post list."""
        result = excluding_pre(
            '<code>{{ posts }}</code>',
            self.blog,
        )
        self.assertIn('{{ posts }}', result)

    def test_full_markdown_pipeline_protects_code(self):
        """End-to-end: variables in fenced code blocks survive the full pipeline."""
        content = '```\n{{ blog_title }}\n```'
        result = markdown(content, blog=self.blog, post=self.post)
        self.assertNotIn('ExPre Blog', str(result))


@mock.patch.dict(os.environ, {'MAIN_SITE_HOSTS': 'testserver'})
class RandomRedirectTests(TestCase):
    """Tests for /random-post and /random-blog redirect endpoints."""

    def setUp(self):
        Stylesheet.objects.create(title='Default', identifier='default', css='')
        self.user = User.objects.create_user(username='randlinkuser', password='pass')
        self.blog = Blog.objects.create(
            user=self.user,
            title='Discoverable Blog',
            subdomain='discblog',
            reviewed=True,
            hidden=False,
        )
        self.post = Post.objects.create(
            blog=self.blog,
            uid='rl1',
            title='Discoverable Post',
            slug='discoverable-post',
            published_date=timezone.now(),
            publish=True,
            make_discoverable=True,
            hidden=False,
            content='x' * 150,
        )

    def test_random_post_redirects(self):
        response = self.client.get('/discover/random-post/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('https://', response.url)

    def test_random_blog_redirects(self):
        response = self.client.get('/discover/random-blog/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('https://', response.url)
