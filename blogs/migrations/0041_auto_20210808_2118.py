# Generated by Django 3.0.7 on 2021-08-08 21:18

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0040_auto_20210719_1819'),
    ]

    operations = [
        migrations.AddField(
            model_name='blog',
            name='subscribed',
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name='blog',
            name='nav',
            field=models.CharField(blank=True, default='[Home](/)\n[Blog](/blog/)', max_length=500),
        ),
    ]