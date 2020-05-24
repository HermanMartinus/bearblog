from django.contrib import admin
from django.urls import path, include
from django.conf.urls import url
from django.views.generic import TemplateView

urlpatterns = [
    path('mothership/', admin.site.urls),
    url(r'^accounts/', include('allauth.urls')),
    path('', include('blogs.urls')),
    path(
        "robots.txt",
        TemplateView.as_view(template_name="robots.txt", content_type="text/plain"),
    ),
]

handler404 = 'blogs.views.not_found'