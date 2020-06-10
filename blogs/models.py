from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User

from .helpers import delete_domain, add_new_domain
import re
import json


class Blog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True)
    title = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True, blank=True)
    subdomain = models.SlugField(max_length=100, unique=True)
    domain = models.CharField(max_length=128, blank=True, null=True)
    content = models.TextField(blank=True)
    hashtags = models.TextField(blank=True)

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
    print("Delete domain from Heroku")

    if instance.domain:
        delete_domain(instance.domain)


class Post(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    published_date = models.DateTimeField(blank=True)
    publish = models.BooleanField(default=True)
    show_in_feed = models.BooleanField(default=True)
    is_page = models.BooleanField(default=False)
    content = models.TextField()

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.slug = self.slug.lower()
        super(Post, self).save(*args, **kwargs)

        # TODO: Make this asynchronous
        all_text = ''
        for entry in Post.objects.filter(blog=self.blog):
            all_text += f'{entry.content} '

        new_hashtags = list(dict.fromkeys(re.findall(r"#(\w+)", all_text)))
        self.blog.hashtags = json.dumps(new_hashtags)
        self.blog.save()


class Upvote(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    ip_address = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.ip_address} | {self.created_date.strftime('%d %b %Y, %X')}"


class PageView(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    post = models.ForeignKey(Post, on_delete=models.CASCADE, blank=True, null=True)
    ip_address = models.CharField(max_length=100, blank=True, null=True)
    referer = models.CharField(max_length=255, blank=True, null=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self, ):
        return f"{self.ip_address} viewed: {self.blog} => {self.post} at {self.timestamp}"

    class Meta:
        ordering = ['-timestamp']