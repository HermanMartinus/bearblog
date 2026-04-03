from django.apps import AppConfig


class BlogsConfig(AppConfig):
    name = 'blogs'

    def ready(self):
        from blogs.scheduler import start_heartbeat
        start_heartbeat()

