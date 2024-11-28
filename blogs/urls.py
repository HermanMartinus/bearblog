from django.urls import path

from blogs.views import blog, dashboard, studio, feed, discover, analytics, emailer, staff, signup_flow, media
from blogs import subscriptions
from conf import logger

import os
from functools import wraps


# Only allow certain urls to reach certain paths
def main_site_only(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.get_host() in os.getenv('MAIN_SITE_HOSTS').split(','):
            # If not the main site, redirect to a potential blog post
            return blog.post(request, slug=request.path)
        return view_func(request, *args, **kwargs)
    return _wrapped_view

urlpatterns = [
    path('', blog.home, name='home'),
    path('logger-test/', logger.logger_test),

    # Staff dashboard
    path('staff/dashboard/', main_site_only(staff.dashboard), name='staff_dashboard'),
    path('staff/review/new/', main_site_only(staff.review_bulk), name='review_new'),
    path('staff/review/opt-in/', main_site_only(staff.review_bulk), name='review_opt_in'),
    path('staff/review/dodgy/', main_site_only(staff.review_bulk), name='review_dodgy'),
    path('staff/review/approve/<pk>', main_site_only(staff.approve), name='review_approve'),
    path('staff/review/block/<pk>', main_site_only(staff.block), name='review_block'),
    path('staff/review/ignore/<pk>', main_site_only(staff.ignore), name='review_ignore'),
    path('staff/review/delete/<pk>', main_site_only(staff.delete), name='review_delete'),
    path('staff/dashboard/delete-empty/', main_site_only(staff.delete_empty), name='delete_empty'),
    path('staff/dashboard/migrate-blog/', main_site_only(staff.migrate_blog), name='migrate_blog'),
    path('staff/dashboard/check-spam/', main_site_only(staff.check_spam), name='check_spam'),
    path('staff/dashboard/performance/', main_site_only(staff.performance_dashboard), name='performance_dashboard'),

    # User dashboard
    path('accounts/delete/', dashboard.delete_user, name='user_delete'),
    path('signup/', signup_flow.signup, name="signup_flow"),

    path('dashboard/', studio.list, name="account"),
    path('dashboard/upgrade/', dashboard.upgrade, name='upgrade'),
    path('dashboard/customise/', studio.dashboard_customisation, name="dashboard_customisation"),

    path('<id>/dashboard/', studio.studio, name="dashboard"),
    path('<id>/delete/', dashboard.blog_delete, name="blog_delete"),
    path('<id>/dashboard/nav/', dashboard.nav, name='nav'),
    path('<id>/dashboard/styles/', dashboard.styles, name='styles'),
    path('<id>/dashboard/settings/', dashboard.settings, name='settings'),
    path('<id>/dashboard/custom-domain/', studio.custom_domain_edit, name='custom_domain_edit'),
    path('<id>/dashboard/settings/advanced/', studio.advanced_settings, name='advanced_settings'),
    path('<id>/dashboard/directives/', studio.directive_edit, name="directive_edit"),
    path('<id>/dashboard/email-list/', emailer.email_list, name='email_list'),

    # Media
    path('<id>/dashboard/media/', media.media_center, name='media_center'),
    path('<id>/dashboard/media/delete-selected/', media.delete_selected_media, name='delete_selected_media'),
    path('<id>/dashboard/upload-image/', media.upload_image, name='upload_image'),
    path('media/<str:img>/', media.image_proxy, name="image-proxy"),

    path('<id>/dashboard/analytics/', analytics.analytics, name='analytics'),
    path('<id>/dashboard/analytics-upgraded/', analytics.analytics_upgraded, name="analytics_upgraded"),

    path('<id>/dashboard/opt-in-review/', dashboard.opt_in_review, name='opt_in_review'),

    path('<id>/dashboard/posts/', dashboard.posts_edit, name='posts_edit'),
    path('<id>/dashboard/pages/', dashboard.pages_edit, name='pages_edit'),
    path('<id>/dashboard/posts/new/', studio.post, name="post_new"),
    path('<id>/dashboard/posts/<uid>/', studio.post, name="post_edit"),
    path('<id>/dashboard/posts/<uid>/delete/', dashboard.post_delete, name='post_delete'),
    path('<id>/dashboard/preview/', studio.preview, name="post_preview"),

    path('<id>/dashboard/post-template/', studio.post_template, name="post_template"),

    # Webhook
    path('lemon-webhook/', subscriptions.lemon_webhook, name='lemon_webhook'),

    # Discover
    path('discover/', main_site_only(discover.discover), name='discover'),
    path('discover/feed/', main_site_only(discover.feed), name='discover_feed'),
    path('discover/search/', main_site_only(discover.search), name='search'),

    # Blog
    path('ping/', blog.ping, name='ping'),
    
    path('sitemap.xml', blog.sitemap, name='sitemap'),
    path('robots.txt', blog.robots, name='robots'),
    path('public-analytics/', blog.public_analytics, name="public_analytics"),
    path('upvote/<uid>/', blog.upvote, name='upvote'),
    path('hit/<uid>/', analytics.post_hit, name='post_hit'),
    path('subscribe/', emailer.subscribe, name='subscribe'),
    path('email-subscribe/', emailer.email_subscribe, name='email_subscribe'),
    path('confirm-subscription/', emailer.confirm_subscription, name='confirm_subscription'),
    
    # Feeds + aliases
    path("feed/", feed.feed),
    path("atom/", feed.feed),
    path("feed/atom/", feed.feed),
    path("feed/rss/", feed.feed),
    path("feed/feed.xml", feed.feed),
    path("feed.xml", feed.feed),
    path("index.xml", feed.feed),
    path("rss.xml", feed.feed),
    path("atom.xml", feed.feed),

    # Generic path endpoint for slugs
    path('<path:slug>/', blog.post, name='post'),
]
