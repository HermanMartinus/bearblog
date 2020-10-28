from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import timedelta

from blogs.models import Blog, Hit, Post
from django.core.exceptions import ObjectDoesNotExist
from blogs.helpers import daterange, root
from django.db.models import Count, Sum, Q
from django.http import HttpResponse

from ipaddr import client_ip
import pygal
import json
from django.utils.datetime_safe import date


@login_required
def analytics(request):
    blog = get_object_or_404(Blog, user=request.user)

    if not blog.upgraded:
        return redirect('account')

    time_threshold = False
    date_from = False
    date_to = False
    chart_data = []
    
    if request.GET.get('date_from', '') and request.GET.get('date_to', ''):
        date_from = parse_date(request.GET.get('date_from', ''))
        date_to = parse_date(request.GET.get('date_to', ''))

        posts = Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__range=[date_from, date_to]))).filter(
                    blog=blog,
                    publish=True,
                    ).order_by('-hit_count', '-published_date')

        hits = Hit.objects.filter(post__blog=blog, created_date__range=[date_from, date_to])

        for single_date in daterange(date_from, date_to):
            chart_data.append({
                "date": single_date.strftime("%Y-%m-%d"),
                "hits": len(list(filter(lambda hit: hit.created_date.date() == single_date, list(hits))))
            })
    else:
        if request.GET.get('days', ''):
            days = int(request.GET.get('days', ''))
        else:
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
    delta = timezone.now() - blog.created_date

    chart = pygal.Line(height=300)
    mark_list = [x['hits'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Reads', mark_list)
    chart.x_labels = [x['date'] for x in chart_data]
    chart_render = chart.render().decode('utf-8')

    return render(request, 'dashboard/analytics.html', {
        'unique_reads': unique_reads,
        'posts': posts,
        'blog': blog,
        'time_threshold': time_threshold,
        'since_started': delta.days,
        'date_from': date_from,
        'date_to': date_to,
        'chart': chart_render
    })


@login_required
def post_analytics(request, pk):
    blog = get_object_or_404(Blog, user=request.user)

    if not blog.upgraded:
        return redirect('account')

    time_threshold = False
    date_from = False
    date_to = False
    chart_data = []

    if request.GET.get('date_from', '') and request.GET.get('date_to', ''):
        date_from = parse_date(request.GET.get('date_from', ''))
        date_to = parse_date(request.GET.get('date_to', ''))

        post = get_object_or_404(Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__range=[date_from, date_to]))), pk=pk)

        hits = Hit.objects.filter(post=post, created_date__range=[date_from, date_to])
        for single_date in daterange(date_from, date_to):
            chart_data.append({
                "date": single_date.strftime("%Y-%m-%d"),
                "hits": len(list(filter(lambda hit: hit.created_date.date() == single_date, list(hits))))
            })
    else:
        if request.GET.get('days', ''):
            days = int(request.GET.get('days', ''))
        else:
            days = 7

        time_threshold = timezone.now() - timedelta(days=days)

        post = get_object_or_404(Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__gt=time_threshold))), pk=pk)

        hits = Hit.objects.filter(post=post, created_date__gt=time_threshold)

        for single_date in daterange(timezone.now() - timedelta(days=days), timezone.now() + timedelta(days=1)):
            chart_data.append({
                "date": single_date.strftime("%Y-%m-%d"),
                "hits": len(list(filter(lambda hit: hit.created_date.date() == single_date.date(), list(hits))))
            })

    delta = timezone.now() - blog.created_date

    chart = pygal.Line(height=300, range=(0, post.hit_count + 5))
    mark_list = [x['hits'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Reads', mark_list)
    chart.x_labels = [x['date'] for x in chart_data]
    chart_render = chart.render().decode('utf-8')

    return render(request, 'dashboard/post_analytics.html', {
        'post': post,
        'blog': blog,
        'time_threshold': time_threshold,
        'since_started': delta.days,
        'date_from': date_from,
        'date_to': date_to,
        'chart': chart_render
    })


def post_hit(request, pk):
    ip_address = client_ip(request)
    post = get_object_or_404(Post, pk=pk)
    post_view_dupe = post.hit_set.filter(ip_address=ip_address)

    if len(post_view_dupe) == 0:
        hit = Hit(post=post, ip_address=ip_address)
        hit.save()

    return HttpResponse("Logged")