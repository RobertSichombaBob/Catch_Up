"""
Catch Up settings.

Every secret and every environment-specific value is read from environment
variables. Nothing secret is stored in this file. See .env.example.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path):
    """Read KEY=value lines from a local .env file (handy on Windows). Real
    environment variables always win, and Render never has a .env file."""
    if not path.is_file():
        return
    for raw in path.read_text(encoding='utf-8').splitlines():
        line = raw.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(BASE_DIR / '.env')


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {'1', 'true', 'yes', 'on'}


def env_list(name, default=''):
    return [item.strip() for item in os.environ.get(name, default).split(',') if item.strip()]


# Render sets RENDER=true on every service. Treat that as production.
ON_RENDER = env_bool('RENDER')
DEBUG = env_bool('DEBUG', default=not ON_RENDER)

SECRET_KEY = env('SECRET_KEY')
if not SECRET_KEY:
    if DEBUG:
        SECRET_KEY = 'dev-only-insecure-key-do-not-use-in-production'
    else:
        raise ImproperlyConfigured('SECRET_KEY must be set when DEBUG is off.')

ALLOWED_HOSTS = env_list('ALLOWED_HOSTS', 'localhost,127.0.0.1')
CSRF_TRUSTED_ORIGINS = env_list('CSRF_TRUSTED_ORIGINS')
RENDER_HOST = env('RENDER_EXTERNAL_HOSTNAME')
if RENDER_HOST:
    ALLOWED_HOSTS.append(RENDER_HOST)
    CSRF_TRUSTED_ORIGINS.append(f'https://{RENDER_HOST}')
if DEBUG:
    ALLOWED_HOSTS += ['testserver']

# Public address of the site, used for links in emails and payment callbacks.
SITE_URL = env('SITE_URL', f'https://{RENDER_HOST}' if RENDER_HOST else 'http://localhost:8000').rstrip('/')
SITE_NAME = 'Catch Up'

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'whitenoise.runserver_nostatic',
    'django.contrib.staticfiles',
    'django.contrib.humanize',
    'apps.accounts',
    'apps.courses',
    'apps.payments',
    'apps.notifications',
    'apps.ledger',
    'apps.classroom',
    'apps.schools',
    'apps.analytics',
    'apps.portal',
    'apps.core',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.core.context_processors.site',
                'apps.notifications.context_processors.notifications',
                'apps.portal.context_processors.navigation',
                'apps.schools.context_processors.schools',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'

# --- Database ---------------------------------------------------------------
# Production uses Postgres from DATABASE_URL (Render fills this in from the
# database in render.yaml). Local development falls back to SQLite.
DATABASE_URL = env('DATABASE_URL')
if DATABASE_URL:
    DATABASES = {
        'default': dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=env_bool('DATABASE_SSL_REQUIRE', default=False),
        )
    }
elif DEBUG:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}
else:
    raise ImproperlyConfigured('DATABASE_URL must be set when DEBUG is off.')

AUTH_USER_MODEL = 'accounts.User'
AUTHENTICATION_BACKENDS = ['apps.accounts.backends.EmailBackend']
LOGIN_URL = 'accounts:login'
LOGIN_REDIRECT_URL = 'core:dashboard'
LOGOUT_REDIRECT_URL = 'core:home'

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator', 'OPTIONS': {'min_length': 8}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-gb'
TIME_ZONE = 'Africa/Lusaka'
USE_I18N = True
USE_TZ = True

# --- Static files -----------------------------------------------------------
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']
# --- Uploaded files (course covers, tutor documents, course materials) -------
# Locally they go in ./media. On Render they go on the persistent disk set up
# in render.yaml (MEDIA_ROOT=/var/data/media). To use S3-compatible object
# storage instead (Cloudflare R2, AWS S3, Backblaze), set AWS_STORAGE_BUCKET_NAME
# and the AWS_* variables in .env.example.
MEDIA_URL = '/media/'
MEDIA_ROOT = Path(env('MEDIA_ROOT', str(BASE_DIR / 'media')))
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_MEMORY_SIZE = 30 * 1024 * 1024
MAX_UPLOAD_MB = int(env('MAX_UPLOAD_MB', '25'))
AWS_STORAGE_BUCKET_NAME = env('AWS_STORAGE_BUCKET_NAME', '')
if AWS_STORAGE_BUCKET_NAME:
    DEFAULT_FILE_BACKEND = 'storages.backends.s3.S3Storage'
    AWS_S3_ENDPOINT_URL = env('AWS_S3_ENDPOINT_URL') or None
    AWS_S3_REGION_NAME = env('AWS_S3_REGION_NAME', 'auto')
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = 600
    AWS_S3_FILE_OVERWRITE = False
else:
    DEFAULT_FILE_BACKEND = 'django.core.files.storage.FileSystemStorage'

STORAGES = {
    'default': {'BACKEND': DEFAULT_FILE_BACKEND},
    'staticfiles': {
        'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'
        if not DEBUG else 'django.contrib.staticfiles.storage.StaticFilesStorage',
    },
}
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# --- Email ------------------------------------------------------------------
# With EMAIL_HOST set, mail goes out over SMTP (Brevo, Mailgun, SendGrid,
# Gmail with an app password...). Without it, emails are printed to the log so
# nothing breaks while you set up a provider.
EMAIL_HOST = env('EMAIL_HOST', '')
if EMAIL_HOST:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_PORT = int(env('EMAIL_PORT', '587'))
    EMAIL_HOST_USER = env('EMAIL_HOST_USER', '')
    EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', '')
    EMAIL_USE_TLS = env_bool('EMAIL_USE_TLS', default=EMAIL_PORT == 587)
    EMAIL_USE_SSL = env_bool('EMAIL_USE_SSL', default=EMAIL_PORT == 465)
    EMAIL_TIMEOUT = 15
else:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', 'Catch Up <no-reply@catchup.example>')
SERVER_EMAIL = DEFAULT_FROM_EMAIL
SUPPORT_EMAIL = env('SUPPORT_EMAIL', 'support@catchup.example')

# --- Payments ---------------------------------------------------------------
# Course prices are monthly. One payment gives ACCESS_PERIOD_DAYS of access,
# and students can renew from RENEWAL_WINDOW_DAYS before it runs out.
COURSE_PRICE_ZMW = env('COURSE_PRICE_ZMW', '80.00')
MIN_COURSE_PRICE = env('MIN_COURSE_PRICE', '50')
MAX_COURSE_PRICE = env('MAX_COURSE_PRICE', '500')
ACCESS_PERIOD_DAYS = int(env('ACCESS_PERIOD_DAYS', '30'))
RENEWAL_WINDOW_DAYS = int(env('RENEWAL_WINDOW_DAYS', '7'))
# Revenue split. The provider's fee (set this to the rate in your pawaPay
# contract) comes off first, then the tutor gets TUTOR_SHARE_PERCENT of the
# rest. Courses run by platform admins keep 100%.
TUTOR_SHARE_PERCENT = int(env('TUTOR_SHARE_PERCENT', '50'))
PAYMENT_FEE_PERCENT = env('PAYMENT_FEE_PERCENT', '0')
PAYOUT_MINIMUM = env('PAYOUT_MINIMUM', '100')
# "simulator" works with no account and is for testing only.
# "pawapay" talks to pawaPay (MTN, Airtel and Zamtel in Zambia).
PAYMENT_PROVIDER = env('PAYMENT_PROVIDER', 'simulator')
PAWAPAY_API_TOKEN = env('PAWAPAY_API_TOKEN', '')
PAWAPAY_SANDBOX = env_bool('PAWAPAY_SANDBOX', default=True)
PAWAPAY_BASE_URL = env(
    'PAWAPAY_BASE_URL',
    'https://api.sandbox.pawapay.io' if PAWAPAY_SANDBOX else 'https://api.pawapay.io',
)
if PAYMENT_PROVIDER == 'simulator' and ON_RENDER and not env_bool('ALLOW_PAYMENT_SIMULATOR'):
    raise ImproperlyConfigured(
        'PAYMENT_PROVIDER is "simulator" on Render. Set PAYMENT_PROVIDER=pawapay, '
        'or set ALLOW_PAYMENT_SIMULATOR=true for a demo where nobody really pays.'
    )
if PAYMENT_PROVIDER == 'pawapay' and not PAWAPAY_API_TOKEN:
    raise ImproperlyConfigured('PAYMENT_PROVIDER is "pawapay" but PAWAPAY_API_TOKEN is not set.')

# --- Security ---------------------------------------------------------------
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
X_FRAME_OPTIONS = 'DENY'
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = env_bool('SECURE_SSL_REDIRECT', default=True)
    SECURE_REDIRECT_EXEMPT = [r'^healthz$']
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = int(env('SECURE_HSTS_SECONDS', '3600'))
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False

from django.contrib.messages import constants as message_constants  # noqa: E402

MESSAGE_TAGS = {message_constants.ERROR: 'error'}

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'plain': {'format': '%(asctime)s %(levelname)s %(name)s: %(message)s'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'plain'}},
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'django': {'handlers': ['console'], 'level': env('DJANGO_LOG_LEVEL', 'INFO'), 'propagate': False},
    },
}
