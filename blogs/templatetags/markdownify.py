from html import escape
from django import template
from django.template.loader import render_to_string

import mistune
import lxml
from bs4 import BeautifulSoup as HtmlParser
from lxml.html.clean import Cleaner, defs
from slugify import slugify

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
    'open.spotify.com'
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
def markdown(content, upgraded=False):
    if not content:
        return ''

    markup = mistune.html(content)
    soup = HtmlParser(markup, 'html.parser')

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

    tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'a', 'span', 'b', 'i', 'strong', 'em'])
    for tag in tags:
        if tag.string and '<code>' not in str(tag):
            tag.string.replace_with(typographic_replacements(tag.string))
            tag.string.replace_with(
                tag.string.replace('{{ email-signup }}', render_to_string('snippets/email_subscribe_form.html')))

    processed_markup = str(soup)

    if not upgraded:
        processed_markup = clean(processed_markup)

    return processed_markup


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
    return HtmlParser(markup, "lxml").text.strip()[:400] + '...'
