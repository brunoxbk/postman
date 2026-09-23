from .base import *  # noqa: F401,F403
from .base import BASE_DIR

DEBUG = True
SECRET_KEY = "dev-only-insecure-key-nao-usar-em-prod"
ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(BASE_DIR / "db.sqlite3"),
    }
}