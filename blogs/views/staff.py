from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.db.models.functions import TruncDate, Length
from django.http import JsonResponse

from blogs.helpers import send_async_mail
from blogs.models import Blog

from datetime import timedelta
import pygal
from pygal.style import LightColorizedStyle
import openai
import os


@staff_member_required
def dashboard(request):
    days_filter = int(request.GET.get('days', 30))
    start_date = (timezone.now() - timedelta(days=days_filter)).date()
    end_date = timezone.now().date()

    blogs = Blog.objects.filter(blocked=False, created_date__gt=start_date).order_by('created_date')

    # Exclude empty blogs
    non_empty_blog_ids = [blog.pk for blog in blogs if not blog.is_empty]
    blogs = blogs.filter(pk__in=non_empty_blog_ids)

    to_review = Blog.objects.filter(to_review=True, reviewed=False, blocked=False).count()

    # Signups
    date_iterator = start_date
    blogs_count = blogs.annotate(date=TruncDate('created_date')).values('date').annotate(c=Count('date')).order_by()

    # Create dates dict with zero signups
    blog_dict = {}
    while date_iterator <= end_date:
        blog_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += timedelta(days=1)

    # Populate dict with signup count
    for signup in blogs_count:
        blog_dict[signup['date'].strftime("%Y-%m-%d")] = signup['c']

    # Generate chart
    chart_data = []
    for date, count in blog_dict.items():
        chart_data.append({'date': date, 'signups': count})

    chart = pygal.Bar(height=300, show_legend=False, style=LightColorizedStyle)
    chart.force_uri_protocol = 'http'
    mark_list = [x['signups'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Signups', mark_list)
    chart.x_labels = [x['date'].split('-')[2] for x in chart_data]
    signup_chart = chart.render_data_uri()

    total_signups = sum([x['signups'] for x in chart_data])

    # Upgrades
    date_iterator = start_date
    blogs = Blog.objects.filter(upgraded=True, created_date__gt=start_date).order_by('created_date')
    upgrades_count = blogs.annotate(date=TruncDate('upgraded_date')).values('date').annotate(c=Count('date')).order_by()

    # Create dates dict with zero upgrades
    blog_dict = {}
    while date_iterator <= end_date:
        blog_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += timedelta(days=1)

    # Populate dict with signup count
    for signup in upgrades_count:
        if signup['date']:
            blog_dict[signup['date'].strftime("%Y-%m-%d")] = signup['c']

    # Generate chart
    chart_data = []
    for date, count in blog_dict.items():
        chart_data.append({'date': date, 'upgrades': count})

    chart = pygal.Bar(height=300, show_legend=False, style=LightColorizedStyle)
    chart.force_uri_protocol = 'http'
    mark_list = [x['upgrades'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Upgrades', mark_list)
    chart.x_labels = [x['date'].split('-')[2] for x in chart_data]
    upgrade_chart = chart.render_data_uri()
    total_upgrades = sum([x['upgrades'] for x in chart_data])

    # Conversion rate
    conversion_rate = total_upgrades / total_signups if total_signups > 0 else 0
    formatted_conversion_rate = f"{conversion_rate*100:.2f}%"

    empty_blogs = get_empty_blogs()

    return render(
        request,
        'staff/dashboard.html',
        {
            'blogs': blogs,
            'total_signups': total_signups,
            'total_upgrades': total_upgrades,
            'conversion_rate': formatted_conversion_rate,
            'signup_chart': signup_chart,
            'upgrade_chart': upgrade_chart,
            'start_date': start_date,
            'end_date': end_date,
            'to_review': to_review,
            'empty_blogs': empty_blogs
        }
    )


def get_empty_blogs():
    # Empty blogs
    # Not used in the last 5 weeks
    # Most recent 100
    timeperiod = timezone.now() - timedelta(weeks=5)
    empty_blogs = Blog.objects.annotate(num_posts=Count('post')).annotate(content_length=Length('content')).filter(
        last_modified__lte=timeperiod, num_posts__lte=0, content_length__lt=50, upgraded=False, custom_styles="").order_by('-created_date')[:100]

    return empty_blogs


@staff_member_required
def delete_empty(request):
    for blog in get_empty_blogs():
        print(f'Deleting {blog}')
        blog.delete()

    return redirect('staff_dashboard')


@staff_member_required
def review_flow(request):
    blogs = Blog.objects.filter(reviewed=False, blocked=False).annotate(
        post_count=Count("post"),
    ).prefetch_related("post_set").order_by('created_date')

    unreviewed_blogs = []
    for blog in blogs:
        if blog.to_review:
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
                'still_to_go': len(unreviewed_blogs),
            })
    else:
        return redirect('staff_dashboard')


@staff_member_required
def approve(request, pk):
    blog = get_object_or_404(Blog, pk=pk)
    blog.reviewed = True
    blog.to_review = False
    blog.save()

    message = request.POST.get("message", "")

    if message and not request.GET.get("no-email", ""):
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


def extract_blog_info(blog):
    posts_info = []
    for post in blog.post_set.all():
        posts_info.append({'title': post.title, 'content': post.content})

    return {
        'title': blog.title,
        'content': blog.content,
        'url': blog.useful_domain(),
        'posts': posts_info
    }
