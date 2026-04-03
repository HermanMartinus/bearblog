import os
import sys
import time
import threading
import traceback

from django.utils import timezone
from django.core.cache import cache


LEADER_KEY = "heartbeat:leader"
LEADER_TTL = 90

_heartbeat_started = False


def all_is_well():
    print(f"It's {timezone.now().strftime('%H:%M')} and All Is Well!")


TASKS = [
    ("all_is_well", all_is_well),
]


def start_heartbeat():
    global _heartbeat_started
    if _heartbeat_started:
        return

    is_gunicorn = 'gunicorn' in sys.modules
    is_runserver = len(sys.argv) > 1 and sys.argv[1] == 'runserver'

    if not (is_gunicorn or is_runserver):
        return

    if is_runserver and os.environ.get('RUN_MAIN') != 'true':
        return

    _heartbeat_started = True
    thread = HeartbeatThread()
    thread.start()


class HeartbeatThread(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.identity = f"{os.environ.get('DYNO', 'dev')}:{os.getpid()}:{threading.get_ident()}"
        self._stop_event = threading.Event()

    def run(self):
        print(f"[heartbeat] started ({self.identity})")
        while not self._stop_event.is_set():
            self._sleep_until_next_minute()
            if self._stop_event.is_set():
                break
            self._try_lead_and_run()

    def stop(self):
        self._stop_event.set()

    def _sleep_until_next_minute(self):
        now = time.time()
        deadline = now + (60 - now % 60)
        while time.time() < deadline and not self._stop_event.is_set():
            remaining = deadline - time.time()
            self._stop_event.wait(min(remaining, 1.0))

    def _try_lead_and_run(self):
        try:
            current = cache.get(LEADER_KEY)

            if current is None:
                acquired = cache.add(LEADER_KEY, self.identity, LEADER_TTL)
                if not acquired:
                    return
            elif current != self.identity:
                return
            else:
                cache.set(LEADER_KEY, self.identity, LEADER_TTL)

            for name, task in TASKS:
                try:
                    task()
                except Exception:
                    print(f"[heartbeat] task {name} failed:\n{traceback.format_exc()}")
        except Exception:
            print(f"[heartbeat] error:\n{traceback.format_exc()}")
