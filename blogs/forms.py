from django import forms

from .models import Blog

class NavForm(forms.ModelForm):
    nav = forms.CharField(
        label="Nav",
        widget=forms.Textarea(attrs={'rows': 10, 'cols': 40}),
        help_text='''<span>Add navigation links in
                    <a href='https://herman.bearblog.dev/markdown-cheatsheet/#links' target='_blank'>
                        markdown
                    </a>
                    <br>
                    [Home](/) [About me](/about-me/) [Blog](/blog/)
                    <br>
                    To add a page to the nav menu set the link value to the link of a published post or page</span>
                    ''',
        required=False,
    )

    class Meta:
        model = Blog
        fields = ('nav',)


class StyleForm(forms.ModelForm):
    custom_styles = forms.CharField(
        label="Edit theme CSS",
        widget=forms.Textarea(),
        required=False,
        help_text="Ensure styling caters to existing dark mode CSS."
    )

    class Meta:
        model = Blog
        fields = ('custom_styles', )


class AccountForm(forms.ModelForm):
    analytics_active = forms.BooleanField(
        label="Collect blog analytics",
        required=False
    )

    fathom_site_id = forms.CharField(
        max_length=20,
        required=False,
        help_text="<span>More in-depth analytics using <a href='https://usefathom.com/ref/GMAGWL' target='_blank'>Fathom</a>.</span>"
    )

    class Meta:
        model = Blog
        fields = ('analytics_active', 'fathom_site_id', 'blog_path')


class AnalyticsForm(forms.ModelForm):
    fathom_site_id = forms.CharField(
        max_length=20,
        required=False,
        help_text="8 upper-case characters"
    )

    class Meta:
        model = Blog
        fields = ('fathom_site_id',)


class PostTemplateForm(forms.ModelForm):
    post_template = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 20, 'cols': 40, 'placeholder': "title: \nmeta_description: \n___\nHello world!"}),
        required=False,
        label='',
        help_text="This will pre-populate on all new posts. Separate header and body content with ___."
    )

    class Meta:
        model = Blog
        fields = ('post_template',)
