from django.contrib.auth.decorators import login_required
from django.db import DataError
from django.forms import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import URLValidator

from ipaddr import client_ip
from random import randint
import re
import random
import string

from blogs.forms import PostTemplateForm
from blogs.helpers import check_connection, sanitise_int
from blogs.models import Blog, Post, Upvote


@login_required
def studio(request):
    blog = None
    try:
        blog = Blog.objects.get(user=request.user)
    except Blog.DoesNotExist:
        subdomain = request.user.username
        if Blog.objects.filter(subdomain=request.user.username):
            subdomain = request.user.username + '-' + str(randint(0, 9))
        blog = Blog(
            user=request.user,
            title="My blog",
            subdomain=slugify(subdomain).replace('_', '-'))
        blog.save()

    error_messages = []
    header_content = request.POST.get('header_content', '')
    body_content = request.POST.get('body_content', '')

    if header_content:
        try:
            error_messages.extend(parse_raw_homepage(blog, header_content, body_content))
        except IndexError:
            error_messages.append("One of the header options is invalid")
        except ValueError as error:
            error_messages.append(error)
        except DataError as error:
            error_messages.append(error)

    info_message = blog.domain and not check_connection(blog)

    return render(request, 'studio/studio.html', {
        'blog': blog,
        'error_messages': error_messages,
        'header_content': header_content,
        'info_message': info_message
    })


def parse_raw_homepage(blog, header_content, body_content):
    raw_header = list(filter(None, header_content.split('\r\n')))

    # Clear out data
    blog.domain = ''
    blog.meta_description = ''
    blog.meta_image = ''
    blog.meta_tag = ''
    blog.lang = 'en'

    error_messages = []
    # Parse and populate header data
    for item in raw_header:
        item = item.split(':', 1)
        name = item[0].strip()
        value = item[1].strip()
        if str(value).lower() == 'true':
            value = True
        if str(value).lower() == 'false':
            value = False

        if name == 'title':
            blog.title = value
        elif name == 'bear_domain':
            subdomain = slugify(value.split('.')[0]).replace('_', '-')
            if not subdomain:
                error_messages.append("{value} is not a valid bear_domain")
            else:
                if not Blog.objects.filter(subdomain=subdomain).exclude(pk=blog.pk).count():
                    blog.subdomain = subdomain
                else:
                    error_messages.append(f"{value} has already been taken")
        elif name == "custom_domain":
            if blog.upgraded:
                if Blog.objects.filter(domain=value).exclude(pk=blog.pk).count() == 0:
                    try:
                        validator = URLValidator()
                        validator('http://' + value)
                        blog.domain = value
                    except ValidationError:
                        error_messages.append(f'{value} is an invalid custom_domain')
                        print("error")
                else:
                    error_messages.append(f"{value} is already registered with another blog")
            else:
                error_messages.append("Upgrade your blog to add a custom domain")
        elif name == 'favicon':
            if len(value) < 20:
                blog.favicon = value
            else:
                error_messages.append("Favicon is too long")
        elif name == 'meta_description':
            blog.meta_description = value
        elif name == 'meta_image':
            blog.meta_image = value
        elif name == 'lang':
            blog.lang = value
        elif name == 'custom_meta_tag':
            pattern = r'<meta\s+(?:[^>]*(?!\b(?:javascript|scripts|url)\b)[^>]*)*>'
            if re.search(pattern, value, re.IGNORECASE):
                blog.meta_tag = value
            else:
                error_messages.append("Invalid custom_meta_tag")
        else:
            error_messages.append(f"{name} is an unrecognised header option")

    if not blog.title:
        blog.title = "My blog"
    if not blog.subdomain:
        blog.slug = slugify(blog.user.username)
    if not blog.favicon:
        blog.favicon = "🐻"

    blog.content = body_content
    blog.last_modified = timezone.now()
    blog.save()
    return error_messages


@login_required
def directive_edit(request):
    blog = get_object_or_404(Blog, user=request.user)

    header = request.POST.get("header", "")
    footer = request.POST.get("footer", "")

    if request.method == "POST":
        blog.header_directive = header
        blog.footer_directive = footer
        blog.save()

    return render(request, 'studio/directive_edit.html', {
        'blog': blog,
    })


