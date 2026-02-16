from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist

from blogs.models import Blog, Post, Upvote
from blogs.helpers import salt_and_hash, unmark
from blogs.views.analytics import render_analytics

import os
import tldextract
import json
import base64

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
        return HttpResponse('Invalid domain', status=422)
    
    try:
        if get_domain_id(domain):
            # print('Ping! Found correct blog. Issuing certificate for', domain)
            return HttpResponse('Ping', status=200)
    except:
        pass

    # print("Ping! Invalid domain", domain)
    return HttpResponse('Invalid domain', status=422)


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
            'meta_description': meta_description
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
    
    if tags:
        # Filter posts that contain ALL specified tags
        posts = [post for post in posts if all(tag in post.tags for tag in tags)]
        available_tags = set()
        for post in posts:
            available_tags.update(post.tags)
    else:
        available_tags = set(blog.tags)
    
    # Prepare tags for JavaScript rendering
    # Only include tags that aren't already active and are available
    tags_to_show = [tag for tag in blog.tags if tag not in tags and tag in available_tags]
    tags_json = base64.b64encode(json.dumps(tags_to_show).encode()).decode()
    active_tags_str = ','.join(tags) if tags else ''
    
    meta_description = blog.meta_description or unmark(blog.content)[:157] + '...'
    blog_path_title = blog.blog_path.replace('-', ' ').capitalize() or 'Blog'
    
    response = render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': posts,
            'meta_description': meta_description,
            'query': tag_param,
            'active_tags': tags,
            'available_tags': available_tags,
            'blog_path_title': blog_path_title,
            'tags_json': tags_json,
            'active_tags_str': active_tags_str,
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
        'meta_image': post.meta_image or blog.meta_image,
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

        response = HttpResponse(f'Upvoted {post.title}')
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response

    return HttpResponse('Forbidden', 403)


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


def favicon(request):
    blog = resolve_address(request)

    if blog and 'https://' in blog.favicon:
        return redirect(blog.favicon)

    if '.ico' in request.path:
        return redirect('/static/favicon.ico', permanent=True)
    return redirect('/static/logo.png', permanent=True)