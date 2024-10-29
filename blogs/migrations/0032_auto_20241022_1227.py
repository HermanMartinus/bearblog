# Generated by Django 3.2.23 on 2024-10-22 12:27

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0031_alter_post_uid'),
    ]

    operations = [
        migrations.AlterField(
            model_name='blog',
            name='domain',
            field=models.CharField(blank=True, db_index=True, max_length=128, null=True),
        ),
        migrations.AlterField(
            model_name='blog',
            name='hidden',
            field=models.BooleanField(db_index=True, default=False),
        ),
        migrations.AlterField(
            model_name='blog',
            name='reviewed',
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]