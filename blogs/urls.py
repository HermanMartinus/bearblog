from django.urls import path
from django.views.generic import TemplateView

from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('accounts/delete/', views.delete_user, name='user_delete'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/posts/', views.posts_edit, name='post'),
    path('dashboard/posts/new/', views.post_new, name='post_new'),
    path('dashboard/posts/<pk>/', views.post_edit, name='post_edit'),
    path('dashboard/posts/<pk>/delete/', views.PostDelete.as_view(), name='post_delete'),
    path('blog/', views.posts, name='posts'),
    path('<slug>/', views.post, name='post'),
]
