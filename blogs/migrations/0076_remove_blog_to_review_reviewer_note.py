from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0075_remove_shadow_votes_and_hidden_fields'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='blog',
            name='reviewer_note',
        ),
        migrations.RemoveField(
            model_name='blog',
            name='to_review',
        ),
    ]
