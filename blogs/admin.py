from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count

from .models import Blog, Post, Upvote, Hit
from django.utils.html import escape, format_html
from blogs.helpers import add_email_address, delete_domain, root
from django.urls import reverse


class UserAdmin(admin.ModelAdmin):
    def subdomain_url(self, obj):
        blog = Blog.objects.get(user=obj)
        return format_html(
            "<a href='http://{url}' target='_blank'>{url}</a>",
            url=root(blog.subdomain))

    subdomain_url.short_description = "Subomain"

    list_display = ('email', 'subdomain_url', 'is_active', 'is_staff', 'date_joined')
    ordering = ('-date_joined',)


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return Blog.objects.annotate(posts_count=Count('post'))

    def post_count(self, obj):
        return obj.posts_count

    post_count.short_description = ('Post count')
    post_count.admin_order_field = "posts_count"

    def domain_url(self, obj):
        if not obj.domain:
            return ''
        return format_html(
            "<a href='http://{url}' target='_blank'>{url}</a>",
            url=obj.domain)

    domain_url.short_description = "Domain url"
    domain_url.admin_order_field = 'domain'

    def subdomain_url(self, obj):
        return format_html(
            "<a href='http://{url}' target='_blank'>{url}</a>",
            url=root(obj.subdomain))

    subdomain_url.short_description = "Subomain"

    def user_link(self, obj):
        return format_html('<a href="{url}">{username}</a>',
                           url=reverse("admin:auth_user_change", args=(obj.user.id,)),
                           username=escape(obj.user))

    user_link.allow_tags = True
    user_link.short_description = "User"

    list_display = (
        'title',
        'reviewed',
        'upgraded',
        'blocked',
        'subdomain_url',
        'domain_url',
        'post_count',
        'user_link',
        'created_date')

    search_fields = ('title', 'subdomain', 'domain', 'user__email')
    ordering = ('-created_date',)

    actions = ['approve_blog', 'block_blog']

    def approve_blog(self, request, queryset):
        queryset.update(reviewed=True)
        for blog in queryset:
            add_email_address(blog.user.email)

    approve_blog.short_description = "Approve selected blogs"

    def block_blog(self, request, queryset):
        for blog in queryset:
            blog.user.is_active = False
            blog.user.save()
            blog.blocked = True
            blog.save()
            print(f"Blocked {blog} and banned {blog.user}")

    block_blog.short_description = "Block selected blogs"


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


@admin.register(Hit)
class HitAdmin(admin.ModelAdmin):
    def post_link(self, obj):
        return format_html('<a href="/mothership/blogs/post/{id}/change/">{post}</a>',
                           id=obj.post.pk,
                           post=escape(obj.post))

    list_display = ('created_date', 'post_link', 'ip_address')
    search_fields = ('created_date', 'post__title')
    ordering = ('-created_date',)
