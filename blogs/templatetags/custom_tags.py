from django import template
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils import dateformat, translation
from django.utils.dateformat import format as date_format
from django.utils.timesince import timesince
from django.utils.text import slugify
from django.utils.safestring import mark_safe

from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

from html import escape

from mistune import HTMLRenderer, create_markdown
from mistune.directives import FencedDirective, RSTDirective
from mistune.directives import Admonition, TableOfContents
from zoneinfo import ZoneInfo

import latex2mathml.converter
import re

from blogs.helpers import unmark
from blogs.models import Post


register = template.Library()

HOST_WHITELIST = [
    'www.youtube.com',
    'www.youtube-nocookie.com',
    'www.slideshare.net',
    'player.vimeo.com',
    'w.soundcloud.com',
    'www.google.com',
    'codepen.io',
    'stackblitz.com',
    'onedrive.live.com',
    'docs.google.com',
    'bandcamp.com',
    'embed.music.apple.com',
    'drive.google.com',
    'share.transistor.fm',
    'share.descript.com',
    'mrkennedy.ca',
    'open.spotify.com',
    'umap.openstreetmap.fr',
    'music.163.com',
    'sheevcharan.substack.com',
    'guestbooks.meadow.cafe',
    'supercut.video',
    'listenbrainz.org',
    'api.listenbrainz.org',
    'archive.org',
    'panel.radiocast.net',
    'embed.ente.io',
    'app.hearthis.at',
    'datawrapper.de',
    'datawrapper.dwcdn.net'
]

TYPOGRAPHIC_REPLACEMENTS = [
    ('(c)', '©'),
    ('(C)', '©'),
    ('(r)', '®'),
    ('(R)', '®'),
    ('(tm)', '™'),
    ('(TM)', '™'),
    ('(p)', '℗'),
    ('(P)', '℗'),
    ('+-', '±'),
    ('\\n', '<br>')
]


def typographic_replacements(text):
    for old, new in TYPOGRAPHIC_REPLACEMENTS:
        text = text.replace(old, new)
    return text

def replace_inline_latex(text):
    latex_exp_inline = re.compile(r'\$\$([^\n]*?)\$\$')
    replaced_text = latex_exp_inline.sub(r'$\1$', text)

    # Escape currency $ pairs like "$30...$50"
    replaced_text = re.sub(r'\$(\d[^$\n]*?)\$(?=\d)', r'\\$\1\\$', replaced_text)

    return replaced_text

def fix_links(text):
    parentheses_pattern = r'\[([^\]]+)\]\(((?:tab:)?https?://[^\)]+\([^\)]*\)[^\)]*)\)'

    def escape_parentheses(match):
        label = match.group(1)
        url = match.group(2)
        # Escape parentheses in the URL
        escaped_url = url.replace('(', '%28').replace(')', '%29')
        return f'[{label}]({escaped_url})'

    fixed_text = re.sub(parentheses_pattern, escape_parentheses, text)
    

    return fixed_text

class MyRenderer(HTMLRenderer):
    def heading(self, text, level, **attrs):
        return f'<h{level} id={slugify(text)}>{text}</h{level}>'
    
    def link(self, text, url, title=None):
        if title:
            title = title.replace("'", "&apos;").replace('"', "&quot;")
        if 'tab:' in url:
            url = url.replace('tab:', '')
            if title:
                return f"<a href='{url}' target='_blank' title='{title}'>{text}</a>"
            return f"<a href='{url}' target='_blank'>{text}</a>"
        
        if title:
            return f"<a href='{url}' title='{title}'>{text}</a>"
        return f"<a href='{url}'>{text}</a>"


    def text(self, text):
        # Replace trailing backslashes with <br>
        if re.match(r'^\s*\\\s*$', text):
            text = '<br>'
        return typographic_replacements(text)
    
    def inline_html(self, html):
        return html
    
    def block_html(self, html):
        return html
    
    def inline_math(self, text):
        # Skip rendering if there's a space before the closing dollar sign
        if text.endswith(' '):
            return f'${text}$'
        try:
            return latex2mathml.converter.convert(text)
        except Exception as e:
            print("LaTeX rendering error")

    
    def block_math(self, text):
        try:
            
            return latex2mathml.converter.convert(text).replace('display="inline"', 'display="block"')
        except Exception as e:
            print("LaTeX rendering error")
    
    def block_code(self, code, info=None):
        if info is None:
            info = 'text'
        try:
            lexer = get_lexer_by_name(info)
        except ValueError:
            lexer = get_lexer_by_name('text')
        
        formatter = HtmlFormatter(style='friendly')
        highlighted_code = highlight(code, lexer, formatter)
        return highlighted_code


