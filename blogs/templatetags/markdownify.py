from django import template
import mistune
from bs4 import BeautifulSoup as html_parser
from lxml.html.clean import clean_html
import re


register = template.Library()


@register.filter
def markdown(value):
    markdown = linkify_hashtags(value)

    markup = mistune.html(markdown)

    soup = html_parser(markup, 'html.parser')
    heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

    for each_tag in heading_tags:
        each_tag.attrs['id'] = f"section-{heading_tags.index(each_tag)}"

    cleaned_markup = clean_html(str(soup))

    return cleaned_markup


def linkify_hashtags(markdown):
    for tag in re.findall(r"(#[\d\w\.]+)", markdown):
        if not re.search(r"\((#[\d\w\.]+)\)", tag):
            text_tag = tag.replace('#', '')
            markdown = markdown.replace(
                tag,
                f"[{tag}](/blog/?q=%23{text_tag})")
    return markdown
