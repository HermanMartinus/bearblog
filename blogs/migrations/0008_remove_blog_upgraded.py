# Generated by Django 3.1.14 on 2024-02-28 11:47

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0007_remove_blog_order_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='blog',
            name='upgraded',
        ),
    ]