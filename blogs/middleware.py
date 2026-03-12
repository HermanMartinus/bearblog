from django.db import connection
from django.http import JsonResponse
from django.middleware.csrf import (
    CsrfViewMiddleware,
    REASON_NO_CSRF_COOKIE,
    REASON_CSRF_TOKEN_MISSING,
    REASON_BAD_ORIGIN
)

import logging
import os
import time
import threading
from collections import defaultdict
from datetime import datetime, timezone

from django.core.cache import cache
from django.core.management import call_command
from ipaddr import client_ip

logger = logging.getLogger(__name__)


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
        if 'ping' in request.path:
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


# Middleware-based task scheduler
# Uses Redis to track last-run timestamps and atomic locks to prevent duplicate execution

SCHEDULED_TASKS = []


def register_task(name, interval_seconds=None, run_at=None):
    def decorator(func):
        SCHEDULED_TASKS.append({
            'name': name,
            'interval_seconds': interval_seconds,
            'run_at': run_at,
            'func': func,
        })
        return func
    return decorator


@register_task('invalidate_cache', interval_seconds=600)
def run_invalidate_cache():
    call_command('invalidate_cache')


@register_task('monitor_custom_domains', interval_seconds=60)
def run_monitor_custom_domains():
    call_command('monitor_custom_domains')


@register_task('send_emails', run_at="20:00")
def run_send_emails():
    call_command('send_emails')


def _run_task_in_thread(task):
    try:
        task['func']()
    except Exception:
        logger.exception("Scheduled task '%s' failed", task['name'])
    finally:
        cache.set(f"scheduler:last_run:{task['name']}", time.time(), timeout=86400)
        cache.delete(f"scheduler:lock:{task['name']}")


class TaskSchedulerMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.environ.get('ENVIRONMENT') != 'dev':
            self._check_tasks()
        return self.get_response(request)

    def _check_tasks(self):
        now = time.time()
        for task in SCHEDULED_TASKS:
            last_run = cache.get(f"scheduler:last_run:{task['name']}")

            if task['run_at']:
                utc_now = datetime.now(timezone.utc)
                hour, minute = map(int, task['run_at'].split(':'))
                target = utc_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if utc_now < target:
                    continue
                target_ts = target.timestamp()
                if last_run is not None and last_run >= target_ts:
                    continue
                lock_timeout = 7200
            else:
                if last_run is not None and (now - last_run) < task['interval_seconds']:
                    continue
                lock_timeout = task['interval_seconds'] * 2

            lock_key = f"scheduler:lock:{task['name']}"
            if not cache.add(lock_key, 1, timeout=lock_timeout):
                continue

            cache.set(f"scheduler:last_run:{task['name']}", now, timeout=86400)

            thread = threading.Thread(
                target=_run_task_in_thread,
                args=(task,),
                daemon=True,
            )
            thread.start()