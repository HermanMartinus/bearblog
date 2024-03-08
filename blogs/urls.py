from django.urls import path
from django.views.generic import RedirectView

from blogs.views import blog, dashboard, studio, feed, discover, analytics, emailer, staff, signup_flow
from blogs import subscriptions
from textblog import logger

urlpatterns = [
    path('', blog.home, name='home'),
    path('logger-test/', logger.logger_test),

    # Staff dashboard
    path('staff/', RedirectView.as_view(pattern_name='staff_dashboard', permanent=False)),
    path('staff/dashboard/', staff.dashboard, name='staff_dashboard'),
    path('staff/review/', staff.review_bulk, name='review'),
    path('staff/review/approve/<pk>', staff.approve, name='review_approve'),
    path('staff/review/block/<pk>', staff.block, name='review_block'),
    path('staff/review/ignore/<pk>', staff.ignore, name='review_ignore'),
    path('staff/review/delete/<pk>', staff.delete, name='review_delete'),
    path('staff/dashboard/delete-empty/', staff.delete_empty, name='delete_empty'),
    path('staff/dashboard/migrate-blog/', staff.migrate_blog, name='migrate_blog'),

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
    path('<id>/dashboard/settings/advanced/', studio.advanced_settings, name='advanced_settings'),
    path('<id>/dashboard/directives/', studio.directive_edit, name="directive_edit"),
    path('<id>/dashboard/email-list/', emailer.email_list, name='email_list'),

    path('<id>/dashboard/analytics/', analytics.analytics, name='analytics'),
    path('<id>/dashboard/analytics-upgraded/', analytics.analytics_upgraded, name="analytics_upgraded"),

    
    path('<id>/dashboard/opt-in-review/', dashboard.opt_in_review, name='opt_in_review'),

    path('<id>/dashboard/posts/', dashboard.posts_edit, name='posts_edit'),
    path('<id>/dashboard/pages/', dashboard.pages_edit, name='pages_edit'),
    path('<id>/dashboard/posts/new/', studio.post, name="post_new"),
    path('<id>/dashboard/posts/<uid>/', studio.post, name="post_edit"),
    path('<id>/dashboard/posts/<uid>/delete/', dashboard.post_delete, name='post_delete'),
    path('<id>/dashboard/preview/', studio.preview, name="post_preview"),
    path('<id>/dashboard/upload-image/', dashboard.upload_image, name='upload_image'),

    path('<id>/dashboard/post-template/', studio.post_template, name="post_template"),

    # Webhook
    path('lemon-webhook/', subscriptions.lemon_webhook, name='lemon_webhook'),

    # Discover
    path('discover/', discover.discover, name='discover'),
    path('discover/feed/', discover.feed, name='discover_feed'),
    path('search/', discover.search, name='search'),

    # Blog
    path('ping/', blog.ping, name='ping'),
    path('blog/', blog.posts, name='posts'),
    path('sitemap.xml', blog.sitemap, name='sitemap'),
    path('robots.txt', blog.robots, name='robots'),
    path('public-analytics/', blog.public_analytics, name="public_analytics"),
    path('upvote/<uid>/', blog.upvote, name='upvote'),
    path('hit/<uid>/', analytics.post_hit, name='post_hit'),
    path('subscribe/', emailer.subscribe, name='subscribe'),
    path('email-subscribe/', emailer.email_subscribe, name='email_subscribe'),
    path('confirm-subscription/', emailer.confirm_subscription, name='confirm_subscription'),
    path("feed/", feed.feed, name="rss_feed"),
    path('<path:slug>/', blog.post, name='post'),
    # path('<slug>/meta_image/', blog.generate_meta_image, name='generate_meta_image'),
]
