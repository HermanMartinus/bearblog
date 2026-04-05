from django.utils import timezone
from django.core.mail import EmailMultiAlternatives
from django.contrib.gis.geoip2 import GeoIP2
from django.db.models import Max, Min
import re
import os
import random
import threading
from requests.exceptions import ConnectionError, ReadTimeout
import requests
from time import time
import geoip2
from ipaddr import client_ip
import hashlib

from blogs.models import Blog, Post


def is_protected(subdomain):
    protected_subdomains = [
        'login',
        'mg',
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
        'support',
        'eng',
        'admin',
        'dashboard',
        'mail',
        'static',
        'blog',
        'dev',
        'beta',
        'staging',
        'secure',
        'user',
        'portal',
        'help',
        'contact',
        'news',
        'media',
        'docs',
        'auth',
        'status',
        'assets',
        'bearblog.dev',
        '*.bearblog.dev',
        'router.bearblog.dev',
        'www.bearblog.dev',
        '_dmarc',
        'domain-proxy',
        'themes'
    ]

    return subdomain in protected_subdomains


def check_connection(blog):
    if not blog.domain:
        return
    else:
        try:
            user_agent = os.environ.get("ADMIN_USER_AGENT", "")
            response = requests.request("GET", blog.useful_domain, headers={"User-Agent": user_agent}, allow_redirects=False, timeout=3)
            return (f'<meta name="{ blog.subdomain }" content="look-for-the-bear-necessities">' in response.text)
        except ConnectionError:
            return False
        except ReadTimeout:
            return False
        except SystemExit:
            return False


def salt_and_hash(request, duration='day'):
    ip_date_salt_string = f"{client_ip(request)}-{timezone.now().date()}-{os.getenv('SALT')}"
    
    if duration == 'year':
        ip_date_salt_string = f"{client_ip(request)}-{timezone.now().year}-{os.getenv('SALT')}"

    hash_id = hashlib.sha256(ip_date_salt_string.encode('utf-8')).hexdigest()

    return hash_id


def get_country(user_ip):
    # user_ip = '45.222.31.178'
    try:
        g = GeoIP2()
        country = g.country(user_ip)

        return country
    except geoip2.errors.AddressNotFoundError:
        return {}


def unmark(content):
    content = re.sub(r'^\s{0,3}#{1,6}\s+(.*)$', r'\1', content, flags=re.MULTILINE)
    content = re.sub(r'^\s{0,3}[-*]{3,}\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s{0,3}>\s+(.*)$', r'\1', content, flags=re.MULTILINE)
    content = re.sub(r'```(.*?)```', r'\1', content, flags=re.DOTALL)
    content = re.sub(r'`([^`]+)`', r'\1', content)
    content = re.sub(r'!\[(.*?)\]\(.*?\)', r'\1', content)
    content = re.sub(r'\[(.*?)\]\(.*?\)', r'\1', content)
    content = re.sub(r'(\*\*|__)(.*?)\1', r'\2', content)
    content = re.sub(r'(\*|_)(.*?[^\\])\1', r'\2', content)
    content = re.sub(r'~~(.*?)~~', r'\1', content)
    content = re.sub(r'^\s{0,3}[-*+]\s+(.*)$', r'\1', content, flags=re.MULTILINE)
    content = re.sub(r'^\s{0,3}\d+\.\s+(.*)$', r'\1', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*\|(.*?)\|\s*$', '\1', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*[:-]{3,}\s*$', '', content, flags=re.MULTILINE)

    return content


def clean_text(text):
    return ''.join(c for c in text if valid_xml_char_ordinal(c))


def valid_xml_char_ordinal(c):
    codepoint = ord(c)
    # conditions ordered by presumed frequency
    return (
        0x20 <= codepoint <= 0xD7FF or
        codepoint in (0x9, 0xA, 0xD) or
        0xE000 <= codepoint <= 0xFFFD or
        0x10000 <= codepoint <= 0x10FFFF
    )


class EmailThread(threading.Thread):
    def __init__(self, subject, html_message, from_email, recipient_list, reply_to=None):
        self.subject = subject
        self.html_message = html_message
        self.from_email = from_email
        self.recipient_list = recipient_list
        self.reply_to = reply_to
        threading.Thread.__init__(self)
    
    def run(self):
        email = EmailMultiAlternatives(
            subject=self.subject,
            body=self.html_message,
            from_email=self.from_email,
            to=self.recipient_list,
            reply_to=self.reply_to if self.reply_to else None,
        )
        email.attach_alternative(self.html_message, "text/html")
        email.send(fail_silently=True)


# Important! All members of the recipient list will see the other recipients in the 'To' field
def send_async_mail(subject, html_message, from_email, recipient_list, reply_to=None):
    if os.getenv('ENVIRONMENT') == 'dev':
        print(f'[DEV] Would send email to {recipient_list}: {subject}')
        return
    print('Sent email to ', recipient_list)
    EmailThread(subject, html_message, from_email, recipient_list, reply_to).start()


_random_post_cache = {'url': '', 'expires': 0}
_random_blog_cache = {'url': '', 'expires': 0}


def _random_by_id(queryset, model):
    agg = model.objects.aggregate(max_id=Max('id'), min_id=Min('id'))
    if not agg['max_id']:
        return None
    for _ in range(10):
        rand_id = random.randint(agg['min_id'], agg['max_id'])
        obj = queryset.filter(id__gte=rand_id).first()
        if obj:
            return obj
    return queryset.first()


def random_post_link():
    if time() < _random_post_cache['expires'] and _random_post_cache['url']:
        return _random_post_cache['url']
    post = _random_by_id(
        Post.objects.filter(
            blog__reviewed=True,
            blog__hidden=False,
            publish=True,
            published_date__lte=timezone.now(),
            make_discoverable=True,
            hidden=False,
            content__isnull=False,
        ).select_related('blog'),
        Post,
    )
    if not post:
        return ''
    url = f"{post.blog.useful_domain}/{post.slug}"
    _random_post_cache['url'] = url
    _random_post_cache['expires'] = time() + 60
    return url


def random_blog_link():
    if time() < _random_blog_cache['expires'] and _random_blog_cache['url']:
        return _random_blog_cache['url']
    blog = _random_by_id(
        Blog.objects.filter(
            reviewed=True,
            hidden=False,
            user__is_active=True,
        ),
        Blog,
    )
    if not blog:
        return ''
    url = blog.useful_domain
    _random_blog_cache['url'] = url
    _random_blog_cache['expires'] = time() + 60
    return url
