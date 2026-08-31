from django.utils.text import slugify
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q
from zoneinfo import ZoneInfo

import io
from datetime import datetime
from PIL import Image, ImageOps
import pillow_heif
import re
import os
import boto3
import logging
import threading

from blogs.models import Blog, Media

pillow_heif.register_heif_opener()

bucket_name = os.getenv('SPACES_BUCKET', 'bear-images')
logger = logging.getLogger(__name__)


image_types = ['png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif', 'svg', 'webp', 'avif', 'ico', 'heic', 'heif']
video_types = ['mp4', 'webm', 'mkv']
audio_types = ['mp3', 'ogg', 'wav', 'opus', 'flac']
document_types = ['pdf', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx', 'txt', 'rtf', 'epub', 'ps', 'odt', 'ods', 'odp', 'odg', 'odf', 'mml', 'odb', 'uot', 'uos', 'uop', 'css']
font_types = ['woff', 'woff2', 'ttf', 'otf']

file_types = image_types + video_types + audio_types + document_types + font_types

file_size_limit = 10 * 1024 * 1024 # 10MB in bytes


class UploadError(Exception):
    def __init__(self, message, status_code=400):
        super().__init__(message)
        self.status_code = status_code


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
    file_list = request.FILES.getlist('file')
    if request.method == "POST" and file_list and blog.user.settings.upgraded is True:
        try:
            upload_files(blog, file_list)
        except UploadError as error:
            error_messages.append(str(error))

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


@login_required
def upload_image(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if request.method == "POST" and blog.user.settings.upgraded is True:
        file_list = request.FILES.getlist('file')
        if not file_list:
            return JsonResponse({'error': 'No file provided.'}, status=400)

        optimise = True
        if request.POST.get('raw') == 'true':
            optimise = False

        try:
            file_links = upload_files(blog, file_list, optimise)
        except UploadError as error:
            return JsonResponse({'error': str(error)}, status=error.status_code)

        return JsonResponse({'urls': sorted(file_links)})
    return JsonResponse({'error': 'Upload failed.'}, status=400)


def upload_files(blog, file_list, optimise=True):
    file_links = []

    for file in file_list:
        # Fair use limit
        if blog.media.count() > 20000:
            raise UploadError('Fair usage limit exceeded. Contact site admin.', status_code=429)

        # Upload size limit
        if file.size > file_size_limit:
            raise UploadError(f'File {file.name} exceeds 10MB limit.', status_code=413)
        
        # Only allowed file types
        extension = os.path.splitext(file.name)[1].lstrip('.').lower()
        if extension not in file_types:
            raise UploadError(f'File type not supported: {file.name}', status_code=415)
        
        # Strip metadata if the file is an image
        if extension in image_types and extension != 'svg' and extension != 'gif':
            try:
                file = process_image(file, optimise)
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                logger.exception('Error processing image %s', file.name)
                raise UploadError(
                    'The image file cannot be identified or is not a valid image.',
                    status_code=422,
                ) from error

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

        file_data = file.read()
        content_type = file.content_type

        Media.objects.create(blog=blog, url=url)
        file_links.append(url)

        thread = threading.Thread(
            target=upload_to_s3,
            args=(filepath, file_data, content_type)
        )
        thread.start()
    
    return sorted(file_links)


def upload_to_s3(filepath, file_data, content_type):
    session = boto3.session.Session()
    client = session.client(
        's3',
        endpoint_url='https://sfo2.digitaloceanspaces.com',
        region_name='sfo2',
        aws_access_key_id=os.getenv('SPACES_ACCESS_KEY_ID'),
        aws_secret_access_key=os.getenv('SPACES_SECRET'))

    try:
        client.put_object(
            Bucket=bucket_name,
            Key=filepath,
            Body=file_data,
            ContentType=content_type,
            ACL='public-read',
        )
    except Exception:
        logger.exception('Error uploading %s to Spaces', filepath)


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
        dt = datetime.fromtimestamp(timestamp, tz=ZoneInfo("UTC"))
        return dt
    else:
        return timezone.now()
    

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
