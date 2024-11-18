from datetime import timedelta
from django.utils import timezone
import threading

from blogs.models import Hit, PersistentStore, RssSubscriber


def daily_task():
    current_time = timezone.now()
    time_24_hours_ago = current_time - timedelta(hours=24)

    persistent_store = PersistentStore.load()

    if persistent_store.last_executed < time_24_hours_ago:
        persistent_store.last_executed = current_time
        persistent_store.save()

        print('Executing daily task')

        t = threading.Thread(target=scrub_hash_ids)
        t.start()


# Scrub all hash_ids and RSS Subscribers that are over 24 hours old
def scrub_hash_ids():
    current_time = timezone.now()
    time_24_hours_ago = current_time - timedelta(hours=24)
    RssSubscriber.objects.filter(access_date__lt=time_24_hours_ago).delete()
    # Hit.objects.filter(created_date__lt=time_24_hours_ago).exclude(hash_id='scrubbed').update(hash_id='scrubbed')
    print('Scrubbed hash_ids')
