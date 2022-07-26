from random import randint
import re
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.forms import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

import tldextract

from blogs.helpers import sanitise_int, unmark
from blogs.models import Blog, Post


def resolve_subdomain(http_host, blog):
    extracted = tldextract.extract(http_host)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return False
    return True


@login_required
def studio(request):
    blog = None
    try:
        blog = Blog.objects.get(user=request.user)
        if not resolve_subdomain(request.META['HTTP_HOST'], blog):
            return redirect(f"https://bearblog.dev/dashboard")
    except Blog.DoesNotExist:
        subdomain = request.user.username
        if Blog.objects.filter(subdomain=request.user.username):
            subdomain = request.user.username + '-' + str(randint(0, 9))
        blog = Blog(
            user=request.user,
            title="My blog",
            subdomain=subdomain)
        blog.save()

    error_message = ""
    raw_content = request.POST.get('raw_content', '')
    if raw_content:
        try:
            parse_raw_homepage(raw_content, blog)
            blog.save()
        except IntegrityError:
            error_message = "This bear_domain is already taken"
        except IndexError:
            error_message = "One of the header options is invalid"
        except ValueError as error:
            error_message = error

    return render(request, 'studio/studio.html', {
        'blog': blog,
        'error_message': error_message,
        'raw_content': raw_content
    })


def parse_raw_homepage(raw_content, blog):
    raw_header = list(filter(None, raw_content.split('___')[0].split('\r\n')))

    # Clear out data
    blog.title = ''
    blog.subdomain = ''
    blog.domain = ''
    blog.meta_description = ''
    blog.meta_image = ''
    blog.meta_tag = ''

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
            blog.subdomain = slugify(value.split('.')[0])
        elif name == "custom_domain":
            if blog.upgraded:
                blog.domain = value
            else:
                raise ValueError("Upgrade your blog to add a custom domain")
        elif name == 'favicon':
            blog.favicon = value
        elif name == 'meta_description':
            blog.meta_description = value
        elif name == 'meta_image':
            blog.meta_image = value
        elif name == 'lang':
            blog.lang = value
        elif name == 'nav':
            blog.nav = value
        elif name == 'custom_meta_tag':
            if re.search(r'<meta (.*?)/>', value) and "url" not in value and "javascript" not in value and "script" not in value:
                blog.meta_tag = value
            else:
                raise ValueError("Invalid custom_meta_tag")
        else:
            raise ValueError(f"Unrecognised value: {name}")

    if not blog.title:
        blog.title = "My blog"
    if not blog.subdomain:
        blog.slug = slugify(blog.user.username)
    if not blog.favicon:
        blog.favicon = "🐻"

    blog.content = raw_content[raw_content.index('___') + 3:].strip()


@login_required
def post(request, pk=None):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"//bearblog.dev/dashboard")

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

    error_message = ""
    raw_content = request.POST.get("raw_content", "")

    if raw_content:
        if post is None:
            post = Post(blog=blog)

        try:
            tags = parse_raw_post(raw_content, post)
            if len(Post.objects.filter(blog=blog, slug=post.slug).exclude(pk=post.pk)) > 0:
                post.slug = post.slug + '-' + str(randint(0, 9))

            post.publish = request.POST.get("publish", False) == "true"

            post.save()

            # Add tags after saved
            post.tags.clear()
            if tags:
                for tag in tags.split(','):
                    if slugify(tag.strip()) != '':
                        post.tags.add(slugify(tag.strip()))

            return redirect(f"/studio/posts/{post.id}/")
        except ValidationError:
            error_message = "One of the header options is invalid"
        except IndexError:
            error_message = "One of the header options is invalid"
        except ValueError as error:
            error_message = error

    return render(request, 'studio/post_edit.html', {
        'blog': blog,
        'root': blog.useful_domain(),
        'tags': tags,
        'post': post,
        'error_message': error_message,
        'raw_content': raw_content
    })


def parse_raw_post(raw_content, post):
    raw_header = list(filter(None, raw_content.split('___')[0].split('\r\n')))

    # Clear out data
    post.slug = ''
    post.canonical_url = ''
    post.meta_description = ''
    post.meta_image = ''
    post.is_page = False
    post.make_discoverable = True
    tags = []

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
            post.title = value
        elif name == 'link':
            post.slug = slugify(value)
        elif name == 'published_date':
            # Check if previously posted 'now'
            value = value.replace('/', '-')
            if not str(post.published_date).startswith(value):
                try:
                    post.published_date = timezone.datetime.fromisoformat(value)
                except ValueError:
                    raise ValueError('Bad date format. Use YYYY-MM-DD')
        elif name == 'tags':
            tags = value
        elif name == 'make_discoverable':
            if type(value) is bool:
                post.make_discoverable = value
            else:
                raise ValueError('make_discoverable needs to be "true" or "false"')
        elif name == 'is_page':
            if type(value) is bool:
                post.is_page = value
            else:
                raise ValueError('is_page needs to be "true" or "false"')
        elif name == 'canonical_url':
            post.canonical_url = value
        elif name == 'meta_description':
            post.meta_description = value
        elif name == 'meta_image':
            post.meta_image = value
        else:
            raise ValueError(f"Unrecognised value: {name}")

    if not post.title:
        post.title = "New post"
    if not post.slug:
        post.slug = slugify(post.title)
    if not post.published_date:
        post.published_date = timezone.now()

    post.content = raw_content[raw_content.index('___') + 3:].strip()

    return tags


@csrf_exempt
@login_required
def preveiw(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"https://bearblog.dev/dashboard")

    error_message = ""
    raw_content = request.POST.get("raw_content", "")
    post = Post(blog=blog)

    if raw_content:
        try:
            parse_raw_post(raw_content, post)
        except ValidationError:
            error_message = "One of the header options is invalid"
        except IndexError:
            error_message = "One of the header options is invalid"
        except ValueError as error:
            error_message = error

        root = blog.useful_domain()
        meta_description = post.meta_description or unmark(post.content)
        full_path = f'{root}/{post.slug}'
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
            'meta_description': meta_description,
            'meta_image': post.meta_image or blog.meta_image,
            'preview': True,
            'error_message': error_message
        }
    )
