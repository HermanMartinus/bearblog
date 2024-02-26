from django.db import migrations, models
import django.db.models.deletion
from django.conf import settings


def create_user_settings_and_copy_blog_data(apps, schema_editor):
    User = apps.get_model(settings.AUTH_USER_MODEL)  # Get the User model
    Blog = apps.get_model('blogs', 'Blog')  # Get the Blog model
    UserSettings = apps.get_model('blogs', 'UserSettings')  # Get the UserSettings model

    for user in User.objects.all():
        # Try to find the first blog associated with the user
        first_blog = Blog.objects.filter(user=user).first()
        
        # Create a new UserSettings instance for the user
        user_settings, created = UserSettings.objects.get_or_create(
            user=user,
            defaults={
                'upgraded': first_blog.upgraded if first_blog else False,
                'upgraded_date': first_blog.upgraded_date if first_blog else None,
                'order_id': first_blog.order_id if first_blog else None,
            }
        )
        
        # If UserSettings already existed, optionally update fields from the first blog
        if not created and first_blog:
            user_settings.upgraded = first_blog.upgraded
            user_settings.upgraded_date = first_blog.upgraded_date
            user_settings.order_id = first_blog.order_id
            user_settings.save()

class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('blogs', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserSettings',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('upgraded', models.BooleanField(default=False)),
                ('upgraded_date', models.DateTimeField(blank=True, null=True)),
                ('order_id', models.CharField(blank=True, max_length=200, null=True)),
                ('user', models.OneToOneField(blank=True, on_delete=django.db.models.deletion.CASCADE, related_name='settings', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(create_user_settings_and_copy_blog_data),
    ]
