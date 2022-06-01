import bleach
from django.contrib.sites.models import Site
from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
from django.shortcuts import get_object_or_404
from django.utils import timezone
import requests
import hashlib
from django.http import Http404
import json
import subprocess
from django.conf import settings
from markdown import Markdown
from io import StringIO
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


def sanitise_int(input, length):
    try:
        print(len(input))
        if len(input) < length:
            return int(bleach.clean(input))
        else:
            raise ValueError
    except ValueError:
        raise Http404("Someone's doing something dodgy ʕ •`ᴥ•´ʔ")


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


def add_new_domain(domain):
    url = "https://api.heroku.com/apps/bear-blog/domains"

    payload = {
        "hostname": domain,
        "sni_endpoint": "saurolophus-08033"
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


def check_records(domain):
    if not domain:
        return
    verification_string = subprocess.Popen(["dig", "-t", "txt", domain, '+short'], stdout=subprocess.PIPE).communicate()[0]
    return ('look-for-the-bear-necessities' in str(verification_string))


def check_dns_connection(domain):
    if not domain:
        return
    try:
        response = requests.request("GET", f'http://{domain}/')
        print(response.text)
        return ('look-for-the-bear-necessities' in response.text or 'Heroku' in response.text)
    except requests.exceptions.ConnectionError:
        return False


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


def bulk_email(queryset, subject, body):
    recipient_list = queryset.filter(subscribed=True).values_list('user__email', flat=True)
    messages = [(
        subject,
        f'{body}\n\n\nUnsubscribe: https://bearblog.dev/bulk_mail_unsubscribe/{recipient}',
        f'''{body}
        <br>
        <p style="text-align: center">
            <small>
                <a href="https://bearblog.dev/">
                    ʕ•ᴥ•ʔ Bear
                </a> |
                <a href="https://bearblog.dev/bulk_mail_unsubscribe/{recipient}">
                    Unsubscribe
                </a>
            </small>
        </p>''',
        'hi@bearblog.dev',
        [recipient]
    ) for recipient in recipient_list]
    send_mass_html_mail(messages)


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
    send_mail(
        'Confirm your email address',
        text_message,
        'subscriptions@bearblog.dev',
        [email],
        fail_silently=False,
        html_message=html_message,
    )
