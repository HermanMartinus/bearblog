from datetime import timedelta
from random import randint
import re
from django.db.models import Count, Sum, Q
from django.contrib.auth.decorators import login_required
from django.db import DataError, IntegrityError
from django.forms import ValidationError
from django.http import Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify

import tldextract
import pygal

from blogs.helpers import check_connection, sanitise_int, unmark
from blogs.models import Blog, Hit, Post


def resolve_subdomain(http_host, blog):
    extracted = tldextract.extract(http_host)
    if extracted.subdomain and extracted.subdomain != blog.subdomain:
        return False
    return True


@login_required
def studio(request):
    blog = None
    try:
        blog = Blog.objects.get(user=request.user)
        if not resolve_subdomain(request.META['HTTP_HOST'], blog):
            return redirect(f"https://bearblog.dev/dashboard")
    except Blog.DoesNotExist:
        subdomain = request.user.username
        if Blog.objects.filter(subdomain=request.user.username):
            subdomain = request.user.username + '-' + str(randint(0, 9))
        blog = Blog(
            user=request.user,
            title="My blog",
            subdomain=subdomain)
        blog.save()

    error_message = ""
    info_message = ""
    raw_content = request.POST.get('raw_content', '')
    if raw_content:
        try:
            parse_raw_homepage(raw_content, blog)
            blog.save()
        except IntegrityError:
            error_message = "This bear_domain is already taken"
        except IndexError:
            error_message = "One of the header options is invalid"
        except ValueError as error:
            error_message = error
        except DataError as error:
            error_message = error

    if blog.domain and not check_connection(blog):
        info_message = f'''
        The DNS records for <b>{blog.domain}</b> have not been set up.
        <h4>Set the following DNS record</h4>
        <table>
            <tr>
                <th>Type</th>
                <th>Name</th>
                <th>Content</th>
                <th>TTL</th>
            </tr>
            <tr>
                <td>CNAME</td>
                <td><small>{blog.blank_domain()}</small></td>
                <td><small>domain-proxy.bearblog.dev</small></td>
                <td>3600</td>
            </tr>
        </table>
        <p>
            <small>
                <b>If you're using Cloudflare turn off the proxy (the little orange cloud).</b>
                <br>
                It may take some time for the DNS records to propagate.
            </small>
        </p>
        '''

    return render(request, 'studio/studio.html', {
        'blog': blog,
        'error_message': error_message,
        'raw_content': raw_content,
        'info_message': info_message
    })


def parse_raw_homepage(raw_content, blog):
    raw_header = list(filter(None, raw_content.split('___')[0].split('\r\n')))

    # Clear out data
    blog.title = ''
    blog.subdomain = ''
    blog.domain = ''
    blog.meta_description = ''
    blog.meta_image = ''
    blog.meta_tag = ''

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
            blog.title = value
        elif name == 'bear_domain':
            blog.subdomain = slugify(value.split('.')[0])
        elif name == "custom_domain":
            if blog.upgraded:
                if len(Blog.objects.filter(domain=value).exclude(pk=blog.pk)) == 0:
                    blog.domain = value
                else:
                    raise ValueError("This domain is already in use")
            else:
                raise ValueError("Upgrade your blog to add a custom domain")
        elif name == 'favicon':
            if len(value) < 20:
                blog.favicon = value
            else:
                raise ValueError("Favicon is too long")
        elif name == 'meta_description':
            blog.meta_description = value
        elif name == 'meta_image':
            blog.meta_image = value
        elif name == 'lang':
            blog.lang = value
        elif name == 'nav':
            blog.nav = value
        elif name == 'custom_meta_tag':
            if re.search(r'<meta (.*?)/>', value) and "url" not in value and "javascript" not in value and "script" not in value:
                blog.meta_tag = value
            else:
                raise ValueError("Invalid custom_meta_tag")
        else:
            raise ValueError(f"Unrecognised value: {name}")

    if not blog.title:
        blog.title = "My blog"
    if not blog.subdomain:
        blog.slug = slugify(blog.user.username)
    if not blog.favicon:
        blog.favicon = "🐻"

    blog.content = raw_content[raw_content.index('___') + 3:].strip()


@login_required
def post(request, pk=None):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"//bearblog.dev/dashboard")

    if pk is None:
        post = None
        tags = []
    else:
        try:
            post = Post.objects.get(blog=blog, pk=sanitise_int(pk))
            tags = post.tags.all()
        except Post.DoesNotExist:
            post = None
            tags = []

    error_message = ""
    raw_content = request.POST.get("raw_content", "")

    if raw_content:
        if post is None:
            post = Post(blog=blog)

        try:
            tags = parse_raw_post(raw_content, post)
            if len(Post.objects.filter(blog=blog, slug=post.slug).exclude(pk=post.pk)) > 0:
                post.slug = post.slug + '-' + str(randint(0, 9))

            post.publish = request.POST.get("publish", False) == "true"

            post.save()

            # Add tags after saved
            post.tags.clear()
            if tags:
                for tag in tags.split(','):
                    if slugify(tag.strip()) != '':
                        post.tags.add(slugify(tag.strip()))

            return redirect(f"/studio/posts/{post.id}/")
        except ValidationError:
            error_message = "One of the header options is invalid"
        except IndexError:
            error_message = "One of the header options is invalid"
        except ValueError as error:
            error_message = error
        except DataError as error:
            error_message = error

    return render(request, 'studio/post_edit.html', {
        'blog': blog,
        'root': blog.useful_domain(),
        'tags': tags,
        'post': post,
        'error_message': error_message,
        'raw_content': raw_content
    })


