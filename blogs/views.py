from django.shortcuts import get_object_or_404, redirect, render
from markdown import markdown
import tldextract

from .models import Blog, Post
from .helpers import unmark, get_base_root, get_root, is_protected


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

    all_posts = Post.objects.filter(
        blog=blog, publish=True).order_by('-published_date')
    nav = all_posts.filter(is_page=True)
    posts = all_posts.filter(is_page=False)
    content = markdown(blog.content, extensions=['fenced_code'])

    return render(
        request,
        'home.html',
        {
            'blog': blog,
            'content': content,
            'posts': posts,
            'nav': nav,
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

    all_posts = Post.objects.filter(
        blog=blog, publish=True).order_by('-published_date')
    nav = all_posts.filter(is_page=True)
    posts = all_posts.filter(is_page=False)

    return render(
        request,
        'posts.html',
        {
            'blog': blog,
            'posts': posts,
            'nav': nav,
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
        all_posts = Post.objects.filter(
            blog=blog).order_by('-published_date')
    else:
        all_posts = Post.objects.filter(
            blog=blog, publish=True).order_by('-published_date')

    nav = all_posts.filter(is_page=True)
    post = get_object_or_404(all_posts, slug=slug)
    content = markdown(post.content, extensions=['fenced_code'])

    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': content,
            'post': post,
            'nav': nav,
            'root': root,
            'meta_description': unmark(post.content)[:160]
        }
    )


def not_found(request, *args, **kwargs):
    return render(request, '404.html', status=404)
