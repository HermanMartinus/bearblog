from django.core.management.base import BaseCommand
from django.db import connection
from blogs.models import BUOYANCY, UPVOTE_CAP


SQL = """
UPDATE blogs_post SET score =
    log(10, GREATEST(LEAST(upvotes, %s) + shadow_votes, 1)::numeric)::double precision
    + (EXTRACT(EPOCH FROM COALESCE(first_published_at, published_date)) - 1577811600)
      / (%s * 86400.0)
WHERE upvotes > 1
  AND COALESCE(first_published_at, published_date) IS NOT NULL
  AND EXTRACT(EPOCH FROM COALESCE(first_published_at, published_date)) > 0
  AND id BETWEEN %s AND %s
"""


class Command(BaseCommand):
    help = 'Recalculates discover feed scores for every upvoted post'

    def handle(self, *args, **kwargs):
        with connection.cursor() as cursor:
            cursor.execute('SELECT MIN(id), MAX(id) FROM blogs_post WHERE upvotes > 1')
            first_id, last_id = cursor.fetchone()
            if first_id is None:
                self.stdout.write(self.style.SUCCESS('No scored posts'))
                return

            # Batched so we never hold row locks on the whole table at once
            batch_size = 5000
            updated = 0
            for start in range(first_id, last_id + 1, batch_size):
                cursor.execute(SQL, [UPVOTE_CAP, BUOYANCY, start, start + batch_size - 1])
                updated += cursor.rowcount

        self.stdout.write(self.style.SUCCESS(
            f'Rescored {updated} posts (buoyancy {BUOYANCY}, cap {UPVOTE_CAP})'
        ))
