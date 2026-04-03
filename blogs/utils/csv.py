import csv
import io
from django.http import HttpResponse


def _header_name(field):
    return field.replace('_', ' ')


def render_to_csv_response(queryset):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename=data.csv'
    _write_csv(queryset, response)
    return response


def write_csv(queryset, buffer):
    text_buffer = io.TextIOWrapper(buffer, encoding='utf-8', newline='')
    _write_csv(queryset, text_buffer)
    text_buffer.detach()


def _write_csv(queryset, output):
    output.write('\ufeff')
    writer = None
    for row in queryset:
        if writer is None:
            headers = list(row.keys())
            writer = csv.DictWriter(output, fieldnames=headers)
            writer.writerow({h: _header_name(h) for h in headers})
        writer.writerow(row)
