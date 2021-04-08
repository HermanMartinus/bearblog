from django import forms
from django.core.validators import RegexValidator, ValidationError

from .helpers import is_protected, root, check_records
from .models import Blog, Post, Emailer

subdomain_validator = RegexValidator(
    r"^(?![0-9]+$)(?!-)[a-zA-Z0-9-]{,63}(?<!-)$",
    "Please enter a valid subdomain")
link_validator = RegexValidator(
    r"[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?",
    "Please enter a valid link slug")
domain_validator = RegexValidator(
    r"^([a-z0-9]+(-[a-z0-9]+)*\.)+[a-z]{2,}$",
    "Please enter a valid domain")


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
            'Protected domain/subdomain',
            params={'value': value},
        )


class BlogForm(forms.ModelForm):
    subdomain = forms.SlugField(
        label="Subdomain",
        help_text=".bearblog.dev | <a href='domain/'>Add a custom domain</a>",
        validators=[subdomain_validator, protected_domains_validator]
    )

    content = forms.CharField(
        label="Homepage content (markdown)",
        help_text="<a href='https://simplemde.com/markdown-guide' target='_blank'>Markdown cheatsheet</a>",
        widget=forms.Textarea(attrs={'rows': 20, 'cols': 40}),
        required=False,
    )

    class Meta:
        model = Blog
        fields = ('title', 'subdomain', 'content',)


class StyleForm(forms.ModelForm):
    favicon = forms.CharField(
        max_length=4,
        help_text="<a href='https://getemoji.com/' target='_blank'>Emoji cheatsheet</a>",
        required=True
    )

    external_stylesheet = forms.CharField(
        help_text="<br>List of <a href='https://www.cssbed.com/' target='_blank'>no-class css themes</a> (only paste the CDN link)",
        required=False,
    )

    custom_styles = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 20, 'cols': 40}),
        required=False,
    )

    class Meta:
        model = Blog
        fields = ('favicon', 'external_stylesheet', 'custom_styles',)


class DomainForm(forms.ModelForm):
    domain = forms.CharField(
        max_length=128,
        label="Custom domain",
        help_text="eg: 'example.com'",
        validators=[domain_validator, protected_domains_validator],
        required=False
    )

    def clean_domain(self):
        domain = self.cleaned_data['domain']

        if domain == '':
            return domain

        if not check_records(domain):
            raise ValidationError(f"TXT record for '{domain}' has not been set.")

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
        help_text="eg: '2020-05-31' (leave empty to post now)",
        required=False
    )

    content = forms.CharField(
        label="Content (markdown)",
        help_text="<a href='https://simplemde.com/markdown-guide' target='_blank'>Markdown cheatsheet</a>",
        widget=forms.Textarea(attrs={'rows': 20, 'cols': 40}),
    )

    canonical_url = forms.CharField(
        label="Canonical url (optional)",
        help_text="<a href='https://ahrefs.com/blog/canonical-tags/#what-is-a-canonical-tag' target='_blank'>Learn more</a>",
        required=False
    )

    show_in_feed = forms.BooleanField(
        help_text=f"Make post discoverable at <a href='http://{root()}/discover/' target='_blank'>{root()}/discover</a>",
        required=False,
        initial=True)

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
        fields = ('title', 'slug', 'canonical_url', 'published_date', 'content', 'tags', 'is_page', 'publish', 'show_in_feed')


class AnalyticsForm(forms.ModelForm):
    class Meta:
        model = Blog
        fields = ('fathom_site_id',)


class NotifyForm(forms.ModelForm):
    notify = forms.BooleanField(
        label="Notify subscribers about new posts?",
        help_text="<br>This will send an email to subscribers letting them know you've just published a new post",
        required=False)
    notification_text = forms.CharField(
        help_text="The link to your new post will be appended to this notification",
        required=False,
        widget=forms.Textarea(attrs={'rows': 5, 'cols': 40}),
    )

    class Meta:
        model = Emailer
        fields = ('notify', 'notification_text')
