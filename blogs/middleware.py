from django.db import connection
from django.http import JsonResponse

import os
import time
from collections import defaultdict

from ipaddr import client_ip


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

        client_ip_address = client_ip(request)
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


