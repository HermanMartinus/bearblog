from django.http import HttpResponse
from django.http.response import Http404
from django.shortcuts import get_object_or_404, render, redirect
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.utils.text import slugify

from blogs.models import Blog, Post, Upvote
from blogs.helpers import salt_and_hash, unmark
from blogs.views.analytics import render_analytics

import os
import tldextract

def resolve_address(request):
    http_host = request.get_host()

    sites = os.getenv('MAIN_SITE_HOSTS').split(',')

    # forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR', '')
    # if forwarded_for:
    #     print('X-Forwarded-For: ', forwarded_for.split(',')[0], 'Full URL: ', request.build_absolute_uri())

    if any(http_host == site for site in sites):
        # Homepage
        return None
    elif any(site in http_host for site in sites):
        # Subdomained blog
        subdomain = tldextract.extract(http_host).subdomain
        
        if request.COOKIES.get('admin_passport') == os.getenv('ADMIN_PASSPORT'):
            return get_object_or_404(Blog.objects.select_related('user').select_related('user__settings'), subdomain__iexact=subdomain)
        else:
            return get_object_or_404(Blog.objects.select_related('user').select_related('user__settings'), subdomain__iexact=subdomain, user__is_active=True)
    else:
        # Custom domain blog
        return get_blog_with_domain(http_host)


def get_blog_with_domain(domain):
    if not domain:
        return False
    try:
        return Blog.objects.get(domain=domain, user__is_active=True)
    except Blog.DoesNotExist:
        # Handle www subdomain if necessary
        if 'www.' in domain:
            return get_object_or_404(Blog, domain__iexact=domain.replace('www.', ''), user__is_active=True)
        else:
            return get_object_or_404(Blog, domain__iexact=f'www.{domain}', user__is_active=True)


@csrf_exempt
def ping(request):
    domain = request.GET.get("domain", None)
    
    try:
        if get_blog_with_domain(domain):
            print('Ping! Found correct blog. Issuing certificate.')
            return HttpResponse('Ping', status=200)
    except:
        pass

    print(f'Ping! Could not find blog with domain {domain}')
    return HttpResponse('Invalid domain', status=422)


def home(request):
    blog = resolve_address(request)
    if not blog:
        return render(request, 'landing.html')

    all_posts = blog.posts.filter(publish=True, published_date__lte=timezone.now(), is_page=False).order_by('-published_date')

    meta_description = blog.meta_description or unmark(blog.content)[:157] + '...'
    
    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'posts': all_posts,
            'meta_description': meta_description
        })


def posts(request, blog):
    if not blog:
        blog = resolve_address(request)
        if not blog:
            return not_found(request)
    
    tag_param = request.GET.get('q', '')
    tags = [t.strip() for t in tag_param.split(',')] if tag_param else []
    tags = [t for t in tags if t]  # Remove empty strings

    posts = blog.posts.filter(blog=blog, publish=True, published_date__lte=timezone.now(), is_page=False).order_by('-published_date')
    if tags:
        # Filter posts that contain ALL specified tags
        posts = [post for post in posts if all(tag in post.tags for tag in tags)]
        
        available_tags = set()
        for post in posts:
            available_tags.update(post.tags)

    else:
        available_tags = set(blog.tags)

    meta_description = blog.meta_description or unmark(blog.content)[:157] + '...'

    blog_path_title = blog.blog_path.replace('-', ' ').capitalize() or 'Blog'

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': posts,
            'meta_description': meta_description,
            'query': tag_param,
            'active_tags': tags,
            'available_tags': available_tags,
            'blog_path_title': blog_path_title
        }
    )


@csrf_exempt
def post(request, slug):
    # Prevent null characters in path
    slug = slug.replace('\x00', '')

    blog = resolve_address(request)
    if not blog:
        return not_found(request)
    
    # Check for a custom RSS feed path
    if slug == blog.rss_alias:
        from blogs.views.feed import feed
        return feed(request)
    
    # Find by post slug
    post = (Post.objects
           .filter(
               blog=blog,
               slug__iexact=slug
           )
           .first())
    
    if not post:
        # Find by post alias
        post = (Post.objects
               .filter(
                   blog=blog,
                   alias__iexact=slug
               )
               .first())
        
        if post:
            return redirect('post', slug=post.slug)
        else:
            # Check for a custom blogreel or /blog path and render the blog page
            if slug == blog.blog_path or slug == 'blog':
                return posts(request, blog)

            return render(request, '404.html', {'blog': blog}, status=404)
    
    # Check if upvoted
    hash_id = salt_and_hash(request, 'year')
    upvoted = post.upvote_set.filter(hash_id=hash_id).exists()

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
        'upvoted': upvoted,
    }

    response = render(request, 'post.html', context)

    if post.publish and not request.GET.get('token'):
        response['CDN-Cache-Control'] = 'public, max-age=1800'  # CDN cache for 30 minutes
        response['Cache-Tag'] = blog.subdomain # Tag for selective purging

    return response


@csrf_exempt
def upvote(request, uid):
    hash_id = salt_and_hash(request, 'year')

    if uid == request.POST.get("uid", "") and not request.POST.get("title", False):
        post = get_object_or_404(Post, uid=uid)
        print("Upvoting", post)
        try:
            upvote, created = Upvote.objects.get_or_create(post=post, hash_id=hash_id)
        
            if created:
                return HttpResponse(f'Upvoted {post.title}')
            raise Http404('Duplicate upvote')
        except Upvote.MultipleObjectsReturned:
            return HttpResponse(f'Upvoted {post.title}')
    raise Http404("Someone's doing something dodgy ʕ •`ᴥ•´ʔ")


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
        posts = blog.posts.filter(publish=True, published_date__lte=timezone.now()).only('slug', 'last_modified').order_by('-published_date')
    except AttributeError:
        posts = []

    return render(request, 'sitemap.xml', {'blog': blog, 'posts': posts}, content_type='text/xml')


def robots(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    return render(request, 'robots.txt',  {'blog': blog}, content_type="text/plain")
