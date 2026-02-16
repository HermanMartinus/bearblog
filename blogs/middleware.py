from django.db import connection
from django.http import JsonResponse
from django.middleware.csrf import (
    CsrfViewMiddleware,
    REASON_NO_CSRF_COOKIE,
    REASON_CSRF_TOKEN_MISSING,
    REASON_BAD_ORIGIN
)

import time
from collections import defaultdict
from ipaddr import client_ip
import os


# This is a workaround to handle custom domains from Django 5.0 there's an explicit CSRF_TRUSTED_ORIGINS list
class AllowAnyDomainCsrfMiddleware(CsrfViewMiddleware):
    def process_view(self, request, callback, callback_args, callback_kwargs):
        if getattr(callback, 'csrf_exempt', False):
            return None

        if request.method not in ('GET', 'HEAD', 'OPTIONS', 'TRACE'):
            # Only check token for unsafe methods
            try:
                return self._check_token(request)
            except Exception as e:
                # Determine the appropriate reason based on the error message
                if 'CSRF cookie not set' in str(e):
                    reason = REASON_NO_CSRF_COOKIE
                elif 'CSRF token missing' in str(e):
                    reason = REASON_CSRF_TOKEN_MISSING
                else:
                    reason = REASON_BAD_ORIGIN
                
                return self._reject(request, reason)


class BotWallMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if 'ping' in request.path or 'feed' in request.path:
            return self.get_response(request)
         
        # Removing because this is getting cached :/
        # if request.GET.get('q'):
        #     if request.COOKIES.get("timezone"):
        #         return self.get_response(request)

        #     return render(request, "botwall.html", status=200)

        return self.get_response(request)

   
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
        # Skip rate limiting for ping and feed endpoints
        if 'ping' in request.path or 'feed' in request.path:
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


# Prevent clickjacking on root domiains
class ConditionalXFrameOptionsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        host = request.get_host().lower()
        main_domains = {'bearblog.dev', 'www.bearblog.dev', 'lh.co'}
        
        if host in main_domains:
            response['X-Frame-Options'] = 'DENY'
        
        return response