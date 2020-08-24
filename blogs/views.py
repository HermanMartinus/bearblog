from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.sites.models import Site
from django.utils import timezone
from django.http import Http404
from django.http import HttpResponse
from django.db.models import Count, ExpressionWrapper, F, FloatField
from blogs.models import Upvote, Blog, Post
from django.db.models.functions import Now


from blogs.helpers import get_nav, get_post, get_posts, unmark, root as get_root

from pg_utils import Seconds
from feedgen.feed import FeedGenerator
from ipaddr import client_ip
from taggit.models import Tag

import tldextract
import json


def resolve_address(request):
    http_host = request.META['HTTP_HOST']
    sites = Site.objects.all()
    if any(http_host == site.domain for site in sites):
        # Homepage
        return False
    elif any(site.domain in http_host for site in sites):
        # Subdomained blog
        blog = get_object_or_404(Blog, subdomain=tldextract.extract(http_host).subdomain)
        return {
            'blog': blog,
            'root': get_root(blog.subdomain)
        }
    else:
        # Custom domain blog
        return {
            'blog': get_object_or_404(Blog, domain=http_host),
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
    for post in all_posts:
        tags += post.tags.most_common()[:10]

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
        upvoted_pose = get_object_or_404(Post, blog=blog, slug=slug)
        posts_upvote_dupe = upvoted_pose.upvote_set.filter(ip_address=ip_address)

        if len(posts_upvote_dupe) == 0:
            upvote = Upvote(post=upvoted_pose, ip_address=ip_address)
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


def feed(request):
    address_info = resolve_address(request)
    if not address_info:
        return redirect('/')

    blog = address_info['blog']
    root = address_info['root']

    all_posts = blog.post_set.filter(publish=True, is_page=False).order_by('-published_date')

    fg = FeedGenerator()
    fg.id(f'http://{root}/')
    fg.author({'name': blog.subdomain, 'email': blog.user.email})
    fg.title(blog.title)
    if blog.content:
        fg.subtitle(unmark(blog.content)[:160])
    else:
        fg.subtitle(blog.title)
    fg.link(href=f"http://{root}/", rel='alternate')

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"http://{root}/{post.slug}/")
        fe.title(post.title)
        fe.author({'name': blog.subdomain, 'email': blog.user.email})
        fe.link(href=f"http://{root}/{post.slug}/")
        fe.content(unmark(post.content))
        fe.updated(post.published_date)

    if request.GET.get('type') == 'rss':
        fg.link(href=f"http://{root}/feed/?type=rss", rel='self')
        rssfeed = fg.rss_str(pretty=True)
        return HttpResponse(rssfeed, content_type='application/rss+xml')
    else:
        fg.link(href=f"http://{root}/feed/", rel='self')
        atomfeed = fg.atom_str(pretty=True)
        return HttpResponse(atomfeed, content_type='application/atom+xml')


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)


def discover(request):
    http_host = request.META['HTTP_HOST']

    get_object_or_404(Site, domain=http_host)

    ip_address = client_ip(request)

    if request.method == "POST":
        pk = request.POST.get("pk", "")
        post = get_object_or_404(Post, pk=pk)
        posts_upvote_dupe = post.upvote_set.filter(ip_address=ip_address)
        if len(posts_upvote_dupe) == 0:
            upvote = Upvote(post=post, ip_address=ip_address)
            upvote.save()

    posts_per_page = 20
    page = 0
    gravity = 1.2
    if request.GET.get('page'):
        page = int(request.GET.get('page'))

    posts_from = page * posts_per_page
    posts_to = (page * posts_per_page) + posts_per_page

    newest = request.GET.get('newest')
    if newest:
        posts = Post.objects.annotate(
            upvote_count=Count('upvote'),
        ).filter(publish=True, show_in_feed=True, published_date__lte=timezone.now()
                 ).order_by('-published_date'
                            ).select_related('blog')[posts_from:posts_to]
    else:
        posts = Post.objects.annotate(
            upvote_count=Count('upvote'),
            score=ExpressionWrapper(
                ((Count('upvote')-1) / ((Seconds(Now() - F('published_date')))+4)**gravity)*100000,
                output_field=FloatField()
            ),
        ).filter(publish=True, show_in_feed=True, published_date__lte=timezone.now()
                 ).order_by('-score', '-published_date'
                            ).select_related('blog').prefetch_related('upvote_set')[posts_from:posts_to]

    upvoted_posts = []
    for post in posts:
        for upvote in post.upvote_set.all():
            if upvote.ip_address == ip_address:
                upvoted_posts.append(post.pk)

    return render(request, 'discover.html', {
        'site': Site.objects.get_current(),
        'posts': posts,
        'next_page': page+1,
        'posts_from': posts_from,
        'gravity': gravity,
        'newest': newest,
        'upvoted_posts': upvoted_posts
    })
