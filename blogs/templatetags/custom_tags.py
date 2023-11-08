from django import template
from django.template.loader import render_to_string
from django.utils import dateformat, translation
from django.utils.dateformat import format as date_format

from html import escape
from bs4 import BeautifulSoup
from lxml.html.clean import Cleaner, defs
from slugify import slugify

import mistune
import lxml
import latex2mathml.converter
import re

register = template.Library()

SAFE_ATTRS = list(defs.safe_attrs) + ['style', 'controls', 'allowfullscreen', 'autoplay', 'loop']

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
def markdown(content, blog=False):
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

    for code_block in soup.findAll('code'):
        if code_block.parent.name == 'pre':
            if code_block.has_attr('class'):
                code_block.parent.attrs['class'] = code_block['class'][0].replace('language-', '')
            code_block.replaceWithChildren()
        else:
            if len(code_block.contents) > 0:
                new_tag = soup.new_tag("code")
                new_tag.append(escape(str(code_block.contents[0])))
                code_block.replace_with(new_tag)

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
        processed_markup = excluding_pre(processed_markup, element_replacement, blog)

    return processed_markup


def excluding_pre(markup, func, blog=None):
    placeholders = {}

    def placeholder_div(match):
        key = f"PLACEHOLDER_{len(placeholders)}"
        placeholders[key] = match.group(0)
        return key

    markup = re.sub(r'(<pre.*?>.*?</pre>|<code.*?>.*?</code>)', placeholder_div, markup, flags=re.DOTALL)

    if blog:
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

def element_replacement(markup, blog):
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
        filtered_posts = apply_filters(blog.post_set.filter(publish=True), tag, limit, order)
        context = {'blog': blog, 'posts': filtered_posts, 'embed': True, 'show_description': description}
        return render_to_string('snippets/post_list.html', context)
    
    markup = re.sub(pattern, replace_with_filtered_posts, markup)

    markup = markup.replace('{{ email-signup }}', render_to_string('snippets/email_subscribe_form.html'))
    markup = markup.replace('{{email-signup}}', render_to_string('snippets/email_subscribe_form.html'))
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