@login_required
def post(request, pk=None):
    blog = get_object_or_404(Blog, user=request.user)
    tags = []
    post = None

    if pk:
        post = Post.objects.filter(blog=blog, pk=sanitise_int(pk)).first()
        if post:
            tags = post.tags.all()

    error_messages = []
    header_content = request.POST.get("header_content", "")
    body_content = request.POST.get("body_content", "")
    preview = request.POST.get("preview", False) == "true"

    if request.method == "POST" and header_content:
        header_content = list(filter(None, header_content.split('\r\n')))
        is_new = False

        if not post:
            post = Post(blog=blog)
            is_new = True

        try:
            # Clear out data
            # post.slug = ''
            post.alias = ''
            post.class_name = ''
            post.canonical_url = ''
            post.meta_description = ''
            post.meta_image = ''
            post.is_page = False
            post.make_discoverable = True
            post.lang = ''
            tags = []

            # Parse and populate header data
            for item in header_content:
                item = item.split(':', 1)
                name = item[0].strip()
                value = item[1].strip()
                if str(value).lower() == 'true':
                    value = True
                if str(value).lower() == 'false':
                    value = False

                if name == 'title':
                    post.title = value
                elif name == 'link':
                    post.slug = slugify(value)
                elif name == 'alias':
                    post.alias = value
                elif name == 'published_date':
                    # Check if previously posted 'now'
                    value = value.replace('/', '-')
                    if not str(post.published_date).startswith(value):
                        try:
                            post.published_date = timezone.datetime.fromisoformat(value)
                        except ValueError:
                            error_messages.append('Bad date format. Use YYYY-MM-DD')
                elif name == 'tags':
                    tags = [tag.strip() for tag in value.split(',')]
                elif name == 'make_discoverable':
                    if type(value) is bool:
                        post.make_discoverable = value
                    else:
                        error_messages.append('make_discoverable needs to be "true" or "false"')
                elif name == 'is_page':
                    if type(value) is bool:
                        post.is_page = value
                    else:
                        error_messages.append('is_page needs to be "true" or "false"')
                elif name == 'class_name':
                    post.class_name = slugify(value)
                elif name == 'canonical_url':
                    post.canonical_url = value
                elif name == 'lang':
                    post.lang = value
                elif name == 'meta_description':
                    post.meta_description = value
                elif name == 'meta_image':
                    post.meta_image = value
                else:
                    error_messages.append(f"{name} is an unrecognised header option")

            if not post.title:
                post.title = "New post"
            if not post.slug:
                post.slug = slugify(post.title)
                if not post.slug or post.slug == "":
                    post.slug = ''.join(random.SystemRandom().choice(string.ascii_letters) for _ in range(10))
            if not post.published_date:
                post.published_date = timezone.now()

            post.content = body_content

            if Post.objects.filter(blog=blog, slug=post.slug).exclude(pk=post.pk).count() > 0:
                post.slug = post.slug + '-' + str(randint(0, 9))

            post.publish = request.POST.get("publish", False) == "true"
            post.last_modified = timezone.now()

            if preview:
                return post
            else:
                post.save()

                if is_new:
                    # Self-upvote
                    upvote = Upvote(post=post, ip_address=client_ip(request))
                    upvote.save()

                    # Add tags after saved
                    post.tags.clear()
                    if tags:
                        for tag in tags:
                            if tag.strip() != '':
                                post.tags.add(tag.strip())

                    # Redirect to the new post detail view
                    return redirect('post_edit', pk=post.pk)

        except ValidationError:
            error_messages.append("One of the header options is invalid")
        except IndexError:
            error_messages.append("One of the header options is invalid")
        except ValueError as error:
            error_messages.append(error)
        except DataError as error:
            error_messages.append(error)

    template_header = ""
    template_body = ""
    if blog.post_template:
        template_parts = blog.post_template.split("___", 1)
        if len(template_parts) == 2:
            template_header, template_body = template_parts

    return render(request, 'studio/post_edit.html', {
        'blog': blog,
        'root': blog.useful_domain(),
        'tags': tags,
        'post': post,
        'error_messages': error_messages,
        'template_header': template_header,
        'template_body': template_body
    })


