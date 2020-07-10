from django import template
import mistune
from bs4 import BeautifulSoup as html_parser
from lxml.html.clean import clean_html
import re


register = template.Library()


@register.filter
def markdown(value):
    markdown = value

    # linkify hashtags
    for tag in re.findall(r"(#[\d\w\.]+)", markdown):
        text_tag = tag.replace('#', '')
        markdown = markdown.replace(
            tag,
            f"[{tag}](/blog/?q=%23{text_tag})")

    markup = mistune.html(markdown)

    soup = html_parser(markup, 'html.parser')
    html_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

    for each_tag in html_tags:
        each_tag.attrs['id'] = f"section-{html_tags.index(each_tag)}"

    cleaned_markup = clean_html(str(soup))
    return cleaned_markup
