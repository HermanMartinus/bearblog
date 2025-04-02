from django.conf import settings
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
from blogs.models import Blog, PersistentStore, Post
from blogs.middleware import request_metrics, redis_client

from statistics import mean
from datetime import timedelta
import pygal
from pygal.style import LightColorizedStyle
import json
import os
from datetime import datetime

@staff_member_required
def dashboard(request):
    days_filter = int(request.GET.get('days', 30))
    start_date = (timezone.now() - timedelta(days=days_filter)).date()
    end_date = timezone.now().date()

    opt_in_blogs_count = len(opt_in_blogs().values_list('id', flat=True))
    dodgy_blogs_count = len(dodgy_blogs().values_list('id', flat=True))
    new_blogs_count = len(new_blogs().values_list('id', flat=True))

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
            'days_filter': days_filter,
            'heroku_slug_description': os.getenv('HEROKU_SLUG_DESCRIPTION'),
            'heroku_release_created_at': datetime.fromisoformat(os.getenv('HEROKU_RELEASE_CREATED_AT', timezone.now().isoformat()).replace('Z', '+00:00'))
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

        return redirect(f"{blog.useful_domain}")


@staff_member_required  
def import_posts(request):
    error_messages = []
    if request.method == "POST":
        subdomain = request.POST.get('subdomain')
        csv_file = request.FILES['csv_file']
        success, message, stats = import_posts_from_csv(subdomain, csv_file)
        error_messages.append(message)
    
    return HttpResponse(error_messages)


def import_posts_from_csv(subdomain, csv_file):
    if not csv_file.name.endswith('.csv'):
        return False, 'Please upload a CSV file', {}
    
    blog = Blog.objects.filter(subdomain=subdomain).first()
    if not blog:
        return False, 'Blog not found', {}
    
    try:
        import csv
        from io import StringIO
        import datetime
        
        decoded_file = csv_file.read().decode('utf-8-sig')  # Use utf-8-sig to handle BOM character
        csv_reader = csv.DictReader(StringIO(decoded_file))
        
        # Fix field names by replacing spaces with underscores and handle BOM character
        csv_data = []
        for row in csv_reader:
            fixed_row = {}
            for key, value in row.items():
                # Remove BOM character if present and fix spaces
                fixed_key = key.replace('\ufeff', '').replace(' ', '_')
                fixed_row[fixed_key] = value
            csv_data.append(fixed_row)
        
        # Track import stats
        imported = 0
        skipped = 0
        
        for row in csv_data:
            # Check if post already exists by UID
            uid_key = 'uid'
            # Check both normal and BOM-prefixed keys
            if uid_key not in row and '\ufeffuid' in row:
                uid_key = '\ufeffuid'
                
            if uid_key in row and row[uid_key]:
                existing = Post.objects.filter(blog=blog, uid=row[uid_key]).first()
                if existing:
                    # Skip existing posts
                    skipped += 1
                    continue
                
            # Create new post
            post = Post(blog=blog)
            
            # Only map specified CSV fields to Post model fields
            # Define field mapping to handle potential BOM character
            field_mapping = {
                'uid': ['uid', '\ufeffuid'],
                'title': ['title', '\ufefftitle'],
                'slug': ['slug', '\ufeffslug'],
                'alias': ['alias', '\ufeffalias'],
                'content': ['content', '\ufeffcontent'],
                'canonical_url': ['canonical_url', '\ufeffcanonical_url'],
                'meta_description': ['meta_description', '\ufeffmeta_description'],
                'meta_image': ['meta_image', '\ufeffmeta_image'],
                'lang': ['lang', '\ufefflang'],
                'class_name': ['class_name', '\ufeffclass_name']
            }
            
            # Set fields based on mapping
            for field, possible_keys in field_mapping.items():
                for key in possible_keys:
                    if key in row and row[key]:
                        setattr(post, field, row[key])
                        break
            
            # Handle boolean fields with potential BOM
            boolean_fields = {
                'is_page': ['is_page', '\ufeffis_page'],
                'publish': ['publish', '\ufeffpublish'],
                'make_discoverable': ['make_discoverable', '\ufeffmake_discoverable']
            }
            
            for field, possible_keys in boolean_fields.items():
                for key in possible_keys:
                    if key in row:
                        value = row[key].lower() == 'true'
                        setattr(post, field, value)
                        break
            
            # Handle date fields with potential BOM
            date_fields = {
                'published_date': ['published_date', '\ufeffpublished_date'],
                'first_published_at': ['first_published_at', '\ufefffirst_published_at']
            }
            
            for field, possible_keys in date_fields.items():
                for key in possible_keys:
                    if key in row and row[key]:
                        try:
                            setattr(post, field, datetime.datetime.fromisoformat(row[key]))
                            break
                        except ValueError:
                            pass  # Skip invalid date format
            
            # Handle tags with potential BOM
            tag_keys = ['all_tags', '\ufeffall_tags']
            for key in tag_keys:
                if key in row and row[key]:
                    post.all_tags = row[key]
                    break
            
            post.save()
            imported += 1
        
        stats = {'imported': imported, 'skipped': skipped}
        
        if imported > 0:
            return True, f'Successfully imported {imported} posts. Skipped {skipped} existing posts.', stats
        else:
            return False, f'No new posts were imported. Skipped {skipped} existing posts.', stats
            
    except Exception as e:
        return False, f'Error importing posts: {str(e)}', {}


