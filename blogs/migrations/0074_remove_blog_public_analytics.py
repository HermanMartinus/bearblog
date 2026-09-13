from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('blogs', '0073_remove_upvote_marking_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='blog',
            name='public_analytics',
        ),
    ]
