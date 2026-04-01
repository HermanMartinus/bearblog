from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.template.loader import render_to_string
from django.db.models import Q, F, Count, Max
from django.db.models.functions import Greatest, Length, TruncWeek, TruncDate, TruncMonth
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth.models import User
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import render

from blogs.helpers import send_async_mail, check_connection
from blogs.models import Blog, PersistentStore, Post, UserSettings

from datetime import timedelta
from dateutil.relativedelta import relativedelta
import json
import os
from datetime import datetime


@staff_member_required
def dashboard(request):
    days_filter = int(request.GET.get('days', 30))
    period = request.GET.get('period', 'weeks')
    start_date = (timezone.now() - timedelta(days=days_filter)).date()
    end_date = timezone.now().date()
    opt_in_blogs_count = len(opt_in_blogs().values_list('id', flat=True))
    dodgy_blogs_count = len(dodgy_blogs().values_list('id', flat=True))
    flagged_blogs_count = len(flagged_blogs().values_list('id', flat=True))
    new_blogs_count = len(new_blogs().values_list('id', flat=True))
    all_empty_blogs = empty_blogs()
    users = User.objects.filter(is_active=True, date_joined__gte=start_date).order_by('date_joined')
    # Configure period settings
    if period == 'days':
        trunc = TruncDate
        delta = timedelta(days=1)
        label_format = lambda d: d.split('-')[2]
        get_start = lambda d: d
    elif period == 'weeks':
        trunc = TruncWeek
        delta = timedelta(days=7)
        label_format = lambda d: d[5:]
        get_start = lambda d: d - timedelta(days=d.weekday())
    elif period == 'months':
        trunc = TruncMonth
        delta = relativedelta(months=1)
        label_format = lambda d: d[:7]
        get_start = lambda d: d.replace(day=1)
    else:
        period = 'weeks'
        trunc = TruncWeek
        delta = timedelta(days=7)
        label_format = lambda d: d[5:]
        get_start = lambda d: d - timedelta(days=d.weekday())
    start_period = get_start(start_date)
    end_period = get_start(end_date)
    # Signups
    user_count = users.annotate(p=trunc('date_joined')).values('p').annotate(c=Count('id')).order_by('p')
    # Create dict with zero signups
    user_dict = {}
    date_iterator = start_period
    while date_iterator <= end_date:
        user_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += delta
    # Populate dict with signup count
    for signup in user_count:
        if signup['p'] is not None:
            p_str = signup['p'].strftime("%Y-%m-%d")
            if p_str in user_dict:
                user_dict[p_str] = signup['c']
    # Generate chart data
    signup_chart_data = []
    for date, count in user_dict.items():
        signup_chart_data.append({'date': date, 'count': count})
    # Upgrades
    upgraded_users = User.objects.filter(settings__upgraded=True, settings__upgraded_date__gte=start_date).order_by('settings__upgraded_date')
    upgrades_count = upgraded_users.annotate(p=trunc('settings__upgraded_date')).values('p').annotate(c=Count('id')).order_by('p')
    # Create dict with zero upgrades
    user_dict = {}
    date_iterator = start_period
    while date_iterator <= end_date:
        user_dict[date_iterator.strftime("%Y-%m-%d")] = 0
        date_iterator += delta
    # Populate dict with upgrade count
    for upgrade in upgrades_count:
        if upgrade['p'] is not None:
            p_str = upgrade['p'].strftime("%Y-%m-%d")
            if p_str in user_dict:
                user_dict[p_str] = upgrade['c']
    # Generate chart data
    upgrade_chart_data = []
    for date, count in user_dict.items():
        upgrade_chart_data.append({'date': date, 'count': count})
    # Calculate signups and upgrades for the period
    signups = users.count()
    upgrades = User.objects.filter(settings__upgraded=True, settings__upgraded_date__gte=start_date).count()
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
            'signup_chart_data': json.dumps(signup_chart_data),
            'upgrade_chart_data': json.dumps(upgrade_chart_data),
            'start_date': start_date,
            'end_date': end_date,
            'opt_in_blogs_count': opt_in_blogs_count,
            'dodgy_blogs_count': dodgy_blogs_count,
            'flagged_blogs_count': flagged_blogs_count,
            'new_blogs_count': new_blogs_count,
            'empty_blogs': all_empty_blogs,
            'days_filter': days_filter,
            'period': period,
            'reviewed_blogs': get_weekly_reviews(),
            'heroku_slug_description': os.getenv('HEROKU_SLUG_DESCRIPTION'),
            'heroku_release_created_at': datetime.fromisoformat(os.getenv('HEROKU_RELEASE_CREATED_AT', timezone.now().isoformat()).replace('Z', '+00:00'))
        }
    )


