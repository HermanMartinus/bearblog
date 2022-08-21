from email.policy import default
from django import forms
from django.core.validators import RegexValidator, ValidationError
from django.template.defaultfilters import slugify

from .helpers import is_protected, root
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
        label="Home page",
        help_text='''
        Learn <a href='https://herman.bearblog.dev/markdown-cheatsheet/' target='_blank'>markdown syntax</a>
        <span style="float:right">
            <a id='upload-image'>Insert image</a>
        </span>''',
        widget=forms.Textarea(attrs={'rows': 20, 'cols': 40}),
        required=False,
    )

    meta_description = forms.CharField(
        label="Meta description",
        help_text="Max 200 characters",
        widget=forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        required=False
    )

    lang = forms.CharField(
        label="lang",
        help_text="<a href='https://docs.bearblog.dev/language-cheatsheet' target='_blank'>Language code cheatsheet</a>",
        widget=forms.TextInput(attrs={'class': "inline"}),
        required=False
    )

    class Meta:
        model = Blog
        fields = ('title', 'subdomain', 'content', 'meta_description', 'lang')


class NavForm(forms.ModelForm):
    nav = forms.CharField(
        label="Nav",
        widget=forms.Textarea(attrs={'rows': 10, 'cols': 40}),
        help_text='''Add navigation links in
                    <a href='https://herman.bearblog.dev/markdown-cheatsheet/#links' target='_blank'>
                        Markdown
                    </a>
                    <br>
                    [Home](/) [About me](/about-me/) Blog(/blog/)
                    <br>
                    To add a page to the nav menu set the link value to the link of a published post or page
                    ''',
        required=False,
    )

    class Meta:
        model = Blog
        fields = ('nav',)


class StyleForm(forms.ModelForm):
    custom_styles = forms.CharField(
        label="Styles",
        widget=forms.Textarea(),
        required=False
    )

    class Meta:
        model = Blog
        widgets = {
            'overwrite_styles': forms.RadioSelect
        }
        fields = ('custom_styles', 'overwrite_styles')


class DomainForm(forms.ModelForm):
    domain = forms.CharField(
        max_length=128,
        label="Custom domain",
        validators=[domain_validator, protected_domains_validator],
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
        self.user = user

    slug = forms.SlugField(
        label="Permalink",
        help_text="eg: 'why-i-like-bears'",
        validators=[link_validator],
        required=False
    )

    published_date = forms.DateTimeField(
        label="Publish date",
        help_text="Leave empty to post now",
        required=False,
        widget=DateInput()
    )

    content = forms.CharField(
        label="Content (markdown)",
        help_text='''
        <a href='https://herman.bearblog.dev/markdown-cheatsheet/' target='_blank'>Markdown cheatsheet</a> |
        <a id='upload-image'>Insert image</a>
        <button id='toggle-full-screen'>&#10529;</button>''',
        widget=forms.Textarea(attrs={'rows': 20, 'cols': 40}),
    )

    meta_description = forms.CharField(
        label="Meta description",
        help_text="Max 200 characters",
        widget=forms.Textarea(attrs={'rows': 2, 'cols': 40}),
        required=False,
    )

    meta_image = forms.CharField(
        label="Meta image URL",
        required=False
    )

    canonical_url = forms.CharField(
        label="Canonical url",
        help_text="<a href='https://ahrefs.com/blog/canonical-tags/#what-is-a-canonical-tag' target='_blank'>Learn more</a>",
        required=False
    )

    publish = forms.BooleanField(
        widget=forms.HiddenInput(),
        required=False
    )

    make_discoverable = forms.BooleanField(
        help_text=f"Show in the <a href='https://{root()}/discover/' target='_blank'>discovery feed</a>",
        required=False,
        initial=True)

    def clean_slug(self):
        if self.cleaned_data['slug']:
            slug = self.cleaned_data['slug']
        else:
            slug = slugify(self.cleaned_data['title'])

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
        fields = (
            'title',
            'slug',
            'canonical_url',
            'published_date',
            'content',
            'meta_description',
            'meta_image',
            'tags',
            'is_page',
            'publish',
            'make_discoverable')


class AccountForm(forms.ModelForm):
    old_editor = forms.BooleanField(
        label="Use the old editor",
        required=False,
        help_text="<br>Note: the old editor does not support real-time previews"
    )

    fathom_site_id = forms.CharField(
        max_length=20,
        required=False,
        help_text="More in-depth analytics using <a href='https://usefathom.com/ref/GMAGWL' target='_blank'>Fathom</a>."
    )

    class Meta:
        model = Blog
        fields = ('old_editor', 'fathom_site_id')


class PostTemplateForm(forms.ModelForm):
    post_template = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 20, 'cols': 40}),
        required=False,
        label=''
    )

    class Meta:
        model = Blog
        fields = ('post_template',)
