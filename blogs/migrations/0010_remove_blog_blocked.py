# Generated by Django 3.1.14 on 2024-02-28 11:57

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0009_auto_20240228_1149'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='blog',
            name='blocked',
        ),
    ]