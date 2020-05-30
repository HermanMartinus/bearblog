from django.urls import path
from django.views.generic import TemplateView

from . import views
from . import dashboard_views

urlpatterns = [
    path('', views.home, name='home'),
    path('accounts/delete/', dashboard_views.delete_user, name='user_delete'),
    path('dashboard/', dashboard_views.dashboard, name='dashboard'),
    path('dashboard/domain/', dashboard_views.domain_edit, name='domain'),
    path('dashboard/posts/', dashboard_views.posts_edit, name='post'),
    path('dashboard/posts/new/', dashboard_views.post_new, name='post_new'),
    path('dashboard/posts/<pk>/', dashboard_views.post_edit, name='post_edit'),
    path('dashboard/posts/<pk>/delete/', dashboard_views.PostDelete.as_view(), name='post_delete'),
    path('ip_test/', dashboard_views.ip_test, name='ip_test'),

    path('blog/', views.posts, name='posts'),
    path('<slug>/', views.post, name='post'),
]
