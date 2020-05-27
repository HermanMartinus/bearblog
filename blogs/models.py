from django.db import models
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from django.contrib.auth.models import User
from .helpers import *

class Blog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True)
    title = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True, blank=True)
    subdomain = models.SlugField(max_length=100, unique=True)
    subdomain_id = models.CharField(max_length=128, unique=True, blank=True, null=True)
    domain = models.CharField(max_length=128, blank=True, null=True)
    content = models.TextField(blank=True)

    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        self.subdomain = self.subdomain.lower()
        if self.domain:
            self.domain = self.domain.lower()
        return super(Blog, self).save(*args, **kwargs)


@receiver(pre_delete, sender=Blog, dispatch_uid='blog_delete_signal')
def delete_blog_receiver(sender, instance, using, **kwargs):
    print("Delete Domain and subdomain DNS records")
    delete_dns_record(instance.subdomain_id)
    delete_domain(instance.domain)

class Post(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=100)
    published_date = models.DateTimeField(auto_now_add=True, blank=True)
    publish =  models.BooleanField(default=True)
    is_page = models.BooleanField(default=False)
    content = models.TextField()

    def __str__(self):
        return self.title
    
    def save(self, *args, **kwargs):
        self.slug = self.slug.lower()
        return super(Post, self).save(*args, **kwargs)
