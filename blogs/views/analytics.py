import threading
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import IntegrityError
from datetime import timedelta

import requests

from blogs.models import Blog, Hit, Post
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

    if blog.upgraded:
        return redirect('/studio/analytics/')

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


def post_hit(request, pk):
    HitThread(request, pk).start()

    return HttpResponse("Logged")


class HitThread(threading.Thread):
    def __init__(self, request, pk):
        self.request = request
        self.pk = pk
        threading.Thread.__init__(self)

    def run(self):
        try:
            ip_hash = hashlib.md5(f"{client_ip(self.request)}-{timezone.now().date()}".encode('utf-8')).hexdigest()
            response = requests.request("GET", f'https://geolocation-db.com/json/{client_ip(self.request)}')
            location = response.json()
            country = ''
            device = ''
            browser = ''
            try:
                if location['country_name'] and location['country_name'] != 'Not found':
                    country = location['country_name']
            except KeyError:
                print('Country not found')

            user_agent = httpagentparser.detect(self.request.META.get('HTTP_USER_AGENT', None))

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

            referrer = self.request.GET.get('ref', None).split('?')[0].split('#')[0]
            Hit.objects.get_or_create(
                post_id=self.pk,
                ip_address=ip_hash,
                referrer=referrer,
                country=country,
                device=device,
                browser=browser)

        except Hit.MultipleObjectsReturned:
            print('Duplicate hit')
        except IntegrityError:
            print('Post does not exist')
