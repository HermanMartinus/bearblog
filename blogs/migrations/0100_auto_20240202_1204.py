# Generated by Django 3.1.14 on 2024-02-02 12:04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0099_blog_rss_alias'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blog',
            name='rss_alias',
            field=models.CharField(blank=True, max_length=100),
        ),
    ]