from datetime import timedelta
from ssl import CertificateError
from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count
from django.utils import timezone
from requests import TooManyRedirects

from .models import Blog, PersistentStore, Post, Stylesheet, Upvote, Hit, Subscriber
from django.utils.html import escape, format_html
from blogs.helpers import check_connection, root
from django.urls import reverse


admin.autodiscover()
admin.site.enable_nav_sidebar = False


class UserAdmin(admin.ModelAdmin):
    def subdomain_url(self, obj):
        blog = Blog.objects.get(user=obj)
        return format_html(
            "<a href='{url}' target='_blank'>{url}</a>",
            url={blog.useful_domain()})

    subdomain_url.short_description = "Subdomain"

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
            return None
        return format_html(
            "<a href='http://{url}' target='_blank'>{url}</a>",
            url=obj.domain)

    domain_url.short_description = "Domain url"
    domain_url.admin_order_field = 'domain'

    def subdomain_url(self, obj):
        return format_html(
            "<a href='http://{url}' target='_blank'>{url}</a>",
            url=root(obj.subdomain))

    subdomain_url.short_description = "Subdomain"

    def user_link(self, obj):
        return format_html('<a href="{url}">{username}</a>',
                           url=reverse("admin:auth_user_change", args=(obj.user.id,)),
                           username=escape(obj.user))

    user_link.allow_tags = True
    user_link.short_description = "User"

    def user_email(self, obj):
        return obj.user.email

    user_email.short_description = "Email"

    list_display = (
        'title',
        'reviewed',
        'upgraded',
        'blocked',
        'subdomain_url',
        'domain_url',
        'post_count',
        'user_link',
        'user_email',
        'created_date')

    search_fields = ('title', 'subdomain', 'domain', 'user__email')
    ordering = ('-created_date',)
    list_filter = (
        ('domain', admin.EmptyFieldListFilter),
        ('upgraded', admin.BooleanFieldListFilter),
        ('blocked', admin.BooleanFieldListFilter),
    )

    def block_blog(self, request, queryset):
        for blog in queryset:
            blog.user.is_active = False
            blog.user.save()
            blog.blocked = True
            blog.save()
            print(f"Blocked {blog} and banned {blog.user}")

    block_blog.short_description = "Block selected blogs"

    def validate_domains(self, request, queryset):
        for blog in queryset:
            print(f'Checking {blog.domain}')
            try:
                if check_connection(blog):
                    print('good')
                else:
                    print('borked!')
            except TooManyRedirects:
                print('borked!')

    actions = ['block_blog', 'validate_domains']


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'blog', 'upvotes', 'published_date')
    search_fields = ('title', 'blog__title')
    ordering = ('-published_date',)


admin.site.register(Upvote)
admin.site.register(Stylesheet)


@admin.register(Hit)
class HitAdmin(admin.ModelAdmin):
    def post_link(self, obj):
        return format_html('<a href="/mothership/blogs/post/{id}/change/">{post}</a>',
                           id=obj.post.pk,
                           post=escape(obj.post))

    list_display = ('created_date', 'post_link', 'hash_id')
    search_fields = ('created_date', 'post__title')
    ordering = ('-created_date',)


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ('subscribed_date', 'blog', 'email_address')


admin.site.register(PersistentStore)
