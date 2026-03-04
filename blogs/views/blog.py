from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.conf import settings

from PIL import Image as PILImage, ImageDraw, ImageFont
from pathlib import Path
import io

from blogs.models import Blog, Post, Upvote
from blogs.helpers import salt_and_hash, unmark
from blogs.templatetags.custom_tags import plain_title
from blogs.views.analytics import render_analytics

import os
import tldextract

def resolve_address(request):
    http_host = request.get_host()

    sites = os.getenv('MAIN_SITE_HOSTS').split(',')

    if any(http_host == site for site in sites):
        # Homepage
        return None
    elif any(site in http_host for site in sites):
        # Subdomained blog
        subdomain = tldextract.extract(http_host).subdomain.lower()

        return get_object_or_404(Blog.objects.select_related('user').select_related('user__settings'), subdomain=subdomain, user__is_active=True)
    else:
        # Custom domain blog
        return get_blog_with_domain(http_host)


def get_blog_with_domain(domain):
    if not domain:
        return False

    pk = get_domain_id(domain)
    if not pk:
        raise Http404

    try:
        # Single PK lookup
        return Blog.objects.select_related('user').select_related('user__settings').get(pk=pk, user__is_active=True)
    except ObjectDoesNotExist:
        raise Http404


def get_domain_id(check):
    if not check:
        return None
    
    domain_map = cache.get('domain_map')

    if domain_map is None:
        domain_map = {
            domain.strip().lower().removeprefix('www.'): pk
            for domain, pk in Blog.objects
                .exclude(domain__isnull=True)
                .exclude(domain='')
                .values_list('domain', 'pk')
        }
        cache.set('domain_map', domain_map, timeout=3600)

    clean = check.strip().lower().removeprefix('www.')

    return domain_map.get(clean)


@csrf_exempt
def ping(request):
    domain = request.GET.get("domain", None)

    if not domain:
        return HttpResponse('Invalid domain', status=422, content_type='text/plain')

    try:
        if get_domain_id(domain):
            # print('Ping! Found correct blog. Issuing certificate for', domain)
            return HttpResponse('Ping', status=200, content_type='text/plain')
    except:
        pass

    # print("Ping! Invalid domain", domain)
    return HttpResponse('Invalid domain', status=422, content_type='text/plain')


def home(request):
    blog = resolve_address(request)
    if not blog:
        # Don't cache here because of dashboard
        return render(request, 'landing.html')

    all_posts = blog.posts.filter(publish=True, published_date__lte=timezone.now(), is_page=False).order_by('-published_date')

    meta_description = blog.meta_description or unmark(blog.content)[:157] + '...'
    
    response = render(
        request,
        'home.html',
        {
            'blog': blog,
            'posts': all_posts,
            'meta_description': meta_description,
            'meta_image': blog.meta_image or f'{blog.useful_domain}/og-image.png',
        }
    )

    response['Cache-Tag'] = blog.subdomain
    response['Cache-Control'] = "public, s-maxage=43200, max-age=0"

    return response


def posts(request, blog):
    if not blog:
        blog = resolve_address(request)
    if not blog:
        return not_found(request)
    
    tag_param = request.GET.get('q', '')
    tags = [t.strip() for t in tag_param.split(',')] if tag_param else []
    tags = [t for t in tags if t]  # Remove empty strings
    
    posts = blog.posts.filter(
        blog=blog, 
        publish=True, 
        published_date__lte=timezone.now(), 
        is_page=False
    ).order_by('-published_date')
    
    include_tags = [t for t in tags if not t.startswith('-')]
    exclude_tags = [t[1:] for t in tags if t.startswith('-') and len(t) > 1]

    if include_tags or exclude_tags:
        posts = [post for post in posts if
            all(t in post.tags for t in include_tags) and
            not any(t in post.tags for t in exclude_tags)]
        available_tags = set()
        for post in posts:
            available_tags.update(post.tags)
    else:
        available_tags = set(blog.tags)

    # Only include tags that aren't already active and are available
    tags_to_show = [tag for tag in blog.tags if tag not in tags and tag not in exclude_tags and tag in available_tags]
    
    meta_description = blog.meta_description or unmark(blog.content)[:157] + '...'
    blog_path_title = blog.blog_path.replace('-', ' ').capitalize() or 'Blog'
    
    response = render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': posts,
            'meta_description': meta_description,
            'meta_image': blog.meta_image or f'{blog.useful_domain}/og-image.png',
            'query': tag_param,
            'active_tags': tags,
            'available_tags': available_tags,
            'blog_path_title': blog_path_title,
            'tags_to_show': tags_to_show,
        }
    )
    
    response['Cache-Tag'] = blog.subdomain
    response['Cache-Control'] = "public, s-maxage=43200, max-age=0"
    return response