def create_or_update_post(request, blog, pk, preview=False):
    if pk is None:
        post = None
        tags = []
    else:
        try:
            post = Post.objects.get(blog=blog, pk=sanitise_int(pk))
            tags = post.tags.all()
        except Post.DoesNotExist:
            post = None
            tags = []

    error_messages = []
    header_content = request.POST.get("header_content", "")
    body_content = request.POST.get("body_content", "")

    if header_content:
        header_content = list(filter(None, header_content.split('\r\n')))
        is_new = False

        if post is None:
            post = Post(blog=blog)
            is_new = True

        try:
            # Clear out data
            # post.slug = ''
            post.alias = ''
            post.class_name = ''
            post.canonical_url = ''
            post.meta_description = ''
            post.meta_image = ''
            post.is_page = False
            post.make_discoverable = True
            post.lang = ''
            tags = []

            # Parse and populate header data
            for item in header_content:
                item = item.split(':', 1)
                name = item[0].strip()
                value = item[1].strip()
                if str(value).lower() == 'true':
                    value = True
                if str(value).lower() == 'false':
                    value = False

                if name == 'title':
                    post.title = value
                elif name == 'link':
                    post.slug = slugify(value)
                elif name == 'alias':
                    post.alias = value
                elif name == 'published_date':
                    # Check if previously posted 'now'
                    value = value.replace('/', '-')
                    if not str(post.published_date).startswith(value):
                        try:
                            post.published_date = timezone.datetime.fromisoformat(value)
                        except ValueError:
                            error_messages.append('Bad date format. Use YYYY-MM-DD')
                elif name == 'tags':
                    tags = [tag.strip() for tag in value.split(',')]
                elif name == 'make_discoverable':
                    if type(value) is bool:
                        post.make_discoverable = value
                    else:
                        error_messages.append('make_discoverable needs to be "true" or "false"')
                elif name == 'is_page':
                    if type(value) is bool:
                        post.is_page = value
                    else:
                        error_messages.append('is_page needs to be "true" or "false"')
                elif name == 'class_name':
                    post.class_name = slugify(value)
                elif name == 'canonical_url':
                    post.canonical_url = value
                elif name == 'lang':
                    post.lang = value
                elif name == 'meta_description':
                    post.meta_description = value
                elif name == 'meta_image':
                    post.meta_image = value
                else:
                    error_messages.append(f"{name} is an unrecognised header option")

            if not post.title:
                post.title = "New post"
            if not post.slug:
                post.slug = slugify(post.title)
                if not post.slug or post.slug == "":
                    post.slug = ''.join(random.SystemRandom().choice(string.ascii_letters) for _ in range(10))
            if not post.published_date:
                post.published_date = timezone.now()

            post.content = body_content

            if Post.objects.filter(blog=blog, slug=post.slug).exclude(pk=post.pk).count() > 0:
                post.slug = post.slug + '-' + str(randint(0, 9))

            post.publish = request.POST.get("publish", False) == "true"
            post.last_modified = timezone.now()

            if preview:
                return post
            else:
                post.save()

                if is_new:
                    # Self-upvote
                    upvote = Upvote(post=post, ip_address=client_ip(request))
                    upvote.save()

                # Add tags after saved
                post.tags.clear()
                if tags:
                    for tag in tags:
                        if tag.strip() != '':
                            post.tags.add(tag.strip())

        except ValidationError:
            error_messages.append("One of the header options is invalid")
        except IndexError:
            error_messages.append("One of the header options is invalid")
        except ValueError as error:
            error_messages.append(error)
        except DataError as error:
            error_messages.append(error)

    return {'post': post, 'tags': tags, 'error_messages': error_messages}


@csrf_exempt
@login_required
def preview(request):
    blog = get_object_or_404(Blog, user=request.user)

    post = create_or_update_post(request, blog, None, True)

    root = blog.useful_domain()
    full_path = f'{root}/{post.slug}/'
    canonical_url = full_path
    if post.canonical_url and post.canonical_url.startswith('https://'):
        canonical_url = post.canonical_url
    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': post.content,
            'post': post,
            'root': blog.useful_domain(),
            'full_path': full_path,
            'canonical_url': canonical_url,
            'meta_image': post.meta_image or blog.meta_image,
            'preview': True,
        }
    )


@login_required
def post_template(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.method == "POST":
        form = PostTemplateForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        form = PostTemplateForm(instance=blog)

    return render(request, 'studio/post_template_edit.html', {
        'blog': blog,
        'form': form})
