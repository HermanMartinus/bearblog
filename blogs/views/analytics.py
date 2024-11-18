from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import IntegrityError
from datetime import timedelta
from django.db.models.functions import TruncDate

from blogs.forms import AnalyticsForm
from blogs.models import Blog, Hit, Post, RssSubscriber
from blogs.helpers import daterange, get_country, salt_and_hash
from django.db.models import Count, Sum, Q
from django.http import HttpResponse

from ipaddr import client_ip
from urllib.parse import urlparse
import httpagentparser
import pygal
import threading

import pygal
from pygal.style import LightColorizedStyle
import djqscsv


@login_required
def analytics(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if blog.user.settings.upgraded:
        return analytics_upgraded(request, id=id)

    time_threshold = False
    chart_data = []

    days = 7

    time_threshold = timezone.now() - timedelta(days=days)

    posts = Post.objects.annotate(
        hit_count=Count('hit', filter=Q(hit__created_date__gt=time_threshold))).filter(
        blog=blog,
        publish=True,
    ).order_by('-hit_count', '-published_date')

    hits = Hit.objects.filter(post__blog=blog, created_date__gt=time_threshold)

    for single_date in daterange(timezone.now() - timedelta(days=days), timezone.now() + timedelta(days=1)):
        chart_data.append({
            "date": single_date.strftime("%Y-%m-%d"),
            "hits": len(list(filter(lambda hit: hit.created_date.date() == single_date.date(), list(hits))))
        })

    unique_reads = posts.aggregate(Sum('hit_count'))
    unique_visitors = len(hits.values('hash_id').distinct())

    chart = pygal.Bar(height=300, show_legend=False)
    mark_list = [x['hits'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Reads', mark_list)
    chart.x_labels = [x['date'] for x in chart_data]
    chart_render = chart.render().decode('utf-8')

    return render(request, 'dashboard/analytics.html', {
        'unique_reads': unique_reads,
        'unique_visitors': unique_visitors,
        'posts': posts,
        'blog': blog,
        'chart': chart_render
    })


@login_required
def analytics_upgraded(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if not blog.user.settings.upgraded:
        return redirect('analytics', id=blog.subdomain)

    if request.method == "POST":
        if request.POST.get('share') == 'public':
            blog.public_analytics = True
        else:
            blog.public_analytics = False
        blog.save()

    if request.GET.get('export', False):
        hits = Hit.objects.filter(post__blog=blog).order_by('created_date')
        return djqscsv.render_to_csv_response(hits)
    return render_analytics(request, blog)


def render_analytics(request, blog, public=False):
    now = timezone.now()
    post_filter = request.GET.get('post', False)
    referrer_filter = request.GET.get('referrer', False)
    days_filter = int(request.GET.get('days', 7))
    start_date = (now - timedelta(days=days_filter)).date()
    end_date = now.date()

    base_hits = Hit.objects.filter(post__blog=blog, created_date__gt=start_date)

    if post_filter:
        base_hits = base_hits.filter(post__slug=post_filter)
    if referrer_filter:
        base_hits = base_hits.filter(referrer=referrer_filter)

    posts = Post.objects.annotate(
        hit_count=Count('hit', filter=Q(hit__in=base_hits)),
    ).filter(
        blog=blog,
        publish=True,
    ).filter(Q(slug=post_filter) if post_filter else Q()
            ).values('title', 'hit_count', 'upvotes', 'published_date', 'slug').order_by('-hit_count', '-published_date')


    hits = base_hits.order_by('created_date')
    start_date = hits.first().created_date.date() if hits.exists() else start_date

    unique_reads = hits.count()
    unique_visitors = hits.values('hash_id').distinct().count()
    on_site = hits.filter(created_date__gt=now-timedelta(minutes=4)).count()

    referrers = hits.exclude(referrer='').values('referrer').annotate(count=Count('referrer')).order_by('-count').values('referrer', 'count')
    devices = hits.exclude(device='').values('device').annotate(count=Count('device')).order_by('-count').values('device', 'count')
    browsers = hits.exclude(browser='').values('browser').annotate(count=Count('browser')).order_by('-count').values('browser', 'count')
    countries = hits.exclude(country='').values('country').annotate(count=Count('country')).order_by('-count').values('country', 'count')

    # Build chart data

    hit_dict = hits.annotate(
        date=TruncDate('created_date')
    ).values('date').annotate(
        c=Count('date')
    ).order_by('date')

    chart_data = []
    date_range = [start_date + timedelta(days=x) for x in range((end_date - start_date).days + 1)]
    hit_date_count = {hit['date']: hit['c'] for hit in hit_dict}

    for date in date_range:
        date_str = date.strftime('%Y-%m-%d')
        count = hit_date_count.get(date, 0)
        chart_data.append({'date': date_str, 'hits': count})

    # Render chart

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

    # RSS Subscriber count
    rss_subscriber_count = RssSubscriber.objects.filter(blog=blog, access_date__gt=now - timedelta(hours=18)).count()

    return render(request, 'studio/analytics.html', {
        'public': public,
        'blog': blog,
        'posts': posts,
        'start_date': start_date,
        'end_date': end_date,
        'unique_reads': unique_reads,
        'unique_visitors': unique_visitors,
        'on_site': on_site,
        'rss_subscriber_count': rss_subscriber_count,
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


def post_hit(request, uid):
    user_agent = request.META.get('HTTP_USER_AGENT', '')
    if 'bot' in user_agent.lower():
        return HttpResponse("Bot traffic")
    
    try:
        user_agent = httpagentparser.detect(request.META.get('HTTP_USER_AGENT', None))

        # Prevent duplicates with ip hash + date
        hash_id = salt_and_hash(request)

        country = get_country(client_ip(request)).get('country_name', '')
        device = user_agent.get('platform', {}).get('name', '')
        browser = user_agent.get('browser', {}).get('name', '')

        referrer = request.GET.get('ref', '')
        if referrer:
            referrer = urlparse(referrer)
            referrer = '{uri.scheme}://{uri.netloc}/'.format(uri=referrer)
        
        post_pk = Post.objects.filter(uid=uid).values_list('pk', flat=True).first()

        if post_pk:
            hit, create = Hit.objects.get_or_create(
                post_id=post_pk,
                hash_id=hash_id,
                referrer=referrer,
                country=country,
                device=device,
                browser=browser)
            if create:
                print('Hit', hit)

    except Hit.MultipleObjectsReturned:
        print('Duplicate hit')
    except IntegrityError:
        print('Post does not exist')

    return HttpResponse("Logged")