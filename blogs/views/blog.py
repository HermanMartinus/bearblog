from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.sites.models import Site
from django.http import HttpResponse
from django.db.models import Count

from blogs.models import Blog, Hit, Post, Upvote
from blogs.helpers import get_nav, get_post, get_posts, unmark, root as get_root

from ipaddr import client_ip
from taggit.models import Tag
import tldextract


def resolve_address(request):
    http_host = request.META['HTTP_HOST']
    sites = Site.objects.all()
    if any(http_host == site.domain for site in sites):
        # Homepage
        return False
    elif any(site.domain in http_host for site in sites):
        # Subdomained blog
        blog = get_object_or_404(Blog, subdomain=tldextract.extract(http_host).subdomain, blocked=False)
        return {
            'blog': blog,
            'root': get_root(blog.subdomain)
        }
    else:
        # Custom domain blog
        return {
            'blog': get_object_or_404(Blog, domain=http_host, blocked=False),
            'root': http_host
        }


def home(request):
    address_info = resolve_address(request)
    if not address_info:
        return render(request, 'landing.html')

    blog = address_info['blog']

    all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'content': blog.content,
            'posts': get_posts(all_posts),
            'nav': get_nav(all_posts),
            'root': address_info['root'],
            'meta_description': unmark(blog.content)[:160]
        })


def posts(request):
    address_info = resolve_address(request)
    if not address_info:
        return redirect('/')

    blog = address_info['blog']

    query = request.GET.get('q', '')
    if query:
        try:
            tag = Tag.objects.get(name=query)
            all_posts = blog.post_set.filter(tags=tag, publish=True).order_by('-published_date')
        except Tag.DoesNotExist:
            all_posts = []
    else:
        all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    tags = []
    for post in get_posts(all_posts):
        tags += post.tags.most_common()[:10]
    tags = list(dict.fromkeys(tags))

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': get_posts(all_posts),
            'nav': get_nav(all_posts),
            'root': address_info['root'],
            'meta_description':  unmark(blog.content)[:160],
            'tags': tags,
            'query': query,
        }
    )


def post(request, slug):
    address_info = resolve_address(request)
    if not address_info:
        return redirect('/')

    blog = address_info['blog']

    ip_address = client_ip(request)

    if request.method == "POST":
        upvoted_post = get_object_or_404(Post, blog=blog, slug=slug)
        posts_upvote_dupe = upvoted_post.upvote_set.filter(ip_address=ip_address)

        if len(posts_upvote_dupe) == 0:
            upvote = Upvote(post=upvoted_post, ip_address=ip_address)
            upvote.save()

    if request.GET.get('preview'):
        all_posts = blog.post_set.annotate(
            upvote_count=Count('upvote')).all().order_by('-published_date')
    else:
        all_posts = blog.post_set.annotate(
            upvote_count=Count('upvote')).filter(publish=True).order_by('-published_date')

    post = get_post(all_posts, slug)

    upvoted = False
    for upvote in post.upvote_set.all():
        if upvote.ip_address == ip_address:
            upvoted = True

    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': post.content,
            'post': post,
            'nav': get_nav(all_posts),
            'root': address_info['root'],
            'meta_description': unmark(post.content)[:160],
            'upvoted': upvoted
        }
    )


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)
