
from django.core.exceptions import ValidationError
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from datetime import datetime
import re
import json
import os
import boto3
import requests
import time

from blogs.models import Blog, Media

file_types = ['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif', 'svg', 'webp', 'avif', 'heic', 'ico', 'mp4']

@csrf_exempt
@login_required
def upload_image(request, id):
    blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if request.method == "POST" and blog.user.settings.upgraded is True:
        file_links = []
        time_string = str(time.time()).split('.')[0]

        for file in request.FILES.getlist('file'):
            extension = file.name.split('.')[-1].lower()
            if extension.endswith(tuple(file_types)):
                
                if file.size > 10 * 1024 * 1024:  # 10MB in bytes
                    raise ValidationError(f'File {file.name} exceeds 10MB limit')
                
                filepath = f'{blog.subdomain}-{time_string}.{extension}'
                url = f'https://bear-images.sfo2.cdn.digitaloceanspaces.com/{filepath}'
                file_links.append(url)

                session = boto3.session.Session()
                client = session.client(
                    's3',
                    endpoint_url='https://sfo2.digitaloceanspaces.com',
                    region_name='sfo2',
                    aws_access_key_id=os.getenv('SPACES_ACCESS_KEY_ID'),
                    aws_secret_access_key=os.getenv('SPACES_SECRET'))

                response = client.put_object(
                    Bucket='bear-images',
                    Key=filepath,
                    Body=file,
                    ContentType=file.content_type,
                    ACL='public-read',
                )

                # Create Media object
                Media.objects.create(blog=blog, url=url)
            else:
                raise ValidationError(f'Format not supported: {extension}')

        return HttpResponse(json.dumps(sorted(file_links)), 200)


@login_required
def media_center(request, id):
    blog = get_object_or_404(Blog, user=request.user, subdomain=id)
    
    if not blog.user.settings.upgraded:
        return redirect('upgrade')
    
    if not blog.media.exists():
        uploaded_images = get_uploaded_images(blog)
        # Create Media objects for existing images
        for url in uploaded_images:
            created_at = extract_date_from_url(url)
            Media.objects.get_or_create(blog=blog, url=url, defaults={'created_at': created_at})

    return render(request, 'dashboard/media.html', {
        'blog': blog,
    })


def extract_date_from_url(url):
    # Regular expression to match the timestamp in the image name
    pattern = r'(?:.com/[^-]+-(\d+)(?:-\d+)?\.)'
    match = re.search(pattern, url)
    if match:
        timestamp = int(match.group(1))
        dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return dt
    else:
        raise ValueError("Invalid URL format")
    

def get_uploaded_images(blog):
    session = boto3.session.Session()
    client = session.client(
        's3',
        endpoint_url='https://sfo2.digitaloceanspaces.com',
        region_name='sfo2',
        aws_access_key_id=os.getenv('SPACES_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('SPACES_SECRET'))

    prefix = f'{blog.subdomain}-'
    response = client.list_objects_v2(Bucket='bear-images', Prefix=prefix)

    if 'Contents' not in response:
        return []

    image_urls = [
        f'https://bear-images.sfo2.cdn.digitaloceanspaces.com/{item["Key"]}'
        for item in response['Contents']
        if item['Key'].split('.')[-1].lower() in file_types
    ]

    return sorted(image_urls)


@login_required
def delete_selected_media(request, id):
    blog = get_object_or_404(Blog, user=request.user, subdomain=id)
    
    if request.method == "POST":
        selected_media = request.POST.getlist('selected_media')
            
        session = boto3.session.Session()
        client = session.client(
            's3',
            endpoint_url='https://sfo2.digitaloceanspaces.com',
            region_name='sfo2',
            aws_access_key_id=os.getenv('SPACES_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('SPACES_SECRET')
        )
        
        for image_key in selected_media:
            url = f'https://bear-images.sfo2.cdn.digitaloceanspaces.com/{image_key}'
            
            if Media.objects.filter(blog=blog, url=url).exists():
                client.delete_object(Bucket='bear-images', Key=image_key)
                Media.objects.filter(blog=blog, url=url).delete()
            else:
                return HttpResponseForbidden("Error: Attempted to delete unauthorized media")
            
        
    return redirect('media_center', id=id)


def image_proxy(request, img):
    # Construct the DigitalOcean Spaces URL
    remote_url = f'https://bear-images.sfo2.cdn.digitaloceanspaces.com/{img}'
    
    # Stream the content from the remote URL
    response = requests.get(remote_url, stream=True)
    
    # Define a generator to yield chunks of the response content
    def generate():
        for chunk in response.iter_content(chunk_size=8192):
            yield chunk
    
    # Return a StreamingHttpResponse
    return StreamingHttpResponse(
        generate(),
        status=response.status_code,
        content_type=response.headers['Content-Type']
    )