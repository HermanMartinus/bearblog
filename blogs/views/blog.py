from PIL import Image, ImageDraw, ImageFont
from io import BytesIO
from django.http import FileResponse
from django.http import HttpResponse
from django.http.response import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.contrib.sites.models import Site
from django.utils import timezone
from django.conf import settings

from blogs.models import Blog, Post, Upvote
from blogs.helpers import get_posts, salt_and_hash, sanitise_int, unmark
from blogs.tasks import daily_task
from blogs.templatetags.custom_tags import format_date
from blogs.views.analytics import render_analytics

import json
import tldextract
import hashlib
import hmac


def resolve_address(request):
    http_host = request.META['HTTP_HOST']

    if http_host == 'bear-blog.herokuapp.com':
        http_host = request.META.get('HTTP_X_FORWARDED_HOST', 'bear-blog.herokuapp.com')

    sites = Site.objects.all()

    if any(http_host == site.domain for site in sites):
        # Homepage
        return None
    elif any(site.domain in http_host for site in sites):
        # Subdomained blog
        return get_object_or_404(Blog, subdomain__iexact=tldextract.extract(http_host).subdomain, blocked=False)
    else:
        # Custom domain blog
        return get_blog_with_domain(http_host)


def get_blog_with_domain(domain):
    if not domain:
        return False
    try:
        return Blog.objects.get(domain=domain, blocked=False)
    except Blog.DoesNotExist:
        # Handle www subdomain if necessary
        if 'www.' in domain:
            return get_object_or_404(Blog, domain__iexact=domain.replace('www.', ''), blocked=False)
        else:
            return get_object_or_404(Blog, domain__iexact=f'www.{domain}', blocked=False)


@csrf_exempt
def ping(request):
    domain = request.GET.get("domain", None)
    print(f'Attempting to issue a certificate for {domain}')

    if get_blog_with_domain(domain):
        print('Found correct blog. Issuing certificate.')
        return HttpResponse('Ping', status=200)
    else:
        print(f'Could not find blog with domain {domain}')
        raise Http404('No such blog')


def home(request):
    blog = resolve_address(request)
    if not blog:
        daily_task()
        return render(request, 'landing.html')

    all_posts = blog.post_set.filter(publish=True, published_date__lte=timezone.now()).order_by('-published_date')

    meta_description = blog.meta_description or unmark(blog.content)

    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'posts': get_posts(all_posts),
            'root': blog.useful_domain(),
            'meta_description': meta_description
        })


def posts(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    tag = request.GET.get('q', '')

    if tag:
        posts = Post.objects.filter(blog=blog, publish=True, published_date__lte=timezone.now()).order_by('-published_date')
        blog_posts = [post for post in posts if tag in post.get_tags]
    else:
        all_posts = blog.post_set.filter(publish=True, published_date__lte=timezone.now()).order_by('-published_date')
        blog_posts = get_posts(all_posts)

    tags = set()
    for post in blog_posts:
        tags.update(post.get_tags)
    tags = sorted(tags)

    meta_description = blog.meta_description or unmark(blog.content)

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': blog_posts,
            'root': blog.useful_domain(),
            'meta_description':  meta_description,
            'tags': tags,
            'query': tag,
        }
    )


@csrf_exempt
def post(request, slug):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    # Check for a custom blogreel path and render the blog page
    if slug == blog.blog_path:
        return posts(request)

    # Find by post slug
    post = Post.objects.filter(blog=blog, slug__iexact=slug).first()
    if not post:
        # Find by post alias
        post = Post.objects.filter(blog=blog, alias__iexact=slug).first()
        if post:
            return redirect(f"/{post.slug}")
        else:
            return render(request, '404.html', {'blog': blog}, status=404)

    # Check if upvoted
    hash_id = salt_and_hash(request, 'year')
    upvoted = post.upvote_set.filter(hash_id=hash_id).exists()

    root = blog.useful_domain()
    meta_description = post.meta_description or unmark(post.content)
    full_path = f'{root}/{post.slug}/'
    canonical_url = full_path
    if post.canonical_url and post.canonical_url.startswith('https://'):
        canonical_url = post.canonical_url

    if post.publish is False and not request.GET.get('preview', False):
        return not_found(request)

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
            'upvoted': upvoted
        }
    )


def post_alias(request, resource):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    post = Post.objects.filter(blog=blog, alias=resource).first()
    if post:
        return redirect(f"/{post.slug}")
    return render(request, '404.html', {'blog': blog}, status=404)


