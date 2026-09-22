from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blogs", "0064_remove_blog_optimise_images"),
    ]

    operations = [
        # Historical field, removed in 0069; use a portable type for SQLite.
        migrations.AddField(
            model_name="post",
            name="search_vector",
            field=models.TextField(null=True),
        ),
    ]
