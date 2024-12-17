from django.utils import timezone
from django.core.mail import send_mail, get_connection, EmailMultiAlternatives
from django.contrib.gis.geoip2 import GeoIP2
from django.conf import settings
from django.db import connection

from functools import wraps
import re
import string
import os
import random
import threading
from requests.exceptions import ConnectionError, ReadTimeout
import requests
import subprocess
from datetime import timedelta
from time import time
import geoip2
from ipaddr import client_ip
import hashlib

from blogs.models import Post


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
    ]

    return subdomain in protected_subdomains


def measure_queries(func):
    def wrapper(*args, **kwargs):
        # Start timing and get initial query count
        start_time = time()
        initial_queries = len(connection.queries)
        
        # Execute the function
        result = func(*args, **kwargs)
        
        # Calculate metrics
        end_time = time()
        final_queries = len(connection.queries)
        
        # Print metrics
        execution_time = end_time - start_time
        query_count = final_queries - initial_queries
        
        print(f"\n{'='*50}")
        print(f"Performance Metrics for {func.__name__}:")
        print(f"Time: {execution_time:.3f} seconds")
        print(f"Queries: {query_count}")
        
        # if query_count > 0:
        #     print("\nQueries executed:")
        #     for query in connection.queries[initial_queries:final_queries]:
        #         print(f"- {query['sql'][:200]}...")
        # print(f"{'='*50}\n")
        
        return result
    return wrapper


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
            response = requests.request("GET", blog.useful_domain, allow_redirects=False, timeout=10)
            return (f'<meta name="{ blog.subdomain }" content="look-for-the-bear-necessities">' in response.text)
        except ConnectionError:
            return False
        except ReadTimeout:
            return False
        except SystemExit:
            return False


def pseudo_word(length=5):
    vowels = "aeiou"
    consonants = "".join(set(string.ascii_lowercase) - set(vowels))
    
    word = ""
    for i in range(length):
        if i % 2 == 0:
            word += random.choice(consonants)
        else:
            word += random.choice(vowels)
    
    return word


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
    content = re.sub(r'^\s{0,3}#{1,6}\s+.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s{0,3}[-*]{3,}\s*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s{0,3}>\s+.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'```.*?```', '', content, flags=re.DOTALL)
    content = re.sub(r'`[^`]+`', '', content)
    content = re.sub(r'!\[.*?\]\(.*?\)', '', content)
    content = re.sub(r'\[.*?\]\(.*?\)', '', content)
    content = re.sub(r'(\*\*|__)(.*?)\1', '', content)
    content = re.sub(r'(\*|_)(.*?)\1', '', content)
    content = re.sub(r'~~.*?~~', '', content)
    content = re.sub(r'^\s{0,3}[-*+]\s+.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s{0,3}\d+\.\s+.*$', '', content, flags=re.MULTILINE)
    content = re.sub(r'^\s*\|.*?\|\s*$', '', content, flags=re.MULTILINE)
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


def random_post_link():
    count = Post.objects.filter(
            blog__reviewed=True,
            publish=True,
            published_date__lte=timezone.now(),
            make_discoverable=True,
            content__isnull=False
        ).count()
    random_index = random.randint(0, count - 1)
    post = Post.objects.filter(
        blog__reviewed=True,
        publish=True,
        published_date__lte=timezone.now(),
        make_discoverable=True,
        content__isnull=False
    )[random_index]

    return f"{post.blog.useful_domain}/{post.slug}"
