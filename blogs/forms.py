from django import forms
from django.core.validators import RegexValidator, ValidationError

from .models import Blog, Post

subdomain_validator = RegexValidator(r"[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?", "Please enter a valid subdomain")
link_validator = RegexValidator(r"[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?", "Please enter a valid link slug")
domain_validator = RegexValidator(r"^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$", "Please enter a valid domain")
script_validator = RegexValidator(r"<[^>]*script", "No script tags allowed", inverse_match=True)

class BlogForm(forms.ModelForm):
    content = forms.CharField(label="Homepage content (markdown)", widget=forms.Textarea(), required=False, validators=[script_validator])
    subdomain = forms.SlugField(label="Subdomain", help_text=".bearblog.dev", validators=[subdomain_validator])
    domain = forms.CharField(max_length=128, label="Custom domain (beta & optional)", help_text="eg: 'example.com' (.dev and .app not supported yet, but will be soon)", validators=[domain_validator], required=False)

    def clean_domain(self):
        domain = self.cleaned_data['domain']
        
        if domain == '':
            return domain
            
        matching_blogs = Blog.objects.filter(domain=domain)

        if self.instance:
            matching_blogs = matching_blogs.exclude(pk=self.instance.pk)
        if matching_blogs.exists():
            raise ValidationError(f"Blog domain '{domain}'  already exists.")
        else:
            return domain
        
    class Meta:
        model = Blog
        fields = ('title', 'subdomain', 'domain', 'content',)

class PostForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        self.user = user
        super(PostForm, self).__init__(*args, **kwargs)

    slug = forms.SlugField(label="Permalink", help_text="(eg: 'why-i-like-bears')", validators=[link_validator])
    content = forms.CharField(label="Content (markdown)", widget=forms.Textarea(), validators=[script_validator])

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