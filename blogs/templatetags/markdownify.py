from django import template
import mistune
from bs4 import BeautifulSoup as html_parser
from lxml.html.clean import clean_html
from slugify import slugify

register = template.Library()


@register.filter
def markdown(value):
    markup = mistune.html(value)

    soup = html_parser(markup, 'html.parser')
    heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

    for each_tag in heading_tags:
        each_tag.attrs['id'] = f"section-{heading_tags.index(each_tag)}"
        each_tag.attrs['id'] = slugify(each_tag.text)

    invalid_tags = ['code']

    for tag in invalid_tags:
        for match in soup.findAll(tag):
            if match.parent.name == 'pre':
                match.parent.wrap(soup.new_tag("p"))
                match.replaceWithChildren()

    cleaned_markup = clean_html(str(soup))

    return cleaned_markup
