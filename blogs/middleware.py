from django.conf import settings
from django.core import signing
from django.http import HttpResponse, JsonResponse

import json
import os
import time
from collections import defaultdict

from blogs.helpers import trusted_client_ip


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


class ProtectedRouteMiddleware:
    PROTECTED_PATHS = {'/blog', '/blog/', '/posts', '/posts/', '/archive', '/archive/', '/writing', '/writing/'}
    COOKIE_NAME = 'protected_route'
    COOKIE_MAX_AGE = 60 * 60 * 24
    COOKIE_SALT = 'blogs.protected_route.cookie'

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path not in self.PROTECTED_PATHS or not request.META.get('QUERY_STRING'):
            return self.get_response(request)

        if self._has_valid_cookie(request):
            return self.get_response(request)

        if request.method in ('GET', 'HEAD'):
            return self._challenge_response(request)

        return self._uncacheable(JsonResponse({'error': 'Browser challenge required'}, status=403))

    def _challenge_response(self, request):
        cookie_value = signing.dumps(
            {'host': request.get_host().lower()},
            salt=self.COOKIE_SALT,
        )
        cookie = (
            f'{self.COOKIE_NAME}={cookie_value}; '
            f'Max-Age={self.COOKIE_MAX_AGE}; Path=/; SameSite=Lax'
        )
        if not settings.DEBUG:
            cookie += '; Secure'

        content = f'''<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Checking your browser</title>
</head>
<body>
    <p id="challenge-status">Checking your browser…</p>
    <script>
        document.cookie = {json.dumps(cookie)};
        window.location.reload();
    </script>
</body>
</html>'''
        return self._uncacheable(HttpResponse(content, status=403, content_type='text/html'))

    def _has_valid_cookie(self, request):
        cookie_value = request.COOKIES.get(self.COOKIE_NAME)
        if not cookie_value:
            return False

        try:
            cookie_data = signing.loads(
                cookie_value,
                salt=self.COOKIE_SALT,
                max_age=self.COOKIE_MAX_AGE,
            )
        except signing.BadSignature:
            return False

        return cookie_data == {'host': request.get_host().lower()}

    @staticmethod
    def _uncacheable(response):
        response['Cache-Control'] = 'private, no-store, max-age=0'
        response['Cloudflare-CDN-Cache-Control'] = 'no-store'
        response['X-Robots-Tag'] = 'noindex, nofollow'
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
