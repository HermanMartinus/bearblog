from django.shortcuts import get_object_or_404, redirect, render
from markdown import markdown
import tldextract
from django.http import Http404
from feedgen.feed import FeedGenerator
from ipaddr import client_ip

from .helpers import unmark, get_base_root, get_root, is_protected
from blogs.helpers import get_nav, get_post, get_posts
from django.http import HttpResponse
from django.db.models import Count, F
from blogs.models import Upvote, Blog, Post
from django.db.models.functions import Now
from pg_utils import Seconds


def home(request):
    http_host = request.META['HTTP_HOST']

    if http_host == 'bearblog.dev' or http_host == 'localhost:8000':
        return render(request, 'landing.html')
    elif 'bearblog.dev' in http_host or 'localhost:8000' in http_host:
        extracted = tldextract.extract(http_host)
        if is_protected(extracted.subdomain):
            return redirect(get_base_root(extracted))

        blog = get_object_or_404(Blog, subdomain=extracted.subdomain)
        root = get_root(extracted, blog.subdomain)
    else:
        blog = get_object_or_404(Blog, domain=http_host)
        root = http_host

    all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    content = markdown(blog.content, extensions=['fenced_code'])

    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'content': content,
            'posts': get_posts(all_posts),
            'nav': get_nav(all_posts),
            'root': root,
            'meta_description': unmark(blog.content)[:160]
        })


def posts(request):
    http_host = request.META['HTTP_HOST']

    if http_host == 'bearblog.dev' or http_host == 'localhost:8000':
        return redirect('/')
    elif 'bearblog.dev' in http_host or 'localhost:8000' in http_host:
        extracted = tldextract.extract(http_host)
        if is_protected(extracted.subdomain):
            return redirect(get_base_root(extracted))

        blog = get_object_or_404(Blog, subdomain=extracted.subdomain)
        root = get_root(extracted, blog.subdomain)
    else:
        blog = get_object_or_404(Blog, domain=http_host)
        root = http_host

    all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': get_posts(all_posts),
            'nav': get_nav(all_posts),
            'root': root,
            'meta_description':  unmark(blog.content)[:160]
        }
    )


def post(request, slug):
    http_host = request.META['HTTP_HOST']

    if http_host == 'bearblog.dev' or http_host == 'localhost:8000':
        return redirect('/')
    elif 'bearblog.dev' in http_host or 'localhost:8000' in http_host:
        extracted = tldextract.extract(http_host)
        if is_protected(extracted.subdomain):
            return redirect(get_base_root(extracted))

        blog = get_object_or_404(Blog, subdomain=extracted.subdomain)
        root = get_root(extracted, blog.subdomain)
    else:
        blog = get_object_or_404(Blog, domain=http_host)
        root = http_host

    if request.GET.get('preview'):
        all_posts = blog.post_set.all().order_by('-published_date')
    else:
        all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

    post = get_post(all_posts, slug)

    content = markdown(post.content, extensions=['fenced_code'])

    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': content,
            'post': post,
            'nav': get_nav(all_posts),
            'root': root,
            'meta_description': unmark(post.content)[:160]
        }
    )


def feed(request):
    http_host = request.META['HTTP_HOST']

    if http_host == 'bearblog.dev' or http_host == 'localhost:8000':
        return redirect('/')
    elif 'bearblog.dev' in http_host or 'localhost:8000' in http_host:
        extracted = tldextract.extract(http_host)
        if is_protected(extracted.subdomain):
            return redirect(get_base_root(extracted))

        blog = get_object_or_404(Blog, subdomain=extracted.subdomain)
        root = get_root(extracted, blog.subdomain)
    else:
        blog = get_object_or_404(Blog, domain=http_host)
        root = http_host

    all_posts = blog.post_set.filter(publish=True, is_page=False).order_by('-published_date')

    fg = FeedGenerator()
    fg.id(f'{root}/')
    fg.author({'name': blog.subdomain, 'email': 'hidden'})
    fg.title(blog.title)
    fg.subtitle(unmark(blog.content)[:160])
    fg.link(href=f"{root}/feed/", rel='self')
    fg.link(href=root, rel='alternate')

    for post in all_posts:
        fe = fg.add_entry()
        fe.id(f"{root}/{post.slug}")
        fe.title(post.title)
        fe.author({'name': blog.subdomain, 'email': 'hidden'})
        fe.link(href=f"{root}/feed")
        fe.content(unmark(post.content))

    atomfeed = fg.atom_str(pretty=True)
    return HttpResponse(atomfeed, content_type='application/atom+xml')


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)


def discover(request):
    http_host = request.META['HTTP_HOST']

    if not (http_host == 'bearblog.dev' or http_host == 'localhost:8000'):
        raise Http404("No Post matches the given query.")

    if request.method == "POST":
        pk = request.POST.get("pk", "")
        post = get_object_or_404(Post, pk=pk)
        ip_address = client_ip(request)
        posts_upvote_dupe = post.upvote_set.filter(ip_address=ip_address)

        if len(posts_upvote_dupe) == 0:
            upvote = Upvote(post=post, ip_address=ip_address)
            upvote.save()

    posts_per_page = 20
    page = 0
    gravity = 1.8
    if request.GET.get('page'):
        page = int(request.GET.get('page'))
    posts_from = page * posts_per_page
    posts_to = (page * posts_per_page) + posts_per_page

    if request.GET.get('newest'):
        posts = Post.objects.annotate(
            upvote_count=Count('upvote'),
        ).filter(publish=True).order_by('-published_date').select_related('blog')[posts_from:posts_to]
    else:
        posts = Post.objects.annotate(
            upvote_count=Count('upvote'),
            score=ExpressionWrapper(
                ((Count('upvote')) / ((Seconds(Now() - F('published_date')))+2)**gravity)*100000,
                output_field=FloatField()
            )
        ).filter(publish=True).order_by('-score').select_related('blog')[posts_from:posts_to]

    return render(request, 'discover.html', {
        'posts': posts,
        'next_page': page+1,
        'posts_from': posts_from,
        'gravity': gravity})
