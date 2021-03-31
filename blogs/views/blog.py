from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.sites.models import Site
from django.http import HttpResponse, HttpResponseNotFound
from django.db.models import Count
from django.utils import timezone

from blogs.models import Blog, Hit, Post, Upvote, Subscriber
from blogs.helpers import get_nav, get_post, get_posts, unmark, validate_subscriber_email

from ipaddr import client_ip
from taggit.models import Tag
import tldextract
import hashlib


def resolve_address(request):
    http_host = request.META['HTTP_HOST']
    sites = Site.objects.all()
    if any(http_host == site.domain for site in sites):
        # Homepage
        return None
    elif any(site.domain in http_host for site in sites):
        # Subdomained blog
        return get_object_or_404(Blog, subdomain=tldextract.extract(http_host).subdomain, blocked=False)
    else:
        # Custom domain blog
        return get_object_or_404(Blog, domain=http_host, blocked=False)


def home(request):
    blog = resolve_address(request)
    if not blog:
        return render(request, 'landing.html')

    all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'content': blog.content,
            'posts': get_posts(all_posts),
            'nav': get_nav(all_posts),
            'root': blog.useful_domain(),
            'meta_description': unmark(blog.content)[:160]
        })


def posts(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    query = request.GET.get('q', '')
    if query:
        try:
            tag = Tag.objects.get(name=query)
            all_posts = blog.post_set.filter(tags=tag, publish=True).order_by('-published_date')
        except Tag.DoesNotExist:
            all_posts = []
        blog_posts = all_posts
    else:
        all_posts = blog.post_set.filter(publish=True).order_by('-published_date')
        blog_posts = get_posts(all_posts)

    tags = []
    for post in all_posts:
        tags += post.tags.most_common()[:10]
    tags = list(dict.fromkeys(tags))

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': blog_posts,
            'nav': get_nav(all_posts),
            'root': blog.useful_domain(),
            'meta_description':  unmark(blog.content)[:160],
            'tags': tags,
            'query': query,
        }
    )


def post(request, slug):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    ip_address = client_ip(request)

    if request.method == "POST":
        if request.POST.get("pk", ""):
            # Upvoting
            pk = request.POST.get("pk", "")
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

    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': post.content,
            'post': post,
            'nav': get_nav(all_posts),
            'root': blog.useful_domain(),
            'meta_description': unmark(post.content)[:160],
            'upvoted': upvoted
        }
    )


def subscribe(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    subscribe_message = ""
    if request.method == "POST":
        if request.POST.get("email", "") and not request.POST.get("name", ""):
            email = request.POST.get("email", "")
            subscriber_dupe = Subscriber.objects.filter(blog=blog, email_address=email)
            if not subscriber_dupe:
                validate_subscriber_email(email, blog)
                subscribe_message = "Check your email to confirm your subscription."
            else:
                subscribe_message = "You are already subscribed."

    all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    return render(
        request,
        'subscribe.html',
        {
            'blog': blog,
            'nav': get_nav(all_posts),
            'root': blog.useful_domain(),
            'subscribe_message': subscribe_message
        }
    )


def confirm_subscription(request):
    blog = resolve_address(request)
    if not blog:
        return not_found(request)

    email = request.GET.get("email", "")
    token = hashlib.md5(f'{email} {blog.subdomain} {timezone.now().strftime("%B %Y")}'.encode()).hexdigest()
    if token == request.GET.get("token", ""):
        subscriber_dupe = Subscriber.objects.filter(blog=blog, email_address=email)
        if not subscriber_dupe:
            subscriber = Subscriber(blog=blog, email_address=email)
            subscriber.save()

        return HttpResponse(f"<p>You've been subscribed to <a href='{blog.useful_domain()}'>{blog.title}</a>. ＼ʕ •ᴥ•ʔ／</p>")

    return HttpResponse("Something went wrong. Try subscribing again. ʕノ•ᴥ•ʔノ ︵ ┻━┻")


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)