def get_weekly_reviews():
    persistent_store = PersistentStore.load()
    reviewed_blogs = persistent_store.reviewed_blogs

     # Aggregate by week
    weekly_reviews = {}
    for date_str, count in reviewed_blogs.items():
        date = datetime.strptime(date_str, '%Y-%m-%d')
        # Find days since last Sunday (week starts at midnight before Monday)
        days_since_sunday = (date.weekday() + 1) % 7
        week_start = (date - timedelta(days=days_since_sunday)).strftime('%Y-%m-%d')
        weekly_reviews[week_start] = weekly_reviews.get(week_start, 0) + count
    
    # Sort by week start date
    weekly_reviews = dict(sorted(weekly_reviews.items()))
    return weekly_reviews


def new_upgrades():
    upgraded_users = User.objects.filter(
        settings__upgraded=True,
        settings__upgraded_date__gte=timezone.now()-timedelta(weeks=1),
        settings__upgraded_email_sent=False,
        settings__order_id__isnull=False
        )
    return upgraded_users


def blogs_with_orphaned_domains():
    return Blog.objects.filter(
        domain__isnull=False,
        user__settings__upgraded=False,
        user__settings__orphaned_domain_warning_email_sent__isnull=True,
    ).exclude(domain='').select_related('user', 'user__settings')


def monthly_users_to_upgrade():
    earliest = timezone.now() - timedelta(days=150)  # ~5 months
    latest = timezone.now() - timedelta(days=60)  # ~2 months
    return UserSettings.objects.filter(
        upgraded=True,
        plan_type='monthly',
        upgraded_date__range=(earliest, latest),
        upgrade_nudge_email_sent__isnull=True,
    ).select_related('user')


def free_users_to_nudge():
    two_months_ago = timezone.now() - timedelta(days=60)
    three_days_ago = timezone.now() - timedelta(days=3)
    return User.objects.filter(
        date_joined__lte=two_months_ago,
        settings__upgraded=False,
        settings__contribution_nudge_email_sent__isnull=True,
    ).filter(
        Q(blogs__last_posted__gte=three_days_ago) |
        Q(blogs__last_modified__gte=three_days_ago)
    ).distinct().select_related('settings').annotate(
        latest_activity=Greatest(
            Max('blogs__last_posted'),
            Max('blogs__last_modified'),
        )
    )


