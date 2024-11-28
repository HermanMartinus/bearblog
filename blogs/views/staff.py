from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse
from django.db.models import Q, F, Count
from django.db.models.functions import Length, TruncDate, Length
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from blogs.helpers import send_async_mail
from blogs.models import Blog, PersistentStore
from blogs.middleware import request_metrics

from statistics import mean
from datetime import timedelta
import pygal
from pygal.style import LightColorizedStyle


@staff_member_required
def dashboard(request):
    days_filter = int(request.GET.get('days', 30))
    start_date = (timezone.now() - timedelta(days=days_filter)).date()
    end_date = timezone.now().date()

    opt_in_blogs_count = opt_in_blogs().count()
    dodgy_blogs_count = dodgy_blogs().count()
    new_blogs_count = new_blogs().count()

    all_empty_blogs = empty_blogs()

    users = User.objects.filter(is_active=True, date_joined__gt=start_date).order_by('date_joined')

    # Signups
    date_iterator = start_date
    user_count = users.annotate(date=TruncDate('date_joined')).values('date').annotate(c=Count('date')).order_by()

    # Create dates dict with zero signups
    user_dict = {}
    while date_iterator <= end_date:
        user_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += timedelta(days=1)

    # Populate dict with signup count
    for signup in user_count:
        user_dict[signup['date'].strftime("%Y-%m-%d")] = signup['c']

    # Generate chart
    chart_data = []
    for date, count in user_dict.items():
        chart_data.append({'date': date, 'signups': count})

    chart = pygal.Bar(height=300, show_legend=False, style=LightColorizedStyle)
    chart.force_uri_protocol = 'http'
    mark_list = [x['signups'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Signups', mark_list)
    chart.x_labels = [x['date'].split('-')[2] for x in chart_data]
    signup_chart = chart.render_data_uri()

    # Upgrades
    date_iterator = start_date
    upgraded_users = User.objects.filter(settings__upgraded=True, settings__upgraded_date__gte=start_date).order_by('settings__upgraded_date')
    upgrades_count = upgraded_users.annotate(date=TruncDate('settings__upgraded_date')).values('date').annotate(c=Count('date')).order_by()


    # Create dates dict with zero upgrades
    user_dict = {}
    while date_iterator <= end_date:
        user_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += timedelta(days=1)

    # Populate dict with signup count
    for signup in upgrades_count:
        if signup['date']:
            user_dict[signup['date'].strftime("%Y-%m-%d")] = signup['c']

    # Generate chart
    chart_data = []
    for date, count in user_dict.items():
        chart_data.append({'date': date, 'upgrades': count})

    chart = pygal.Bar(height=300, show_legend=False, style=LightColorizedStyle)
    chart.force_uri_protocol = 'http'
    mark_list = [x['upgrades'] for x in chart_data]
    [x['date'] for x in chart_data]
    chart.add('Upgrades', mark_list)
    chart.x_labels = [x['date'].split('-')[2] for x in chart_data]
    upgrade_chart = chart.render_data_uri()

    # Calculate signups and upgrades for the past month
    signups = users.count()
    upgrades = User.objects.filter(settings__upgraded=True, settings__upgraded_date__gt=start_date).count()

    # Calculate all-time totals
    total_signups = User.objects.count()
    total_upgrades = User.objects.filter(settings__upgraded=True).count()

    # Calculate conversion rates
    conversion_rate = upgrades / signups if signups > 0 else 0
    total_conversion_rate = total_upgrades / total_signups if total_signups > 0 else 0

    formatted_conversion_rate = f"{conversion_rate*100:.2f}%"
    formatted_total_conversion_rate = f"{total_conversion_rate*100:.2f}%"

    return render(
        request,
        'staff/dashboard.html',
        {
            'signups': signups,
            'upgrades': upgrades,
            'total_signups': total_signups,
            'total_upgrades': total_upgrades,
            'conversion_rate': formatted_conversion_rate,
            'total_conversion_rate': formatted_total_conversion_rate,
            'signup_chart': signup_chart,
            'upgrade_chart': upgrade_chart,
            'start_date': start_date,
            'end_date': end_date,
            'opt_in_blogs_count': opt_in_blogs_count,
            'dodgy_blogs_count': dodgy_blogs_count,
            'new_blogs_count': new_blogs_count,
            'empty_blogs': all_empty_blogs,
            'days_filter': days_filter
        }
    )


@staff_member_required
def check_spam(request):
    if request.method == "POST":
        query = request.POST.get('query')

        if not query:
            return HttpResponse("Either email or subdomain must be provided.")
        
        user = User.objects.filter(email=query).first()
        if user:
            blog = user.blogs.first()
        else:
            blog = Blog.objects.filter(subdomain=query).first()
        
        if not user and not blog:
            return HttpResponse("User or blog not found.")
        
        if request.POST.get('unblock'):
            blog.user.is_active = True
            blog.user.save()
            return redirect(blog.useful_domain)

        return redirect(f"{blog.useful_domain}?reviewer=herman")


@staff_member_required
def delete_empty(request):
    for blog in empty_blogs():
        blog.delete()

    return redirect('staff_dashboard')


def empty_blogs():
    # Not used in the last year
    timeperiod = timezone.now() - timedelta(days=365)
    blogs = Blog.objects.annotate(num_posts=Count('posts')).annotate(content_length=Length('content')).filter(
        last_modified__lte=timeperiod, num_posts__lte=0, content_length__lt=60, user__settings__upgraded=False, custom_styles="").order_by('-created_date')[:100]

    return blogs


def new_blogs():
    persistent_store = PersistentStore.load()
    ignore_terms = persistent_store.ignore_terms

    to_review = Blog.objects.filter(
        Q(ignored_date__lt=F('last_modified')) | Q(ignored_date__isnull=True),
        reviewed=False,
        user__is_active=True,
        to_review=False,
        created_date__lte=timezone.now() - timedelta(days=2)
    ).order_by('created_date')

    for term in ignore_terms:
        to_review = to_review.exclude(content__icontains=term)
    
    return to_review


def opt_in_blogs():
    to_review = Blog.objects.filter(reviewed=False, user__is_active=True, to_review=True).order_by('created_date')
    
    return to_review


def dodgy_blogs():
    to_review = Blog.objects.filter(
        reviewed=False,
        user__is_active=True,
        to_review=False,
        dodginess_score__gt=2,
        ignored_date__isnull=True
    ).prefetch_related('posts').order_by('-dodginess_score')

    return to_review


@staff_member_required
def review_bulk(request):
    if 'opt-in' in request.path:
        blogs = opt_in_blogs()[:100]
    elif 'new' in request.path:
        blogs = new_blogs()[:100]
    elif 'dodgy' in request.path:
        blogs = dodgy_blogs()[:100]

    still_to_go = blogs.count()
    persistent_store = PersistentStore.load()

    if blogs:
        return render(
            request,
            'staff/review_bulk.html',
            {
                'blogs': blogs,
                'still_to_go': still_to_go,
                'highlight_terms': persistent_store.highlight_terms
            }
        )
    else:
        return redirect('staff_dashboard')


@staff_member_required
def approve(request, pk):
    if request.method == "POST":
        blog = get_object_or_404(Blog, pk=pk)
        blog.reviewed = True
        blog.to_review = False
        
        if request.POST.get("hide", False):
            blog.hidden = True

        blog.save()

        message = request.POST.get("message", "")
        
        if message:
            send_async_mail(
                "I've just reviewed your blog",
                message,
                'Herman Martinus <herman@bearblog.dev>',
                [blog.user.email]
            )
        return HttpResponse("Approved")


@staff_member_required
def block(request, pk):
    if request.method == "POST":
        blog = get_object_or_404(Blog, pk=pk)
        blog.user.is_active = not blog.user.is_active
        blog.user.save()
        return HttpResponse("Blocked")


@staff_member_required
def delete(request, pk):
    if request.method == "POST":
        blog = get_object_or_404(Blog, pk=pk)
        blog.delete()
        return HttpResponse("Deleted")


@staff_member_required
def ignore(request, pk):
    if request.method == "POST":
        blog = get_object_or_404(Blog, pk=pk)
        blog.ignored_date = timezone.now()
        blog.to_review = False
        blog.save()
        return HttpResponse("Ignored")


@staff_member_required
def migrate_blog(request):
    if request.method == "POST":
        subdomain = request.POST.get('subdomain')
        email = request.POST.get('email')
        message = ""
        if not email or not subdomain:
            return HttpResponse("Both email and subdomain must be provided.")
        
        user = User.objects.filter(email=email).first()
        if not user:
            return HttpResponse("User not found.")
        message += f"Found user: {user}...<br>"
        
        blog = Blog.objects.filter(subdomain=subdomain).first()
        if not blog:
            return HttpResponse("Blog not found.")
        message += f"Found blog: {blog.title} ({blog.useful_domain})...<br>"
        
        old_user = blog.user
        message += f'Migrating blog ({blog.title}) from {old_user} to {user}...<br>'
        blog.user = user
        blog.save()

        if old_user.blogs.count() == 0:
            message += f'User {old_user} has no more blogs and will be deleted...<br>'
            old_user.delete()
            message += 'Deleted...\n'
        
        return HttpResponse(message)


@staff_member_required
def performance_dashboard(request):
    metrics_summary = {}
    
    for endpoint, measurements in request_metrics.items():
        if measurements:
            metrics_summary[endpoint] = {
                'count': len(measurements),
                'avg_total': mean(m['total_time'] for m in measurements) * 1000,
                'avg_db': mean(m['db_time'] for m in measurements) * 1000,
                'avg_compute': mean(m['compute_time'] for m in measurements) * 1000,
                'max_total': max(m['total_time'] for m in measurements) * 1000,
                'max_db': max(m['db_time'] for m in measurements) * 1000,
                'max_compute': max(m['compute_time'] for m in measurements) * 1000,
                'db_percent': (mean(m['db_time'] for m in measurements)) / (mean(m['total_time'] for m in measurements)) * 100,
                'compute_percent': 100 - (mean(m['db_time'] for m in measurements)) / (mean(m['total_time'] for m in measurements)) * 100,
            }
    
    # Sort metrics by average total time (descending)
    sorted_metrics = dict(sorted(
        metrics_summary.items(),
        key=lambda x: x[1]['avg_total'],
        reverse=True
    ))
    
    return render(request, 'staff/performance.html', {
        'metrics': sorted_metrics
    })
