import threading
import bleach
from bs4 import BeautifulSoup
from django.contrib.sites.models import Site
from requests.exceptions import ConnectionError
from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
import mistune
import requests
from django.http import Http404
import subprocess
from django.conf import settings
from _datetime import timedelta
import geoip2
from django.contrib.gis.geoip2 import GeoIP2
import openai


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
            response = requests.request("GET", blog.useful_domain(), allow_redirects=False, timeout=10)
            return (f'<meta name="{ blog.subdomain }" content="look-for-the-bear-necessities"/>' in response.text)
        except ConnectionError:
            return False
        except SystemExit:
            return False


def get_user_location(user_ip):
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


def query_gpt(instruction):
    openai.api_key = settings.OPENAI_KEY
    system_prompt = {"role": "system", "content": "You are a CSS bot"}
    user_data = []
    user_data.append({"role": "user", "content": instruction})

    response = openai.ChatCompletion.create(model="gpt-4",
                                            messages=[system_prompt] +
                                            user_data,
                                            temperature=0.6)

    # Extract the chatbot's response
    chatbot_response = response.choices[0].message['content'].strip()

    return chatbot_response
