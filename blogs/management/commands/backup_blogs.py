from django.core.management.base import BaseCommand
from django.utils import timezone
from blogs.models import Blog
import djqscsv
import zipfile
from io import BytesIO
import os
from datetime import timedelta

class Command(BaseCommand):
    help = 'Backup all active blogs to a zip file of CSVs'

    def handle(self, *args, **options):
        # Get blogs that have been active in the last year
        self.stdout.write('Finding active blogs...')
        blogs_to_backup = Blog.objects.filter(last_posted__gte=timezone.now() - timedelta(days=180))
        total_blogs = blogs_to_backup.count()
        self.stdout.write(f'Found {total_blogs} blogs with activity recently')
        
        zip_path = f'blog_backups.zip'
        
        # Create a zip file
        self.stdout.write(f'Creating backup at {zip_path}')
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            processed = 0
            skipped = 0
            
            for blog in blogs_to_backup:
                # Define fields to export
                fields = ['uid', 'title', 'slug', 'alias', 'published_date', 'all_tags', 
                          'publish', 'make_discoverable', 'is_page', 'content', 
                          'canonical_url', 'meta_description', 'meta_image', 'lang', 
                          'class_name', 'first_published_at']
                
                # Skip blogs with no posts
                if blog.posts.count() == 0:
                    skipped += 1
                    continue
                    
                # Create CSV in memory
                csv_buffer = BytesIO()
                djqscsv.write_csv(blog.posts.values(*fields), csv_buffer)
                
                # Add CSV to zip file
                csv_buffer.seek(0)
                filename = f"{blog.subdomain}.csv"
                zip_file.writestr(filename, csv_buffer.getvalue())
                
                processed += 1
                if processed % 100 == 0:
                    self.stdout.write(f'Processed {processed} blogs...')
        
        # Output summary
        self.stdout.write(self.style.SUCCESS(
            f'Backup complete! Processed {processed} blogs, skipped {skipped} empty blogs.'
        ))
        self.stdout.write(self.style.SUCCESS(f'Backup saved to {zip_path}')) 