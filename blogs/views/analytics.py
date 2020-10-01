from django.shortcuts import get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.utils.dateparse import parse_date
from datetime import timedelta

from blogs.models import Blog, Hit, Post
from django.core.exceptions import ObjectDoesNotExist
from blogs.helpers import root
from django.db.models import Count, Sum, Q
from django.http import HttpResponse

from ipaddr import client_ip


@login_required
def analytics(request):
    blog = get_object_or_404(Blog, user=request.user)
    time_threshold = False
    date_from = False
    date_to = False
    
    if request.GET.get('date_from', '') and request.GET.get('date_to', ''):
        date_from = parse_date(request.GET.get('date_from', ''))
        date_to = parse_date(request.GET.get('date_to', ''))

        posts = Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__range=[date_from, date_to]))).filter(
                    blog=blog,
                    publish=True,
                    ).order_by('-hit_count', '-published_date')
    else:
        if request.GET.get('days', ''):
            days = int(request.GET.get('days', ''))
        else:
            days = 1

        time_threshold = timezone.now() - timedelta(days=days)

        posts = Post.objects.annotate(
                hit_count=Count('hit', filter=Q(hit__created_date__gt=time_threshold))).filter(
                    blog=blog,
                    publish=True,
                    ).order_by('-hit_count', '-published_date')

    unique_reads = posts.aggregate(Sum('hit_count'))
    delta = timezone.now() - blog.created_date

    return render(request, 'dashboard/analytics.html', {
        'unique_reads': unique_reads,
        'posts': posts,
        'blog': blog,
        'time_threshold': time_threshold,
        'since_started': delta.days,
        'date_from': date_from,
        'date_to': date_to
    })


@login_required
def post_analytics(request, pk):
    post = get_object_or_404(Post, pk=pk)

    return HttpResponse("Work in progress  ᕦʕ •ᴥ•ʔᕤ")


def post_hit(request, pk):
    ip_address = client_ip(request)
    post = get_object_or_404(Post, pk=pk)
    post_view_dupe = post.hit_set.filter(ip_address=ip_address)

    if len(post_view_dupe) == 0:
        hit = Hit(post=post, ip_address=ip_address)
        hit.save()

    return HttpResponse("Logged")