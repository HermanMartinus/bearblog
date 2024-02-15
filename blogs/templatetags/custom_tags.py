from django import template
from django.utils import timezone
from django.template.loader import render_to_string
from django.utils import dateformat, translation
from django.utils.dateformat import format as date_format
from django.utils.timesince import timesince

from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

from html import escape
from bs4 import BeautifulSoup
from lxml.html.clean import Cleaner, defs
from slugify import slugify

import mistune
import lxml
import latex2mathml.converter
import re

from blogs.models import Post

register = template.Library()

SAFE_ATTRS = list(defs.safe_attrs) + ['style', 'controls', 'allowfullscreen', 'autoplay', 'loop', 'open']

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
    'umap.openstreetmap.fr'
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


@register.filter
def markdown(content, blog_or_post=False):
    post = None
    blog= None
    if blog_or_post:
        if isinstance(blog_or_post, Post):
            post = blog_or_post
            blog = post.blog
        else:
            blog = blog_or_post
        
    if not content:
        return ''

    markup = mistune.html(content)

    soup = BeautifulSoup(markup, 'html.parser')

    heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    for tag in heading_tags:
        tag.attrs['id'] = slugify(tag.text)

    for anchor in soup.find_all('a', href=True):
        if 'tab:' in anchor.attrs['href']:
            anchor.attrs['href'] = anchor.attrs['href'].replace('tab:', '')
            anchor.attrs['target'] = '_blank'

    for code_block in soup.find_all('code'):
        if code_block.parent and code_block.parent.name == 'pre':
            # Add pygments
            language = code_block.get('class', [''])[0].split('-')[-1]
            try:
                lexer = get_lexer_by_name(language)
            except ValueError:
                lexer = get_lexer_by_name('text')

            formatter = HtmlFormatter(style='friendly')
            highlighted_code = highlight(code_block.get_text(), lexer, formatter)

            new_code = BeautifulSoup(highlighted_code, 'html.parser')
            code_block.parent.replace_with(new_code)

    processed_markup = str(soup)

    # If not upgraded remove iframes and js
    if not blog or not blog.upgraded:
        processed_markup = clean(processed_markup)

    # Replace LaTeX between $$ with MathML
    processed_markup = excluding_pre(processed_markup, render_latex)

    # Add typographic replacements
    processed_markup = excluding_pre(processed_markup, typographic_replacements)

    # Replace {{ xyz }} elements
    if blog:
        processed_markup = excluding_pre(processed_markup, element_replacement, blog, post)

    return processed_markup


def excluding_pre(markup, func, blog=None, post=None):
    placeholders = {}

    def placeholder_div(match):
        key = f"PLACEHOLDER_{len(placeholders)}"
        placeholders[key] = match.group(0)
        return key

    markup = re.sub(r'(<pre.*?>.*?</pre>|<code.*?>.*?</code>)', placeholder_div, markup, flags=re.DOTALL)

    if blog:
        if post: 
            markup = func(markup, blog, post)
        else:
            markup = func(markup, blog)
    else:
        markup = func(markup)

    for key in sorted(placeholders.keys(), reverse=True):
        markup = markup.replace(key, placeholders[key])

    return markup


def render_latex(markup):
    latex_exp_block = re.compile(r'\$\$\n([\s\S]*?)\n\$\$')
    latex_exp_inline = re.compile(r'\$\$([^\n]*?)\$\$')

    def replace_with_mathml(match):
        latex_content = match.group(1)
        mathml_output = latex2mathml.converter.convert(latex_content)
        return mathml_output

    def replace_with_mathml_block(match):
        latex_content = match.group(1)
        mathml_output = latex2mathml.converter.convert(latex_content).replace('display="inline"', 'display="block"')
        return mathml_output

    try:
        markup = latex_exp_block.sub(replace_with_mathml_block, markup)
        markup = latex_exp_inline.sub(replace_with_mathml, markup)
    except Exception as e:
        print("LaTeX rendering error")

    return markup