@staff_member_required
def actions(request):
    upgraded_users = list(new_upgrades().select_related('settings'))
    nudge_users = list(monthly_users_to_upgrade())
    contribution_nudge_users = list(free_users_to_nudge())
    orphaned_blogs = [blog for blog in blogs_with_orphaned_domains() if check_connection(blog)]
    cutoff = timezone.now() - timedelta(days=14)
    overdue_blogs = list(Blog.objects.filter(
        user__settings__upgraded=False,
        user__settings__orphaned_domain_warning_email_sent__lte=cutoff,
    ).exclude(domain='').exclude(domain__isnull=True).select_related('user', 'user__settings'))

    # Group orphaned blogs by user
    orphaned_by_user = {}
    for blog in orphaned_blogs:
        orphaned_by_user.setdefault(blog.user, []).append(blog)

    result = None
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'email_new_upgrades':
            count = 0
            for user in upgraded_users:
                send_async_mail(
                    "You upgraded!",
                    render_to_string('emails/upgraded.html'),
                    'Herman Martinus <herman@mg.bearblog.dev>',
                    [user.email],
                    ['Herman Martinus <herman@bearblog.dev>'],
                )
                user.settings.upgraded_email_sent = True
                user.settings.save()
                count += 1
            result = f"Emailed {count} new upgrades."
            upgraded_users = list(new_upgrades().select_related('settings'))

        elif action == 'email_nudge_monthly':
            count = 0
            for user_settings in nudge_users:
                send_async_mail(
                    "Your subscription",
                    render_to_string('emails/upgrade_from_monthly.html'),
                    'Herman Martinus <herman@mg.bearblog.dev>',
                    [user_settings.user.email],
                    ['Herman Martinus <herman@bearblog.dev>'],
                )
                user_settings.upgrade_nudge_email_sent = timezone.now()
                user_settings.save()
                count += 1
            result = f"Emailed {count} monthly users to upgrade."
            nudge_users = list(monthly_users_to_upgrade())

        elif action == 'email_domain_warnings':
            count = 0
            for user, user_blogs in list(orphaned_by_user.items()):
                send_async_mail(
                    "Your custom domain",
                    render_to_string('emails/domain_warning.html', {'blogs': user_blogs}),
                    'Herman Martinus <herman@mg.bearblog.dev>',
                    [user.email],
                    ['Herman Martinus <herman@bearblog.dev>'],
                )
                user.settings.orphaned_domain_warning_email_sent = timezone.now()
                user.settings.save()
                count += 1
            result = f"Emailed {count} users about orphaned domains."
            orphaned_blogs = list(blogs_with_orphaned_domains())
            orphaned_by_user = {}
            for blog in orphaned_blogs:
                orphaned_by_user.setdefault(blog.user, []).append(blog)

        elif action == 'email_contribution_nudge':
            count = 0
            for user in contribution_nudge_users:
                send_async_mail(
                    "Your support",
                    render_to_string('emails/contribution_nudge.html'),
                    'Herman Martinus <herman@mg.bearblog.dev>',
                    [user.email],
                    ['Herman Martinus <herman@bearblog.dev>'],
                )
                user.settings.contribution_nudge_email_sent = timezone.now()
                user.settings.save()
                count += 1
            result = f"Emailed {count} free users about contributing."
            contribution_nudge_users = list(free_users_to_nudge())

        elif action == 'remove_orphaned_domains':
            count = 0
            for blog in overdue_blogs:
                blog.domain = ''
                blog.save()
                blog.user.settings.orphaned_domain_warning_email_sent = None
                blog.user.settings.save()
                count += 1
            if count:
                cache.delete('domain_map')
            result = f"Removed domains from {count} blogs."
            overdue_blogs = list(Blog.objects.filter(
                user__settings__upgraded=False,
                user__settings__orphaned_domain_warning_email_sent__lte=cutoff,
            ).exclude(domain='').exclude(domain__isnull=True).select_related('user', 'user__settings')[:20])

    return render(request, 'staff/actions.html', {
        'upgraded_users': upgraded_users,
        'nudge_users': nudge_users,
        'orphaned_blogs': orphaned_blogs,
        'orphaned_by_user': orphaned_by_user,
        'overdue_blogs': overdue_blogs,
        'contribution_nudge_users': contribution_nudge_users,
        'result': result,
    })


