from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.db import DataError, IntegrityError
from django.forms import ValidationError
from django.http import Http404
from django.views.decorators.csrf import csrf_exempt
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.text import slugify
from django.core.validators import URLValidator

from datetime import timedelta
from random import randint
import re
import pygal
from pygal.style import LightColorizedStyle
import djqscsv

from blogs.forms import AnalyticsForm, PostTemplateForm
from blogs.helpers import check_connection, sanitise_int, unmark
from blogs.models import Blog, Hit, Post


@login_required
def studio(request):
    blog = None
    try:
        blog = Blog.objects.get(user=request.user)
    except Blog.DoesNotExist:
        subdomain = request.user.username
        if Blog.objects.filter(subdomain=request.user.username):
            subdomain = request.user.username + '-' + str(randint(0, 9))
        blog = Blog(
            user=request.user,
            title="My blog",
            subdomain=slugify(subdomain).replace('_', '-'))
        blog.save()

    error_message = ""
    info_message = ""
    raw_content = request.POST.get('raw_content', '')
    if raw_content:
        try:
            parse_raw_homepage(raw_content, blog)
            blog.last_modified = timezone.now()
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
                <br>
                <a href="https://docs.bearblog.dev/custom-domains/" target="_blank">Having issues?</a>
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
            subdomain = slugify(value.split('.')[0]).replace('_', '-')
            if not subdomain:
                raise ValueError("Please provide a valid bear_domain")
            else:
                blog.subdomain = subdomain
        elif name == "custom_domain":
            if blog.upgraded:
                if Blog.objects.filter(domain=value).exclude(pk=blog.pk).count() == 0:
                    try:
                        validator = URLValidator()
                        validator('http://' + value)
                        blog.domain = value
                    except ValidationError:
                        raise ValueError('This is an invalid custom_domain')   
                else:
                    raise ValueError("This domain is already taken")
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
            if Post.objects.filter(blog=blog, slug=post.slug).exclude(pk=post.pk).count() > 0:
                post.slug = post.slug + '-' + str(randint(0, 9))

            post.publish = request.POST.get("publish", False) == "true"
            post.last_modified = timezone.now()

            post.save()

            # Add tags after saved
            post.tags.clear()
            if tags:
                for tag in tags.split(','):
                    if tag.strip() != '':
                        post.tags.add(tag.strip())

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
    post.alias = ''
    post.class_name = ''
    post.canonical_url = ''
    post.meta_description = ''
    post.meta_image = ''
    post.is_page = False
    post.make_discoverable = True
    post.lang = ''
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
        elif name == 'alias':
            post.alias = value
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
        elif name == 'class_name':
            post.class_name = slugify(value)
        elif name == 'canonical_url':
            post.canonical_url = value
        elif name == 'lang':
            post.lang = value
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
        full_path = f'{root}/{post.slug}/'
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
def post_template(request):
    blog = get_object_or_404(Blog, user=request.user)

    if request.method == "POST":
        form = PostTemplateForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        initial = {'post_template': '''title: Post title
___

# Big header
## Medium header
### Small header

**bold**
*italics*
~~strikethrough~~

This is a [link](http://www.example.com) and this one opens in a [new tab](tab:https://www.example.com).

![Image](https://i.imgur.com/3jxqrKP.jpeg)'''}
        if blog.post_template:
            form = PostTemplateForm(instance=blog)
        else:
            form = PostTemplateForm(instance=blog, initial=initial)

    return render(request, 'studio/post_template_edit.html', {
        'blog': blog,
        'form': form})


@login_required
def analytics(request):
    blog = get_object_or_404(Blog, user=request.user)

    if not blog.upgraded:
        return redirect('/dashboard/analytics/')

    if request.GET.get('share', False):
        if request.GET.get('share') == 'public':
            blog.public_analytics = True
        else:
            blog.public_analytics = False
        blog.save()

    if request.GET.get('export', False):
        hits = Hit.objects.filter(post__blog=blog).order_by('created_date')
        return djqscsv.render_to_csv_response(hits)
    return render_analytics(request, blog)


