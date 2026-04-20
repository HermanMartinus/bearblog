from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("blogs", "0066_remove_blog_analytics_update"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="content_length",
            field=models.IntegerField(default=0, db_index=True),
        ),
        migrations.RunSQL(
            sql="UPDATE blogs_post SET content_length = LENGTH(COALESCE(content, ''));",
            reverse_sql="UPDATE blogs_post SET content_length = 0;",
        ),
    ]
