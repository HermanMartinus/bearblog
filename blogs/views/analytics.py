from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone

from django.http import HttpResponse
from django.db import IntegrityError, connection
from django.db.models import DateField, Count, Sum, Q
from django.db.models.functions import Cast

from blogs.models import Blog, Hit, Post
from blogs.helpers import daterange, get_country, salt_and_hash

from datetime import timedelta
from ipaddr import client_ip
from urllib.parse import urlparse
import httpagentparser
import pygal

import pygal
import djqscsv


def get_int(value, default):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


@login_required
def analytics(request, id):
    if request.user.is_superuser:
        blog = get_object_or_404(Blog, subdomain=id)
    else:
        blog = get_object_or_404(Blog, user=request.user, subdomain=id)

    if request.GET.get('export', False):
        hits = Hit.objects.filter(post__blog=blog).order_by('created_date')
        return djqscsv.render_to_csv_response(hits)

    return render_analytics(request, blog)


def render_analytics(request, blog, public=False):
    now = timezone.now()
    post_filter = request.GET.get('post', False)
    referrer_filter = request.GET.get('referrer', False)
    days_filter = get_int(request.GET.get('days', 7), 7)
    start_date = (now - timedelta(days=days_filter)).date()
    end_date = now.date()

    base_hits = Hit.objects.filter(blog=blog, created_date__gt=start_date)

    if post_filter:
        if post_filter == 'homepage':
            base_hits = base_hits.filter(post__isnull=True)
        else:
            base_hits = base_hits.filter(post__slug=post_filter)
    if referrer_filter:
        base_hits = base_hits.filter(referrer=referrer_filter)

    hits = base_hits.order_by('created_date')
    start_date = hits.first().created_date.date() if hits.exists() else start_date

    unique_reads = base_hits.count()
    unique_visitors = base_hits.values('hash_id').distinct().count()
    on_site = hits.filter(created_date__gt=now-timedelta(minutes=4)).count()

    # Build chart data
    hit_dict = hits.annotate(
        date=Cast('created_date', output_field=DateField())
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

    posts = get_posts(blog.id, start_date, post_filter, referrer_filter)

    referrers = base_hits.exclude(referrer='').values('referrer').annotate(count=Count('referrer')).order_by('-count').values('referrer', 'count')
    devices = base_hits.exclude(device='').values('device').annotate(count=Count('device')).order_by('-count').values('device', 'count')
    browsers = base_hits.exclude(browser='').values('browser').annotate(count=Count('browser')).order_by('-count').values('browser', 'count')
    countries = base_hits.exclude(country='').values('country').annotate(count=Count('country')).order_by('-count').values('country', 'count')

    return render(request, 'studio/analytics.html', {
        'public': public,
        'blog': blog,
        'posts': posts,
        'start_date': start_date,
        'end_date': end_date,
        'unique_reads': unique_reads,
        'unique_visitors': unique_visitors,
        'on_site': on_site,
        'chart_data': chart_data,
        'referrers': referrers,
        'devices': devices,
        'browsers': browsers,
        'countries': countries,
        'days_filter': days_filter,
        'post_filter': post_filter,
        'referrer_filter': referrer_filter,
    })


def get_posts(blog_id, start_date, post_filter=None, referrer_filter=None):
    with connection.cursor() as cursor:
        # Get homepage hits
        cursor.execute("""
            SELECT 'Home' as title,
                   0 as upvotes,
                   NULL as published_date,
                   'homepage' as slug,
                   (SELECT COUNT(h.id)
                    FROM blogs_hit h
                    WHERE h.blog_id = %s
                    AND h.post_id IS NULL
                    AND h.created_date > %s
                    AND (h.referrer = %s OR %s IS NULL)) AS hit_count
            WHERE (%s = 'homepage' OR %s IS NULL)
            
            UNION ALL
            
            SELECT p.title,
                   p.upvotes,
                   p.published_date,
                   p.slug,
                   (SELECT COUNT(h.id)
                    FROM blogs_hit h
                    WHERE h.blog_id = %s
                    AND h.post_id = p.id
                    AND h.created_date > %s
                    AND (h.referrer = %s OR %s IS NULL)) AS hit_count
            FROM blogs_post p
            WHERE p.blog_id = %s
            AND p.publish
            AND (p.slug = %s OR %s IS NULL)
            ORDER BY hit_count DESC, published_date DESC
        """, [
            blog_id, start_date, referrer_filter or None, referrer_filter or None,
            post_filter or None, post_filter or None,
            blog_id, start_date, referrer_filter or None, referrer_filter or None,
            blog_id, post_filter or None, post_filter or None
        ])
        columns = ['title', 'upvotes', 'published_date', 'slug', 'hit_count']
        posts = [dict(zip(columns, row)) for row in cursor.fetchall()]
    return posts


@csrf_exempt
def hit(request):
    if request.GET.get('blog') and get_int(request.GET.get('score', 0), 0) > 50 and not request.GET.get('title') and not 'bot' in request.META.get('HTTP_USER_AGENT'):
        user_agent = httpagentparser.detect(request.META.get('HTTP_USER_AGENT', None))

        # Prevent duplicates with ip hash + date
        hash_id = salt_and_hash(request)

        country = get_country(client_ip(request)).get('country_name', '')
        device = user_agent.get('platform', {}).get('name', '')
        browser = user_agent.get('browser', {}).get('name', '')
        
        referrer = request.GET.get('referrer','')
        if referrer:
            referrer = urlparse(referrer)
            referrer = '{uri.scheme}://{uri.netloc}/'.format(uri=referrer)
        

        blog_pk = Blog.objects.filter(subdomain=request.GET.get('blog')).values_list('pk', flat=True).first()
        post_pk = None
        if '/' not in request.GET.get('token'):
            post_pk = Post.objects.filter(uid=request.GET.get('token')).values_list('pk', flat=True).first()
        
        if blog_pk:
            try:
                hit, create = Hit.objects.get_or_create(
                    blog_id=blog_pk,
                    post_id=post_pk,
                    hash_id=hash_id,
                    referrer=referrer,
                    country=country,
                    device=device,
                    browser=browser)
                if create:
                    print('Hit:', hit)
            except Hit.MultipleObjectsReturned:
                pass

        response = HttpResponse("Logged hit")
        response['X-Robots-Tag'] = 'noindex, nofollow'
        return response
    
    return HttpResponse('Forbidden', status=403)