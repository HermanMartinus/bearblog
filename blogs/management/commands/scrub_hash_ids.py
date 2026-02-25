from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from blogs.models import Hit


class Command(BaseCommand):
    help = 'Scrubs hash_ids from hits older than 24 hours'

    def handle(self, *args, **kwargs):
        time_24_hours_ago = timezone.now() - timedelta(hours=24)
        Hit.objects.filter(created_date__lt=time_24_hours_ago).exclude(hash_id='scrubbed').update(hash_id='scrubbed')
        self.stdout.write(self.style.SUCCESS('Scrubbed hash_ids'))
