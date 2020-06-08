from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.edit import DeleteView
from django.utils import timezone
from django.contrib.auth import get_user_model
import tldextract

from .forms import BlogForm, PostForm, DomainForm
from .models import Blog, Post
from .helpers import root as get_root


@login_required
def dashboard(request):
    extracted = tldextract.extract(request.META['HTTP_HOST'])

    try:
        blog = Blog.objects.get(user=request.user)
        if extracted.subdomain and extracted.subdomain != blog.subdomain:
            return redirect(f"{get_root(blog.subdomain)}/dashboard")

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
            'root': get_root(blog.subdomain),
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
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    blog = get_object_or_404(Blog, user=request.user)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return redirect(
            f"{get_root(blog.subdomain)}/dashboard/posts")

    posts = Post.objects.filter(blog=blog).order_by('-published_date')

    return render(request, 'dashboard/posts.html', {
        'posts': posts,
        'blog': blog
    })


@login_required
def post_new(request):
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    blog = get_object_or_404(Blog, user=request.user)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return redirect(
            f"{get_root(blog.subdomain)}/dashboard/posts/new")

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
    return render(request, 'dashboard/post_edit.html', {
        'form': form,
        'blog': blog
    })


@login_required
def post_edit(request, pk):
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    blog = get_object_or_404(Blog, user=request.user)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return redirect(
            f"{get_root(blog.subdomain)}/dashboard/posts")

    post = get_object_or_404(Post, blog=blog, pk=pk)
    if request.method == "POST":
        form = PostForm(request.user, request.POST, instance=post)
        if form.is_valid():
            post = form.save(commit=False)
            post.blog = blog
            post.save()
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
    extracted = tldextract.extract(request.META['HTTP_HOST'])
    blog = Blog.objects.get(user=request.user)

    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return redirect(f"{get_root(blog.subdomain)}/dashboard")

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