@staff_member_required
def check_spam(request):
    if request.method == "POST":
        query = request.POST.get('query', '').strip()

        if not query:
            return JsonResponse({'error': 'Either email or subdomain must be provided.'}, status=400)

        # Clean subdomain input: strip protocol and .bearblog.dev suffix
        cleaned = query.lower()
        for prefix in ['https://', 'http://']:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        cleaned = cleaned.rstrip('/')
        for suffix in ['.bearblog.dev', '.lh.co']:
            if cleaned.endswith(suffix):
                cleaned = cleaned[:-len(suffix)]

        # Look up by email first, then by cleaned subdomain
        user = User.objects.filter(email=query).first()
        if user:
            blog = user.blogs.first()
        else:
            blog = Blog.objects.filter(subdomain=cleaned).first()

        if not blog:
            return JsonResponse({'error': 'Blog not found.'}, status=404)

        posts = []
        for post in blog.posts.all().order_by('-published_date'):
            posts.append({
                'title': post.title,
                'slug': post.slug,
                'published_date': post.published_date.isoformat() if post.published_date else None,
                'content': post.content,
                'make_discoverable': post.make_discoverable,
            })

        data = {
            'title': blog.title,
            'subdomain': blog.subdomain,
            'domain': blog.domain or '',
            'email': blog.user.email,
            'useful_domain': blog.useful_domain,
            'bear_domain': blog.bear_domain,
            'created_date': blog.created_date.isoformat(),
            'last_modified': blog.last_modified.isoformat(),
            'last_posted': blog.last_posted.isoformat() if blog.last_posted else None,
            'upgraded': blog.user.settings.upgraded,
            'is_active': blog.user.is_active,
            'reviewed': blog.reviewed,
            'flagged': blog.flagged,
            'hidden': blog.hidden,
            'dodginess_score': blog.dodginess_score,
            'reviewer_note': blog.reviewer_note,
            'robots_txt': blog.robots_txt,
            'content': blog.content,
            'posts': posts,
            'admin_usersettings_url': f'/mothership/blogs/usersettings/{blog.user.settings.pk}/change/',
            'admin_blog_url': f'/mothership/blogs/blog/{blog.pk}/change/',
        }

        return JsonResponse(data)


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
        
        csv.field_size_limit(20 * 1024 * 1024)  # 10MB limit

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
    to_review = Blog.objects.filter(
        Q(ignored_date__lt=F('last_modified')) | Q(ignored_date__isnull=True),
        permanent_ignore=False,
        reviewed=False,
        user__is_active=True,
        to_review=False,
        flagged=False,
        created_date__lte=timezone.now() - timedelta(days=1)
    )

    # Avoid showing empty blogs
    to_review = to_review.annotate(num_posts=Count('posts')).annotate(content_length=Length('content')).exclude(
       Q(num_posts__lte=0, content_length__lt=200) & ~Q(content__icontains="http")
    )
    
    return to_review


def opt_in_blogs():
    to_review = Blog.objects.filter(reviewed=False, user__is_active=True, to_review=True)
    
    return to_review


def dodgy_blogs():
    to_review = Blog.objects.filter(
        reviewed=False, user__is_active=True, to_review=False, flagged=False, dodginess_score__gt=2, ignored_date__isnull=True
    ).prefetch_related('posts')

    return to_review

def flagged_blogs():
    to_review = Blog.objects.filter(flagged=True).prefetch_related('posts')
    return to_review


@staff_member_required
def review_bulk(request):
    if 'opt-in' in request.path:
        blogs = opt_in_blogs().select_related('user').prefetch_related('posts').order_by('created_date')[:100]
    elif 'new' in request.path:
        blogs = new_blogs().select_related('user').prefetch_related('posts').order_by('created_date')[:100]
    elif 'dodgy' in request.path:
        blogs = dodgy_blogs().select_related('user').prefetch_related('posts').order_by('-dodginess_score')[:100]
    elif 'flagged' in request.path:
        blogs = flagged_blogs().select_related('user')

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


def increment_reviewed():
    persistent_store = PersistentStore.load()
    today = timezone.now().date().isoformat()
    
    reviewed_blogs = persistent_store.reviewed_blogs
    reviewed_blogs[today] = reviewed_blogs.get(today, 0) + 1
    
    persistent_store.reviewed_blogs = reviewed_blogs
    persistent_store.save()


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
                'Herman Martinus <herman@mg.bearblog.dev>',
                [blog.user.email],
                ['Herman Martinus <herman@bearblog.dev>'],
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

        increment_reviewed()

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
        else:
            if blog.created_date > timezone.now() - timedelta(weeks=1) and request.POST.get('email'):
                send_async_mail(
                    "Welcome to Bear",
                    render_to_string('emails/welcome.html'),
                    'Herman Martinus <herman@mg.bearblog.dev>',
                    [blog.user.email],
                    ['Herman Martinus <herman@bearblog.dev>'],
                )
        blog.ignored_date = timezone.now()
        blog.flagged = False
        blog.to_review = False
        blog.save()

        increment_reviewed()

        return HttpResponse("Ignored")
    

@staff_member_required
def flag(request, pk):
    if request.method == "POST":
        blog = get_object_or_404(Blog, pk=pk)
        blog.flagged = True
        blog.save()

        increment_reviewed()

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


# Playground for testing

@staff_member_required
def playground(request):
    return HttpResponse("Hello")