def parse_raw_post(raw_content, post):
    raw_header = list(filter(None, raw_content.split('___')[0].split('\r\n')))

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
        elif name == 'link':
            post.slug = slugify(value)
        elif name == 'published_date':
            # Check if previously posted 'now'
            value = value.replace('/', '-')
            if not str(post.published_date).startswith(value):
                try:
                    post.published_date = timezone.datetime.fromisoformat(value)
                except ValueError:
                    raise ValueError('Bad date format. Use YYYY-MM-DD')
        elif name == 'tags':
            tags = value
        elif name == 'make_discoverable':
            if type(value) is bool:
                post.make_discoverable = value
            else:
                raise ValueError('make_discoverable needs to be "true" or "false"')
        elif name == 'is_page':
            if type(value) is bool:
                post.is_page = value
            else:
                raise ValueError('is_page needs to be "true" or "false"')
        elif name == 'canonical_url':
            post.canonical_url = value
        elif name == 'meta_description':
            post.meta_description = value
        elif name == 'meta_image':
            post.meta_image = value
        else:
            raise ValueError(f"Unrecognised value: {name}")

    if not post.title:
        post.title = "New post"
    if not post.slug:
        post.slug = slugify(post.title)
    if not post.published_date:
        post.published_date = timezone.now()

    post.content = raw_content[raw_content.index('___') + 3:].strip()

    return tags


@csrf_exempt
@login_required
def preview(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"https://bearblog.dev/dashboard")

    error_message = ""
    raw_content = request.POST.get("raw_content", "")
    post = Post(blog=blog)

    if raw_content:
        try:
            parse_raw_post(raw_content, post)
        except ValidationError:
            error_message = "One of the header options is invalid"
        except IndexError:
            error_message = "One of the header options is invalid"
        except ValueError as error:
            error_message = error

        root = blog.useful_domain()
        meta_description = post.meta_description or unmark(post.content)
        full_path = f'{root}/{post.slug}'
        canonical_url = full_path
        if post.canonical_url and post.canonical_url.startswith('https://'):
            canonical_url = post.canonical_url
    else:
        raise Http404()

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
            'preview': True,
            'error_message': error_message
        }
    )


@login_required
def analytics(request):
    blog = get_object_or_404(Blog, user=request.user)
    if not resolve_subdomain(request.META['HTTP_HOST'], blog):
        return redirect(f"https://bearblog.dev/dashboard")

    days = 30

    time_threshold = timezone.now() - timedelta(days=days)

    posts = Post.objects.annotate(
            hit_count=Count('hit', filter=Q(hit__created_date__gt=time_threshold))
            ).prefetch_related('hit_set', 'upvote_set').filter(
                blog=blog,
                publish=True,
            ).order_by('-hit_count', '-published_date')

    hits = Hit.objects.filter(post__blog=blog, created_date__gt=time_threshold).order_by('created_date')
    unique_reads = posts.aggregate(Sum('hit_count'))
    unique_visitors = len(hits.values('ip_address').distinct())

    referrers = distinct_count(hits, 'referrer')
    devices = distinct_count(hits, 'device')
    browsers = distinct_count(hits, 'browser')
    countries = distinct_count(hits, 'country')

    end_date = timezone.now()
    delta = timedelta(days=1)
    chart_data = []
    while time_threshold <= end_date:
        day_hit_count = len(hits.filter(created_date__gt=time_threshold, created_date__lt=time_threshold+delta))
        chart_data.append({'date': time_threshold.strftime("%Y-%m-%d"), 'hits': day_hit_count})
        time_threshold += delta

    # print(len(chart_data))

    chart = pygal.Bar(height=300)
    mark_list = [x['hits'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Reads', mark_list)
    chart.x_labels = [x['date'].split('-')[2] for x in chart_data]
    chart_render = chart.render().decode('utf-8')

    return render(request, 'studio/analytics.html', {
        'blog': blog,
        'posts': posts,
        'unique_reads': unique_reads,
        'unique_visitors': unique_visitors,
        'chart': chart_render,
        'referrers': referrers,
        'devices': devices,
        'browsers': browsers,
        'countries': countries
    })


def distinct_count(hits, parameter):
    distinct_list = hits.values(parameter).distinct().order_by()
    for distinct in distinct_list:
        # if distinct[parameter] == '' or distinct[parameter] is None:
        #     del distinct[parameter]
        # else:
        parameter_filter = {}
        parameter_filter[parameter] = distinct[parameter]
        distinct['number'] = len(hits.filter(**parameter_filter))

    distinct_list = [x for x in distinct_list if x[parameter]]
    return list(distinct_list)
