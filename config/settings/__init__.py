import os

from django.core.exceptions import ImproperlyConfigured

MODULE = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.dev")
if MODULE not in ("config.settings.dev", "config.settings.prod"):
    raise ImproperlyConfigured(f"DJANGO_SETTINGS_MODULE inválido: {MODULE}")