@staff_member_required
def delete_empty(request):
    for blog in empty_blogs():
        blog.delete()

    return redirect('staff_dashboard')


def empty_blogs():
    # Not used in the last year
    timeperiod = timezone.now() - timedelta(days=365)
    blogs = Blog.objects.annotate(num_posts=Count('posts')).annotate(content_length=Length('content')).filter(
        last_modified__lte=timeperiod, num_posts__lte=0, content_length__lt=60, user__settings__upgraded=False).order_by('-created_date')[:100]

    return blogs


def new_blogs():
    # TODO: Clean up ingore terms
    # persistent_store = PersistentStore.load()
    # ignore_terms = persistent_store.ignore_terms

    to_review = Blog.objects.filter(
        Q(ignored_date__lt=F('last_modified')) | Q(ignored_date__isnull=True),
        permanent_ignore=False,
        reviewed=False,
        user__is_active=True,
        to_review=False,
        created_date__lte=timezone.now() - timedelta(days=2)
    )

    # for term in ignore_terms:
    #     to_review = to_review.exclude(content__icontains=term)
    
    return to_review


def opt_in_blogs():
    to_review = Blog.objects.filter(reviewed=False, user__is_active=True, to_review=True)
    
    return to_review


def dodgy_blogs():
    to_review = Blog.objects.filter(
        Q(reviewed=False, user__is_active=True, to_review=False, dodginess_score__gt=2, ignored_date__isnull=True) |
        Q(flagged=True)
    ).prefetch_related('posts')

    return to_review


@staff_member_required
def review_bulk(request):
    if 'opt-in' in request.path:
        blogs = opt_in_blogs().select_related('user').prefetch_related('posts').order_by('created_date')[:100]
    elif 'new' in request.path:
        blogs = new_blogs().select_related('user').prefetch_related('posts').order_by('-created_date')[:100]
    elif 'dodgy' in request.path:
        blogs = dodgy_blogs().select_related('user').prefetch_related('posts').order_by('-dodginess_score')[:100]

    still_to_go = len(blogs)
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
        blog.flagged = False
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
        blog.flagged = False
        blog.save()
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
        if blog.ignored_date:
            blog.permanent_ignore = True
        blog.ignored_date = timezone.now()
        blog.flagged = False
        blog.to_review = False
        blog.save()
        return HttpResponse("Ignored")
    

@staff_member_required
def flag(request, pk):
    if request.method == "POST":
        blog = get_object_or_404(Blog, pk=pk)
        blog.flagged = True
        blog.save()
        return HttpResponse("Flagged")


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
    
    if redis_client:
        # Get metrics from Redis
        for key in redis_client.keys('request_metrics:*'):
            endpoint = key.decode('utf-8').split(':')[1]
            measurements = json.loads(redis_client.get(key))
            
            if measurements:
                metrics_summary[endpoint] = calculate_metrics_summary(measurements)
    else:
        # Get metrics from in-memory storage
        for endpoint, measurements in request_metrics.items():
            if measurements:
                metrics_summary[endpoint] = calculate_metrics_summary(measurements)
    
    # Sort metrics by average total time (descending)
    sorted_metrics = dict(sorted(
        metrics_summary.items(),
        key=lambda x: x[1]['avg_total'],
        reverse=True
    ))
    
    return render(request, 'staff/performance.html', {
        'metrics': sorted_metrics
    })

def calculate_metrics_summary(measurements):
    """Helper function to calculate metrics summary"""
    return {
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

# Playground for testing

@staff_member_required
def playground(request):
    return HttpResponse("Hello")
