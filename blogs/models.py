from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User

from .helpers import delete_domain, add_new_domain
from taggit.managers import TaggableManager


class Blog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True)
    title = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True, blank=True)
    subdomain = models.SlugField(max_length=100, unique=True)
    domain = models.CharField(max_length=128, blank=True, null=True)
    content = models.TextField(blank=True)
    reviewed = models.BooleanField(default=False)
    upgraded = models.BooleanField(default=False)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if self.pk:
            if self.domain:
                self.domain = self.domain.lower()
            old_domain = Blog.objects.get(pk=self.pk).domain
            if old_domain != self.domain:
                delete_domain(old_domain)
                if self.domain:
                    add_new_domain(self.domain)

        self.subdomain = self.subdomain.lower()

        return super(Blog, self).save(*args, **kwargs)


@receiver(pre_delete, sender=Blog, dispatch_uid='blog_delete_signal')
def delete_blog_receiver(sender, instance, using, **kwargs):
    print("Setting user to inactive")
    instance.user.is_active = False
    instance.user.save()

    if instance.domain:
        print("Deleting domain from Heroku")
        delete_domain(instance.domain)


class Style(models.Model):
    blog = models.OneToOneField(
        Blog,
        on_delete=models.CASCADE,
        primary_key=True
    )
    background_color = models.CharField(max_length=7, blank=True)
    font_color = models.CharField(max_length=7, blank=True)
    heading_color = models.CharField(max_length=7, blank=True)
    link_color = models.CharField(max_length=7, blank=True)
    font_family = models.CharField(max_length=200, blank=True)
    custom_css = models.TextField(blank=True)

    def __str__(self):
        return self.blog.title


class Post(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    published_date = models.DateTimeField(blank=True)
    tags = TaggableManager(blank=True)
    publish = models.BooleanField(default=True)
    show_in_feed = models.BooleanField(default=True)
    is_page = models.BooleanField(default=False)
    content = models.TextField()
    canonical_url = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.slug = self.slug.lower()
        super(Post, self).save(*args, **kwargs)


class Upvote(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    ip_address = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.created_date.strftime('%d %b %Y, %X')} - {self.ip_address} - {self.post}"


class Hit(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    ip_address = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.created_date.strftime('%d %b %Y, %X')} - {self.ip_address} - {self.post}"