def post(request, slug):
    # Prevent null characters in path
    slug = slug.replace('\x00', '')

    if slug[0] == '/' and slug[-1] == '/':
        slug = slug[1:-1]

    blog = resolve_address(request)
    if not blog:
        return not_found(request)
    
    # Check for a custom RSS feed path
    if slug == blog.rss_alias:
        from blogs.views.feed import feed
        return feed(request)

    # Find by post slug
    post = Post.objects.filter(blog=blog, slug__iexact=slug).first()

    if not post:
        # Find by post alias
        post = Post.objects.filter(blog=blog, alias__iexact=slug).first()
        
        if post:
            return redirect('post', slug=post.slug)
        else:
            # Check for a custom blogreel or /blog path and render the blog page
            if slug == blog.blog_path or slug == 'blog':
                return posts(request, blog)

            response = render(request, '404.html', {'blog': blog}, status=404)
            response['Cache-Tag'] = blog.subdomain
            response['Cache-Control'] = "max-age=43200"
            return response

    meta_description = post.meta_description or unmark(post.content)[:157] + '...'
    full_path = f'{blog.useful_domain}/{post.slug}/'
    canonical_url = full_path
    if post.canonical_url and post.canonical_url.startswith('https://'):
        canonical_url = post.canonical_url

    if post.publish is False and not request.GET.get('token') == post.token:
        return not_found(request)

    context = {
        'blog': blog,
        'post': post,
        'full_path': full_path,
        'canonical_url': canonical_url,
        'meta_description': meta_description,
        'meta_image': post.meta_image or blog.meta_image or f'{blog.useful_domain}/{post.slug}/og-image.png',
    }

    response = render(request, 'post.html', context)

    if post.publish and not request.GET.get('token'):
        response['Cache-Tag'] = blog.subdomain
        response['Cache-Control'] = "public, s-maxage=43200, max-age=0"

    return response


def get_upvote_info(request, uid):
    post = get_object_or_404(Post.objects.only('upvotes'), uid=uid)
    hash_id = salt_and_hash(request, 'year')
    upvoted = post.upvote_set.filter(hash_id=hash_id).exists()
    
    response = JsonResponse({
        "upvoted": upvoted,
        "upvote_count": post.upvotes,
    })
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


@csrf_exempt
def upvote(request):
    if request.POST.get("uid", "") and not request.POST.get("title", False):
        hash_id = salt_and_hash(request, 'year')
        post = get_object_or_404(Post, uid=request.POST.get("uid", ""))
        try:
            upvote, created = Upvote.objects.get_or_create(post=post, hash_id=hash_id)
        
            if created:
                print("Upvoting", post)
            else:
                print("Not upvoting: Duplicate upvote")
        except Upvote.MultipleObjectsReturned:
            print("Not upvoting: Duplicate upvote")

        response = HttpResponse(f'Upvoted {post.title}', content_type='text/plain')
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    return HttpResponse('Forbidden', status=403, content_type='text/plain')


def public_analytics(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    if not blog or not blog.user.settings.upgraded or not blog.public_analytics:
        return not_found(request)

    return render_analytics(request, blog, True)


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)


