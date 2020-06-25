from django import template
import mistune
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
    cleaned_markup = clean_html(markup)

    return cleaned_markup
