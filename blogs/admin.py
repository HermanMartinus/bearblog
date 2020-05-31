from django.contrib import admin
from django.db.models import Count
from .models import Blog, Post, Upvote
from django.utils.html import format_html


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return Blog.objects.annotate(posts_count=Count('post'))

    def post_count(self, obj):
        return obj.posts_count

    post_count.short_description = ('Post count')

    def domain_url(self, obj):
        return format_html(
            "<a href='http://{url}' target='_blank'>{url}</a>",
            url=obj.domain)

    domain_url.short_description = "Domain url"

    def subdomain_url(self, obj):
        return format_html(
            "<a href='http://{url}.bearblog.dev' target='_blank'>{url}.bearblog.dev</a>",
            url=obj.subdomain)

    subdomain_url.short_description = "Subomain"

    list_display = (
        'title',
        'subdomain_url',
        'domain',
        'domain_url',
        'user',
        'post_count',
        'created_date')

    search_fields = ('title', 'subdomain', 'domain', 'user__email')
    ordering = ('-created_date', 'domain')


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return Post.objects.annotate(upvote_count=Count('upvote'))

    def upvote_count(self, obj):
        return obj.upvote_count

    upvote_count.short_description = ('Upvotes')

    list_display = ('title', 'blog', 'upvote_count', 'published_date')
    search_fields = ('title', 'blog__title')
    ordering = ('-published_date',)


admin.site.register(Upvote)