def generate_meta_image(request, slug):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    post = Post.objects.filter(blog=blog, slug__iexact=slug).first()

    img = Image.new('RGB', (250, 180), color="#01242e")
    d = ImageDraw.Draw(img)

    font_title = ImageFont.load_default()
    font_date = ImageFont.load_default()
    font_description = ImageFont.load_default()

    description = post.meta_description or post.content
    if len(description) > 180:
        description = description[0:180].strip() + '...'

    # Insert line breaks after a space without breaking a word
    words = description.split(' ')
    lines = []
    current_line = ''

    for word in words:
        if len(current_line) + len(word) <= 35:
            current_line += ' ' + word if current_line else word
        else:
            lines.append(current_line.strip())
            current_line = word

    if current_line:
        lines.append(current_line.strip())

    description = '\n'.join(lines)

    title = f"# {post.title}"
    if len(title) > 35:
        title = f"{title[0:35].strip()}..."

    # Draw text
    d.text((10, 10), title, fill=(255, 255, 255), font=font_title)
    d.text((10, 40), f"*{format_date(post.published_date, blog.date_format, blog.lang)}*", fill=(255, 255, 255), font=font_date)
    d.text((10, 60), description, fill=(255, 255, 255), font=font_description)
    d.text((10, 160), blog.useful_domain(), fill=(255, 255, 255), font=font_description)

    img_io = BytesIO()
    img.save(img_io, 'PNG', quality=100)
    img_io.seek(0)

    return FileResponse(img_io, filename='meta.png', content_type='image/png')


@csrf_exempt
def upvote(request, pk):
    hash_id = salt_and_hash(request, 'year')

    if pk == request.POST.get("pk", "") and not request.POST.get("title", False):
        pk = sanitise_int(pk, 7)
        post = get_object_or_404(Post, pk=pk)

        upvote, created = Upvote.objects.get_or_create(post=post, hash_id=hash_id)

        post.update_score()

        if created:
            return HttpResponse(f'Upvoted {post.title}')
        raise Http404('Duplicate upvote')
    raise Http404("Someone's doing something dodgy ʕ •`ᴥ•´ʔ")


def public_analytics(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    if not blog or not blog.upgraded or not blog.public_analytics:
        return not_found(request)

    return render_analytics(request, blog, True)


@csrf_exempt
def lemon_webhook(request):
    digest = hmac.new(settings.LEMONSQUEEZY_SIGNATURE.encode('utf-8'), msg=request.body, digestmod=hashlib.sha256).hexdigest()

    if request.META.get('HTTP_X_SIGNATURE') != digest:
        raise Http404('Blog not found')

    data = json.loads(request.body, strict=False)

    # Blog upgrade
    if 'order_created' in request.META.get('HTTP_X_EVENT_NAME', ''):
        blog = None
        try:
            subdomain = str(data['meta']['custom_data']['blog'])
            blog = get_object_or_404(Blog, subdomain=subdomain)
            print(f'Found subdomain {subdomain}, upgrading blog...')
        except KeyError:
            email = str(data['data']['attributes']['user_email'])
            blog = Blog.objects.get(user__email=email)
            print(f'Found email address {email}, upgrading blog...')

        if blog:
            blog.reviewed = True
            blog.upgraded = True
            blog.upgraded_date = timezone.now()
            blog.order_id = data['data']['id']
            blog.save()
            return HttpResponse(f'Upgraded {blog}')

    # Blog downgrade
    elif 'subscription_expired' in request.META.get('HTTP_X_EVENT_NAME', ''):
        blog = None
        try:
            blog = get_object_or_404(Blog, order_id=data['data']['attributes']['order_id'])
            print('Found order_id, downgrading blog...')
            if blog:
                blog.upgraded = False
                blog.upgraded_date = None
                blog.order_id = None
                blog.save()
                return HttpResponse(f'Downgraded {blog}')
        except KeyError:
            print('Could not find order_id')

    return HttpResponse('Valid webhook call with no action taken')


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)


def sitemap(request):
    blog = resolve_address(request)
    posts = []
    try:
        posts = blog.post_set.filter(publish=True, published_date__lte=timezone.now()).order_by('-published_date')
    except AttributeError:
        posts = []

    return render(request, 'sitemap.xml', {'blog': blog, 'posts': posts}, content_type='text/xml')


def robots(request):
    blog = resolve_address(request)
    return render(request, 'robots.txt',  {'blog': blog}, content_type="text/plain")
