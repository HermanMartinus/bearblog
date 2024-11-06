from django.db import connection
import time
from collections import defaultdict
from statistics import mean
from threading import Lock
from contextlib import contextmanager
import threading

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

    def __call__(self, request):
        # Start timing
        start_time = time.time()
        
        # Track DB queries
        with track_db_time():
            response = self.get_response(request)
            db_time = getattr(_local, 'db_time', 0.0)

        # Calculate timings
        total_time = time.time() - start_time
        compute_time = total_time - db_time

        # Store metrics (thread-safe)
        endpoint = f"{request.method} {request.path}"
        with metrics_lock:
            request_metrics[endpoint].append({
                'total_time': total_time,
                'db_time': db_time,
                'compute_time': compute_time,
                'timestamp': time.time()
            })
            # Keep only last 100 requests per endpoint
            request_metrics[endpoint] = request_metrics[endpoint][-100:]

        return response


class XClacksOverheadMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['X-Clacks-Overhead'] = 'GNU Terry Pratchett'
        return response
