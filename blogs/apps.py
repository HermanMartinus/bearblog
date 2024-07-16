from django.apps import AppConfig
import logging

logger = logging.getLogger(__name__)


class BlogsConfig(AppConfig):
    name = 'blogs'

    def ready(self):
        print("ʕ≧ᴥ≦ʔ Bear has been activated!")
        logger.log(1, "ʕ≧ᴥ≦ʔ Bear has been activated!", exc_info=True)

