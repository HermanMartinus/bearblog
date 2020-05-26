from django.contrib import admin
from django.db.models import Count
from .models import *

@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return Blog.objects.annotate(posts_count=Count('post'))

    def post_count(self, obj):
        return obj.posts_count

    post_count.short_description = ('Post count')

    list_display = ('title', 'user', 'post_count', 'created_date')
    search_fields = ('title', 'user__email')
    ordering = ('-created_date',)

@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'blog', 'published_date')
    search_fields = ('title', 'blog__title')
    ordering = ('-published_date',)