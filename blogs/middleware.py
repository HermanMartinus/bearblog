from django.db import connection
from django.urls import resolve, Resolver404
import time
from collections import defaultdict
from statistics import mean
from threading import Lock
import threading
from contextlib import contextmanager
import json
import redis
import os
from typing import Dict, List, Optional

# Thread-safe storage for metrics (used in local dev)
request_metrics = defaultdict(list)
metrics_lock = Lock()

# Thread-local storage for query times
_local = threading.local()

# Setup Redis if URL exists (production)
redis_client = None
if redis_url := os.getenv('REDISCLOUD_URL'):

    redis_client = redis.from_url(redis_url)

class MetricsStorage:
    """Handles storing metrics in either Redis or memory"""
    def __init__(self):
        self.redis_key = 'django_metrics'

    def get_metrics(self, endpoint: str) -> List[dict]:
        if redis_client:
            metrics_json = redis_client.hget(self.redis_key, endpoint)
            return json.loads(metrics_json) if metrics_json else []
        else:
            with metrics_lock:
                return request_metrics[endpoint]

    def save_metrics(self, endpoint: str, metrics: List[dict]):
        if redis_client:
            redis_client.hset(self.redis_key, endpoint, json.dumps(metrics))
        else:
            with metrics_lock:
                request_metrics[endpoint] = metrics

    def get_all_metrics(self) -> Dict[str, List[dict]]:
        if redis_client:
            all_metrics = {}
            for endpoint in redis_client.hkeys(self.redis_key):
                endpoint = endpoint.decode('utf-8')
                metrics = json.loads(redis_client.hget(self.redis_key, endpoint))
                if metrics:
                    all_metrics[endpoint] = metrics
            return all_metrics
        else:
            with metrics_lock:
                return dict(request_metrics)

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
        self.metrics_storage = MetricsStorage()

    def get_pattern_name(self, request) -> Optional[str]:
        # Skip HEAD and OPTIONS requests
        if request.method in ['HEAD', 'OPTIONS']:
            return None
            
        try:
            resolver_match = resolve(request.path)
            # Get the URL pattern from the resolver match
            return f"{request.method} {resolver_match.route}"
        except Resolver404:
            return None

    def __call__(self, request):
        # Start timing
        start_time = time.time()
        
        # Track DB queries
        with track_db_time():
            response = self.get_response(request)
            db_time = getattr(_local, 'db_time', 0.0)

        # Get the generic URL pattern instead of the exact path
        endpoint = self.get_pattern_name(request)
        
        # Skip storing metrics for 404s or unresolvable URLs
        if endpoint is None:
            return response

        # Calculate timings
        total_time = time.time() - start_time
        compute_time = total_time - db_time

        # Get existing metrics
        metrics = self.metrics_storage.get_metrics(endpoint)
        
        # Add new metric
        metrics.append({
            'total_time': total_time,
            'db_time': db_time,
            'compute_time': compute_time,
            'timestamp': time.time()
        })
        
        # Keep only last 100 requests
        metrics = metrics[-100:]
        
        # Save metrics
        self.metrics_storage.save_metrics(endpoint, metrics)

        return response


class XClacksOverheadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Clacks-Overhead'] = 'GNU Terry Pratchett'
        return response
