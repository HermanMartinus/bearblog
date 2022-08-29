from datetime import timedelta
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from blogs.helpers import send_async_mail
from django.db.models.functions import TruncDate

from blogs.models import Blog

import pygal
from pygal.style import LightColorizedStyle


@staff_member_required
def dashboard(request):
    days_filter = int(request.GET.get('days', 7))
    start_date = (timezone.now() - timedelta(days=days_filter)).date()
    end_date = timezone.now().date()

    blogs = Blog.objects.filter(blocked=False, created_date__gt=start_date).order_by('created_date')

    date_iterator = start_date
    blogs_count = blogs.annotate(date=TruncDate('created_date')).values('date').annotate(c=Count('date')).order_by()

    # create dates dict with zero hits
    blog_dict = {}
    while date_iterator <= end_date:
        blog_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += timedelta(days=1)

    # populate dict with hits count
    for hit in blogs_count:
        blog_dict[hit['date'].strftime("%Y-%m-%d")] = hit['c']

    # generate chart
    chart_data = []
    for date, count in blog_dict.items():
        chart_data.append({'date': date, 'signups': count})

    chart = pygal.Bar(height=300, show_legend=False, style=LightColorizedStyle)
    chart.force_uri_protocol = 'http'
    mark_list = [x['signups'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Reads', mark_list)
    chart.x_labels = [x['date'].split('-')[2] for x in chart_data]
    chart_render = chart.render_data_uri()

    return render(
            request,
            'staff/dashboard.html',
            {
                'blogs': blogs,
                'chart': chart_render,
            }
    )


@staff_member_required
def review_flow(request):
    blogs = Blog.objects.filter(reviewed=False, blocked=False).annotate(
        post_count=Count("post"),
    ).prefetch_related("post_set").order_by('created_date')

    unreviewed_blogs = []
    for blog in blogs:
        grace_period = timezone.now() - timedelta(days=14)
        if (
            blog.content == "Hello World!"
            and blog.post_count == 0
            and not blog.custom_styles
        ):

            # Delete empty blogs 14 days old
            if blog.created_date < grace_period:
                blog.delete()
        else:
            delay_period = timezone.now() - timedelta(days=2)
            if blog.created_date < delay_period:
                unreviewed_blogs.append(blog)

    if unreviewed_blogs:
        blog = unreviewed_blogs[0]
        all_posts = blog.post_set.filter(publish=True).order_by('-published_date')

        return render(
            request,
            'staff/review_flow.html',
            {
                'blog': blog,
                'content': blog.content or "~nothing here~",
                'posts': all_posts,
                'root': blog.useful_domain(),
                'still_to_go': len(unreviewed_blogs)
            })
    else:
        return HttpResponse("No blogs left to review! \ʕ•ᴥ•ʔ/")


@staff_member_required
def approve(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.reviewed = True
    blog.save()

    message = request.POST.get("message", "")

    if not request.GET.get("no-email", ""):
        send_async_mail(
            "I've just reviewed your blog",
            message,
            'Herman Martinus <herman@bearblog.dev>',
            [blog.user.email]
        )
    return redirect('review_flow')


@staff_member_required
def block(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.blocked = True
    blog.save()
    return redirect('review_flow')


@staff_member_required
def delete(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.delete()
    return redirect('review_flow')
