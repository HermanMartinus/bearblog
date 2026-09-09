from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0072_upvote_marked_signals_upvote_token_age_bucket'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='upvote',
            name='marked',
        ),
        migrations.RemoveField(
            model_name='upvote',
            name='marked_signals',
        ),
        migrations.RemoveField(
            model_name='upvote',
            name='token_age_bucket',
        ),
    ]
