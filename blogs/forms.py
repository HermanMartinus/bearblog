from django import forms
from django.core.validators import RegexValidator, ValidationError

from .models import Blog, Post

subdomain_validator = RegexValidator(r"[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?", "Please enter a valid subdomain")
link_validator = RegexValidator(r"[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?", "Please enter a valid link slug")

class BlogForm(forms.ModelForm):
    content = forms.CharField(label="Homepage content (markdown)", widget=forms.Textarea())
    subdomain = forms.SlugField(label="Subdomain", help_text=".bearblog.dev", validators=[subdomain_validator])
    class Meta:
        model = Blog
        fields = ('title', 'subdomain', 'content',)

class PostForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(PostForm, self).__init__(*args, **kwargs)

    slug = forms.SlugField(label="Permalink", help_text="(eg: 'why-i-like-bears')", validators=[link_validator])
    content = forms.CharField(label="Content (markdown)", widget=forms.Textarea())

    def clean_slug(self):
        slug = self.cleaned_data['slug']
        
        blog = Blog.objects.get(user=self.user)
        matching_posts = Post.objects.filter(blog=blog, slug=slug)
        
        if self.instance:
            matching_posts = matching_posts.exclude(pk=self.instance.pk)
        if matching_posts.exists():
            raise ValidationError(f"Post link: '{slug}'  already exist.")
        else:
            return slug

    class Meta:
        model = Post
        fields = ('title', 'slug', 'content', 'is_page', 'publish')