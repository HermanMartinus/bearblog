from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Test command for task scheduler'

    def handle(self, *args, **kwargs):
        self.stdout.write(self.style.SUCCESS('Hello world!'))
