# Generated by Django 3.1.14 on 2023-04-25 08:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0082_blog_reviewer_note'),
    ]

    operations = [
        migrations.AddField(
            model_name='blog',
            name='footer_directive',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='blog',
            name='header_directive',
            field=models.TextField(blank=True),
        ),
    ]