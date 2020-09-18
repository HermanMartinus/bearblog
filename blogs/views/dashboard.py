from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.edit import DeleteView
from django.utils import timezone
from django.db.models import Count
from django.contrib.auth import get_user_model

import tldextract
from ipaddr import client_ip

from blogs.forms import BlogForm, PostForm, DomainForm
from blogs.models import Blog, Post, Upvote
from blogs.helpers import root as get_root


def resolve_subdomain(http_host, blog):
    extracted = tldextract.extract(http_host)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return False
    return True


@login_required
def dashboard(request):
    try:
        blog = Blog.objects.get(user=request.user)
        if not resolve_subdomain(request.META['HTTP_HOST'], blog):
            return redirect(f"http://{get_root(blog.subdomain)}/dashboard")

        if request.method == "POST":
            form = BlogForm(request.POST, instance=blog)
            if form.is_valid():
                blog_info = form.save(commit=False)
                blog_info.save()
        else:
            form = BlogForm(instance=blog)

        return render(request, 'dashboard/dashboard.html', {
            'form': form,
            'blog': blog,
            'root': get_root(blog.subdomain)
        })

    except Blog.DoesNotExist:
        if request.method == "POST":
            form = BlogForm(request.POST)
            if form.is_valid():
                blog = form.save(commit=False)
                blog.user = request.user
                blog.created_date = timezone.now()
                blog.save()

                return render(request, 'dashboard/dashboard.html', {
                    'form': form,
                    'blog': blog,
                    'root': get_root(blog.subdomain),
                })
            return render(request, 'dashboard/dashboard.html', {'form': form})

        else:
            form = BlogForm()
            return render(request, 'dashboard/dashboard.html', {'form': form})


@login_required
def posts_edit(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"http://{get_root(blog.subdomain)}/dashboard")

    posts = Post.objects.annotate(
            hit_count=Count('hit')).filter(blog=blog).order_by('-published_date')

    return render(request, 'dashboard/posts.html', {
        'posts': posts,
        'blog': blog
    })


@login_required
def post_new(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"http://{get_root(blog.subdomain)}/dashboard")

    if request.method == "POST":
        form = PostForm(request.user, request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.blog = blog
            if not post.published_date:
                post.published_date = timezone.now()
            post.save()
            form.save_m2m()

            upvote = Upvote(post=post, ip_address=client_ip(request))
            upvote.save()
            return redirect(f"/dashboard/posts/{post.id}/")
    else:
        form = PostForm(request.user)
    return render(request, 'dashboard/post_edit.html', {
        'form': form,
        'blog': blog
    })


@login_required
def post_edit(request, pk):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"http://{get_root(blog.subdomain)}/dashboard")

    post = get_object_or_404(Post, blog=blog, pk=pk)
    if request.method == "POST":
        form = PostForm(request.user, request.POST, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.blog = blog
            if not post.published_date:
                post.published_date = timezone.now()
            post.save()
            form.save_m2m()
    else:
        form = PostForm(request.user, instance=post)

    return render(request, 'dashboard/post_edit.html', {
        'form': form,
        'blog': blog,
        'post': post,
        'root': get_root(blog.subdomain),
    })


@login_required
def domain_edit(request):
    blog = Blog.objects.get(user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"http://{get_root(blog.subdomain)}/dashboard")

    if request.method == "POST":
        form = DomainForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        form = DomainForm(instance=blog)

    return render(request, 'dashboard/domain_edit.html', {
        'form': form,
        'blog': blog,
        'root': get_root(blog.subdomain),
    })


@login_required
def delete_user(request):
    if request.method == "POST":
        user = get_object_or_404(get_user_model(), pk=request.user.pk)
        user.delete()
        return redirect('/')

    return render(request, 'account/account_confirm_delete.html')


class PostDelete(DeleteView):
    model = Post
    success_url = '/dashboard/posts'
