from django.db import models
from django.contrib.auth.models import User

class Blog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, blank=True)
    title = models.CharField(max_length=200)
    created_date = models.DateTimeField(auto_now_add=True, blank=True)
    subdomain = models.SlugField(max_length=100, unique=True)
    content = models.TextField(blank=True)

    def __str__(self):
        return self.title

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
