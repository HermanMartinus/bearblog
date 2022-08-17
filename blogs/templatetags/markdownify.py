from django import template
import mistune
import html
from bs4 import BeautifulSoup as html_parser
from lxml.html.clean import Cleaner
import lxml
from slugify import slugify

register = template.Library()


@register.filter
def markdown(content):
    if not content:
        return ''

    markup = mistune.html(content)

    soup = html_parser(markup, 'html.parser')
    heading_tags = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])

    for each_tag in heading_tags:
        each_tag.attrs['id'] = slugify(each_tag.text)

    for each_anchor in soup.find_all('a', href=True):
        if 'tab:' in each_anchor.attrs['href']:
            each_anchor.attrs['href'] = each_anchor.attrs['href'].replace('tab:', '')
            each_anchor.attrs['target'] = '_blank'

    for match in soup.findAll('code'):
        if match.parent.name == 'pre':
            if match.has_attr('class'):
                match.parent.attrs['class'] = match['class'][0].replace('language-', '')
            match.replaceWithChildren()
        else:
            if len(match.contents) > 0:
                new_tag = soup.new_tag("code")
                new_tag.append(html.escape(str(match.contents[0])))
                match.replace_with(new_tag)

    safe_attrs = list(lxml.html.clean.defs.safe_attrs) + ['style', 'controls']
    lxml.html.clean.defs.safe_attrs = safe_attrs
    lxml.html.clean.Cleaner.safe_attrs = lxml.html.clean.defs.safe_attrs
    host_whitelist = [
        'www.youtube.com',
        'www.slideshare.net',
        'player.vimeo.com',
        'w.soundcloud.com',
        'www.google.com',
        'codepen.io',
        'stackblitz.com']
    cleaner = Cleaner(host_whitelist=host_whitelist, safe_attrs=safe_attrs)
    cleaned_markup = cleaner.clean_html(str(soup))

    cleaned_markup = cleaned_markup.replace('{{ email-signup }}', template.loader.render_to_string('snippets/email_subscribe_form.html'))
    # TODO: add 'sandbox' attribute to all iframes

    return cleaned_markup
