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
    'supercut.video'
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
    ('+-', '±')
]


def typographic_replacements(text):
    for old, new in TYPOGRAPHIC_REPLACEMENTS:
        text = text.replace(old, new)
    return text

def replace_inline_latex(text):
    latex_exp_inline = re.compile(r'\$\$([^\n]*?)\$\$')
    replaced_text = latex_exp_inline.sub(r'$\1$', text)

    return replaced_text

def fix_links(text):
    parentheses_pattern = r'\[([^\]]+)\]\(((?:tab:)?https?://[^\)]+\([^\)]+\)[^\)]*)\)'

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
    
    
markdown_renderer = create_markdown(
    renderer=MyRenderer(),
    plugins=['math', 'strikethrough', 'footnotes', 'table', 'superscript', 'subscript', 'mark', 'task_lists', 'abbr'],
    escape=False)


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
        # TODO: Implement excluding_script to not parse script tags
        # processed_markup = excluding_script(content)
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


# Exclude script and style tags from markdown rendering
def excluding_script(markup):
    placeholders = {}

    def placeholder_div(match):
        key = f"PLACEHOLDER_{len(placeholders)}"
        print(placeholders)
        placeholders[key] = match.group(0)
        return key

    markup = re.sub(r'(<script.*?>.*?</script>|<style.*?>.*?</style>)', placeholder_div, markup, flags=re.DOTALL)

    markup = markdown_renderer(markup)

    for key in sorted(placeholders.keys(), reverse=True):
        markup = markup.replace(key, placeholders[key])

    return markup


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


def apply_filters(posts, tag=None, limit=None, order=None):
    if order == 'asc':
        posts = posts.order_by('published_date')
    else:
        posts = posts.order_by('-published_date')
    if tag:
        # Split tags by comma and strip whitespace
        tags = [t.strip() for t in tag.replace('"', '').split(',')]
        if tags:
            posts = [post for post in posts if all(tag in post.tags for tag in tags)]
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
        tag, limit, order, description, content = None, None, None, False, False
        
        # Extract and process parameters one by one
        param_pattern = r'(tag:([^|}\s][^|}]*)|limit:(\d+)|order:(asc|desc)|description:(True)|content:(True))'
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
            # Only show content if injection is on page or homepage
            elif 'content:' in param[0] and not post or post.is_page:
                content = param[5] == 'True'

        filtered_posts = apply_filters(blog.posts.filter(publish=True, is_page=False, published_date__lte=timezone.now()), tag, limit, order)
        context = {'blog': blog, 'posts': filtered_posts, 'embed': True, 'show_description': description, 'show_content': content, 'tz': tz}
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
        markup = markup.replace('{{email-signup}}', render_to_string('snippets/email_subscribe_form.html'))
    else:
        markup = markup.replace('{{ email-signup }}', '')
        markup = markup.replace('{{email-signup}}', '')

    markup = markup.replace('{{ blog_title }}', escape(blog.title))
    markup = markup.replace('{{ blog_description }}', escape(blog.meta_description))
    markup = markup.replace('{{ blog_created_date }}', format_date(blog.created_date, blog.date_format, blog.lang, tz))
    markup = markup.replace('{{ blog_last_modified }}', timesince(blog.last_modified))
    if blog.last_posted:
        markup = markup.replace('{{ blog_last_posted }}', timesince(blog.last_posted))
    else:
        markup = markup.replace('{{ blog_last_posted }}', '')
        
    markup = markup.replace('{{ blog_link }}', f"{blog.useful_domain}")

    if post:
        markup = markup.replace('{{ post_title }}', escape(post.title))
        markup = markup.replace('{{ post_description }}', escape(post.meta_description))
        markup = markup.replace('{{ post_published_date }}', format_date(post.published_date, blog.date_format, blog.lang, tz))
        last_modified = post.last_modified or timezone.now()
        markup = markup.replace('{{ post_last_modified }}', timesince(last_modified))
        markup = markup.replace('{{ post_link }}', f"{blog.useful_domain}/{post.slug}")

    translation.activate(current_lang)

    return markup


@register.filter
def clean(markup):
    cleaned_markup = re.sub(r'<script.*?>.*?</script>', '', markup, flags=re.DOTALL | re.IGNORECASE)
    
    cleaned_markup = re.sub(r'\son\w+="[^"]*"', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'\son\w+=\'[^\']*\'', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'\son\w+=\w+', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'(<\w+\s+.*?)(href|src)\s*=\s*["\']?javascript:[^"\']*["\']?', r'\1', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'<(object|embed|form|input|button).*?>', '', cleaned_markup, flags=re.IGNORECASE)
    cleaned_markup = re.sub(r'</(object|embed|form|input|button)>', '', cleaned_markup, flags=re.IGNORECASE)
    
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
