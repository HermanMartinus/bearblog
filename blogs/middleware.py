from django.http import JsonResponse

import os
import time
from collections import defaultdict

from blogs.helpers import get_country, salt_and_hash, trusted_client_ip


# Reject traffic reaching the dyno without going through Cloudflare.
class BlockHerokuAppMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.META.get('HTTP_HOST', '').split(':')[0].lower()

        if host.endswith('.herokuapp.com'):
            print(
                f"HEROKUDIRECT host={host!r} "
                f"path={request.path!r} fwd_host={request.META.get('HTTP_X_FORWARDED_HOST', '')!r} "
                f"ua={request.META.get('HTTP_USER_AGENT', '')!r}"
            )
            return JsonResponse({"error": "Bad Request"}, status=400)

        return self.get_response(request)


# Block auth and admin paths on non-main domains
class MainSitePathProtectionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().lower()
        main_domains = set(os.getenv('MAIN_SITE_HOSTS', '').split(','))

        if host not in main_domains and request.path.startswith(('/accounts/', '/mothership/')):
            return JsonResponse({"error": "Bad Request"}, status=400)

        return self.get_response(request)


# Prevent clickjacking on root domains
class ConditionalXFrameOptionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        host = request.get_host().lower()
        main_domains = set(os.getenv('MAIN_SITE_HOSTS', '').split(','))

        if host in main_domains:
            response['X-Frame-Options'] = 'DENY'

        return response


class RateLimitMiddleware:
    RATE_LIMIT = 10  # max requests per thread
    if os.getenv('ENVIRONMENT') == 'dev':
        RATE_LIMIT = 100
    TIME_WINDOW = 10  # seconds
    BAN_DURATION = 60  # seconds

    def __init__(self, get_response):
        self.get_response = get_response
        self.ip_request_counts = defaultdict(list)
        self.banned_ips = {}

    def __call__(self, request):
        # Reject requests with NUL characters
        if '\x00' in request.get_full_path():
            return JsonResponse({"error": "Bad Request"}, status=400)

        # Skip rate limiting for ping (Caddy)
        if request.path in ('/ping', '/ping/'):
            return self.get_response(request)

        client_ip_address = trusted_client_ip(request)
        current_time = time.time()

        full_path = request.get_full_path()

        # Prevent long paths
        if len(full_path) > 400:
            return JsonResponse({"error": "URI Too Long"}, status=414)

        # Ban WP scrapers
        if '.php' in full_path or '.env' in full_path:
            self.banned_ips[client_ip_address] = current_time + self.BAN_DURATION

        # Honeypot
        if 'pot-of-honey' in full_path:
            print("Banned: Caught in the honeypot")
            self.banned_ips[client_ip_address] = current_time + self.BAN_DURATION


        # Ban SQL injection attacks
        if 'sysdate(' in  full_path or 'sleep(' in full_path or 'waitfor%20delay' in full_path:
            self.banned_ips[client_ip_address] = current_time + self.BAN_DURATION


        # Check ban
        if client_ip_address in self.banned_ips and current_time < self.banned_ips[client_ip_address]:
            print(f"Banned: {client_ip_address} at {full_path}")
            return JsonResponse({'error': 'Rate limit exceeded'}, status=429)

        # Clean up old requests
        self.ip_request_counts[client_ip_address] = [
            timestamp for timestamp in self.ip_request_counts[client_ip_address]
            if current_time - timestamp < self.TIME_WINDOW
        ]

        # Record current request
        self.ip_request_counts[client_ip_address].append(current_time)

        # Check rate limit
        if len(self.ip_request_counts[client_ip_address]) > self.RATE_LIMIT:
            self.banned_ips[client_ip_address] = current_time + self.BAN_DURATION
            print(f"Rate limit: Exceeded for {client_ip_address} at {full_path}")
            print(f"Rate limit: User agent {request.META.get('HTTP_USER_AGENT')}")
            return JsonResponse({'error': 'Rate limit exceeded'}, status=429)

        return self.get_response(request)


# Temporary: log hits on the upvote endpoint while tracking down bot upvoting
class UpvoteLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.rstrip('/') != '/upvote':
            return self.get_response(request)

        started = time.time()
        response = self.get_response(request)

        try:
            print(self.log_line(request, response, time.time() - started))
        except Exception as error:
            print(f"UPVOTELOG error={error!r}")

        return response

    def log_line(self, request, response, duration):
        ip = trusted_client_ip(request)
        uid = request.POST.get('uid', '')
        token = request.POST.get('token', '')

        fields = {
            'ip': ip,
            'country': get_country(ip).get('country_code', ''),
            'hash': salt_and_hash(request, 'year')[:12],
            'method': request.method,
            'status': response.status_code,
            'ms': int(duration * 1000),
            'uid': uid,
            'token': 'missing' if not token else 'placeholder' if token == uid else 'signed',
            'honeypot': bool(request.POST.get('title', '')),
            'ua': request.META.get('HTTP_USER_AGENT', ''),
            'referer': request.META.get('HTTP_REFERER', ''),
            'origin': request.META.get('HTTP_ORIGIN', ''),
            'lang': request.META.get('HTTP_ACCEPT_LANGUAGE', ''),
            'accept': request.META.get('HTTP_ACCEPT', ''),
            'encoding': request.META.get('HTTP_ACCEPT_ENCODING', ''),
            'content_type': request.META.get('CONTENT_TYPE', ''),
            'sec_fetch_site': request.META.get('HTTP_SEC_FETCH_SITE', ''),
            'sec_fetch_mode': request.META.get('HTTP_SEC_FETCH_MODE', ''),
            'sec_fetch_dest': request.META.get('HTTP_SEC_FETCH_DEST', ''),
            'sec_ch_ua': request.META.get('HTTP_SEC_CH_UA', ''),
            'sec_ch_ua_mobile': request.META.get('HTTP_SEC_CH_UA_MOBILE', ''),
            'sec_ch_ua_platform': request.META.get('HTTP_SEC_CH_UA_PLATFORM', ''),
            'cf_ray': request.META.get('HTTP_CF_RAY', ''),
            'cf_country': request.META.get('HTTP_CF_IPCOUNTRY', ''),
        }

        return 'UPVOTELOG ' + ' '.join(f"{key}={value!r}" for key, value in fields.items())