def apply_filters(posts, tag=None, limit=None, order=None):
    if tag:
        tag = tag.replace('"', '').strip()
        posts = posts.filter(all_tags__contains=tag)
    if order == 'asc':
        posts = posts.order_by('published_date')
    else:
        posts = posts.order_by('-published_date')
    if limit is not None:
        try:
            limit = int(limit)
            posts = posts[:limit]
        except ValueError:
            pass
    return posts

def element_replacement(markup, blog, post=None):
    pattern = r'\{\{\s*posts' \
          r'(?:\s*\|\s*tag:\s*(?P<tag>[^\|]+))?' \
          r'(?:\s*\|\s*limit:\s*(?P<limit>\d+))?' \
          r'(?:\s*\|\s*order:\s*(?P<order>asc|desc))?' \
          r'(?:\s*\|\s*description:\s*(?P<description>True))?' \
          r'\s*\}\}'


    def replace_with_filtered_posts(match):
        tag = match.group('tag')
        limit = match.group('limit')
        order = match.group('order')
        description = match.group('description') == 'True'
        filtered_posts = apply_filters(blog.post_set.filter(publish=True, is_page=False), tag, limit, order)
        context = {'blog': blog, 'posts': filtered_posts, 'embed': True, 'show_description': description}
        return render_to_string('snippets/post_list.html', context)
    
    markup = re.sub(pattern, replace_with_filtered_posts, markup)

    current_lang = "en" # translation.get_language()
    translation.activate(blog.lang)
    if post:
        translation.activate(post.lang)

    markup = markup.replace('{{ email-signup }}', render_to_string('snippets/email_subscribe_form.html'))
    markup = markup.replace('{{email-signup}}', render_to_string('snippets/email_subscribe_form.html'))

    markup = markup.replace('{{ blog_title }}', escape(blog.title))
    markup = markup.replace('{{ blog_description }}', escape(blog.meta_description))
    markup = markup.replace('{{ blog_created_date }}', format_date(blog.created_date, blog.date_format, blog.lang))
    markup = markup.replace('{{ blog_last_modified }}', timesince(blog.last_modified))
    if blog.last_posted:
        markup = markup.replace('{{ blog_last_posted }}', timesince(blog.last_posted))
    markup = markup.replace('{{ blog_link }}', f"{blog.useful_domain}")

    if post:
        markup = markup.replace('{{ post_title }}', escape(post.title))
        markup = markup.replace('{{ post_description }}', escape(post.meta_description))
        markup = markup.replace('{{ post_published_date }}', format_date(post.published_date, blog.date_format, blog.lang))
        last_modified = post.last_modified or timezone.now()
        markup = markup.replace('{{ post_last_modified }}', timesince(last_modified))
        markup = markup.replace('{{ post_link }}', f"{blog.useful_domain}/{post.slug}")

    translation.activate(current_lang)

    return markup


@register.filter
def clean(markup):
    defs.safe_attrs = SAFE_ATTRS
    Cleaner.safe_attrs = defs.safe_attrs
    cleaner = Cleaner(host_whitelist=HOST_WHITELIST, safe_attrs=SAFE_ATTRS)
    try:
        cleaned_markup = cleaner.clean_html(markup)
    except lxml.etree.ParserError:
        cleaned_markup = ""

    return cleaned_markup


@register.filter
def unmark(content):
    markup = mistune.html(content)
    return BeautifulSoup(markup, "lxml").text.strip()[:400] + '...'


@register.simple_tag
def format_date(date, format_string, lang=None):
    if date is None:
        return ''
    if not format_string:
        format_string = 'd M, Y'

    if lang:
        current_lang = translation.get_language()
        translation.activate(lang)
        formatted_date = date_format(date, format_string)
        translation.activate(current_lang)
        return formatted_date
    return dateformat.format(date, format_string)
