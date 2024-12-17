from django.contrib.auth.decorators import login_required
from django.db import DataError
from django.forms import ValidationError
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, render, redirect
from django.http import HttpResponseBadRequest
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import URLValidator

from datetime import datetime
import json
import random
import string

from blogs.forms import AdvancedSettingsForm, BlogForm, DashboardCustomisationForm, PostTemplateForm
from blogs.helpers import check_connection, is_protected, salt_and_hash
from blogs.models import Blog, Post, Upvote
from blogs.subscriptions import get_subscriptions


@login_required
def list(request):
    blogs = Blog.objects.filter(user=request.user)

    if request.method == "POST":
        form = BlogForm(request.POST)
        if form.is_valid():
            if blogs.count() >= request.user.settings.max_blogs:
                form.add_error('title', 'You have reached the maximum number of blogs.')
            else:
                subdomain = slugify(form.cleaned_data['subdomain'])

                if not is_protected(subdomain) and not Blog.objects.filter(subdomain=subdomain).exists():
                    blog_info = form.save(commit=False)
                    blog_info.user = request.user
                    blog_info.save()
                    return redirect('dashboard', id=blog_info.subdomain)
                else:
                    form.add_error('subdomain', 'This subdomain is already in use or protected.')
    else:
        form = BlogForm()

    subscription_cancelled = None
    subscription_link = None

    if request.user.settings.order_id:
        subscription = get_subscriptions(request.user.settings.order_id)

        try:
            if subscription:
                subscription_cancelled = subscription['data'][0]['attributes']['cancelled']
                subscription_link = subscription['data'][0]['attributes']['urls']['customer_portal']
        except (KeyError, IndexError, TypeError):
            print('No sub found')

    return render(request, 'studio/blog_list.html', {'blogs': blogs, 'form': form, 'subscription_cancelled': subscription_cancelled, 'subscription_link': subscription_link})


@login_required
def studio(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    error_messages = []
    header_content = request.POST.get('header_content', '')
    body_content = request.POST.get('body_content', '')

    if request.method == "POST" and header_content:
        try:
            error_messages.extend(parse_raw_homepage(blog, header_content, body_content))
        except IndexError:
            error_messages.append("One of the header options is invalid")
        except ValueError as error:
            error_messages.append(error)
        except DataError as error:
            error_messages.append(error)

    return render(request, 'studio/studio.html', {
        'blog': blog,
        'error_messages': error_messages,
        'header_content': header_content,
    })


def parse_raw_homepage(blog, header_content, body_content):
    raw_header = [item for item in header_content.split('\r\n') if item]
    
    # Clear out data
    blog.favicon = ''
    blog.meta_description = ''
    blog.meta_image = ''

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
        elif name == 'favicon':
            if len(value) < 100:
                blog.favicon = value
            else:
                error_messages.append("Favicon is too long. Use an emoji.")
        elif name == 'meta_description':
            blog.meta_description = value
        elif name == 'meta_image':
            blog.meta_image = value
        else:
            error_messages.append(f"{name} is an unrecognised header option")

    if not blog.title:
        blog.title = "My blog"
    if not blog.subdomain:
        blog.slug = slugify(blog.user.username)

    blog.content = body_content
    blog.last_modified = timezone.now()
    blog.save()
    return error_messages


@login_required
def post(request, id, uid=None):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    is_page = request.GET.get('is_page', '')
    tags = []
    post = None

    if uid:
        post = Post.objects.filter(blog=blog, uid=uid).first()

    error_messages = []
    header_content = request.POST.get("header_content", "")
    body_content = request.POST.get("body_content", "")
    preview = request.POST.get("preview", False) == "true"

    if request.method == "POST" and header_content:
        raw_header = [item for item in header_content.split('\r\n') if item]
        is_new = False

        if not post:
            post = Post(blog=blog)
            is_new = True

        try:
            # Clear out data
            slug = ''
            post.alias = ''
            post.class_name = ''
            post.canonical_url = ''
            post.meta_description = ''
            post.meta_image = ''
            post.is_page = False
            post.make_discoverable = True
            post.lang = ''
            post.all_tags = '[]'

            # Parse and populate header data
            for item in raw_header:
                item = item.split(':', 1)
                name = item[0].strip()

                # Prevent index error
                if len(item) == 2:
                    value = item[1].strip()
                else:
                    value = ''

                if str(value).lower() == 'true':
                    value = True
                if str(value).lower() == 'false':
                    value = False

                if name == 'title':
                    post.title = value
                elif name == 'link':
                    slug = value
                elif name == 'alias':
                    post.alias = value
                elif name == 'published_date':
                    if not value:
                        post.published_date = timezone.now()
                    else:
                        value = str(value).replace('/', '-')
                        try:
                            # Convert given date/time from local timezone to UTC
                            naive_datetime = datetime.fromisoformat(value)
                            user_timezone = request.COOKIES.get('timezone', 'UTC')
                            user_tz = timezone.get_default_timezone() if user_timezone == 'UTC' else timezone.pytz.timezone(user_timezone)
                            aware_datetime = timezone.make_aware(naive_datetime, user_tz)
                            utc_datetime = aware_datetime.astimezone(timezone.utc)
                            post.published_date = utc_datetime
                        except Exception as e:
                            error_messages.append('Bad date format. Use YYYY-MM-DD HH:MM')
                elif name == 'tags':
                    tags = []
                    for tag in value.split(','):
                        stripped_tag = tag.strip()
                        if stripped_tag and stripped_tag not in tags:
                            tags.append(stripped_tag)
                    post.all_tags = json.dumps(tags)
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

            post.slug = unique_slug(blog, post, slug)

            if not post.published_date:
                post.published_date = timezone.now()

            post.content = body_content

            post.publish = request.POST.get("publish", False) == "true"
            post.last_modified = timezone.now()

            if preview:
                return post
            else:
                post.save()
                
                if is_new:
                    # Self-upvote
                    upvote = Upvote(post=post, hash_id=salt_and_hash(request, 'year'))
                    upvote.save()

                    # Redirect to the new post detail view
                    return redirect('post_edit', id=blog.subdomain, uid=post.uid)

        except Exception as error:
            error_messages.append(f"Header attribute error - your post has not been saved. Error: {str(error)}")
            post.content = body_content

    template_header = ""
    template_body = ""
    if blog.post_template:
        template_parts = blog.post_template.split("___", 1)
        if len(template_parts) == 2:
            template_header, template_body = template_parts

    return render(request, 'studio/post_edit.html', {
        'blog': blog,
        'post': post,
        'error_messages': error_messages,
        'template_header': template_header,
        'template_body': template_body,
        'is_page': is_page
    })


def unique_slug(blog, post, new_slug):
    slug = slugify(new_slug) or slugify(post.title) or slugify(str(random.randint(0,9999)))
    new_stack = "-new"

    while Post.objects.filter(blog=blog, slug=slug).exclude(pk=post.pk).exists():
        slug = f"{slug}{new_stack}"
        new_stack += "-new"

    return slug


@csrf_exempt
@login_required
def preview(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    post = Post(blog=blog)

    header_content = request.POST.get("header_content", "")
    body_content = request.POST.get("body_content", "")
    try:
        if header_content:
            raw_header = [item for item in header_content.split('\r\n') if item]

            if post is None:
                post = Post(blog=blog)

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
                elif name == 'alias':
                    post.alias = value
                elif name == 'published_date':
                    # Check if previously posted 'now'
                    value = value.replace('/', '-')
                    if not str(post.published_date).startswith(value):
                        post.published_date = timezone.datetime.fromisoformat(value)
                elif name == 'make_discoverable':
                    post.make_discoverable = value
                elif name == 'is_page':
                    post.is_page = value
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

            if not post.title:
                post.title = "New post"
            if not post.slug:
                post.slug = slugify(post.title)
                if not post.slug or post.slug == "":
                    post.slug = ''.join(random.SystemRandom().choice(string.ascii_letters) for _ in range(10))
            if not post.published_date:
                post.published_date = timezone.now()

            post.content = body_content

    except ValidationError:
        return HttpResponseBadRequest("One of the header options is invalid")
    except IndexError:
        return HttpResponseBadRequest("One of the header options is invalid")
    except ValueError as error:
        return HttpResponseBadRequest(error)
    except DataError as error:
        return HttpResponseBadRequest(error)

    full_path = f'{blog.useful_domain}/{post.slug}/'
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
            'full_path': full_path,
            'canonical_url': canonical_url,
            'meta_image': post.meta_image or blog.meta_image,
            'preview': True,
        }
    )


