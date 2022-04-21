
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.edit import DeleteView
from django.utils import timezone
from django.db.models import Count
from django.contrib.auth import get_user_model
from django.utils.text import slugify

import json
import requests
import os
import boto3
import tldextract
from ipaddr import client_ip
from datetime import datetime
import time

from blogs.forms import BlogForm, DomainForm, NavForm, PostForm, StyleForm
from blogs.models import Blog, Post, Upvote, Image


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
            return redirect(f"{blog.useful_domain()}/dashboard")

        if request.method == "POST":
            form = BlogForm(request.POST, instance=blog)
            if form.is_valid():
                blog_info = form.save(commit=False)
                blog_info.save()
        else:
            form = BlogForm(instance=blog)

    except Blog.DoesNotExist:
        blog = Blog(
            user=request.user,
            title=f"{request.user.username}'s blog",
            subdomain=slugify(f"{request.user.username}-new"),
            created_date=timezone.now()
        )
        blog.save()
        form = BlogForm(instance=blog)

    return render(request, 'dashboard/dashboard.html', {
        'form': form,
        'blog': blog,
        'root': blog.useful_domain()
    })


@login_required
def nav(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    if request.method == "POST":
        form = NavForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
        else:
            form = NavForm(instance=blog)
    else:
        form = NavForm(instance=blog)

    return render(request, 'dashboard/nav.html', {
        'form': form,
        'blog': blog,
        'root': blog.useful_domain()
    })


@login_required
def styles(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    if request.method == "POST":
        form = StyleForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        form = StyleForm(instance=blog)

    return render(request, 'dashboard/styles.html', {
        'blog': blog,
        'form': form,
        'root': blog.useful_domain(),
    })


@login_required
def posts_edit(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

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
        return redirect(f"{blog.useful_domain()}/dashboard")

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
        return redirect(f"{blog.useful_domain()}/dashboard")

    post = get_object_or_404(Post, blog=blog, pk=pk)
    published_date_old = post.published_date
    if request.method == "POST":
        form = PostForm(request.user, request.POST, instance=post)
        if form.is_valid():
            post_new = form.save(commit=False)
            post_new.blog = blog
            # This prevents the resetting of time to 00:00 if same day edit
            if (published_date_old and
                post_new.published_date and
                    published_date_old.date() == post_new.published_date.date()):
                post_new.published_date = published_date_old
            if not post_new.published_date:
                post_new.published_date = timezone.now()
            post_new.save()
            form.save_m2m()
    else:
        form = PostForm(request.user, instance=post)

    return render(request, 'dashboard/post_edit.html', {
        'form': form,
        'blog': blog,
        'post': post,
        'root': blog.useful_domain(),
    })


@csrf_exempt
def upload_image(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.method == "POST":
        extention = request.FILES.getlist('file')[0].name.split('.')[-1]
        if extention.lower().endswith(('png', 'jpg', 'jpeg', 'tiff', 'bmp', 'gif')):
            filepath = blog.subdomain + '-' + str(time.time()).split('.')[0] + '.' + extention

            session = boto3.session.Session()
            client = session.client(
                's3',
                endpoint_url='https://sfo2.digitaloceanspaces.com',
                region_name='sfo2',
                aws_access_key_id='KKKRU7JXRF6ZOLEGJPPX',
                aws_secret_access_key=os.getenv('SPACES_SECRET'))

            response = client.put_object(
                Bucket='bear-images',
                Key=filepath,
                Body=request.FILES.getlist('file')[0],
                ACL='public-read',
                )

            return HttpResponse('https://bear-images.sfo2.cdn.digitaloceanspaces.com/'+filepath, 200)


@login_required
def images(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    image_url = None

    if request.method == "POST":
        url = "https://api.cloudflare.com/client/v4/accounts/d8b6eb36804dc8209919ad7451605f7e/images/v1"
        headers = {
            "Authorization": "Bearer suJv_Lk52Ho_ozVjtKXn5hq5GvTs3wq1iNckCEPk"
        }
        payload = {
            'file': (f'bear-{blog.subdomain}-{datetime.strftime(timezone.now(), "%Y-%m-%d")}', request.FILES.get('image').read())
        }
        response = requests.post(url, files=payload, headers=headers)
        json_result = json.loads(response.text)["result"]
        for variant in json_result["variants"]:
            if "optimised" in variant:
                optimised_url = variant
            elif "icon" in variant:
                icon_url = variant
            elif "public" in variant:
                large_url = variant
        image = Image(
            blog=blog,
            title=request.POST.get('title', ''),
            optimised_url=optimised_url,
            icon_url=icon_url,
            large_url=large_url
        )
        image.save()

    return render(request, 'dashboard/media.html', {
        'blog': blog,
        'root': blog.useful_domain(),
        'images': blog.image_set.all()
    })


class ImageDelete(DeleteView):
    model = Image
    success_url = '/dashboard/images'


@login_required
def domain_edit(request):
    blog = Blog.objects.get(user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

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
        'root': blog.useful_domain(),
    })


@login_required
def account(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    return render(request, "dashboard/account.html", {"blog": blog})


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
