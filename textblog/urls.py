from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import TemplateView, RedirectView


def trigger_error(request):
    division_by_zero = 1 / 0


urlpatterns = [
    path('sentry-debug/', trigger_error),
    path('mothership/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('blogs.urls')),
    path("favicon.ico", RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

handler404 = 'blogs.views.blog.not_found'
