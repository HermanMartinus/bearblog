# Generated by Django 3.2.23 on 2024-09-26 07:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0026_alter_blog_date_format'),
    ]

    operations = [
        migrations.AddField(
            model_name='blog',
            name='optimise_images',
            field=models.BooleanField(default=True),
        ),
    ]
