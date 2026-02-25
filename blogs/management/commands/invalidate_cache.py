from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta
from blogs.models import Post

class Command(BaseCommand):
    help = 'Invalidates Cloudflare cache'

    def handle(self, *args, **kwargs):
        # Find posts that just became public in the last 10 minutes (scheduled to run every 10 min).
        # This catches scheduled posts going live so Cloudflare doesn't keep serving stale cached pages.
        for post in Post.objects.filter(publish=True, published_date__lte=timezone.now(), published_date__gte=timezone.now() - timedelta(minutes=10)):
            post.blog.invalidate_cloudflare_cache()
            self.stdout.write(self.style.SUCCESS(f'Successfully invalidated Cloudflare cache for {post.blog.subdomain}'))
        self.stdout.write(self.style.SUCCESS(f'All invalidations done'))