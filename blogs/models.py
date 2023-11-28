from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from django.contrib.sites.models import Site

import json
from math import log
import random
import string


class Blog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True)
    title = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True, blank=True)
    last_modified = models.DateTimeField(auto_now_add=True, blank=True)
    subdomain = models.SlugField(max_length=100, unique=True)
    domain = models.CharField(max_length=128, blank=True, null=True)

    nav = models.CharField(max_length=500, default="[Home](/) [Blog](/blog/)", blank=True)
    content = models.TextField(default="Hello World!", blank=True)
    meta_description = models.CharField(max_length=200, blank=True)
    meta_image = models.CharField(max_length=200, blank=True)
    lang = models.CharField(max_length=10, default='en', blank=True)
    meta_tag = models.CharField(max_length=500, blank=True)
    blog_path = models.CharField(max_length=200, default="blog")
    header_directive = models.TextField(blank=True)
    footer_directive = models.TextField(blank=True)

    reviewed = models.BooleanField(default=False)
    to_review = models.BooleanField(default=False)
    reviewer_note = models.TextField(blank=True)

    upgraded = models.BooleanField(default=False)
    upgraded_date = models.DateTimeField(blank=True, null=True)
    order_id = models.CharField(max_length=200, blank=True, null=True)
    blocked = models.BooleanField(default=False)

    custom_styles = models.TextField(blank=True)
    overwrite_styles = models.BooleanField(
        default=False,
        choices=((True, 'Overwrite default styles'), (False, 'Extend default styles')),
        verbose_name='')
    favicon = models.CharField(max_length=10, default="🐼")

    dashboard_styles = models.TextField(blank=True)

    date_format = models.CharField(max_length=32, blank=True)

    analytics_active = models.BooleanField(default=True)
    fathom_site_id = models.CharField(max_length=8, blank=True)
    public_analytics = models.BooleanField(default=False)

    post_template = models.TextField(blank=True)
    robots_txt = models.TextField(blank=True)

    @property
    def older_than_one_day(self):
        return (timezone.now() - self.created_date).days > 1

    @property
    def contains_code(self):
        return "```" in self.content

    @property
    def blank_bear_domain(self):
        return f'{self.subdomain}.{Site.objects.get_current().domain}'

    @property
    def bear_domain(self):
        return f'https://{self.blank_bear_domain}'

    @property
    def blank_useful_domain(self):
        if self.domain:
            return self.domain
        else:
            return f'{self.blank_bear_domain}'

    @property
    def useful_domain(self):
        return f'https://{self.blank_useful_domain}'

    @property
    def dynamic_useful_domain(self):
        return f'//{self.blank_useful_domain}'
    
    @property
    def is_empty(self):
        content_length = len(self.content) if self.content is not None else 0
        return not self.upgraded and content_length < 20 and self.post_set.count() == 0 and self.custom_styles == ""
    
    @property
    def tags(self):
        all_tags = []
        for post in Post.objects.filter(blog=self, publish=True, is_page=False, published_date__lt=timezone.now()):
            all_tags.extend(json.loads(post.all_tags))
            all_tags = list(set(all_tags))
        return sorted(all_tags)
    
    @property
    def last_posted(self):
        return self.post_set.filter(publish=True, published_date__lt=timezone.now()).order_by('-published_date').values_list('published_date', flat=True).first()

    def __str__(self):
        return f'{self.title} ({self.useful_domain})'


class Post(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    uid = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200)
    alias = models.CharField(max_length=200, blank=True)
    published_date = models.DateTimeField(blank=True)
    last_modified = models.DateTimeField(auto_now_add=True, blank=True)
    all_tags = models.TextField(default='[]')
    publish = models.BooleanField(default=True)
    make_discoverable = models.BooleanField(default=True)
    is_page = models.BooleanField(default=False)
    content = models.TextField()
    canonical_url = models.CharField(max_length=200, blank=True)
    meta_description = models.CharField(max_length=200, blank=True)
    meta_image = models.CharField(max_length=200, blank=True)
    lang = models.CharField(max_length=10, blank=True)
    class_name = models.CharField(max_length=200, blank=True)

    upvotes = models.IntegerField(default=0)
    score = models.FloatField(default=0)
    hidden = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)

    @property
    def contains_code(self):
        return "```" in self.content

    @property
    def tags(self):
        return sorted(json.loads(self.all_tags))

    def update_score(self):
        self.upvotes = self.upvote_set.count()

        if self.upvotes > 1:
            log_of_upvotes = log(self.upvotes, 10)

            seconds = self.published_date.timestamp()
            if seconds > 0:
                score = (log_of_upvotes) + ((seconds - 1577811600) / (14 * 86400))
                self.score = score

        self.save()
        return
    
    def save(self, *args, **kwargs):
        self.slug = self.slug.lower()
        if not self.all_tags:
            self.all_tags = '[]'
        
        # Create unique random identifier
        if not self.uid:
            allowed_chars = string.ascii_letters.replace('O', '').replace('l', '')
            self.uid = ''.join(random.choice(allowed_chars) for _ in range(20))

        super(Post, self).save(*args, **kwargs)

    def __str__(self):
        return self.title


class Upvote(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    hash_id = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.created_date.strftime('%d %b %Y, %X')} - {self.hash_id} - {self.post}"


class Hit(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    hash_id = models.CharField(max_length=200)
    referrer = models.URLField(default=None, blank=True, null=True)
    country = models.CharField(max_length=200, blank=True)
    device = models.CharField(max_length=200, blank=True)
    browser = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return f"{self.created_date.strftime('%d %b %Y, %X')} - {self.hash_id} - {self.post}"


class Subscriber(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    email_address = models.EmailField()
    subscribed_date = models.DateTimeField(auto_now_add=True)


class Stylesheet(models.Model):
    title = models.CharField(max_length=100)
    identifier = models.SlugField(max_length=100, unique=True)
    css = models.TextField(blank=True)
    external = models.BooleanField(default=False)
    image = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.title


# Singleton model to store Bear specific settings
class PersistentStore(models.Model):
    last_executed = models.DateTimeField(default=timezone.now)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super(PersistentStore, self).save(*args, **kwargs)

    def __str__(self):
        return self.last_executed.strftime('%d %B %Y, %I:%M %p')
