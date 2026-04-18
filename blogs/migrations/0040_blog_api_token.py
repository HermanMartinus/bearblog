from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0039_blog_reviewed'),
    ]

    operations = [
        migrations.AddField(
            model_name='blog',
            name='api_token',
            field=models.CharField(blank=True, max_length=64, null=True, unique=True),
        ),
    ]
