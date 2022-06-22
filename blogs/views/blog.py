import json
from django.http import HttpResponse
from django.http.response import Http404
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt
from django.contrib.sites.models import Site
from django.db.models import Count
from django.utils import timezone

from blogs.models import Blog, Post, Upvote
from blogs.helpers import get_blog_with_domain, get_post, get_posts, sanitise_int, unmark

from ipaddr import client_ip
from taggit.models import Tag
import tldextract


def resolve_address(request):
    http_host = request.META['HTTP_HOST']
    if http_host == 'bear-blog.herokuapp.com':
        try:
            http_host = request.META['HTTP_X_FORWARDED_HOST']
        except KeyError:
            print('Bad proxy request')

    sites = Site.objects.all()

    if any(http_host == site.domain for site in sites):
        # Homepage
        return None
    elif any(site.domain in http_host for site in sites):
        # Subdomained blog
        return get_object_or_404(Blog, subdomain=tldextract.extract(http_host).subdomain, blocked=False)
    else:
        # Custom domain blog
        return get_blog_with_domain(http_host)


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
        return render(request, 'landing.html')

    all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    meta_description = blog.meta_description or unmark(blog.content)[:160]

    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'content': blog.content,
            'posts': get_posts(all_posts),
            'root': blog.useful_domain(),
            'meta_description': meta_description
        })


def posts(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    query = request.GET.get('q', '')
    if query:
        try:
            tag = Tag.objects.get(name=query)
            all_posts = blog.post_set.filter(tags=tag, publish=True, published_date__lte=timezone.now()).order_by('-published_date')
        except Tag.DoesNotExist:
            all_posts = []
        blog_posts = all_posts
    else:
        all_posts = blog.post_set.filter(publish=True, published_date__lte=timezone.now()).order_by('-published_date')
        blog_posts = get_posts(all_posts)

    tags = []
    for post in all_posts:
        tags += post.tags.most_common()[:10]
    tags = list(dict.fromkeys(tags))

    meta_description = blog.meta_description or unmark(blog.content)[:160]

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': blog_posts,
            'root': blog.useful_domain(),
            'meta_description':  meta_description,
            'tags': tags,
            'query': query,
        }
    )


@csrf_exempt
def post(request, slug):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    ip_address = client_ip(request)

    if request.method == "POST":
        if request.POST.get("pk", ""):
            # Upvoting
            pk = sanitise_int(request.POST.get("pk", ""), 7)
            post = get_object_or_404(Post, pk=pk)
            posts_upvote_dupe = post.upvote_set.filter(ip_address=ip_address)
            if len(posts_upvote_dupe) == 0:
                upvote = Upvote(post=post, ip_address=ip_address)
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

    meta_description = post.meta_description or unmark(post.content)[:160]

    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': post.content,
            'post': post,
            'root': blog.useful_domain(),
            'full_path': f'{blog.useful_domain()}/{post.slug}',
            'meta_description': meta_description,
            'meta_image': post.meta_image or blog.meta_image,
            'upvoted': upvoted
        }
    )


@csrf_exempt
def lemon_webhook(request):
    data = json.loads(request.body, strict=False)
    print(data)
    try:
        subdomain = str(data['meta']['custom_data']['blog'])
        blog = get_object_or_404(Blog, subdomain=subdomain)
        print('Found subdomain, upgrading blog...')
    except KeyError:
        email = str(data['data']['attributes']['user_email'])
        blog = Blog.objects.get(user__email=email)
        print('Found email address, upgrading blog...')

    blog.reviewed = True
    blog.upgraded = True
    blog.upgraded_date = timezone.now()
    blog.save()

    return HttpResponse(f'Upgraded {blog}')


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)
