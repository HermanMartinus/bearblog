from django.contrib import admin
from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin
from django.db.models import Count
from django.utils.html import escape, format_html, format_html_join
from django.urls import reverse
from django.utils.safestring import mark_safe

from blogs.models import Blog, PersistentStore, Post, RssSubscriber, Stylesheet, Upvote, Hit, Subscriber, UserSettings, Media


admin.autodiscover()
admin.site.enable_nav_sidebar = False


class UserAdmin(admin.ModelAdmin):
    list_display = ('email', 'is_active', 'is_staff', 'date_joined')
    ordering = ('-date_joined',)
    search_fields = ('email', 'blogs__subdomain')


admin.site.unregister(User)
admin.site.register(User, UserAdmin)

@admin.register(UserSettings)
class UserSettingsAdmin(admin.ModelAdmin):
    list_display = ('email', 'user_link', 'date_joined', 'blogs', 'display_is_active', 'upgraded', 'upgraded_date', 'order_id')
    
    def email(self, obj):
        return obj.user.email
    
    def user_link(self, obj):
        user = obj.user
        user_model = user.__class__
        app_label = user_model._meta.app_label
        model_name = user_model._meta.model_name
        url_name = f'admin:{app_label}_{model_name}_change'
        url = reverse(url_name, args=[user.pk])
        return format_html('<a href="{}">{}</a>', url, user.pk)
    user_link.short_description = 'User'
    
    def date_joined(self, obj):
        return obj.user.date_joined

    def display_is_active(self, obj):
        return obj.user.is_active
    display_is_active.short_description = 'Active'
    display_is_active.boolean = True

    def blogs(self, obj):
        blogs_data = (
            (
                blog.dynamic_useful_domain,
                blog.subdomain,
                reverse('admin:blogs_blog_change', args=[blog.pk]),
            ) for blog in obj.user.blogs.all()
        )

        blogs_links = format_html_join(
            mark_safe(', '),
            '{} <a href="{}" target="_blank">[edit]</a>',
            ((format_html('<a href="{0}" target="_blank">{1}</a>', url, subdomain), edit_url) for url, subdomain, edit_url in blogs_data)
        )
        return blogs_links or 'No blogs'

    search_fields = ('user__email', 'user__blogs__title', 'user__blogs__subdomain')

    list_filter = (
        ('upgraded', admin.BooleanFieldListFilter),
        ('user__is_active', admin.BooleanFieldListFilter),
    )


@admin.register(Blog)
class BlogAdmin(admin.ModelAdmin):
    def get_queryset(self, request):
        return Blog.objects.annotate(posts_count=Count('posts'))

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
            url=obj.blank_bear_domain)
    subdomain_url.short_description = "Subdomain"

    def user_link(self, obj):
        return format_html('<a href="{url}">{username}</a>',
                           url=reverse("admin:blogs_usersettings_change", args=(obj.user.settings.id,)),
                           username=escape(obj.user.email))
    user_link.allow_tags = True
    user_link.short_description = "User Settings"

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = "Email"

    def display_upgraded(self, obj):
        return obj.user.settings.upgraded
    display_upgraded.short_description = 'Upgraded'
    display_upgraded.boolean = True

    def display_is_active(self, obj):
        return obj.user.is_active
    display_is_active.short_description = 'Active'
    display_is_active.boolean = True

    list_display = (
        'title',
        'user_link',
        'subdomain_url',
        'domain_url',
        'reviewed',
        'display_upgraded',
        'display_is_active',
        'post_count',
        'created_date')

    search_fields = ('title', 'subdomain', 'domain', 'user__email')
    ordering = ('-created_date',)
    list_filter = (
        ('domain', admin.EmptyFieldListFilter),
        ('user__settings__upgraded', admin.BooleanFieldListFilter),
        ('user__is_active', admin.BooleanFieldListFilter),
    )

    def block_blog(self, request, queryset):
        for blog in queryset:
            blog.user.is_active = False
            blog.user.save()
            print(f"Blocked {blog} and banned {blog.user}")

    block_blog.short_description = "Block selected blogs"

    actions = ['block_blog']


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ('title', 'blog', 'upvotes', 'published_date')
    search_fields = ('title', 'blog__title')
    ordering = ('-published_date',)


admin.site.register(Upvote)
admin.site.register(Stylesheet)
admin.site.register(RssSubscriber)
admin.site.register(Media)


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
