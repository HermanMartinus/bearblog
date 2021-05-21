from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.sites.models import Site
from django.db.models import Count

from blogs.models import Blog, Post, Upvote
from blogs.helpers import add_email_address, get_nav, get_post, get_posts, unmark

from ipaddr import client_ip
from taggit.models import Tag
import tldextract


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

    meta_description = blog.meta_description or unmark(blog.content)[:160]

    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'content': blog.content,
            'posts': get_posts(all_posts),
            'nav': get_nav(all_posts),
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

    meta_description = blog.meta_description or unmark(blog.content)[:160]

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': blog_posts,
            'nav': get_nav(all_posts),
            'root': blog.useful_domain(),
            'meta_description':  meta_description,
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

    meta_description = post.meta_description or unmark(post.content)[:160]

    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': post.content,
            'post': post,
            'nav': get_nav(all_posts),
            'root': blog.useful_domain(),
            'meta_description': meta_description,
            'upvoted': upvoted
        }
    )


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)


@staff_member_required
def review_flow(request):
    unreviewed_blogs = Blog.objects.filter(reviewed=False, blocked=False).order_by('created_date')

    if unreviewed_blogs:
        blog = unreviewed_blogs[0]
        all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

        return render(
            request,
            'review_flow.html',
            {
                'blog': blog,
                'content': blog.content or "~nothing here~",
                'posts': all_posts,
                'root': blog.useful_domain(),
                'still_to_go': len(unreviewed_blogs)
            })
    else:
        return HttpResponse("No blogs left to review! \ʕ•ᴥ•ʔ/")


@staff_member_required
def approve(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.reviewed = True
    blog.save()
    add_email_address(blog.user.email)
    return redirect('review_flow')


@staff_member_required
def block(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.blocked = True
    blog.save()
    return redirect('review_flow')
