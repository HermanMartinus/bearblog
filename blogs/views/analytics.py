import threading
from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import IntegrityError
from datetime import timedelta

import requests

from blogs.models import Blog, Hit, Post
from blogs.forms import AnalyticsForm
from blogs.helpers import daterange
from django.db.models import Count, Sum, Q
from django.http import HttpResponse

from ipaddr import client_ip
import httpagentparser
import pygal
import hashlib


@login_required
def analytics(request):
    blog = get_object_or_404(Blog, user=request.user)

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
    unique_visitors = len(hits.values('ip_address').distinct())

    delta = timezone.now() - blog.created_date

    chart = pygal.Bar(height=300)
    mark_list = [x['hits'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Reads', mark_list)
    chart.x_labels = [x['date'] for x in chart_data]
    chart_render = chart.render().decode('utf-8')

    if request.method == "POST":
        form = AnalyticsForm(request.POST, instance=blog)
        if form.is_valid():
            blog_info = form.save(commit=False)
            blog_info.save()
    else:
        form = AnalyticsForm(instance=blog)

    return render(request, 'dashboard/analytics.html', {
        'unique_reads': unique_reads,
        'unique_visitors': unique_visitors,
        'posts': posts,
        'blog': blog,
        'chart': chart_render,
        'form': form
    })


def post_hit(request, pk):
    ip_hash = hashlib.md5(f"{client_ip(request)}-{timezone.now().date()}".encode('utf-8')).hexdigest()
    try:
        response = requests.request("GET", f'https://geolocation-db.com/json/{client_ip(request)}')
        location = response.json()
        country = ''
        device = ''
        browser = ''
        try:
            if location['country_name'] and location['country_name'] != 'Not found':
                country = location['country_name']
        except KeyError:
            print('Country not found')

        user_agent = httpagentparser.detect(request.META.get('HTTP_USER_AGENT', None))

        try:
            if not user_agent['bot']:
                device = user_agent['platform']['name']
        except KeyError:
            print('Platform not found')

        try:
            if not user_agent['bot']:
                browser = user_agent['browser']['name']
        except KeyError:
            print('Platform not found')

        Hit.objects.get_or_create(
            post_id=pk,
            ip_address=ip_hash,
            referrer=request.GET.get('ref', None),
            country=country,
            device=device,
            browser=browser)

        # HitThread(hit, client_ip(request)).start()
    except Hit.MultipleObjectsReturned:
        print('Duplicate hit')
    except IntegrityError:
        print('Post does not exist')

    return HttpResponse("Logged")


class HitThread(threading.Thread):
    def __init__(self, hit, ip_address):
        self.ip_address = ip_address
        self.hit = hit
        threading.Thread.__init__(self)

    def run(self):
        response = requests.request("GET", f'https://geolocation-db.com/json/{self.ip_address}')
        self.hit.country = response.json()
        self.hit.save()
        print(self.hit)
