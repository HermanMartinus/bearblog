from django.utils import timezone

import os
import boto3
from io import BytesIO
import djqscsv
from threading import Thread


def backup_in_thread(blog):
    if os.getenv('ENVIRONMENT') == 'dev':
        return

    if blog.reviewed:
        print(f"Backing up {blog.title} in thread")
        thread = Thread(target=backup_blog, args=(blog,))
        thread.start()
        return thread
    else:
        print(f"Blog {blog.title} is not reviewed, skipping backup")


def backup_blog(blog):
    date_str = timezone.now().strftime('%Y-%m-%d-%H-%M')
    base_path = f'content/{blog.subdomain}/{date_str}'
    
    aws_access_key = os.environ.get('SPACES_ACCESS_KEY_ID')
    aws_secret_key = os.environ.get('SPACES_SECRET')
    s3_bucket = 'bear-backup'
    
    try:
        s3_client = boto3.client(
            's3',
            region_name='fra1',
            endpoint_url='https://fra1.digitaloceanspaces.com',
            aws_access_key_id=aws_access_key,
            aws_secret_access_key=aws_secret_key
        )
        
        uploaded_files = []
        
        # Export and upload posts CSV
        if blog.posts.count() > 0:
            # Create posts CSV in memory
            posts_csv_buffer = BytesIO()
            djqscsv.write_csv(blog.posts.values(), posts_csv_buffer)
            
            # Upload posts CSV
            posts_csv_buffer.seek(0)
            posts_object_path = f'{base_path}/posts.csv'
            s3_client.upload_fileobj(posts_csv_buffer, s3_bucket, posts_object_path)
            uploaded_files.append(posts_object_path)
        
        # Export and upload blog info CSV
        blog_csv_buffer = BytesIO()

        # Create a queryset with just this blog
        blog_queryset = type(blog).objects.filter(pk=blog.pk)
        djqscsv.write_csv(blog_queryset.values(), blog_csv_buffer)
        
        # Upload blog CSV
        blog_csv_buffer.seek(0)
        blog_object_path = f'{base_path}/blog.csv'
        s3_client.upload_fileobj(blog_csv_buffer, s3_bucket, blog_object_path)
        uploaded_files.append(blog_object_path)
        
        return {
            'success': True,
            'blog_subdomain': blog.subdomain,
            'backup_date': date_str,
            'uploaded_files': uploaded_files,
            'post_count': blog.posts.count()
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e),
            'blog_subdomain': blog.subdomain
        }
