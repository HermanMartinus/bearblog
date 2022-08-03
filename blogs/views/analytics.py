from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.db import IntegrityError
from datetime import timedelta

from blogs.models import Blog, Hit, Post
from blogs.forms import AnalyticsForm
from blogs.helpers import daterange
from django.db.models import Count, Sum, Q
from django.http import HttpResponse

from ipaddr import client_ip
import httpagentparser
import pygal
import json
from django.utils.datetime_safe import date
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
    print(httpagentparser.detect(request.META.get('HTTP_USER_AGENT', None)))

    ip_hash = hashlib.md5(f"{client_ip(request)}-{timezone.now().date()}".encode('utf-8')).hexdigest()
    try:
        Hit.objects.get_or_create(post_id=pk, ip_address=ip_hash)
    except Hit.MultipleObjectsReturned:
        print('Duplicate hit')
    except IntegrityError:
        print('Post does not exist')

    return HttpResponse("Logged")
