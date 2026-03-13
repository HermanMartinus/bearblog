from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = 'Backfill search vectors for discoverable posts'

    def add_arguments(self, parser):
        parser.add_argument('batch_size', type=int, help='Number of posts to backfill')

    def handle(self, *args, **kwargs):
        batch_size = kwargs['batch_size']
        with connection.cursor() as cursor:
            cursor.execute("""
                UPDATE blogs_post
                SET search_vector = to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(all_tags, '') || ' ' || LEFT(COALESCE(content, ''), 50000))
                WHERE id IN (
                    SELECT p.id FROM blogs_post p
                    INNER JOIN blogs_blog b ON p.blog_id = b.id
                    INNER JOIN auth_user u ON b.user_id = u.id
                    WHERE p.search_vector IS NULL
                        AND p.publish = TRUE
                        AND p.hidden = FALSE
                        AND p.make_discoverable = TRUE
                        AND p.published_date <= NOW()
                        AND LENGTH(COALESCE(p.content, '')) >= 100
                        AND b.reviewed = TRUE
                        AND b.hidden = FALSE
                        AND u.is_active = TRUE
                    LIMIT %s
                )
            """, [batch_size])
            self.stdout.write(f'Updated {cursor.rowcount} posts')

            cursor.execute("""
                SELECT COUNT(*) FROM blogs_post p
                INNER JOIN blogs_blog b ON p.blog_id = b.id
                INNER JOIN auth_user u ON b.user_id = u.id
                WHERE p.search_vector IS NULL
                    AND p.publish = TRUE
                    AND p.hidden = FALSE
                    AND p.make_discoverable = TRUE
                    AND p.published_date <= NOW()
                    AND LENGTH(COALESCE(p.content, '')) >= 100
                    AND b.reviewed = TRUE
                    AND b.hidden = FALSE
                    AND u.is_active = TRUE
            """)
            remaining = cursor.fetchone()[0]
            self.stdout.write(f'{remaining} remaining')
