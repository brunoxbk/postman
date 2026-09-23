from .base import *  # noqa: F401,F403
from .base import env

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = False
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

DATABASES = {"default": env.db("DATABASE_URL", default="sqlite:///db.sqlite3")}

STORAGES = {
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True