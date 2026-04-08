from django.apps import AppConfig


class BlogsConfig(AppConfig):
    name = 'blogs'

    def ready(self):
        # TODO: Investigate whether this will work robustly
        # from blogs.scheduler import start_heartbeat
        # start_heartbeat()
        pass

