from django.db import migrations, models


def backfill_marked_signals(apps, schema_editor):
    Upvote = apps.get_model('blogs', 'Upvote')
    pending = []

    queryset = Upvote.objects.filter(marked=True).exclude(marked_reason='')
    for upvote in queryset.iterator(chunk_size=1000):
        upvote.marked_signals = [upvote.marked_reason]
        pending.append(upvote)
        if len(pending) == 1000:
            Upvote.objects.bulk_update(pending, ['marked_signals'])
            pending = []

    if pending:
        Upvote.objects.bulk_update(pending, ['marked_signals'])


class Migration(migrations.Migration):

    dependencies = [
        ('blogs', '0071_upvote_marked_upvote_marked_reason'),
    ]

    operations = [
        migrations.AddField(
            model_name='upvote',
            name='marked_signals',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.AddField(
            model_name='upvote',
            name='token_age_bucket',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.RunPython(backfill_marked_signals, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='upvote',
            name='marked_reason',
        ),
    ]
