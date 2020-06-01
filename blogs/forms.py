from django import forms
from django.core.validators import RegexValidator, ValidationError

from .helpers import is_protected
from .models import Blog, Post

subdomain_validator = RegexValidator(
    r"^(?![0-9]+$)(?!-)[a-zA-Z0-9-]{,63}(?<!-)$",
    "Please enter a valid subdomain")
link_validator = RegexValidator(
    r"[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?",
    "Please enter a valid link slug")
domain_validator = RegexValidator(
    r"^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$",
    "Please enter a valid domain")
script_validator = RegexValidator(
    r"<[^>]*script",
    "No script tags allowed", inverse_match=True)
tags_validator = RegexValidator(
    r"([^,]+)",
    "These tags are not valid (eg: tag1, tag2, tag3)")


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kwargs):
        kwargs["format"] = "%Y-%m-%d"
        super().__init__(**kwargs)


class TimeInput(forms.TimeInput):
    input_type = "time"


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kwargs):
        kwargs["format"] = "%Y-%m-%dT%H:%M"
        super().__init__(**kwargs)


def protected_domains_validator(value):
    if is_protected(value):
        raise ValidationError(
            'Protected subdomain',
            params={'value': value},
        )


class BlogForm(forms.ModelForm):
    content = forms.CharField(
        label="Homepage content (markdown)",
        widget=forms.Textarea(),
        required=False,
        validators=[script_validator]
    )
    subdomain = forms.SlugField(
        label="Subdomain",
        help_text=".bearblog.dev",
        validators=[subdomain_validator, protected_domains_validator]
    )

    class Meta:
        model = Blog
        fields = ('title', 'subdomain', 'content',)


class DomainForm(forms.ModelForm):
    domain = forms.CharField(
        max_length=128,
        label="Custom domain",
        help_text="eg: 'example.com'",
        validators=[domain_validator],
        required=False
    )

    def clean_domain(self):
        domain = self.cleaned_data['domain']

        if domain == '':
            return domain

        matching_blogs = Blog.objects.filter(domain=domain)

        if self.instance:
            matching_blogs = matching_blogs.exclude(pk=self.instance.pk)
        if matching_blogs.exists():
            raise ValidationError(f"Domain '{domain}'  already exists.")
        else:
            return domain

    class Meta:
        model = Blog
        fields = ('domain',)


class PostForm(forms.ModelForm):
    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["published_date"].widget = DateInput()
        self.user = user

    slug = forms.SlugField(
        label="Permalink",
        help_text="eg: 'why-i-like-bears'",
        validators=[link_validator]
    )

    published_date = forms.DateTimeField(
        label="Date",
        help_text="eg: '2020-05-31'"
    )

    content = forms.CharField(
        label="Content (markdown)",
        help_text="Add hastags preceeded by a backslash for categorization eg: '\#bear #blog #bearblog'",
        widget=forms.Textarea(),
        validators=[script_validator]
    )

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
        fields = ('title', 'slug', 'published_date', 'content', 'is_page', 'publish', 'show_in_feed')
