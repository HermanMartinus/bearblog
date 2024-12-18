import sentry_sdk
import os
import dj_database_url
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_NAME = "🐼 BEARBLOG 🐼"

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.getenv('SECRET')
LEMONSQUEEZY_SIGNATURE = os.getenv('LEMONSQUEEZY_SIGNATURE')

DEBUG = (os.getenv('DEBUG') == 'True')

if not DEBUG:
    # Logging settings
    def before_send(event, hint):
        """Don't log django.DisallowedHost errors."""
        if 'log_record' in hint:
            if hint['log_record'].name == 'django.security.DisallowedHost':
                return None
        return event

    sentry_sdk.init(
        dsn=os.getenv("SENTRY_DSN"),
        auto_session_tracking=False,
        traces_sample_rate=0,
        profiles_sample_rate=0,
        send_default_pii=True,
        before_send=before_send
    )

    # ADMINS = (('Webmaster', os.getenv('ADMIN_EMAIL')),)

# Host & proxy settings
ALLOWED_HOSTS = ['*']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

X_FRAME_OPTIONS = 'ALLOWALL'

INTERNAL_IPS = ['127.0.0.1']

# Application definition
SITE_ID = 1

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.sites',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'blogs.apps.BlogsConfig',
    'allauth.account',
    'allauth.socialaccount',
    'debug_toolbar',
    'pygmentify',
]

AUTHENTICATION_BACKENDS = (
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
)

MIDDLEWARE = [
    'django.middleware.gzip.GZipMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'debug_toolbar.middleware.DebugToolbarMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'blogs.middleware.RequestPerformanceMiddleware',
    'allauth.account.middleware.AccountMiddleware'
]

ROOT_URLCONF = 'conf.urls'
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [
            os.path.normpath(os.path.join(BASE_DIR, 'templates')),
        ],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'django.template.context_processors.request',
                'blogs.context_processors.tz'
            ],
        },
    },
]


WSGI_APPLICATION = 'conf.wsgi.application'

# All-auth setup
ACCOUNT_AUTHENTICATION_METHOD = 'email'
if not DEBUG:
    ACCOUNT_EMAIL_VERIFICATION = 'none'
    ACCOUNT_CONFIRM_EMAIL_ON_GET = True
    ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_SIGNUP_PASSWORD_ENTER_TWICE = False
ACCOUNT_DEFAULT_HTTP_PROTOCOL = "https"

# Database
# https://docs.djangoproject.com/en/3.0/ref/settings/#databases

CONN_MAX_AGE = 600
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': os.path.join(BASE_DIR, 'dev.db'),
    }
}

if os.getenv('DATABASE_URL'):
    db_from_env = dj_database_url.config(conn_max_age=CONN_MAX_AGE)
    DATABASES['default'].update(db_from_env)

DATA_UPLOAD_MAX_MEMORY_SIZE = 10485760  # 10 MB
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Password validation
# https://docs.djangoproject.com/en/3.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
# https://docs.djangoproject.com/en/3.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_L10N = True

USE_TZ = True

# Static files
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_URL = "static/"
STATICFILES_DIRS = [
    BASE_DIR / "static",
]
GEOIP_PATH = "geoip/"

# Enable WhiteNoise's GZip compression of static assets.
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

LOGIN_REDIRECT_URL = '/dashboard/'

# Emailer

DEFAULT_FROM_EMAIL = "ʕ•ᴥ•ʔ Bear Blog <noreply@bearblog.dev>"
SERVER_EMAIL = "ʕ•ᴥ•ʔ Bear Admin <noreply@bearblog.dev>"
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = 'smtp.eu.mailgun.org'
EMAIL_HOST_USER = 'postmaster@mg.bearblog.dev'
EMAIL_HOST_PASSWORD = os.getenv('MAILGUN_PASSWORD', False)
EMAIL_PORT = 587
EMAIL_USE_TLS = True

# Referrer policy
SECURE_REFERRER_POLICY = "origin-when-cross-origin"
