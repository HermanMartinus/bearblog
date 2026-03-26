from django.urls import path, re_path
from blogs.views import blog, feed, analytics, emailer

urlpatterns = [
    path('', blog.home, name='home'),
    path('favicon.ico', blog.favicon, name='favicon'),
    path("apple-touch-icon.png", blog.favicon),
    path("apple-touch-icon-precomposed.png", blog.favicon),
    re_path(r"^favicons/.*$", blog.favicon),
    path('sitemap.xml', blog.sitemap, name='sitemap'),
    path('robots.txt', blog.robots, name='robots'),
    path('public-analytics/', blog.public_analytics, name="public_analytics"),
    path('upvote/', blog.upvote, name='upvote'),
    path('upvote-info/<uid>/', blog.get_upvote_info, name='get_upvote_info'),
    path('hit/', analytics.hit, name='hit'),
    path('subscribe/', emailer.subscribe, name='subscribe'),
    path('email-subscribe/', emailer.email_subscribe, name='email_subscribe'),
    path("feed/", feed.feed),
    path("atom/", feed.feed),
    path("rss/", feed.feed),
    path("feed/atom/", feed.feed),
    path("feed/rss/", feed.feed),
    path("feed.xml", feed.feed),
    path("atom.xml", feed.feed),
    path("rss.xml", feed.feed),
    path("index.xml", feed.feed),
    path('<path:slug>/', blog.post, name='post'),
]
