import django.contrib.postgres.search
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("blogs", "0064_remove_blog_optimise_images"),
    ]

    operations = [
        # Add the search_vector field
        migrations.AddField(
            model_name="post",
            name="search_vector",
            field=django.contrib.postgres.search.SearchVectorField(null=True),
        ),
        # Add GIN index on the field
        migrations.RunSQL(
            sql="CREATE INDEX blogs_post_search_vector_gin ON blogs_post USING GIN (search_vector);",
            reverse_sql="DROP INDEX IF EXISTS blogs_post_search_vector_gin;",
        ),
    ]