@login_required
def post_template(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

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


@login_required
def custom_domain_edit(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if not blog.user.settings.upgraded:
        return redirect('upgrade')

    error_messages = []

    if request.method == "POST":
        custom_domain = request.POST.get("custom-domain", "")

        if Blog.objects.filter(domain__iexact=custom_domain).exclude(pk=blog.pk).count() == 0:
            try:
                validator = URLValidator()
                validator('http://' + custom_domain)
                blog.domain = custom_domain
                blog.save()
            except ValidationError:
                error_messages.append(f'{custom_domain} is an invalid domain')
                print("error")
        elif not custom_domain:
            blog.domain = ''
            blog.save()
        else:
            error_messages.append(f"{custom_domain} is already registered with another blog")

    # If records not set correctly
    if blog.domain and not check_connection(blog):
        error_messages.append(f"The DNS records for { blog.domain } have not been set.")

    return render(request, 'studio/custom_domain_edit.html', {
        'blog': blog,
        'error_messages': error_messages
    })


@login_required
def directive_edit(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if not blog.user.settings.upgraded:
        return redirect('upgrade')

    header = request.POST.get("header", "")
    footer = request.POST.get("footer", "")

    if request.method == "POST":
        blog.header_directive = header
        blog.footer_directive = footer
        blog.save()

    return render(request, 'studio/directive_edit.html', {
        'blog': blog
    })


@login_required
def advanced_settings(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if request.method == "POST":
        form = AdvancedSettingsForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        form = AdvancedSettingsForm(instance=blog)

    return render(request, 'dashboard/advanced_settings.html', {
        'blog': blog,
        'form': form
    })


@login_required
def dashboard_customisation(request):
    if request.method == "POST":
        form = DashboardCustomisationForm(request.POST, instance=request.user.settings)
        if form.is_valid():
            user_settings = form.save(commit=False)
            user_settings.save()
    else:
        form = DashboardCustomisationForm(instance=request.user.settings)

    return render(request, 'dashboard/dashboard_customisation.html', {'form': form})