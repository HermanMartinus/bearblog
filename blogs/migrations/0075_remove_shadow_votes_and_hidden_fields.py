from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('blogs', '0074_remove_blog_public_analytics'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='blog',
            name='hidden',
        ),
        migrations.RemoveField(
            model_name='post',
            name='hidden',
        ),
        migrations.RemoveField(
            model_name='post',
            name='shadow_votes',
        ),
    ]
