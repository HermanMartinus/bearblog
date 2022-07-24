from email import header
from random import randint
from django.contrib.auth.decorators import login_required
from django.forms import ValidationError
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.views.generic.edit import DeleteView
from django.utils import timezone
from django.db.models import Count
from django.contrib.auth import get_user_model
from django.utils.text import slugify

import json
import os
import boto3
import re
import tldextract
from ipaddr import client_ip
import time
import djqscsv

from blogs.forms import AccountForm, BlogForm, DomainForm, NavForm, PostForm, StyleForm
from blogs.helpers import get_post, sanitise_int, unmark
from blogs.models import Blog, Post, Upvote
from blogs.views.blog import post


def resolve_subdomain(http_host, blog):
    extracted = tldextract.extract(http_host)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return False
    return True


@login_required
def studio(request):
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

    return render(request, 'studio/studio.html', {
        'form': form,
        'blog': blog,
        'root': blog.useful_domain()
    })


@login_required
def post(request, pk=None):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    try:
        post = Post.objects.get(blog=blog, pk=pk)
        tags = post.tags.all()
    except Post.DoesNotExist:
        post = None
        tags = []

    raw_content = request.POST.get("raw_content", "")

    if raw_content:
        if post is None:
            post = Post(blog=blog)

        parse_raw_content(raw_content, post)
        if len(Post.objects.filter(blog=blog, slug=post.slug).exclude(pk=post.pk)) > 0:
            post.slug = post.slug + '-' + str(randint(0, 9))

        post.publish = request.POST.get("publish", False) == "true"

        post.save()

        # Add tags after saved
        post.tags.clear()
        if tags:
            for tag in tags.split(','):
                post.tags.add(slugify(tag.strip()))

        return redirect(f"/studio/posts/{post.id}/")

    return render(request, 'studio/post_edit.html', {
        'blog': blog,
        'root': blog.useful_domain(),
        'tags': tags,
        'post': post
    })


def parse_raw_content(raw_content, post):
    raw_header = list(filter(None, raw_content.split('---')[1].split('\r\n')))

    # Clear out data
    post.slug = ''
    post.canonical_url = ''
    post.meta_description = ''
    post.meta_image = ''
    post.is_page = False
    post.make_discoverable = True
    tags = []

    # Parse and populate header data
    for item in raw_header:
        item = item.split(':', 1)
        name = item[0].strip()
        value = item[1].strip()
        if str(value).lower() == 'true':
            value = True
        if str(value).lower() == 'false':
            value = False

        if name == 'title':
            post.title = value
        if name == 'link':
            post.slug = slugify(value)
        if name == 'published_date':
            # Check if previously posted 'now'
            if not str(post.published_date).startswith(value):
                try:
                    post.published_date = timezone.datetime.fromisoformat(value)
                except ValueError:
                    print('Bad date')
        if name == 'tags':
            tags = value
        if name == 'make_discoverable':
            post.make_discoverable = value
        if name == 'is_page':
            post.is_page = value
        if name == 'canonical_url':
            post.canonical_url = value
        if name == 'meta_description':
            post.meta_description = value
        if name == 'meta_image':
            post.meta_image = value

    if not post.title:
        post.title = "New post"
    if not post.slug:
        post.slug = slugify(post.title)
    if not post.published_date:
        post.published_date = timezone.now()

    post.content = raw_content[raw_content.replace('---', '', 1).index('---') + 8:].strip()


@csrf_exempt
@login_required
def preveiw(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"{blog.useful_domain()}/dashboard")

    raw_content = request.POST.get("raw_content", "")
    post = Post(blog=blog)

    if raw_content:
        parse_raw_content(raw_content, post)

        root = blog.useful_domain()
        meta_description = post.meta_description or unmark(post.content)
        full_path = f'{root}/{post.slug}'
        canonical_url = full_path
        if post.canonical_url and post.canonical_url.startswith('https://'):
            canonical_url = post.canonical_url

    return render(
        request,
        'post.html',
        {
            'blog': blog,
            'content': post.content,
            'post': post,
            'root': blog.useful_domain(),
            'full_path': full_path,
            'canonical_url': canonical_url,
            'meta_description': meta_description,
            'meta_image': post.meta_image or blog.meta_image,
            'preview': True
        }
    )
