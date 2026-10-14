from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0081_post_published_date_nullable'),
    ]

    operations = [
        migrations.RenameField(
            model_name='post',
            old_name='make_discoverable',
            new_name='discoverable',
        ),
    ]
