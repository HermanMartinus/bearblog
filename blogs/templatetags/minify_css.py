from django import template
from django.template.loader import get_template
from django.template import Engine, Template
import re
import markdown

register = template.Library()


@register.simple_tag(takes_context=True)
def include_css(context, template_name):
    return minify(get_template(template_name).render(context.flatten()))


@register.filter
def minify(css):
    css = re.sub(r'url\((["\'])([^)]*)\1\)', r'url(\2)', css)
    css = re.sub(r'\s+', ' ', css)
    css = re.sub(r'#([0-9a-f])\1([0-9a-f])\2([0-9a-f])\3(\s|;)', r'#\1\2\3\4', css)

    css = re.sub(r':\s*0(\.\d+([cm]m|e[mx]|in|p[ctx]))\s*;', r':\1;', css)
    return css