def sitemap(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)
    
    try:
        posts = blog.posts.filter(publish=True, published_date__lte=timezone.now()).only('slug', 'last_modified', 'blog_id').order_by('-published_date')
    except AttributeError:
        posts = []
    
    response = render(request, 'sitemap.xml', {'blog': blog, 'posts': posts}, content_type='text/xml')
    response['Cache-Tag'] = blog.subdomain
    response['Cache-Control'] = "public, s-maxage=43200, max-age=0"
    return response


def robots(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    response = render(request, 'robots.txt',  {'blog': blog}, content_type="text/plain")
    response['Cache-Tag'] = blog.subdomain
    response['Cache-Control'] = "public, s-maxage=43200, max-age=0"
    return response


def og_image(request, post_slug=None):
    blog = resolve_address(request)
    if not blog:
        raise Http404

    if post_slug:
        post = Post.objects.filter(blog=blog, slug__iexact=post_slug, publish=True).first()
        if not post:
            raise Http404
        title = plain_title(post.title)
        snippet = post.meta_description or unmark(post.content)[:250] + '...'
    else:
        title = plain_title(blog.title)
        snippet = blog.meta_description or unmark(blog.content)[:250] + '...'

    img_bytes = _generate_og_image(title, snippet)

    response = HttpResponse(img_bytes, content_type='image/png')
    response['Cache-Tag'] = blog.subdomain
    response['Cache-Control'] = 'public, s-maxage=86400, max-age=3600'
    return response


def _load_font(bold=False, size=48):
    """Load Verdana (Bear Blog default), falling back to DejaVu Sans, then Pillow default."""
    font_paths = [
        # macOS
        f'/System/Library/Fonts/Supplemental/Verdana{" Bold" if bold else ""}.ttf',
        f'/Library/Fonts/Verdana{" Bold" if bold else ""}.ttf',
        # Linux
        f'/usr/share/fonts/truetype/msttcorefonts/{"Verdana_Bold" if bold else "Verdana"}.ttf',
        f'/usr/share/fonts/truetype/dejavu/DejaVuSans{"-Bold" if bold else ""}.ttf',
    ]
    for path in font_paths:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def _generate_og_image(title, snippet):
    width, height = 1200, 630
    img = PILImage.new('RGB', (width, height), '#ffffff')
    draw = ImageDraw.Draw(img)

    font_large = _load_font(bold=True, size=48)
    font_small = _load_font(bold=False, size=26)

    # Bear ASCII art in bottom-right
    static_dir = Path(settings.STATICFILES_DIRS[0])
    try:
        bear = PILImage.open(static_dir / 'bear_ascii.png').convert('RGBA')
        img.paste(bear, (width - bear.width - 60, height - bear.height - 40), bear)
    except Exception:
        pass

    margin_x = 80
    max_text_width = width - margin_x * 2

    # Draw title
    title_lines = _wrap_text(draw, title, font_large, max_text_width)
    if len(title_lines) > 3:
        title_lines = title_lines[:3]
        title_lines[-1] = title_lines[-1].rstrip() + '...'

    y = 80
    for line in title_lines:
        draw.text((margin_x, y), line, fill='#333333', font=font_large)
        y += 60

    # Draw snippet
    y += 30
    snippet_lines = _wrap_text(draw, snippet, font_small, max_text_width)
    max_snippet_lines = min(4, max(1, (height - y - 80) // 38))
    if len(snippet_lines) > max_snippet_lines:
        snippet_lines = snippet_lines[:max_snippet_lines]
        snippet_lines[-1] = snippet_lines[-1].rstrip() + '...'

    for line in snippet_lines:
        draw.text((margin_x, y), line, fill='#888888', font=font_small)
        y += 38

    buffer = io.BytesIO()
    img.save(buffer, format='PNG', optimize=True)
    return buffer.getvalue()


def _wrap_text(draw, text, font, max_width):
    words = text.split()
    lines = []
    current_line = ''
    for word in words:
        test_line = f'{current_line} {word}'.strip()
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines or ['']


def favicon(request):
    blog = resolve_address(request)

    if blog and 'https://' in blog.favicon:
        return redirect(blog.favicon)

    if '.ico' in request.path:
        return redirect('/static/favicon.ico', permanent=True)
    return redirect('/static/logo.png', permanent=True)