from django.core.management.base import BaseCommand
from django.utils import timezone

from blogs.models import Blog

import djqscsv
import zipfile
from io import BytesIO
import os
from datetime import timedelta
import boto3
from botocore.exceptions import NoCredentialsError
import uuid

class Command(BaseCommand):
    help = 'Backup all active blogs to a zip file of CSVs and upload to S3'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=365,
            help='Number of days to look back for active blogs',
        )

    def handle(self, *args, **options):
        date_str = timezone.now().strftime('%Y%m%d')
        
        # Get blogs that have been active recently
        self.stdout.write('Finding active blogs...')
        blogs_to_backup = Blog.objects.filter(last_posted__gte=timezone.now() - timedelta(days=options['days']))
        total_blogs = blogs_to_backup.count()
        self.stdout.write(f'Found {total_blogs} blogs with recent activity')
        
        # Create a zip file in memory
        self.stdout.write('Creating backup in memory')
        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            processed = 0
            skipped = 0
            
            for blog in blogs_to_backup:
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
        
        # Upload to S3
        self.stdout.write('Uploading backup to S3...')
        try:
            aws_access_key = os.environ.get('SPACES_ACCESS_KEY_ID')
            aws_secret_key = os.environ.get('SPACES_SECRET')
            s3_bucket = 'bear-backup'
            
            if not all([aws_access_key, aws_secret_key, s3_bucket]):
                self.stdout.write(self.style.ERROR(
                    'AWS credentials not found. Set SPACES_ACCESS_KEY_ID, and SPACES_SECRET environment variables.'
                ))
                return
            
            # Create a unique object name
            unique_id = str(uuid.uuid4())[:8]
            object_name = f'content/blog_backups_{date_str}_{unique_id}.zip'
            
            s3_client = boto3.client(
                's3',
                region_name='fra1',
                endpoint_url='https://fra1.digitaloceanspaces.com',
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key
            )
            
            # Reset buffer position to beginning before upload
            zip_buffer.seek(0)
            s3_client.upload_fileobj(zip_buffer, s3_bucket, object_name)
            
            self.stdout.write(self.style.SUCCESS(f'Backup uploaded to S3!'))
            
        except NoCredentialsError:
            self.stdout.write(self.style.ERROR('AWS credentials not found or invalid'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error uploading to S3: {str(e)}')) 