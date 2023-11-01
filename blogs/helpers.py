from django.utils import timezone
from django.contrib.sites.models import Site
from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
from django.contrib.gis.geoip2 import GeoIP2
from django.http import Http404
from django.conf import settings

import random
import threading
import bleach
from bs4 import BeautifulSoup
from requests.exceptions import ConnectionError, ReadTimeout
import mistune
import requests
import subprocess
from datetime import timedelta
import geoip2
from ipaddr import client_ip
import hashlib


def root(subdomain=''):
    domain = Site.objects.get_current().domain
    if subdomain == '':
        return f"{domain}"
    else:
        return f"{subdomain}.{domain}"


def get_posts(all_posts):
    return list(filter(lambda post: not post.is_page, all_posts))


def sanitise_int(input, length=10):
    try:
        if len(input) < length:
            return int(bleach.clean(input))
        else:
            raise ValueError
    except ValueError:
        raise Http404("Someone's doing something dodgy ʕ •`ᴥ•´ʔ")


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
            response = requests.request("GET", blog.useful_domain(), allow_redirects=False, timeout=10)
            return (f'<meta name="{ blog.subdomain }" content="look-for-the-bear-necessities">' in response.text)
        except ConnectionError:
            return False
        except ReadTimeout:
            return False
        except SystemExit:
            return False


def salt_and_hash(request, duration='day'):
    if duration == 'year':
        hash_id = hashlib.md5(f"{client_ip(request)}-{timezone.now().year}".encode('utf-8')).hexdigest()
    else:
        hash_id = hashlib.md5(f"{client_ip(request)}-{timezone.now().date()}".encode('utf-8')).hexdigest()
    return hash_id


def get_country(user_ip):
    # user_ip = '45.222.31.178'
    try:
        g = GeoIP2()
        country = g.country(user_ip)

        return country
    except geoip2.errors.AddressNotFoundError:
        return {}


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


def random_error_message():
    errors = [
        'Whoops. Looks like our servers are bearly functioning. Try again later.',
        'Ensure content contains necessary parameters.',
        'Something went wrong. Please try restarting your computer.',
        'Your password needs a special character, a number, and a capital letter.',
        'Ensure content is the correct length.',
        'Bear with us as we fix our software.'
    ]

    return random.choice(errors)
