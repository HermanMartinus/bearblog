from django.contrib.sites.models import Site
import requests
from django.http import Http404
import json
from django.conf import settings
from markdown import Markdown
from io import StringIO
from ipaddr import client_ip


def root(subdomain=''):
    domain = Site.objects.get_current().domain
    if subdomain == '':
        return f"{domain}"
    else:
        return f"{subdomain}.{domain}"


def get_nav(all_posts):
    return list(filter(lambda post: post.is_page, all_posts))


def get_posts(all_posts):
    return list(filter(lambda post: not post.is_page, all_posts))


def get_post(all_posts, slug):
    try:
        return list(filter(lambda post: post.slug == slug, all_posts))[0]
    except IndexError:
        raise Http404("No Post matches the given query.")


def is_protected(subdomain):
    protected_subdomains = [
        'login',
        'www',
        'api',
        'signup',
        'signin',
        'profile',
        'register',
        'post',
        'http',
        'https',
        'account',
        'router',
        'settings',
        'bearblog.dev',
        '*.bearblog.dev',
        'router.bearblog.dev',
        'www.bearblog.dev',
    ]

    return subdomain in protected_subdomains


def add_new_domain(domain):
    url = "https://api.heroku.com/apps/bear-blog/domains"

    payload = {
        "hostname": domain
    }

    headers = {
        'content-type': "application/json",
        'accept': "application/vnd.heroku+json; version=3",
        'authorization': f'Bearer {settings.HEROKU_BEARER_TOKEN}',
    }

    response = requests.request(
        "POST", url, data=json.dumps(payload), headers=headers)

    print(response.text)

    return id


def delete_domain(domain):
    url = f"https://api.heroku.com/apps/bear-blog/domains/{domain}"

    payload = {
        "hostname": domain
    }

    headers = {
        'content-type': "application/json",
        'accept': "application/vnd.heroku+json; version=3",
        'authorization': f'Bearer {settings.HEROKU_BEARER_TOKEN}',
    }

    response = requests.request(
        "DELETE", url, data=json.dumps(payload), headers=headers)

    print(response.text)


def unmark_element(element, stream=None):
    if stream is None:
        stream = StringIO()
    if element.text:
        stream.write(element.text)
    for sub in element:
        unmark_element(sub, stream)
    if element.tail:
        stream.write(element.tail)
    return stream.getvalue()


# patching Markdown
Markdown.output_formats["plain"] = unmark_element
__md = Markdown(output_format="plain")
__md.stripTopLevelTags = False


def unmark(text):
    return __md.convert(text)


def log_view(request, blog, post=None):
    ip_address = client_ip(request)

    if post:
        print(post.title)

    http_referer = request.META.get('HTTP_REFERER')
    referer = None
    if http_referer:
        if request.META.get('HTTP_HOST') not in http_referer:
            referer = http_referer

    return {'blog': blog, 'post': post, 'ip_address': ip_address, 'referer': referer}
    
