from django.db import connection
from django.http import JsonResponse

import os
import time
from collections import defaultdict

from ipaddr import client_ip

from blogs.helpers import caddy_proxy_ips, trusted_client_ip


# TEMPORARY: confirms how IPs actually arrive before we swap client_ip out for
# trusted_client_ip. Remove once confirmed.
class IPDiagnosticMiddleware:
    SAMPLE_RATE = 200  # log 1 in N agreeing requests; divergences always log

    def __init__(self, get_response):
        self.get_response = get_response
        self.counter = 0

    def __call__(self, request):
        # Every local request is route=no-cf, which would otherwise always log
        if os.getenv('ENVIRONMENT') != 'dev':
            self.counter += 1
            try:
                self.log(request)
            except Exception as e:
                # Diagnostics must never take the site down
                print(f"IPDIAG error: {e}")
        return self.get_response(request)

    def log(self, request):
        meta = request.META
        cf = meta.get('HTTP_CF_CONNECTING_IP', '').strip()
        xff = meta.get('HTTP_X_FORWARDED_FOR', '').strip()
        real = meta.get('HTTP_X_REAL_IP', '').strip()
        remote = meta.get('REMOTE_ADDR', '').strip()

        if not cf:
            route = 'no-cf'  # bypassed Cloudflare entirely
        elif cf in caddy_proxy_ips():
            route = 'droplet'
        else:
            route = 'direct'

        old = client_ip(request)
        new = trusted_client_ip(request)
        agree = old == new

        # Agreeing requests are the expected case, so only sample them
        if agree and route != 'no-cf' and self.counter % self.SAMPLE_RATE:
            return

        print(
            f"IPDIAG route={route} agree={agree} old={old!r} new={new!r} "
            f"cf={cf!r} xff={xff!r} real={real!r} remote={remote!r} "
            f"host={meta.get('HTTP_HOST', '')!r} fwd_host={meta.get('HTTP_X_FORWARDED_HOST', '')!r} "
            f"get_host={request.get_host()!r} cf_country={meta.get('HTTP_CF_IPCOUNTRY', '')!r} "
            f"path={request.path!r}"
        )


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


