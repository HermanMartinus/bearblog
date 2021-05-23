from django.urls import path
from django.views.generic import TemplateView

from .views import blog, dashboard, feed, discover, analytics, emailer

urlpatterns = [
    path('', blog.home, name='home'),
    path('contribute/', TemplateView.as_view(template_name='contribute.html')),
    path('review/', blog.review_flow, name='review_flow'),
    path('review/approve/<pk>', blog.approve, name='review_approve'),
    path('review/block/<pk>', blog.block, name='review_block'),
    path('accounts/delete/', dashboard.delete_user, name='user_delete'),
    path('dashboard/', dashboard.dashboard, name='dashboard'),
    path('dashboard/styles/', dashboard.styles, name='styles'),
    path('dashboard/account/', dashboard.account, name='account'),
    path('dashboard/domain/', dashboard.domain_edit, name='domain'),
    path('dashboard/subscribers/', emailer.subscribers, name='subscribers'),
    path('dashboard/subscribers/settings/', emailer.notification_settings, name='notification_settings'),
    path('dashboard/export_emails/', dashboard.export_emails, name='export_emails'),
    path('dashboard/analytics/', analytics.analytics, name='analytics'),
    path('dashboard/posts/', dashboard.posts_edit, name='post'),
    path('dashboard/posts/new/', dashboard.post_new, name='post_new'),
    path('dashboard/posts/<pk>/', dashboard.post_edit, name='post_edit'),
    path('dashboard/posts/<pk>/delete/', dashboard.PostDelete.as_view(), name='post_delete'),

    path('discover/', discover.discover, name='discover'),

    path('.well-known/acme-challenge/<challenge>', blog.challenge, name='challenge'),
    path('blog/', blog.posts, name='posts'),
    path('subscribe/', emailer.subscribe, name='subscribe'),
    path('confirm-subscription/', emailer.confirm_subscription, name='confirm_subscription'),
    path('hit/<pk>/', analytics.post_hit, name='post_hit'),
    path("feed/", feed.feed, name="post_feed"),
    path('<slug>/', blog.post, name='post'),
]
