from conf.settings import *

ROOT_URLCONF = 'conf.urls_public'

INSTALLED_APPS = [app for app in INSTALLED_APPS if app not in [
    'django.contrib.admin',
]]

MIDDLEWARE = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]
