from django import template
import mistune
from lxml.html.clean import clean_html
import re

register = template.Library()


@register.filter
def markdown(value):
    markup = mistune.html(value)
    cleaned_markup = clean_html(markup)

    # linkify hashtags
    for tag in re.findall(r"(#[\d\w\.]+)", cleaned_markup):
        text_tag = tag.replace('#', '')
        cleaned_markup = cleaned_markup.replace(
            tag,
            f"<a href='/blog/?q=%23{text_tag}'>{tag}</a>")

    return cleaned_markup
