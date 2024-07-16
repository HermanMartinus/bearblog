from django.apps import AppConfig


class BlogsConfig(AppConfig):
    name = 'blogs'

    def ready(self):
        print("ʕ≧ᴥ≦ʔ Bear has been activated!")