_mistune_renderer = create_markdown(
    renderer=MyRenderer(),
    plugins=['math', 'strikethrough', 'footnotes', 'table', 'superscript', 'subscript', 'mark', 'task_lists', 'abbr', RSTDirective([
        Admonition(),
        TableOfContents(),
    ]),],
    escape=False)
# Remove 8-spaces for code block functionality
_mistune_renderer.block.rules.remove('indent_code')
_mistune_renderer.block.compile_sc()


def markdown_renderer(content):
    """Render markdown with script blocks protected from text processing."""
    # Protect fenced code blocks from script extraction
    code_placeholders = {}

    def replace_code(match):
        key = f"BEAR_CODE_{len(code_placeholders)}"
        code_placeholders[key] = match.group(0)
        return key

    content = re.sub(r'(```[^\n]*\n.*?```|~~~[^\n]*\n.*?~~~)', replace_code, content, flags=re.DOTALL)

    # Extract script blocks (now only those outside code fences)
    script_placeholders = {}

    def replace_script(match):
        key = f"<!--BEAR_SCRIPT_{len(script_placeholders)}-->"
        script_placeholders[key] = match.group(0)
        return key

    content = re.sub(r'<script\b[^>]*>.*?</script>', replace_script, content, flags=re.DOTALL | re.IGNORECASE)

    # Restore code blocks before rendering
    for key, code in code_placeholders.items():
        content = content.replace(key, code)

    result = _mistune_renderer(content)

    for key, script in script_placeholders.items():
        result = result.replace(key, script)

    return result


@register.simple_tag(takes_context=False)
def markdown(content, blog=None, post=None, tz=None):
    content = str(content)
    if not content:
        return ''

    # Removes old formatted inline LaTeX
    content = replace_inline_latex(content)
    # Find urls with parentheses and escape them
    content = fix_links(content)

    try:
        processed_markup = markdown_renderer(content)
    except TypeError:
        return ''

    # If not upgraded remove iframes and js
    if not blog or not blog.user.settings.upgraded:
        processed_markup = clean(processed_markup)

    # Replace {{ xyz }} elements
    if blog:
        processed_markup = excluding_pre(processed_markup, blog, post, tz=tz)

    return mark_safe(processed_markup)


# Replace elements in all but pre and code tags
def excluding_pre(markup, blog=None, post=None, tz=None):
    placeholders = {}

    def placeholder_div(match):
        key = f"PLACEHOLDER_{len(placeholders)}"
        placeholders[key] = match.group(0)
        return key

    markup = re.sub(r'(<pre.*?>.*?</pre>|<code.*?>.*?</code>)', placeholder_div, markup, flags=re.DOTALL)

    if blog:
        if post: 
            markup = element_replacement(markup, blog, post, tz=tz)
        else:
            markup = element_replacement(markup, blog, tz=tz)
    else:
        markup = element_replacement(markup, tz=tz)

    for key in sorted(placeholders.keys(), reverse=True):
        markup = markup.replace(key, placeholders[key])

    return markup


def apply_filters(posts, tag=None, limit=None, order=None, from_date=None, to_date=None):
    if order == 'asc':
        posts = posts.order_by('published_date')
    else:
        posts = posts.order_by('-published_date')
    if from_date:
        try:
            start = timezone.datetime.strptime(from_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo('UTC'))
            posts = posts.filter(published_date__gte=start)
        except ValueError:
            pass
    if to_date:
        try:
            end = timezone.datetime.strptime(to_date, '%Y-%m-%d').replace(tzinfo=ZoneInfo('UTC'))
            end += timezone.timedelta(days=1)
            posts = posts.filter(published_date__lt=end)
        except ValueError:
            pass
    if tag:
        # Split tags by comma and strip whitespace
        tags = [t.strip() for t in tag.replace('"', '').split(',')]
        include_tags = [t for t in tags if t and not t.startswith('-')]
        exclude_tags = [t[1:] for t in tags if t.startswith('-') and len(t) > 1]
        if include_tags or exclude_tags:
            posts = [post for post in posts if
                all(t in post.tags for t in include_tags) and
                not any(t in post.tags for t in exclude_tags)]
    if limit is not None:
        try:
            limit = int(limit)
            posts = posts[:limit]
        except ValueError:
            pass
    return posts


