from django.utils import timezone
from django.db import models
from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.cache import cache

from allauth.account.models import EmailAddress

import json
from math import log
import random
import string
import hashlib


class UserSettings(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='settings', blank=True)
    upgraded = models.BooleanField(default=False)
    upgraded_date = models.DateTimeField(blank=True, null=True)
    order_id = models.CharField(max_length=100, blank=True, null=True)

    dashboard_styles = models.TextField(blank=True)
    dashboard_footer = models.TextField(blank=True)

    def __str__(self):
        return f'{self.user} - Settings'


# On User save, create UserSettigs
@receiver(post_save, sender=User)
def create_user_settings(sender, instance, **kwargs):
    user_settings, created = UserSettings.objects.get_or_create(user=instance)
    if user_settings.upgraded:
        user_settings.user.blogs.update(reviewed=True)


class Blog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True, related_name='blogs')
    title = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True, blank=True)
    last_modified = models.DateTimeField(auto_now_add=True, blank=True)
    subdomain = models.SlugField(max_length=100, unique=True)
    domain = models.CharField(max_length=128, blank=True, null=True)
    auth_token = models.CharField(max_length=128, blank=True)

    nav = models.TextField(default="[Home](/) [Blog](/blog/)", blank=True)
    content = models.TextField(default="Hello World!", blank=True)
    meta_description = models.CharField(max_length=200, blank=True)
    meta_image = models.CharField(max_length=200, blank=True)
    lang = models.CharField(max_length=10, default='en', blank=True)
    meta_tag = models.CharField(max_length=500, blank=True)
    blog_path = models.CharField(max_length=200, default="blog")
    header_directive = models.TextField(blank=True)
    footer_directive = models.TextField(blank=True)

    dodginess_score = models.FloatField(default=0)
    reviewed = models.BooleanField(default=False)
    ignored_date = models.DateTimeField(blank=True, null=True)
    to_review = models.BooleanField(default=False)
    reviewer_note = models.TextField(blank=True)
    hidden = models.BooleanField(default=False)

    custom_styles = models.TextField(blank=True)
    overwrite_styles = models.BooleanField(
        default=False,
        choices=((True, 'Overwrite default styles'), (False, 'Extend default styles')),
        verbose_name='')
    favicon = models.CharField(max_length=100, default="🐼", blank=True)

    date_format = models.CharField(max_length=32, blank=True)

    analytics_active = models.BooleanField(default=True)
    fathom_site_id = models.CharField(max_length=8, blank=True)
    public_analytics = models.BooleanField(default=False)

    post_template = models.TextField(blank=True)
    robots_txt = models.TextField(blank=True)
    rss_alias = models.CharField(max_length=100, blank=True)
    
    @property
    def older_than_one_day(self):
        return (timezone.now() - self.created_date).days > 1

    @property
    def user_email_verified(self):
        return EmailAddress.objects.filter(user=self.user, verified=True).exists()

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
        return not self.user.settings.upgraded and content_length < 20 and self.posts.count() == 0 and self.custom_styles == ""
    
    @property
    def tags(self):
        all_tags = []
        for post in Post.objects.filter(blog=self, publish=True, is_page=False, published_date__lt=timezone.now()):
            all_tags.extend(json.loads(post.all_tags))
            all_tags = list(set(all_tags))
        return sorted(all_tags)
    
    @property
    def last_posted(self):
        return self.posts.filter(publish=True, published_date__lt=timezone.now()).order_by('-published_date').values_list('published_date', flat=True).first()

    def generate_auth_token(self):
        allowed_chars = string.ascii_letters.replace('O', '').replace('l', '')
        self.auth_token = ''.join(random.choice(allowed_chars) for _ in range(30))
        self.save()

    def determine_dodginess(self):
        persistent_store = PersistentStore.load()
        dodgy_term_count = 0
        all_content = f"{self.title} {self.content}"
        
        post = self.posts.first()
        if post:
            all_content += f"{post.title} {post.content}"

        for term in persistent_store.highlight_terms:
            dodgy_term_count += all_content.lower().count(term.lower())

        self.dodginess_score = dodgy_term_count

    def save(self, *args, **kwargs):
        if self.user.settings.upgraded:
            self.reviewed = True
        
        if not self.reviewed:
            self.determine_dodginess()
        
        # Invalidate feed cache
        CACHE_KEY = f'{self.subdomain}_all_posts'
        cache.delete(CACHE_KEY)

        super(Blog, self).save(*args, **kwargs)

    def __str__(self):
        return f'{self.title} ({self.useful_domain})'


