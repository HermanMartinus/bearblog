from django.db import connection
from django.urls import resolve, Resolver404
import time
from collections import defaultdict
from statistics import mean
from threading import Lock
import threading
from contextlib import contextmanager

# Thread-safe storage for metrics
request_metrics = defaultdict(list)
metrics_lock = Lock()

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
        # Cache common methods as a set for faster lookups
        self.skip_methods = {'HEAD', 'OPTIONS'}

    def get_pattern_name(self, request):
        # Use set lookup instead of list comparison
        if request.method in self.skip_methods:
            return None
            
        # Move resolver_match access outside of try block for better performance
        resolver_match = getattr(request, 'resolver_match', None)
        if resolver_match is not None:
            return f"{request.method} {resolver_match.route}"
            
        try:
            resolver_match = resolve(request.path)
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

        # Calculate timings
        total_time = time.time() - start_time
        
        new_metric = {
            'total_time': total_time,
            'db_time': db_time,
            'compute_time': total_time - db_time,
            'timestamp': start_time
        }

        # Store metrics (thread-safe)
        with metrics_lock:
            metrics = request_metrics[endpoint]
            metrics.append(new_metric)
            if len(metrics) > 50:
                del metrics[:-50]

        return response


class XClacksOverheadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Clacks-Overhead'] = 'GNU Terry Pratchett'
        return response
