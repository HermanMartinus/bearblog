from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0013_alter_post_options'),
    ]

    operations = [
        migrations.CreateModel(
            name='Upvote',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('session_key', models.CharField(max_length=40)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('post', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='upvotes', to='blogs.post')),
            ],
            options={
                'unique_together': {('post', 'session_key')},
            },
        ),
    ]
