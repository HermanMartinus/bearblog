from django.contrib.auth import login, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.edit import DeleteView
from django.utils import timezone
from markdown import markdown
import tldextract

from .forms import BlogForm, PostForm
from .models import Blog, Post
from .helpers import *

def home(request):
    http_host = request.META['HTTP_HOST']

    if http_host == 'bearblog.dev' or http_host == 'localhost:8000':
        return render(request, 'landing.html')
    elif 'bearblog.dev' in http_host or 'localhost:8000' in http_host:
        extracted = tldextract.extract(http_host)
        blog = get_object_or_404(Blog, subdomain=extracted.subdomain)
        root = get_root(extracted, blog.subdomain)
    else:
        blog = get_object_or_404(Blog, domain=http_host)
        root = http_host

    all_posts = Post.objects.filter(blog=blog, publish=True).order_by('-published_date')
    nav = all_posts.filter(is_page=True)
    posts = all_posts.filter(is_page=False)
    content = markdown(blog.content)

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
        blog = get_object_or_404(Blog, subdomain=extracted.subdomain)
        root = get_root(extracted, blog.subdomain)
    else:
        blog = get_object_or_404(Blog, domain=http_host)
        root = http_host

    all_posts = Post.objects.filter(blog=blog, publish=True).order_by('-published_date')
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
        blog = get_object_or_404(Blog, subdomain=extracted.subdomain)
        root = get_root(extracted, blog.subdomain)
    else:
        blog = get_object_or_404(Blog, domain=http_host)
        root = http_host

    all_posts = Post.objects.filter(blog=blog, publish=True).order_by('-published_date')
    nav = all_posts.filter(is_page=True)
    post = get_object_or_404(all_posts, slug=slug)
    content = markdown(post.content)

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


@login_required
def dashboard(request):
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    
    try:
        blog = Blog.objects.get(user=request.user)
        if extracted.subdomain and extracted.subdomain != blog.subdomain:
            return redirect("{}/dashboard".format(get_root(extracted, blog.subdomain)))

        message = ''
        old_subdomain = blog.subdomain
        old_domain = blog.domain
        if request.method == "POST":
            form = BlogForm(request.POST, instance=blog)
            if form.is_valid():
                blog_info = form.save(commit=False)
                
                if blog_info.domain != old_domain:
                    delete_domain(old_domain)
                    if blog_info.domain:
                        add_new_domain(blog_info.domain)
                        message = f'Set the CNAME record for {blog_info.domain} to point at bearblog.dev'
                if blog_info.subdomain != old_subdomain:
                    blog_info.subdomain_id = update_dns_record(blog.subdomain_id, blog_info.subdomain)
                    message = 'It may take ~5 minutes to activate your new subdomain'
                
                blog_info.save()
        else:
            form = BlogForm(instance=blog)

        return render(request, 'dashboard/dashboard.html', {
            'form': form,
            'blog': blog,
            'root': get_root(extracted, blog.subdomain),
            'message': message
        })

    except Blog.DoesNotExist:
        if request.method == "POST":
            form = BlogForm(request.POST)
            if form.is_valid():
                blog = form.save(commit=False)
                blog.user = request.user
                blog.created_date = timezone.now()
                blog.subdomain_id = create_dns_record(blog.subdomain)
                if blog.domain:
                    add_new_domain(blog.domain)
                blog.save()
                
                return render(request, 'dashboard/dashboard.html', {
                    'form': form,
                    'blog': blog,
                    'root': get_root(extracted, blog.subdomain),
                    'message': 'It may take ~5 minutes to activate your new subdomain'
                })
            return render(request, 'dashboard/dashboard.html', {'form': form})
            
        else:
            form = BlogForm()
            return render(request, 'dashboard/dashboard.html', {'form': form})

@login_required
def posts_edit(request):
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    blog = get_object_or_404(Blog, user=request.user)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return redirect("{}/dashboard/posts".format(get_root(extracted, blog.subdomain)))

    posts = Post.objects.filter(blog=blog).order_by('-published_date')

    return render(request, 'dashboard/posts.html', {'posts': posts, 'blog': blog})

@login_required
def post_new(request):
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    blog = get_object_or_404(Blog, user=request.user)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return redirect("{}/dashboard/posts/new".format(get_root(extracted, blog.subdomain)))

    message = ''
    if request.method == "POST":
        form = PostForm(request.user, request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.blog = blog
            post.published_date = timezone.now()
            post.save()
            return redirect(f"/dashboard/posts/{post.id}/")
    else:
        form = PostForm(request.user)
    return render(request, 'dashboard/post_edit.html', {'form': form, 'blog': blog, 'message': message})

@login_required
def post_edit(request, pk):
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    blog = get_object_or_404(Blog, user=request.user)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return redirect("{}/dashboard/posts".format(get_root(extracted, blog.subdomain)))

    post = get_object_or_404(Post, pk=pk)
    message = ''
    if request.method == "POST":
        form = PostForm(request.user, request.POST, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.blog = blog
            post.published_date = timezone.now()
            post.save()
            message = 'Saved'
    else:
        form = PostForm(request.user, instance=post)
    
    return render(request, 'dashboard/post_edit.html', {
        'form': form,
        'blog': blog,
        'post': post,
        'root': get_root(extracted, blog.subdomain),
        'message': message
    })

class PostDelete(DeleteView):
    model = Post
    success_url = '/dashboard/posts'

def not_found(request, *args, **kwargs):
    return render(request,'404.html', status=404)