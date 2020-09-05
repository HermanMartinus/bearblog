from django import template
import mistune
from bs4 import BeautifulSoup as html_parser
from lxml.html.clean import clean_html
from slugify import slugify
from pygments import highlight
from pygments.lexers import get_lexer_by_name
from pygments.formatters import HtmlFormatter

register = template.Library()


class HighlightRenderer(mistune.HTMLRenderer):
    def block_code(self, code, lang=None):
        if lang:
            lexer = get_lexer_by_name(lang, stripall=True)
            formatter = HtmlFormatter(full=True, linenos=True, style='colorful')
            return highlight(code, lexer, formatter)

        # lexer = get_lexer_by_name('python', stripall=True)
        # formatter = HtmlFormatter(full=True, linenos=True, style='colorful')
        # return highlight(code, lexer, formatter)
        return '<pre><code>' + mistune.escape(code) + '</code></pre>'


@register.filter
def markdown(value):
    markdown = mistune.create_markdown(renderer=HighlightRenderer())
    markup = markdown(value)

    soup = html_parser(markup, 'html.parser')
    heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
    for each_tag in heading_tags:
        each_tag.attrs['id'] = slugify(each_tag.text)

    cleaned_markup = clean_html(str(soup))

    return cleaned_markup

