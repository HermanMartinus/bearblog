from django import template
import mistune
from lxml.html.clean import clean_html

register = template.Library()


@register.filter
def markdown(value):
    markup = mistune.html(value)
    cleaned_markup = clean_html(markup)
    return cleaned_markup
