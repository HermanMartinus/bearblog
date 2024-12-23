from django.utils.text import slugify
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden
from django.http import StreamingHttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q

import io
from datetime import datetime
from PIL import Image, UnidentifiedImageError, ImageOps
import re
import json
import os
import boto3
import requests

from blogs.models import Blog, Media

bucket_name = 'bear-images'


image_types = ['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif', 'svg', 'webp', 'avif', 'ico', 'heic', 'css']
video_types = ['mp4', 'webm', 'mkv']
audio_types = ['mp3', 'ogg', 'wav', 'opus', 'flac']
document_types = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'rtf', 'epub', 'ps', 'odt', 'ods', 'odp', 'odg', 'odf', 'mml', 'odb', 'uot', 'uos', 'uop']
font_types = ['woff', 'woff2', 'ttf', 'otf']

file_types = image_types + video_types + audio_types + document_types + font_types

file_size_limit = 10 * 1024 * 1024 # 10MB in bytes


@login_required
def media_center(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)
    
    if not blog.user.settings.upgraded:
        return redirect('upgrade')

    error_messages = []

    # Upload media
    if request.method == "POST" and request.FILES.getlist('file') and blog.user.settings.upgraded is True:
        file_links = upload_files(blog, request.FILES.getlist('file'))
        for link in file_links:
            if 'Error' in link:
                error_messages.append(link)

    # Prefill blogs with existing images on the bucket
    if not blog.media.exists():
        prefill_blog_media(blog)

    image_filter = Q()
    for ext in image_types + video_types:
        image_filter |= Q(url__iendswith=ext)
    
    images = blog.media.filter(image_filter).order_by('-created_at')

    document_filter = Q()
    for ext in audio_types + document_types + font_types:
        document_filter |= Q(url__iendswith=ext)

    documents = blog.media.filter(document_filter).order_by('-created_at')

    accepted_file_types = ','.join([f'.{ext}' for ext in image_types + video_types + audio_types + document_types + font_types])

    return render(request, 'dashboard/media.html', {
        'blog': blog,
        'images': images,
        'documents': documents,
        'accepted_file_types': accepted_file_types,
        'error_messages': error_messages
    })


@csrf_exempt
@login_required
def upload_image(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if request.method == "POST" and blog.user.settings.upgraded is True:
        file_links = upload_files(blog, request.FILES.getlist('file'))

        return HttpResponse(json.dumps(sorted(file_links)), 200)


def upload_files(blog, file_list):
    file_links = []

    for file in file_list:
        # Fair use limit
        if blog.media.count() > 20000:
            file_links.append('Error: Fair usage limit exceeded. Contact site admin.')
            return sorted(file_links)

        # Upload size limit
        if file.size > file_size_limit:
            file_links.append(f'Error: File {file.name} exceeds 10MB limit')
            break
        
        # Only allowed file types but also explicitly excluding heic since Safari auto-converts it otherwise
        if not file.name.lower().endswith(tuple(file_types)) or file.name.lower().endswith('heic'):
            file_links.append(f'Error: File type not supported: {file.name}')
            break
        
        extension = file.name.split('.')[-1].lower()
        
        # Strip metadata if the file is an image
        if extension in image_types and not extension.endswith('svg') and not extension.endswith('gif'):
            try:
                file = process_image(file, blog.optimise_images)
            except UnidentifiedImageError:
                file_links.append(f'Error: The image file cannot be identified or is not a valid image.')
                break

        file_name = slugify(file.name.split('.')[-2].lower())
        extension = file.name.split('.')[-1].lower()

        # Check for duplicate names
        count = 0
        new_file_name = file_name
        while blog.media.filter(url__icontains=new_file_name).exists():
            count += 1
            new_file_name = f"{file_name}-{count}"
        file_name = new_file_name
        
        filepath = f'{blog.subdomain}/{file_name}.{extension}'
        url = f'https://{bucket_name}.sfo2.cdn.digitaloceanspaces.com/{filepath}'
        file_links.append(url)

        session = boto3.session.Session()
        client = session.client(
            's3',
            endpoint_url='https://sfo2.digitaloceanspaces.com',
            region_name='sfo2',
            aws_access_key_id=os.getenv('SPACES_ACCESS_KEY_ID'),
            aws_secret_access_key=os.getenv('SPACES_SECRET'))

        response = client.put_object(
            Bucket=bucket_name,
            Key=filepath,
            Body=file,
            ContentType=file.content_type,
            ACL='public-read',
        )

        # Create Media object
        Media.objects.create(blog=blog, url=url)
    
    return sorted(file_links)


def process_image(file, optimise):
    original_image = Image.open(file)
    # Keeps orientation information
    image = ImageOps.exif_transpose(original_image)

    data = io.BytesIO()

    if optimise:
        max_width = 1200
        if image.width > max_width:
            # Calculate the new height to maintain the aspect ratio
            ratio = max_width / float(image.width)
            new_height = int(float(image.height) * ratio)
            # Resize the image with high-quality resampling
            image = image.resize((max_width, new_height), resample=Image.LANCZOS)

        image.save(data, format='WEBP')
        # Update file name and content type for WebP
        file_name = os.path.splitext(file.name)[0] + '.webp'
        content_type = 'image/webp'
    else:
        if image.mode == 'P':
            image = image.convert('RGB')
        # Save the image to strip metadata (EXIF, etc.)
        image.save(data, format=original_image.format)
        file_name = file.name
        content_type = file.content_type

    data.seek(0)

    print('Stripped metadata')

    original_size = file.size / 1024
    new_size = len(data.getvalue()) / 1024
    compression_rate = (original_size - new_size) / original_size * 100 if original_size != 0 else 0

    print(f'Original size: {original_size:.2f} KB')
    print(f'New size: {new_size:.2f} KB')
    print(f'Compression rate: {compression_rate:.2f}%')

    return InMemoryUploadedFile(
        file=data,
        field_name=None,
        name=file_name,
        content_type=content_type,
        size=len(data.getvalue()),
        charset=None
    )


def prefill_blog_media(blog):
    uploaded_images = get_uploaded_images(blog)
    # Create Media objects for existing images
    for url in uploaded_images:
        created_at = extract_date_from_url(url)
        Media.objects.get_or_create(blog=blog, url=url, defaults={'created_at': created_at})


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
    response = client.list_objects_v2(Bucket=bucket_name, Prefix=prefix)

    if 'Contents' not in response:
        return []

    image_urls = [
        f'https://{bucket_name}.sfo2.cdn.digitaloceanspaces.com/{item["Key"]}'
        for item in response['Contents']
        if item['Key'].split('.')[-1].lower() in file_types
    ]

    return sorted(image_urls)


@login_required
def delete_selected_media(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
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
        print(selected_media)
        for url in selected_media:
            print(url)
            if Media.objects.filter(blog=blog, url=url).exists():
                key = url.replace(f'https://{bucket_name}.sfo2.cdn.digitaloceanspaces.com/', '')
                print(f"Deleting key: {key}")
                response = client.delete_object(Bucket=bucket_name, Key=key)
                # print("S3 Response:", response)
                Media.objects.filter(blog=blog, url=url).delete()
            else:
                return HttpResponseForbidden("Error: Attempted to delete unauthorized media")

            
        
    return redirect('media_center', id=id)


def image_proxy(request, img):
    # Construct the DigitalOcean Spaces URL
    remote_url = f'https://{bucket_name}.sfo2.cdn.digitaloceanspaces.com/{img}'
    
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