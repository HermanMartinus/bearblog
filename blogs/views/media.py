from django.utils.text import slugify
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.files.uploadedfile import InMemoryUploadedFile
from django.db.models import Q

import io
from PIL import Image, ImageOps
import pillow_heif
import os
import boto3
import threading

from blogs.models import Blog, Media

pillow_heif.register_heif_opener()


def get_storage_config():
    return {
        'bucket': os.getenv('OBJECT_STORAGE_BUCKET'),
        'public_url': os.getenv('OBJECT_STORAGE_PUBLIC_URL', '').rstrip('/'),
        'endpoint_url': os.getenv('OBJECT_STORAGE_ENDPOINT_URL') or None,
        'region': os.getenv('OBJECT_STORAGE_REGION') or None,
        'access_key_id': os.getenv('OBJECT_STORAGE_ACCESS_KEY_ID') or None,
        'secret_access_key': os.getenv('OBJECT_STORAGE_SECRET_ACCESS_KEY') or None,
        'acl': os.getenv('OBJECT_STORAGE_ACL', ''),
    }


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
    storage_config = get_storage_config()
    if not storage_config['bucket'] or not storage_config['public_url']:
        raise UploadError('Object storage is not configured.', status_code=503)

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
        url = f"{storage_config['public_url']}/{filepath}"

        file_data = file.read()
        content_type = file.content_type

        Media.objects.create(blog=blog, url=url)
        file_links.append(url)

        thread = threading.Thread(
            target=upload_to_object_storage,
            args=(filepath, file_data, content_type)
        )
        thread.start()
    
    return sorted(file_links)


def upload_to_object_storage(filepath, file_data, content_type):
    config = get_storage_config()
    client = boto3.session.Session().client(
        's3',
        endpoint_url=config['endpoint_url'],
        region_name=config['region'],
        aws_access_key_id=config['access_key_id'],
        aws_secret_access_key=config['secret_access_key'],
    )

    try:
        params = {
            'Bucket': config['bucket'],
            'Key': filepath,
            'Body': file_data,
            'ContentType': content_type,
        }
        if config['acl']:
            params['ACL'] = config['acl']
        client.put_object(**params)
    except Exception:
        pass


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

    return InMemoryUploadedFile(
        file=data,
        field_name=None,
        name=file_name,
        content_type=content_type,
        size=len(data.getvalue()),
        charset=None
    )


@login_required
def delete_selected_media(request, id):
    blog = get_object_or_404(Blog, user=request.user, subdomain=id)
    
    if request.method == "POST":
        selected_media = request.POST.getlist('selected_media')
        config = get_storage_config()
        if not config['bucket'] or not config['public_url']:
            return HttpResponseForbidden("Error: Object storage is not configured")
        client = boto3.session.Session().client(
            's3',
            endpoint_url=config['endpoint_url'],
            region_name=config['region'],
            aws_access_key_id=config['access_key_id'],
            aws_secret_access_key=config['secret_access_key'],
        )
        for url in selected_media:
            if Media.objects.filter(blog=blog, url=url).exists():
                try:
                    prefix = f"{config['public_url']}/"
                    if not url.startswith(prefix):
                        raise ValueError
                    key = url[len(prefix):]
                except ValueError:
                    return HttpResponseForbidden("Error: Media storage is not configured for this URL")
                client.delete_object(Bucket=config['bucket'], Key=key)
                Media.objects.filter(blog=blog, url=url).delete()
            else:
                return HttpResponseForbidden("Error: Attempted to delete unauthorized media")

            
        
    return redirect('media_center', id=id)