def element_replacement(markup, blog, post=None, tz=None):
    # Match the entire {{ posts ... }} directive, including parameters
    pattern = r'\{\{\s*posts([^}]*)\}\}'
    
    def replace_with_filtered_posts(match):
        params_str = match.group(1) 
        tag, limit, order, description, image, content = None, None, None, False, False, False
        from_date = None
        to_date = None

        # Extract and process parameters one by one
        param_pattern = r'(tag:([^|}\s][^|}]*)|limit:(\d+)|order:(asc|desc)|description:(True)|image:(True)|content:(True)|from:(\d{4}-\d{2}-\d{2})|to:(\d{4}-\d{2}-\d{2}))'
        params = re.findall(param_pattern, params_str)
        for param in params:
            if 'tag:' in param[0]:
                tag = param[1].strip()
            elif 'limit:' in param[0]:
                limit = int(param[2])
            elif 'order:' in param[0]:
                order = param[3]
            elif 'description:' in param[0]:
                description = param[4] == 'True'
            elif 'image:' in param[0]:
                image  = param[5] == 'True'
            # Only show content if injection is on page or homepage
            elif 'content:' in param[0] and (not post or post.is_page):
                content = param[6] == 'True'
            elif 'from:' in param[0]:
                from_date = param[7]
            elif 'to:' in param[0]:
                to_date = param[8]

        filtered_posts = apply_filters(blog.posts.filter(publish=True, is_page=False, published_date__lte=timezone.now()), tag, limit, order, from_date, to_date)
        context = {'blog': blog, 'posts': filtered_posts, 'embed': True, 'show_description': description, 'show_image': image, 'show_content': content, 'tz': tz}
        return render_to_string('snippets/post_list.html', context)

    # Replace each matched directive with rendered content
    markup = re.sub(pattern, replace_with_filtered_posts, markup)

    # Date translation replacement
    current_lang = "en" # translation.get_language()
    translation.activate(blog.lang)
    if post:
        translation.activate(post.lang)

    if blog.user.settings.upgraded:
        markup = markup.replace('{{ email-signup }}', render_to_string('snippets/email_subscribe_form.html'))
        markup = markup.replace('{{ email_signup }}', render_to_string('snippets/email_subscribe_form.html'))
    else:
        markup = markup.replace('{{ email-signup }}', '')
        markup = markup.replace('{{ email_signup }}', '')

    markup = markup.replace('{{ blog_title }}', escape(blog.title))
    markup = markup.replace('{{ blog_description }}', escape(blog.meta_description))
    markup = markup.replace('{{ blog_created_date }}',  render_to_string('snippets/formatted_date.html', {"date": blog.created_date}))
    markup = markup.replace('{{ blog_last_modified }}', timesince(blog.last_modified))
    if blog.last_posted:
        markup = markup.replace('{{ blog_last_posted }}', timesince(blog.last_posted))
    else:
        markup = markup.replace('{{ blog_last_posted }}', '')

    markup = markup.replace('{{ tags }}', render_to_string('snippets/blog_tags.html', {"tags": blog.tags, "blog_path": blog.blog_path or "blog"}))
        
    markup = markup.replace('{{ blog_link }}', f"{blog.useful_domain}")

    if post:
        markup = markup.replace('{{ post_title }}', safe_title(post.title))
        markup = markup.replace('{{ post_description }}', escape(post.meta_description))
        markup = markup.replace('{{ post_published_date }}', render_to_string('snippets/formatted_date.html', {"date": post.published_date}))
        last_modified = post.last_modified or timezone.now()
        markup = markup.replace('{{ post_last_modified }}', timesince(last_modified))
        markup = markup.replace('{{ post_link }}', f"{blog.useful_domain}/{post.slug}")

        if "{{ next_post }}" in markup or "{{ previous_post }}" in markup:
            # Only find adjacent posts if necessary
            adjacent_posts = get_adjacent_posts(post, blog)
            next_link = ""
            previous_link = ""
            if adjacent_posts['next_slug']:
                next_link = f'<a class="next-post" href="/{adjacent_posts['next_slug']}" title="{escape(adjacent_posts['next_title'])}">Next</a>'
            if adjacent_posts['previous_slug']:
                previous_link = f'<a class="previous-post" href="/{adjacent_posts['previous_slug']}" title="{escape(adjacent_posts['previous_title'])}">Previous</a>'
            markup = markup.replace('{{ next_post }}', next_link)
            markup = markup.replace('{{ previous_post }}', previous_link)

    translation.activate(current_lang)

    return markup


