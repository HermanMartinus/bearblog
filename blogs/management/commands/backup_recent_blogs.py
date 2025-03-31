from datetime import timedelta
from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone
import zipfile
from io import BytesIO
import os
import sys
import djqscsv
from blogs.models import Blog

class Command(BaseCommand):
    help = 'Backup blogs modified or with posts in the last 24 hours as CSV files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--output-dir',
            default='backups',
            help='Directory where backup files will be saved'
        )
        parser.add_argument(
            '--days',
            type=int,
            default=1,
            help='Number of days to look back for changes (default: 1)'
        )
        parser.add_argument(
            '--no-zip',
            action='store_true',
            help='Save individual CSV files instead of a zip archive'
        )
        parser.add_argument(
            '--stdout',
            action='store_true',
            help='Output zip file to stdout for downloading from Heroku'
        )

    def handle(self, *args, **options):
        # Get parameters
        output_dir = options['output_dir']
        days = options['days']
        no_zip = options['no_zip']
        to_stdout = options['stdout']
        
        # Get blogs modified or with posts in the specified time period
        time_period = timezone.now() - timedelta(days=days)
        
        # Find blogs with recent activity
        recent_blogs = Blog.objects.filter(
            Q(last_modified__gte=time_period) | 
            Q(last_posted__gte=time_period)
        ).distinct()

        if len(recent_blogs) == 0:
            self.stdout.write(self.style.WARNING('No blogs with recent activity found'))
            return
            
        if not to_stdout:
            self.stdout.write(f'Found {recent_blogs.count()} blogs with recent activity')
        
        if to_stdout:
            # Create a zip file in memory and output to stdout
            zip_buffer = BytesIO()
            with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for blog in recent_blogs:
                    csv_data = self._get_blog_csv_data(blog, verbose=False)
                    if csv_data:
                        filename = f"{blog.subdomain}_{timezone.now().strftime('%Y%m%d')}.csv"
                        zip_file.writestr(filename, csv_data)
            
            # Write the zip file to stdout
            sys.stdout.buffer.write(zip_buffer.getvalue())
        elif no_zip:
            # Create output directory if it doesn't exist
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            # Save individual CSV files
            for blog in recent_blogs:
                self._backup_blog_to_csv(blog, output_dir)
        else:
            # Create output directory if it doesn't exist
            if not os.path.exists(output_dir):
                os.makedirs(output_dir)
                
            # Create a zip file
            zip_filename = os.path.join(output_dir, f"blog_backups_{timezone.now().strftime('%Y%m%d')}.zip")
            with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for blog in recent_blogs:
                    csv_data = self._get_blog_csv_data(blog)
                    if csv_data:
                        filename = f"{blog.subdomain}_{timezone.now().strftime('%Y%m%d')}.csv"
                        zip_file.writestr(filename, csv_data)
            
            self.stdout.write(self.style.SUCCESS(f'Successfully created backup zip at {zip_filename}'))
    
    def _get_blog_csv_data(self, blog, verbose=True):
        # Define the fields to include in the CSV
        fields = ['uid', 'title', 'slug', 'alias', 'published_date', 'all_tags', 
                  'publish', 'make_discoverable', 'is_page', 'content', 
                  'canonical_url', 'meta_description', 'meta_image', 'lang', 
                  'class_name', 'first_published_at']
        
        # Get posts for this blog
        posts = blog.posts.values(*fields)
        
        if posts.exists():
            # Create CSV in memory
            csv_buffer = BytesIO()
            djqscsv.write_csv(posts, csv_buffer)
            if verbose:
                self.stdout.write(f'  - Added {posts.count()} posts from {blog.subdomain}')
            return csv_buffer.getvalue()
        return None
    
    def _backup_blog_to_csv(self, blog, output_dir):
        csv_data = self._get_blog_csv_data(blog)
        if csv_data:
            filename = os.path.join(output_dir, f"{blog.subdomain}_{timezone.now().strftime('%Y%m%d')}.csv")
            with open(filename, 'wb') as f:
                f.write(csv_data)
            self.stdout.write(self.style.SUCCESS(f'  - Saved {filename}')) 