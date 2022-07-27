import threading
import bleach
from bs4 import BeautifulSoup
from django.contrib.sites.models import Site
from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
from django.shortcuts import get_object_or_404
from django.utils import timezone
import mistune
import requests
import hashlib
from django.http import Http404
import subprocess
from django.conf import settings
from _datetime import timedelta

from blogs.models import Blog


def root(subdomain=''):
    domain = Site.objects.get_current().domain
    if subdomain == '':
        return f"{domain}"
    else:
        return f"{subdomain}.{domain}"


def get_blog_with_domain(domain):
    if not domain:
        return False
    try:
        return Blog.objects.get(domain=domain, blocked=False)
    except Blog.DoesNotExist:
        # Handle www subdomain if necessary
        if 'www.' in domain:
            return get_object_or_404(Blog, domain=domain.replace('www.', ''), blocked=False)
        else:
            return get_object_or_404(Blog, domain=f'www.{domain}', blocked=False)


def get_posts(all_posts):
    return list(filter(lambda post: not post.is_page, all_posts))


def get_post(all_posts, slug):
    try:
        return list(filter(lambda post: post.slug == slug, all_posts))[0]
    except IndexError:
        raise Http404("No Post matches the given query.")


def sanitise_int(input, length=10):
    try:
        if len(input) < length:
            return int(bleach.clean(input))
        else:
            raise ValueError
    except ValueError:
        raise Http404("Someone's doing something dodgy ʕ •`ᴥ•´ʔ")


def sanitise_text(text):
    htmlCodes = (
        ('&', '&amp;'),
        ('<', '&lt;'),
        ('>', '&gt;'),
        ('"', '&quot;'),
        ("'", '&#39;'),)
    for c, html_code in htmlCodes:
        cleaned_text = text.replace(html_code, c)
    return cleaned_text


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
        '_dmarc',
    ]

    return subdomain in protected_subdomains


def check_records(domain):
    if not domain:
        return
    verification_string = subprocess.Popen(["dig", "-t", "txt", domain, '+short'], stdout=subprocess.PIPE).communicate()[0]
    return ('look-for-the-bear-necessities' in str(verification_string))


def check_connection(blog):
    if not blog.domain:
        return
    else:
        try:
            response = requests.request("GET", blog.useful_domain())
            return (f'<meta name="{ blog.subdomain }" content="look-for-the-bear-necessities"/>' in response.text)
        except ConnectionError:
            return False


def unmark(markdown):
    markup = mistune.html(markdown)
    return BeautifulSoup(markup, "lxml").text.strip()[:157] + '...'


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


def daterange(start_date, end_date):
    for n in range(int((end_date - start_date).days)):
        yield start_date + timedelta(n)


def send_mass_html_mail(datatuple, fail_silently=False, user=None, password=None, connection=None):
    connection = connection or get_connection(username=user, password=password, fail_silently=fail_silently)
    messages = []
    for subject, text, html, from_email, recipient in datatuple:
        message = EmailMultiAlternatives(subject, text, from_email, recipient)
        message.attach_alternative(html, 'text/html')
        messages.append(message)
    return connection.send_messages(messages)


def validate_subscriber_email(email, blog):
    token = hashlib.md5(f'{email} {blog.subdomain} {timezone.now().strftime("%B %Y")}'.encode()).hexdigest()
    confirmation_link = f'{blog.useful_domain()}/confirm-subscription/?token={token}&email={email}'

    html_message = f'''
        You've decided to subscribe to {blog.title} ({blog.useful_domain()}). That's awesome!
        <br>
        <br>
        Follow this <a href="{confirmation_link}">link</a> to confirm your subscription.
        <br>
        <br>
        Made with <a href="https://bearblog.dev">Bear ʕ•ᴥ•ʔ</a>
    '''
    text_message = f'''
        You've decided to subscribe to {blog.title} ({blog.useful_domain()}). That's awesome!

        Follow this link to confirm your subscription: {confirmation_link}

        Made with Bear ʕ•ᴥ•ʔ
    '''
    send_async_mail(
        'Confirm your email address',
        html_message,
        'Bear ʕ•ᴥ•ʔ <no_reply@bearblog.dev>',
        [email],
    )


class EmailThread(threading.Thread):
    def __init__(self, subject, html_message, from_email, recipient_list):
        self.subject = subject
        self.html_message = html_message
        self.from_email = from_email
        self.recipient_list = recipient_list
        threading.Thread.__init__(self)

    def run(self):
        send_mail(
            self.subject,
            self.html_message,
            self.from_email,
            self.recipient_list,
            fail_silently=True,
            html_message=self.html_message)


def send_async_mail(subject, html_message, from_email, recipient_list):
    if settings.DEBUG:
        print(html_message)
    else:
        print('Sent email to ', recipient_list)
        EmailThread(subject, html_message, from_email, recipient_list).start()
