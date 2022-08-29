from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import TemplateView, RedirectView

urlpatterns = [
    path('mothership/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', include('blogs.urls')),
    path("favicon.ico", RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
    path('404/', TemplateView.as_view(template_name="404.html", content_type="text/html"))
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

handler404 = 'blogs.views.blog.not_found'