class Post(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='posts')
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

    first_published_at = models.DateTimeField(blank=True, null=True)
    upvotes = models.IntegerField(default=0)
    shadow_votes = models.IntegerField(default=0)
    score = models.FloatField(default=0)
    hidden = models.BooleanField(default=False)
    pinned = models.BooleanField(default=False)

    @property
    def contains_code(self):
        return "```" in self.content

    @property
    def tags(self):
        return sorted(json.loads(self.all_tags))
    
    @property
    def token(self):
        return hashlib.sha256(self.uid.encode()).hexdigest()[0:10]

    def update_score(self):
        self.upvotes = self.upvote_set.count()
        upvotes = self.upvotes

        if upvotes > 1: 
            # Cap upvotes at 40 so they don't stick to the top forever
            if upvotes > 40:
                upvotes = 40

            upvotes += self.shadow_votes

            log_of_upvotes = log(upvotes, 10)

            posted_at = self.first_published_at or self.published_date

            seconds = posted_at.timestamp()
            if seconds > 0:
                gravity = 14
                score = (log_of_upvotes) + ((seconds - 1577811600) / (gravity * 86400))
                self.score = score
    
    def save(self, *args, **kwargs):
        self.slug = self.slug.lower()
        if not self.all_tags:
            self.all_tags = '[]'
        
        # Create unique random identifier
        if not self.uid:
            allowed_chars = string.ascii_letters.replace('O', '').replace('l', '')
            self.uid = ''.join(random.choice(allowed_chars) for _ in range(20))

        # Set first_published_at for score calculation
        if self.publish and self.first_published_at is None:
            self.first_published_at = self.published_date or timezone.now()

        # Update the score for the discover feed
        self.update_score()

        # Save blog to trigger determine_dodginess
        self.blog.save()

        super(Post, self).save(*args, **kwargs)

    def __str__(self):
        return self.title


class Upvote(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE)
    created_date = models.DateTimeField(auto_now_add=True)
    hash_id = models.CharField(max_length=200)

    def save(self, *args, **kwargs):
        # Save the Upvote instance
        super(Upvote, self).save(*args, **kwargs)
        
        # Update the post score on post save
        self.post.save()

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
    
    def __str__(self):
        return f"{self.blog.title} - {self.email_address}"


class RssSubscriber(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE)
    access_date = models.DateTimeField(auto_now_add=True)
    hash_id = models.CharField(max_length=200)

    def __str__(self):
        return f"{self.access_date.strftime('%d %b %Y, %X')} - {self.blog.title} - {self.hash_id}"


class Stylesheet(models.Model):
    title = models.CharField(max_length=100)
    identifier = models.SlugField(max_length=100, unique=True)
    css = models.TextField(blank=True)
    external = models.BooleanField(default=False)
    image = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.title


class Media(models.Model):
    blog = models.ForeignKey(Blog, on_delete=models.CASCADE, related_name='media')
    url = models.URLField(max_length=500)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.blog.subdomain} - {self.url} - {self.created_at}"
    

# Singleton model to store Bear specific settings
class PersistentStore(models.Model):
    last_executed = models.DateTimeField(default=timezone.now)
    review_ignore_terms = models.TextField(blank=True, default='[]')
    review_highlight_terms = models.TextField(blank=True, default='[]')

    @property
    def ignore_terms(self):
        return sorted(json.loads(self.review_ignore_terms))
    
    @property
    def highlight_terms(self):
        return sorted(json.loads(self.review_highlight_terms))
    
    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj

    def save(self, *args, **kwargs):
        self.pk = 1
        super(PersistentStore, self).save(*args, **kwargs)

    def __str__(self):
        return self.last_executed.strftime('%d %B %Y, %I:%M %p')
