# Generated by Django 3.2.23 on 2024-09-04 08:51

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0025_usersettings_max_blogs'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blog',
            name='date_format',
            field=models.CharField(blank=True, default='d M, Y', max_length=32),
        ),
    ]
