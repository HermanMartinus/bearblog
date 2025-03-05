from django.db import connection
from django.urls import resolve, Resolver404
from django.http import JsonResponse
from django.middleware.csrf import (
    CsrfViewMiddleware,
    REASON_NO_CSRF_COOKIE,
    REASON_CSRF_TOKEN_MISSING,
    REASON_BAD_ORIGIN
)

import time
import threading
from collections import defaultdict
from contextlib import contextmanager
from ipaddr import client_ip
import sentry_sdk
import redis
import json
import os


# Replace the in-memory metrics with Redis connection handling
redis_client = None
if os.environ.get('REDISCLOUD_URL'):
    redis_client = redis.from_url(os.environ.get('REDISCLOUD_URL'))

# Fallback to in-memory when Redis is not available
request_metrics = defaultdict(list)
    

# Thread-local storage for query times
_local = threading.local()

@contextmanager
def track_db_time():
    _local.db_time = 0.0
    def execute_wrapper(execute, sql, params, many, context):
        start = time.time()
        try:
            return execute(sql, params, many, context)
        finally:
            _local.db_time += time.time() - start
    
    with connection.execute_wrapper(execute_wrapper):
        yield
        

class RequestPerformanceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.skip_methods = {'HEAD', 'OPTIONS'}
        self.max_metrics = 50

    def get_pattern_name(self, request):
        if request.method in self.skip_methods:
            return None
            
        try:
            resolver_match = getattr(request, 'resolver_match', None) or resolve(request.path)
            # Normalize all feed endpoints to a single path
            if resolver_match.func.__name__ == 'feed':
                return f"{request.method} feed/"
            return f"{request.method} {resolver_match.route}"
        except Resolver404:
            return None
        
    def __call__(self, request):
        endpoint = self.get_pattern_name(request)
        if endpoint is None:
            return self.get_response(request)

        start_time = time.time()
        
        with track_db_time():
            response = self.get_response(request)
            db_time = getattr(_local, 'db_time', 0.0)

        total_time = time.time() - start_time
        
        metric_data = {
            'total_time': total_time,
            'db_time': db_time,
            'compute_time': total_time - db_time,
            'timestamp': start_time
        }

        if redis_client:
            # Use Redis for storage
            try:
                redis_key = f"request_metrics:{endpoint}"
                # Get existing metrics
                metrics = redis_client.get(redis_key)
                if metrics:
                    metrics = json.loads(metrics)
                else:
                    metrics = []
                
                # Add new metric
                metrics.append(metric_data)
                # Keep only last 50 metrics
                metrics = metrics[-self.max_metrics:]
                
                # Store back in Redis without TTL
                redis_client.set(
                    redis_key,
                    json.dumps(metrics)
                )
            except redis.RedisError:
                # Fallback to in-memory if Redis fails
                metrics = request_metrics[endpoint]
                metrics.append(metric_data)
                if len(metrics) > self.max_metrics:
                    del metrics[:-self.max_metrics]
        else:
            # Use in-memory storage
            metrics = request_metrics[endpoint]
            metrics.append(metric_data)
            if len(metrics) > self.max_metrics:
                del metrics[:-self.max_metrics]

        return response


class LongRequestMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold = 15  # seconds

    def __call__(self, request):
        start_time = time.time()
        response = self.get_response(request)
        duration = time.time() - start_time
        
        if duration > self.threshold:
            # Capture the long-running request in Sentry
            with sentry_sdk.push_scope() as scope:
                scope.set_extra("request_duration", duration)
                scope.set_extra("path", request.path)
                scope.set_extra("method", request.method)
                sentry_sdk.capture_message(
                    f"Long running request detected: {duration:.2f}s",
                    level="warning"
                )
        
        return response
    

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
    RATE_LIMIT = 60  # max requests
    TIME_WINDOW = 60  # seconds

    def __init__(self, get_response):
        self.get_response = get_response
        self.ip_request_counts = defaultdict(list)

    def __call__(self, request):
        # Skip rate limiting for ping and feed endpoints
        if  'ping' in request.path or 'feed' in request.path:
            return self.get_response(request)

        client_ip_address = client_ip(request)
        current_time = time.time()

        # Clean up old requests
        self.ip_request_counts[client_ip_address] = [
            timestamp for timestamp in self.ip_request_counts[client_ip_address]
            if current_time - timestamp < self.TIME_WINDOW
        ]
        
        # Record the current request
        self.ip_request_counts[client_ip_address].append(current_time)

        # Check if the IP has exceeded the rate limit
        if len(self.ip_request_counts[client_ip_address]) > self.RATE_LIMIT: 
            full_path = request.build_absolute_uri()
            print(f"Rate limit: Exceeded for {client_ip_address} at {full_path}")
            print(f"Rate limit: User agent {request.META.get('HTTP_USER_AGENT')}")
            return JsonResponse(
                {'error': 'Rate limit exceeded'},
                status=429
            )

        return self.get_response(request)
