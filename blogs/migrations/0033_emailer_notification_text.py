# Generated by Django 3.0.7 on 2021-04-08 09:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0032_auto_20210408_0927'),
    ]

    operations = [
        migrations.AddField(
            model_name='emailer',
            name='notification_text',
            field=models.TextField(blank=True),
        ),
    ]