def get_adjacent_posts(post, blog):
    base_qs = Post.objects.filter(
        blog=blog,
        is_page=False,
        publish=True,
        published_date__lte=timezone.now()
    ).values('slug', 'title', 'published_date', 'id')

    next_post = base_qs.filter(
        published_date__gt=post.published_date
    ).order_by('published_date', 'id').first()

    previous_post = base_qs.filter(
        published_date__lt=post.published_date
    ).order_by('-published_date', '-id').first()

    return {
        'next_slug': next_post['slug'] if next_post else None,
        'next_title': next_post['title'] if next_post else None,
        'previous_slug': previous_post['slug'] if previous_post else None,
        'previous_title': previous_post['title'] if previous_post else None,
    }


@register.filter
def safe_title(title):
    """Convert **bold** to <b>, *italic* to <i>, and &nbsp; to non-breaking spaces in titles."""
    escaped = escape(title)
    escaped = re.sub(r'\*\*(.+?)\*\*', r'<b>\1</b>', escaped)
    escaped = re.sub(r'\*(.+?)\*', r'<i>\1</i>', escaped)
    escaped = escaped.replace('&amp;nbsp;', '\u00a0')
    return mark_safe(escaped)


@register.filter
def plain_title(title):
    """Strip * markers and &nbsp; for plain-text contexts."""
    title = re.sub(r'\*+(.+?)\*+', r'\1', title)
    title = title.replace('&nbsp;', ' ')
    return title


@register.filter
def clean(markup):
    cleaned_markup = re.sub(r'<script.*?>.*?</script>', '', markup, flags=re.DOTALL | re.IGNORECASE)
    
    cleaned_markup = re.sub(r'\son\w+="[^"]*"', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'\son\w+=\'[^\']*\'', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'\son\w+=\w+', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'(<\w+\s+.*?)(href|src)\s*=\s*["\']?javascript:[^"\']*["\']?', r'\1', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'<(object|embed|form|input|button).*?>', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'</(object|embed|form|input|button)>', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'<\w+\s*[^>]*\bon\w+\s*=\s*(".*?"|\'.*?\'|[^\s>]*)\s*[^>]*>', '', cleaned_markup, flags=re.IGNORECASE | re.DOTALL)
    
    def iframe_whitelisted(match):
        src = match.group(2)
        if any(host in src for host in HOST_WHITELIST):
            return match.group(0)
        return ''

    cleaned_markup = re.sub(r'(<iframe.*?src=["\'])([^"\']*)(["\'].*?>.*?</iframe>)', iframe_whitelisted, cleaned_markup, flags=re.DOTALL | re.IGNORECASE)

    return cleaned_markup


@register.filter
def remove_markup(content):
    return unmark(content)[:400] + '...'


# This is only used in the post editor
@register.simple_tag
def format_date(date, format_string, lang=None, tz='UTC'):
    if date is None:
        return ''
    if not format_string:
        format_string = 'd M, Y'
    if not tz:
        tz = 'UTC'

    try:
        user_tz = ZoneInfo(tz)
        date = date.astimezone(user_tz)
    except Exception as e:
        print(e)
        pass

    if lang:
        current_lang = translation.get_language()
        translation.activate(lang)
        formatted_date = date_format(date, format_string)
        translation.activate(current_lang)
        return formatted_date
    
    return dateformat.format(date, format_string)


@register.filter
def remove_tag(list_obj, item):
    return [x for x in list_obj if x != item]