def render_analytics(request, blog, public=False):
    post_filter = request.GET.get('post', False)
    referrer_filter = request.GET.get('referrer', False)
    days_filter = int(request.GET.get('days', 7))
    delta = timedelta(days=1)
    start_date = (timezone.now() - timedelta(days=days_filter)).date()
    end_date = timezone.now().date()

    if post_filter:
        if referrer_filter:
            posts = Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__gt=start_date, hit__referrer=referrer_filter))
                ).prefetch_related('hit_set', 'upvote_set').filter(
                    blog=blog,
                    pk=post_filter,
                    publish=True,
                ).values('pk', 'title', 'hit_count', 'published_date', 'slug').order_by('-hit_count', '-published_date')
            hits = Hit.objects.filter(
                post__blog=blog,
                post__id=post_filter,
                referrer=referrer_filter,
                created_date__gt=start_date).order_by('created_date')
        else:
            posts = Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__gt=start_date))
                ).prefetch_related('hit_set', 'upvote_set').filter(
                    blog=blog,
                    pk=post_filter,
                    publish=True,
                ).values('pk', 'title', 'hit_count', 'published_date', 'slug').order_by('-hit_count', '-published_date')
            hits = Hit.objects.filter(
                post__blog=blog,
                post__id=post_filter,
                created_date__gt=start_date).order_by('created_date')
    else:
        if referrer_filter:
            posts = Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__gt=start_date, hit__referrer=referrer_filter))
                ).prefetch_related('hit_set', 'upvote_set').filter(
                    blog=blog,
                    publish=True,
                ).values('pk', 'title', 'hit_count', 'published_date', 'slug').order_by('-hit_count', '-published_date')

            hits = Hit.objects.filter(
                post__blog=blog,
                referrer=referrer_filter,
                created_date__gt=start_date).order_by('created_date')
        else:
            posts = Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__gt=start_date))
                ).prefetch_related('hit_set', 'upvote_set').filter(
                    blog=blog,
                    publish=True,
                ).values('pk', 'title', 'hit_count', 'published_date', 'slug').order_by('-hit_count', '-published_date')
            hits = Hit.objects.filter(
                post__blog=blog,
                created_date__gt=start_date).order_by('created_date')

    if hits.count() > 0:
        start_date = hits[0].created_date.date()

    unique_reads = hits.count()
    unique_visitors = hits.values('ip_address').distinct().order_by().count()

    on_site = hits.filter(created_date__gt=timezone.now()-timedelta(minutes=4)).count()

    referrers = distinct_count(hits, 'referrer')
    devices = distinct_count(hits, 'device')
    browsers = distinct_count(hits, 'browser')
    countries = distinct_count(hits, 'country')

    chart_data = []
    date_iterator = start_date

    hits_count = hits.annotate(date=TruncDate('created_date')).values('date').annotate(c=Count('date')).order_by()

    # create dates dict with zero hits
    hit_dict = {}
    while date_iterator <= end_date:
        hit_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += delta

    # populate dict with hits count
    for hit in hits_count:
        hit_dict[hit['date'].strftime("%Y-%m-%d")] = hit['c']

    # generate chart
    for date, count in hit_dict.items():
        chart_data.append({'date': date, 'hits': count})

    chart = pygal.Bar(height=300, show_legend=False, style=LightColorizedStyle)
    chart.force_uri_protocol = 'http'
    mark_list = [x['hits'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Reads', mark_list)
    chart.x_labels = [x['date'].split('-')[2] for x in chart_data]
    chart_render = chart.render_data_uri()

    if request.method == "POST":
        form = AnalyticsForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        form = AnalyticsForm(instance=blog)

    return render(request, 'studio/analytics.html', {
        'public': public,
        'blog': blog,
        'posts': posts,
        'start_date': start_date,
        'end_date': end_date,
        'unique_reads': unique_reads,
        'unique_visitors': unique_visitors,
        'on_site': on_site,
        'chart': chart_render,
        'referrers': referrers,
        'devices': devices,
        'browsers': browsers,
        'countries': countries,
        'days_filter': days_filter,
        'post_filter': post_filter,
        'referrer_filter': referrer_filter,
        'form': form
    })


def distinct_count(hits, parameter):
    distinct_list = hits.values(parameter).distinct().order_by()
    for distinct in distinct_list:
        parameter_filter = {}
        parameter_filter[parameter] = distinct[parameter]
        distinct['number'] = hits.filter(**parameter_filter).count()

    distinct_list = [x for x in distinct_list if x[parameter]]
    return sorted(distinct_list, key=lambda item: item['number'], reverse=True)
