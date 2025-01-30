from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.views.generic import RedirectView
from django.contrib.admin.views.decorators import staff_member_required
from silk import urls as silk_urls


urlpatterns = [
    path('mothership/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('silk/', include((silk_urls.urlpatterns, 'silk'), namespace='silk')),
    path('', include('blogs.urls')),
    path("favicon.ico", RedirectView.as_view(url='/static/favicon.ico', permanent=True)),
    path("logo.png", RedirectView.as_view(url='/static/logo.png', permanent=True)),
]

if settings.DEBUG:
    import debug_toolbar
    urlpatterns = [
        path('__debug__/', include(debug_toolbar.urls)),
    ] + urlpatterns

handler404 = 'blogs.views.blog.not_found'
