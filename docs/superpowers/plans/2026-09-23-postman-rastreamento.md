# Postman — Rastreador de Encomendas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar uma aplicação Django com painel web e API que consome a API PacoteVício (RapidAPI) para cadastrar e rastrear encomendas de 6 transportadoras, com sincronização via cron 3×/dia e deploy no Dokku.

**Architecture:** Django 5.2 LTS + DRF. Configuração desacoplada via `django-environ` (tudo em variáveis de ambiente). Um único cliente HTTP (`requests`) conversa com a API externa; cada transportadora tem um *adapter* que normaliza a resposta divergente para um formato canônico. Um management command (`sync_trackings`) percorre as encomendas ativas, aplica regras de negócio (estado final encerra, atraso, dedupe de eventos, cota mensal) e é chamado pelo cron do host Dokku. UI em templates Django (pt-BR); API protegida por `Api-Key` (`djangorestframework-api-key`) para o Hermes agent.

**Tech Stack:** Python 3.12 (Dokku via `runtime.txt`), Django 5.2, django-rest-framework, djangorestframework-api-key, django-environ, whitenoise, requests, psycopg[binary], gunicorn, PostgreSQL (dev usa SQLite padrão).

**Spec:** `docs/superpowers/specs/2026-09-23-postman-rastreamento-design.md`

> **Nota de execução (pós-implementação):** este plano foi executado por completo e os
> trechos abaixo já refletem o que está no repositório. Divergências aplicadas durante a
> implementação: `config/settings/base.py` usa autenticação customizada
> (`apps.trackings.auth.APIKeyAuthentication`) pois `djangorestframework-api-key` ≥ 3.1
> removeu `rest_framework_api_key.authentication`; `dev.py` usa `BASE_DIR / "db.sqlite3"`;
> `prod.py` ganhou `SECURE_SSL_REDIRECT` + HSTS; os adapters normalizam eventos em ordem
> **decrescente** e o Correios usa o campo `codigo` como `status_key`; o padrão Total
> Express aceita o sufixo `tx`; `sync_package` não tem o parâmetro `enforce_cota`;
> o teste de `SyncLog` usa `count_today()` (não `increment_and_get_count`).

## Global Constraints

- Versões: Python 3.12 (prod), `Django~=5.2`, `djangorestframework~=3.16`, `psycopg[binary]>=3.2`. Local dev Python 3.10+ é aceitável.
- `config/settings/base.py` é a base única; `dev.py` (DEBUG on, sqlite) e `prod.py` (DEBUG off, Postgres/estativos comprimidos) herdam dela. `DJANGO_SETTINGS_MODULE` seleciona.
- Nenhuma chave/segredo no código: tudo via `env()` do django-environ. `DJANGO_SECRET_KEY` default de dev só para `dev.py`.
- Nomes/defaults exatos de variáveis: `PACOTE_VICIO_API_KEY`, `PACOTE_VICIO_BASE_URL=https://api.pacotevicio.dev`, `PACOTE_VICIO_TIMEOUT=35`, `COTA_MENSAL=900`, `LANGUAGE_CODE="pt-br"`, `TIME_ZONE="America/Sao_Paulo"`, `USE_TZ=True`.
- Horários do cron: 08:40, 13:00, 19:00 `America/Sao_Paulo`, chamando `python manage.py sync_trackings`.
- UI em pt-BR. API sob `/api/v1/`.
- Modelos: `trackings.Package`, `trackings.TrackingEvent`, `core.SyncLog`.
- Test runner: `django.test`. Rodar com `python manage.py test`.

---

### Task 1: Scaffolding do projeto — settings, manage.py, Procfile, deps

**Files:**
- Create: `requirements.txt`, `runtime.txt`, `Procfile`, `.dockerignore`, `.gitignore`, `.env.sample`, `manage.py`
- Create: `config/__init__.py`, `config/settings/__init__.py`, `config/settings/base.py`, `config/settings/dev.py`, `config/settings/prod.py`, `config/urls.py`, `config/wsgi.py`, `config/asgi.py`
- Create: `apps/__init__.py`, `apps/core/__init__.py`, `apps/carriers/__init__.py`, `apps/trackings/__init__.py`
- Create: `apps/core/apps.py`, `apps/carriers/apps.py`, `apps/trackings/apps.py`
- Test: `apps/core/tests/__init__.py`, `apps/core/tests/test_config.py`

**Interfaces:**
- Consumes: nada.
- Produces: o app instalável roda `manage.py check` sem erros; rotas `/admin/` e health. Tasks seguintes importam `config.settings.base` helpers `env = environ.Env` (re-exportado em `apps/core/settings.py` opcionalmente — manter import direto de `config.settings.base`).

- [ ] **Step 1: Criar venv e instalar deps**

```bash
python3 -m venv .venv && source .venv/bin/activate
```

- [ ] **Step 2: Escrever o teste de configuração (failing)**

`apps/core/tests/test_config.py`:
```python
from django.test import SimpleTestCase
from django.conf import settings


class ConfigTestCase(SimpleTestCase):
    def test_language_pt_br(self):
        self.assertEqual(settings.LANGUAGE_CODE, "pt-br")

    def test_timezone_sao_paulo(self):
        self.assertEqual(settings.TIME_ZONE, "America/Sao_Paulo")
```

- [ ] **Step 3: Rodar o teste para ver falhar**

Run: `source .venv/bin/activate && python manage.py test apps.core -v 2`
Expected: erro `ModuleNotFoundError: No module named 'django'` (ou `No module named config`) — ainda não existe nada.

- [ ] **Step 4: Implementar scaffolding**

`requirements.txt`:
```
Django~=5.2
djangorestframework~=3.16
djangorestframework-api-key~=3.0
django-environ~=0.12
whitenoise~=6.9
requests~=2.32
psycopg[binary]~=3.2
gunicorn~=23.0
```

`runtime.txt`:
```
python-3.12.4
```

`Procfile`:
```
web: gunicorn config.wsgi:application --bind 0.0.0.0:$PORT
```

`.dockerignore`:
```
.venv
__pycache__
*.pyc
staticfiles
.env
.git
docs
```

`.gitignore`:
```
.venv/
__pycache__/
*.pyc
staticfiles/
.env
```

`.env.sample`:
```
DJANGO_DEBUG=0
DJANGO_SECRET_KEY=troque-por-chave-aleatoria
DJANGO_ALLOWED_HOSTS=localhost,seudominio.com
DATABASE_URL=
DJANGO_TIME_ZONE=America/Sao_Paulo
PACOTE_VICIO_API_KEY=sua-chave-rapidapi
PACOTE_VICIO_BASE_URL=https://api.pacotevicio.dev
PACOTE_VICIO_TIMEOUT=35
COTA_MENSAL=900
```

`manage.py`:
```python
#!/usr/bin/env python
import os
import sys


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    from django.core.management import execute_from_command_line
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
```

`config/__init__.py` (vazio).

`config/settings/__init__.py`:
```python
from django.core.exceptions import ImproperlyConfigured
import os

MODULE = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.dev")
if MODULE not in ("config.settings.dev", "config.settings.prod"):
    raise ImproperlyConfigured(f"DJANGO_SETTINGS_MODULE inválido: {MODULE}")
```

`config/settings/base.py`:
```python
from pathlib import Path
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, ""),
    DJANGO_ALLOWED_HOSTS=(list, ["*"]),
    DJANGO_TIME_ZONE=(str, "America/Sao_Paulo"),
    CSRF_TRUSTED_ORIGINS=(list, []),
    PACOTE_VICIO_API_KEY=(str, ""),
    PACOTE_VICIO_BASE_URL=(str, "https://api.pacotevicio.dev"),
    PACOTE_VICIO_TIMEOUT=(int, 35),
    COTA_MENSAL=(int, 900),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_api_key",
    "apps.core",
    "apps.carriers",
    "apps.trackings",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "apps" / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {"default": env.db(default="sqlite:///db.sqlite3")}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = env("DJANGO_TIME_ZONE")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

PACOTE_VICIO_API_KEY = env("PACOTE_VICIO_API_KEY")
PACOTE_VICIO_BASE_URL = env("PACOTE_VICIO_BASE_URL")
PACOTE_VICIO_TIMEOUT = env("PACOTE_VICIO_TIMEOUT")
COTA_MENSAL = env("COTA_MENSAL")

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.trackings.auth.APIKeyAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework_api_key.permissions.HasAPIKey",
    ],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 50,
}

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"
```

`config/settings/dev.py`:
```python
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
```

> Em prod o `DATABASE_URL` de Postgres sobrescreve (ver `prod.py`).

`config/settings/prod.py`:
```python
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
```

`config/urls.py`:
```python
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.trackings.api_urls")),
    path("", include("apps.trackings.web_urls")),
]
```

**Nota:** `apps.trackings.api_urls` e `apps.trackings.web_urls` ainda não existem nesta task — para poder rodar `check`, crie módulos mínimos:

`apps/trackings/api_urls.py`:
```python
from django.urls import path

urlpatterns = []
```

`apps/trackings/web_urls.py`:
```python
from django.urls import path

urlpatterns = []
```

`config/wsgi.py`:
```python
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
application = get_wsgi_application()
```

`config/asgi.py` (idem com `get_asgi_application`).

`apps/core/apps.py`:
```python
from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
```

`apps/carriers/apps.py`:
```python
from django.apps import AppConfig


class CarriersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.carriers"
```

`apps/trackings/apps.py`:
```python
from django.apps import AppConfig


class TrackingsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.trackings"
```

`config/settings/__init__.py` continua como escrito acima. Em `INSTALLED_APPS` também adicionar `"apps.core.apps.CoreConfig"`? Manter nome curto (`apps.core`) é suficiente e simples.

- [ ] **Step 5: Rodar testes para passar**

Run: `python manage.py test apps.core -v 2`
Expected: `ok` (2 testes). Antes: `python manage.py migrate` (cria sqlite).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "chore: scaffolding do projeto django"
```

---

### Task 2: Modelo de dados — Package, TrackingEvent, SyncLog

**Files:**
- Create: `apps/carriers/constants.py`
- Create: `apps/trackings/models.py`
- Create: `apps/trackings/migrations/__init__.py` (virá do makemigrations)
- Create: `apps/core/models.py` (`SyncLog`)
- Create: `apps/core/admin.py` (registrar mínimos em task posterior — aqui registrar SyncLog)
- Test: `apps/trackings/tests/__init__.py`, `apps/trackings/tests/test_models.py`

**Interfaces:**
- Consumes: config/settings.base (todos apps registrados).
- Produces:
  - `apps.carriers.constants.CARRIER_CHOICES` (lista de tuplas slug/label) e `CARRIER_*_LABEL`/slugs.
  - `trackings.models.Package` com campos e métodos: `tracking_code, carrier, label, document, status_code, status_label, location, last_event_at, estimated_delivery, state, is_active, is_delayed, last_synced_at, last_error, last_raw, created_at, updated_at`; métodos `mark_terminal()`, `display_document` (helper).
  - `trackings.models.TrackingEvent` com `package FK, occurred_at, status_key, status_label, location, raw, fingerprint`; `unique_together`/`unique` em `fingerprint`.
  - `core.models.SyncLog` com `day (Date, unique), requests (int), quota_limit (int), created_at`; método `classmethod increment()`.
  - `STATE_CHOICES` de Package.

- [ ] **Step 1: Escrever o teste (failing)**

`apps/trackings/tests/test_models.py`:
```python
from django.db import IntegrityError
from django.test import TestCase

from apps.carriers.constants import CARRIER_CORREIOS
from apps.trackings.models import (
    Package,
    TrackingEvent,
    STATE_IN_TRANSIT,
)


class PackageModelTestCase(TestCase):
    def test_create_and_terminal(self):
        p = Package.objects.create(
            tracking_code="AM101610575BR",
            carrier=CARRIER_CORREIOS,
            state=STATE_IN_TRANSIT,
        )
        p.mark_terminal("ENTREGUE", "delivered")
        p.save()  # mark_terminal só altera o objeto em memória — persistir
        p.refresh_from_db()
        self.assertFalse(p.is_active)
        self.assertEqual(p.state, "delivered")
        self.assertEqual(p.status_code, "ENTREGUE")


class TrackingEventFingerprintTestCase(TestCase):
    def test_dedupe_by_fingerprint(self):
        p = Package.objects.create(tracking_code="X1", carrier=CARRIER_CORREIOS)
        TrackingEvent.objects.create(
            package=p,
            status_key="BDE",
            status_label="Entregue",
            fingerprint="fp-1",
        )
        with self.assertRaises(IntegrityError):
            TrackingEvent.objects.create(
                package=p, status_key="BDE", status_label="Entregue", fingerprint="fp-1")
```

`apps/core/tests/test_synclog.py`:
```python
from django.test import TestCase

from apps.core.models import SyncLog


class SyncLogTestCase(TestCase):
    def test_increment_same_day(self):
        SyncLog.increment()
        SyncLog.increment()
        SyncLog.increment()
        self.assertEqual(SyncLog.count_today(), 3)

    def test_count_today_isolation(self):
        SyncLog.increment()
        self.assertEqual(SyncLog.count_today(), 1)
```

- [ ] **Step 2: Rodar o teste para falhar**

Run: `python manage.py test apps.trackings apps.core -v 2`
Expected: erros de import/No module.

- [ ] **Step 3: Implementar**

`apps/carriers/constants.py`:
```python
CARRIER_CORREIOS = "correios"
CARRIER_ALIEXPRESS = "aliexpress"
CARRIER_SHOPEE = "shopee"
CARRIER_ANJUN = "anjun"
CARRIER_JTEXPRESS = "jtexpress"
CARRIER_TOTALEXPRESS = "totalexpress"

CARRIER_CHOICES = [
    (CARRIER_CORREIOS, "Correios"),
    (CARRIER_ALIEXPRESS, "AliExpress"),
    (CARRIER_SHOPEE, "Shopee Xpress"),
    (CARRIER_ANJUN, "Anjun Express"),
    (CARRIER_JTEXPRESS, "J&T Express"),
    (CARRIER_TOTALEXPRESS, "Total Express"),
]

CARRIER_LABELS = dict(CARRIER_CHOICES)
```

`apps/trackings/models.py`:
```python
import hashlib
from django.db import models
from django.utils import timezone
from apps.carriers.constants import CARRIER_CHOICES

STATE_IN_TRANSIT = "in_transit"
STATE_DELIVERED = "delivered"
STATE_FAILED = "failed"
STATE_RETURNED = "returned"
STATE_INACTIVE = "inactive"

STATE_CHOICES = [
    (STATE_IN_TRANSIT, "Em trânsito"),
    (STATE_DELIVERED, "Entregue"),
    (STATE_FAILED, "Falha"),
    (STATE_RETURNED, "Devolvida"),
    (STATE_INACTIVE, "Encerrada"),
]

TERMINAL_STATES = {STATE_DELIVERED, STATE_FAILED, STATE_RETURNED, STATE_INACTIVE}


class Package(models.Model):
    tracking_code = models.CharField(max_length=64, unique=True)
    carrier = models.CharField(max_length=20, choices=CARRIER_CHOICES, db_index=True)
    label = models.CharField(max_length=128, blank=True)
    document = models.CharField(max_length=16, blank=True, help_text="CPF somente dígitos (obrigatório p/ J&T)")
    status_code = models.CharField(max_length=64, blank=True)
    status_label = models.CharField(max_length=255, blank=True)
    location = models.CharField(max_length=255, blank=True)
    last_event_at = models.DateTimeField(null=True, blank=True)
    estimated_delivery = models.DateField(null=True, blank=True)
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default=STATE_IN_TRANSIT, db_index=True)
    is_active = models.BooleanField(default=True)
    is_delayed = models.BooleanField(default=False)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True)
    last_raw = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.label or self.tracking_code

    def mark_terminal(self, status_code: str, state: str) -> None:
        self.status_code = status_code
        self.state = state
        self.is_active = False

    @property
    def display_code(self) -> str:
        return self.label or self.tracking_code

    @property
    def masked_document(self) -> str:
        if not self.document:
            return ""
        digits = "".join(ch for ch in self.document if ch.isdigit())
        if len(digits) < 6:
            return digits
        return f"***.***.***-{digits[-2:]}"


class TrackingEvent(models.Model):
    package = models.ForeignKey(Package, on_delete=models.CASCADE, related_name="events")
    occurred_at = models.DateTimeField(null=True, blank=True)
    status_key = models.CharField(max_length=128)
    status_label = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True)
    raw = models.JSONField(default=dict, blank=True)
    fingerprint = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-occurred_at", "-id"]

    def __str__(self):
        return f"{self.package.tracking_code} — {self.status_label}"

    @staticmethod
    def make_fingerprint(package_id: int, occurred_at, status_key: str, status_label: str) -> str:
        stamp = occurred_at.isoformat() if occurred_at else ""
        base = f"{package_id};{stamp};{status_key};{status_label}".lower()
        return hashlib.sha1(base.encode("utf-8")).hexdigest()
```

> **Ajuste aplicado:** a versão acima (com `.lower()` e sem o `.replace` quebrado) é a
> que está implementada em `apps/trackings/models.py`.

`apps/core/models.py`:
```python
from datetime import timezone as dt_tz
from django.db import models
from django.utils import timezone
from django.conf import settings


class SyncLog(models.Model):
    day = models.DateField(unique=True)
    requests = models.PositiveIntegerField(default=0)
    quota_limit = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-day"]

    def __str__(self):
        return f"{self.day} — {self.requests}/{self.quota_limit}"

    @classmethod
    def _row(cls):
        today = timezone.localdate()
        obj, _ = cls.objects.get_or_create(day=today, defaults={"quota_limit": getattr(settings, "COTA_MENSAL", 900)})
        return obj

    @classmethod
    def increment(cls) -> int:
        obj = cls._row()
        obj.requests += 1
        obj.save()
        return obj.requests

    @classmethod
    def count_today(cls) -> int:
        return cls._row().requests

    @classmethod
    def increment_and_get_count(cls) -> int:
        return cls.increment()

    @classmethod
    def is_paused(cls) -> bool:
        row = cls._row()
        return row.requests >= row.quota_limit
```

`apps/core/admin.py`:
```python
from django.contrib import admin
from apps.core.models import SyncLog


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ("day", "requests", "quota_limit")
```

- [ ] **Step 4: Rodar makemigrations + testes**

Run: `python manage.py makemigrations trackings core && python manage.py migrate && python manage.py test apps.trackings apps.core -v 2`
Expected: migrations criadas, testes PASS (o teste de fingerprint espera 2 events tentando o segundo create e espera exception de IntegrityError — usar `from django.db import IntegrityError` import no teste e sobe apenas `IntegrityError`).

**Ajustar teste**: o teste usa `assertRaises(Exception, ...)` — substituir por `IntegrityError`:
```python
from django.db import IntegrityError
...
with self.assertRaises(IntegrityError):
    TrackingEvent.objects.create(...)
```

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: modelos Package e TrackingEvent + SyncLog"
```

---

### Task 3: Parsing de datas e cliente HTTP da API PacoteVício

**Files:**
- Create: `apps/carriers/parsing.py`
- Create: `apps/carriers/client.py`
- Create: `apps/carriers/exceptions.py`
- Test: `apps/carriers/tests/__init__.py`, `apps/carriers/tests/test_parsing.py`, `apps/carriers/tests/test_client.py`

**Interfaces:**
- Consumes: `django.conf.settings.PACOTE_VICIO_*`, `requests`.
- Produces:
  - `parsing.parse_datetime(value) -> datetime | None` (lida com ISO `YYYY-MM-DD HH:MM:SS[.ffffff]`, unix em ms, `DD-MM-YYYY HH:MM:SS`, timestamp com timezone label tipo ISO 8601).
  - `parsing.parse_date(value) -> date | None` (lida com `DD/MM/YYYY` e `YYYY-MM-DD`).
  - `parsing.to_aware(dt) -> datetime` (usa zoneinfo America/Sao_Paulo para naive).
  - `client.PacoteVicioClient` com método `fetch(path: str, params: dict) -> dict`; levanta `PacoteVicioClientError` (4xx), `PacoteVicioServerError` (5xx/timeout), ambos herdando `PacoteVicioError(Exception)`.
  - exceções em `apps/carriers/exceptions.py`.

- [ ] **Step 1: Escrever testes (failing)**

`apps/carriers/tests/test_parsing.py`:
```python
from datetime import datetime
from django.test import SimpleTestCase
from apps.carriers.parsing import parse_datetime, parse_date, to_aware


class ParsingTestCase(SimpleTestCase):
    def test_iso_microseconds(self):
        dt = parse_datetime("2025-03-03 23:30:03.000000")
        self.assertIsNotNone(dt)
        self.assertEqual(dt.date().isoformat(), "2025-03-03")

    def test_iso_plain(self):
        dt = parse_datetime("2025-05-28 13:33:27")
        self.assertEqual(dt.date().isoformat(), "2025-05-28")

    def test_unix_millis(self):
        dt = parse_datetime(1748410407000)
        self.assertEqual(dt.date().isoformat(), "2025-05-28")

    def test_unix_seconds(self):
        dt = parse_datetime(1749140169)
        self.assertEqual(dt.date().isoformat(), "2025-06-05")

    def test_day_first(self):
        dt = parse_datetime("21-01-2025 09:22:13")
        self.assertEqual(dt.date().isoformat(), "2025-01-21")

    def test_to_aware_naive(self):
        out = to_aware(datetime(2025, 3, 3, 23, 30, 3))
        self.assertEqual(out.tzname(), "America/Sao_Paulo")

    def test_date_dmy(self):
        self.assertEqual(parse_date("20/03/2025").isoformat(), "2025-03-20")

    def test_date_ymd(self):
        self.assertEqual(parse_date("2026-03-23").isoformat(), "2026-03-23")
```

`apps/carriers/tests/test_client.py`:
```python
from unittest import mock
from django.test import SimpleTestCase
from apps.carriers.client import PacoteVicioClient
from apps.carriers.exceptions import PacoteVicioClientError, PacoteVicioServerError, PacoteVicioError


class ClientTestCase(SimpleTestCase):
    def test_success(self):
        resp = mock.Mock()
        resp.ok = True
        resp.status_code = 200
        resp.json.return_value = {"codObjeto": "X"}
        with mock.patch("apps.carriers.client.requests.get", return_value=resp) as get:
            client = PacoteVicioClient()
            data = client.fetch("/correios", {"tracking_code": "AM101610575BR"})
        get.assert_called_once()
        self.assertEqual(data["codObjeto"], "X")

    def test_client_error_raises(self):
        resp = mock.Mock()
        resp.ok = False
        resp.status_code = 401
        resp.text = "unauthorized"
        with mock.patch("apps.carriers.client.requests.get", return_value=resp):
            client = PacoteVicioClient()
            with self.assertRaises(PacoteVicioClientError):
                client.fetch("/correios", {"tracking_code": "X"})

    def test_server_error_raises(self):
        resp = mock.Mock()
        resp.ok = False
        resp.status_code = 500
        resp.text = "boom"
        with mock.patch("apps.carriers.client.requests.get", return_value=resp):
            with self.assertRaises(PacoteVicioServerError):
                PacoteVicioClient().fetch("/correios", {"tracking_code": "X"})
```

- [ ] **Step 2: Rodar testes para falhar

Run: `python manage.py test apps.carriers -v 2`
Expected: ImportError/No module errors.

- [ ] **Step 3: Implementar**

`apps/carriers/exceptions.py`:
```python
class PacoteVicioError(Exception):
    pass


class PacoteVicioClientError(PacoteVicioError):
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(message or f"Erro {status_code}")


class PacoteVicioServerError(PacoteVicioError):
    pass
```

`apps/carriers/parsing.py`:
```python
from datetime import datetime, date
from zoneinfo import ZoneInfo

PT_BR_TZ = ZoneInfo("America/Sao_Paulo")

_FORMATS_DMY = ["%d-%m-%Y %H:%M:%S"]
_FORMATS_ISO = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]


def parse_datetime(value) -> datetime | None:
    """Converte qualquer formato comum dos carriers num datetime aware (ou naive)."""
    if value is None or value == "":
        return None
    if isinstance(value, int):
        ms = value
        if len(str(abs(value))) > 11:
            ms = value / 1000
        return datetime.fromtimestamp(ms, tz=PT_BR_TZ)
    text = str(value).strip()
    if "T" in text:
        text = text.replace("Z", "+00:00")
        if "+" not in text and text.endswith((":00", ":00:00")):
            text = text.replace("T", " ")
    for fmt in _FORMATS_ISO:
        try:
            return datetime.fromisoformat(text if "T" in text else text)
        except ValueError:
            pass
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    for fmt in _FORMATS_DMY:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=PT_BR_TZ)
    return dt.astimezone(PT_BR_TZ)
```

**Refinamento para robustez (usar esta versão final do parsing):**

`parsing.py` final:
```python
import datetime as _dt
from datetime import datetime, date
from zoneinfo import ZoneInfo

PT_BR_TZ = ZoneInfo("America/Sao_Paulo")

_ISO_WITH_WS = ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"]
_DMY_WITH_WS = ["%d-%m-%Y %H:%M:%S"]


def parse_datetime(value) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        seconds = value
        if abs(seconds) > 10_000_000_000:
            seconds = seconds / 1000
        return datetime.fromtimestamp(seconds, tz=PT_BR_TZ)
    text = str(value).strip()
    for fmt in _ISO_WITH_WS:
        try:
            return to_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    for fmt in _DMY_WITH_WS:
        try:
            return to_aware(datetime.strptime(text, fmt))
        except ValueError:
            continue
    if "T" in text:
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def parse_date(value) -> date | None:
    if value is None or value == "":
        return None
    text = str(value).strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_aware(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=PT_BR_TZ)
    return dt
```

O correto para o teste `test_unix_millis` (1748410407000) e `test_unix_seconds` (1749140169) não é necessário validar o envoltório `.date()` do sistema de fuso UTC — o teste compara `.date().isoformat()`. `datetime.fromtimestamp(1748410407000/1000, tz=PT_BR_TZ)` — dado ~= "2025-05-28" e "2025-06-05" (labels de exemplo do doc). Para não depender de datas relativas, os asserts do teste acima já assumem `2025-05-28` e `2025-06-05`. `fromtimestamp(1748410407, tz) == 2025-05-28 13:33:27-03:00` → data 2025-05-28 OK. `1749140169` em UTC → 2025-06-05 05-06-05? 1749140169 = 2025-06-05~ → tz PT-BR = 2025-06-05 (≈ 02:03 UTC-3? na verdade 2025-06-05 02:xx) → data 2025-06-05 OK.

- [ ] **Step 4: Implementar cliente**

`apps/carriers/client.py`:
```python
import requests
from django.conf import settings
from apps.carriers.exceptions import PacoteVicioClientError, PacoteVicioServerError


class PacoteVicioClient:
    def __init__(self, auth_base: str | None = None, timeout: int | None = None):
        self.base_url = auth_base or settings.PACOTE_VICIO_BASE_URL
        self.api_key = getattr(settings, "PACOTE_VICIO_API_KEY", "")
        self.timeout = timeout or settings.PACOTE_VICIO_TIMEOUT

    def fetch(self, path: str, params: dict) -> dict:
        url = f"{self.base_url.rstrip('/')}/{path.strip('/')}"
        try:
            resp = requests.get(url, params=params, timeout=self.timeout, headers={"X-RapidAPI-Key": self.api_key})
        except requests.RequestException as exc:
            raise PacoteVicioServerError(f"Falha de rede/timeout: {exc}") from exc
        if not resp.ok:
            if 400 <= resp.status_code < 500:
                raise PacoteVicioClientError(resp.status_code, resp.text[:300])
            raise PacoteVicioServerError(f"HTTP {resp.status_code}: {resp.text[:300]}")
        return resp.json()
```

- [ ] **Step 5: Rodar testes para passar**

Run: `python manage.py test apps.carriers -v 2`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: cliente HTTP e parsing de datas"
```

---

### Task 4: Adapters das transportadoras (6 clientes) + NormalizedPayload + detecção

**Files:**
- Create: `apps/carriers/payload.py` (dataclasses `EventData`, `NormalizedPayload`)
- Create: `apps/carriers/adapters.py` — **um único módulo** com as 6 classes, registry `ADAPTERS`, `detect_carrier(code)`, `get_adapter(nid)`.
- Test: `apps/carriers/tests/fixtures/*.json` (payloads de exemplo do doc_api.md), `apps/carriers/tests/test_adapters.py`.

**Interfaces:**
- Consumes: `apps.carriers.parsing` (`parse_datetime`, `parse_date`, `to_aware`), `apps.carriers.constants`.
- Produces:
  - `payload.EventData(occurred_at, status_key, status_label, location="", raw={})`
  - `payload.NormalizedPayload(tracking_code, status_code, status_label, location, last_event_at, estimated_delivery, is_terminal, events, raw)`
  - Cada Adapter tem `.nid`, `.name`, `.host_path`, `.requires_document`, `.build_params(tracking_code, document="") -> dict`, `.normalize(raw) -> NormalizedPayload`.
  - `ADAPTERS: dict[str, Adapter]`, `detect_carrier(code: str) -> str | None`, `get_adapter(nid) -> Adapter`.

- [ ] **Step 1: Escrever fixtures**

Copiar o conteúdo de cada `<details>` do `doc_api.md` para:
- `apps/carriers/tests/fixtures/correios.json` — exemplo Correios (eventos BDE e PO).
- `apps/carriers/tests/fixtures/aliexpress.json`
- `apps/carriers/tests/fixtures/shopee.json`
- `apps/carriers/tests/fixtures/anjun.json`
- `apps/carriers/tests/fixtures/jtexpress.json`
- `apps/carriers/tests/fixtures/totalexpress.json`

- [ ] **Step 2: Escrever testes (failing)**

`apps/carriers/tests/test_adapters.py`:
```python
import json
from pathlib import Path
from django.test import SimpleTestCase
from apps.carriers.adapters import ADAPTERS, detect_carrier, get_adapter

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads(FIXTURES.joinpath(name).read_text())


class AdaptersTestCase(SimpleTestCase):
    def test_all_registered(self):
        self.assertEqual(
            {"correios", "aliexpress", "shopee", "anjun", "jtexpress", "totalexpress"},
            set(ADAPTERS.keys()),
        )

    def test_correios_normalize(self):
        raw = load("correios.json")
        n = get_adapter("correios").normalize(raw)
        self.assertEqual(n.tracking_code, "AM101610575BR")
        self.assertTrue(n.is_terminal)
        self.assertEqual(n.status_label, "ENTREGUE")
        self.assertEqual(len(n.events), 2)
        self.assertEqual(n.events[0].status_key, "BDE")

    def test_aliexpress_normalize(self):
        n = get_adapter("aliexpress").normalize(load("aliexpress.json"))
        self.assertIsNotNone(n.last_event_at)
        self.assertIsNotNone(n.estimated_delivery)

    def test_shopee_normalize(self):
        n = get_adapter("shopee").normalize(load("shopee.json"))
        self.assertEqual(n.status_code, "Delivered")
        self.assertTrue(n.is_terminal)
        self.assertEqual(len(n.events), 8)

    def test_anjun_normalize(self):
        n = get_adapter("anjun").normalize(load("anjun.json"))
        self.assertEqual(n.tracking_code, "AJ250101341570001")
        self.assertTrue(n.is_terminal)

    def test_jtexpress_normalize(self):
        n = get_adapter("jtexpress").normalize(load("jtexpress.json"))
        self.assertEqual(n.status_code, "100")
        self.assertTrue(n.is_terminal)

    def test_totalexpress_normalize(self):
        n = get_adapter("totalexpress").normalize(load("totalexpress.json"))
        self.assertEqual(n.tracking_code, "AMZB901884819tx")
        self.assertTrue(n.is_terminal)
        self.assertEqual(len(n.events), 7)
        self.assertEqual(n.estimated_delivery.isoformat(), "2026-03-23")

    def test_detect(self):
        cases = [
            ("AM101610575BR", "correios"),
            ("LP00123456789CN", "aliexpress"),
            ("BR2561249217932", "shopee"),
            ("AJ250101341570001", "anjun"),
            ("888030556767025", "jtexpress"),
            ("AMZB901884819tx", "totalexpress"),
            ("ZZ999999999BX", None),
        ]
        for code, expected in cases:
            self.assertEqual(detect_carrier(code), expected, code)


class JTAdapterTestCase(SimpleTestCase):
    def test_requires_document(self):
        self.assertTrue(get_adapter("jtexpress").requires_document)

    def test_build_params_with_document(self):
        params = get_adapter("jtexpress").build_params("888030556767025", "12345678901")
        self.assertEqual(params["document"], "12345678901")
        self.assertEqual(params["tracking_code"], "888030556767025")
```

- [ ] **Step 3: Rodar testes para falhar**

Run: `python manage.py test apps.carriers -v 2`
Expected: ModuleNotFoundError (adapters ainda não existe).

- [ ] **Step 4: Implementar payload e adapters**

`apps/carriers/payload.py`:
```python
from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass(slots=True)
class EventData:
    occurred_at: datetime | None = None
    status_key: str = ""
    status_label: str = ""
    location: str = ""
    raw: dict = field(default_factory=dict)


@dataclass(slots=True)
class NormalizedPayload:
    tracking_code: str
    status_code: str
    status_label: str
    location: str
    last_event_at: datetime | None
    estimated_delivery: date | None
    is_terminal: bool
    events: list[EventData]
    raw: dict
```

`apps/carriers/adapters.py`:
```python
import re
from datetime import date, datetime

from apps.carriers.constants import (
    CARRIER_CORREIOS, CARRIER_ALIEXPRESS, CARRIER_SHOPEE,
    CARRIER_ANJUN, CARRIER_JTEXPRESS, CARRIER_TOTALEXPRESS,
)
from apps.carriers.payload import EventData, NormalizedPayload
from apps.carriers.parsing import parse_datetime, parse_date, to_aware


def _clean(text) -> str:
    if text is None:
        return ""
    return " ".join(str(text).split())


class BaseAdapter:
    nid: str = ""
    name: str = ""
    host_path: str = ""
    requires_document: bool = False

    def build_params(self, tracking_code: str, document: str = "") -> dict:
        params = {"tracking_code": tracking_code}
        if self.requires_document:
            params["document"] = document
        return params

    def normalize(self, raw: dict) -> NormalizedPayload:
        raise NotImplementedError


class CorreiosAdapter(BaseAdapter):
    nid = CARRIER_CORREIOS
    name = "Correios"
    host_path = "/correios"

    def normalize(self, raw: dict) -> NormalizedPayload:
        events = []
        for ev in raw.get("eventos", []):
            dt = parse_datetime(ev.get("dtHrCriado", {}).get("date"))
            unidade = ev.get("unidade") or {}
            end = unidade.get("endereco") or {}
            city = _clean(end.get("cidade"))
            uf = _clean(end.get("uf"))
            location = " / ".join(x for x in (city, uf) if x)
            events.append(EventData(
                occurred_at=to_aware(dt) if dt else None,
                status_key=_clean(ev.get("codigo")),
                status_label=_clean(ev.get("descricaoWeb") or ev.get("descricao")),
                location=location,
                raw=ev,
            ))
        is_terminal = (
            any(_clean(ev.get("finalizador")).upper() == "S" for ev in raw.get("eventos", []))
            or raw.get("situacao") == "E"
        )
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("codObjeto", ""),
            status_code=_clean(raw.get("situacao")),
            status_label=events[0].status_label if events else "",
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=parse_date(_clean(raw.get("dtPrevista"))),
            is_terminal=is_terminal,
            events=events,
            raw=raw,
        )


class AliExpressAdapter(BaseAdapter):
    nid = CARRIER_ALIEXPRESS
    name = "AliExpress"
    host_path = "/aliexpress"

    def normalize(self, raw: dict) -> NormalizedPayload:
        events = []
        for ev in raw.get("detailList", []):
            try:
                ts = int(ev.get("time") or 0)
            except (TypeError, ValueError):
                ts = 0
            events.append(EventData(
                occurred_at=parse_datetime(ts or None),
                status_key=_clean(ev.get("actionCode")),
                status_label=_clean(ev.get("standerdDesc") or ev.get("descTitle")),
                location=_clean(ev.get("desc")),
                raw=ev,
            ))
        status = _clean(raw.get("status"))
        status_desc = _clean(raw.get("statusDesc"))
        eta = raw.get("globalEtaInfo") or {}
        est = None
        mms = eta.get("deliveryMaxTime")
        if mms:
            est = date.fromtimestamp(int(mms) / 1000)
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("mailNo", ""),
            status_code=status,
            status_label=status_desc,
            location="",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=est,
            is_terminal="deliver" in (status + " " + status_desc).lower(),
            events=events,
            raw=raw,
        )


class ShopeeAdapter(BaseAdapter):
    nid = CARRIER_SHOPEE
    name = "Shopee Xpress"
    host_path = "/shopee"

    def normalize(self, raw: dict) -> NormalizedPayload:
        events = []
        for ev in raw.get("tracking_list", []):
            message = _clean(ev.get("message"))
            head = message.split("]")[0].strip("[]") if message else ""
            events.append(EventData(
                occurred_at=parse_datetime(ev.get("timestamp") or None),
                status_key=_clean(ev.get("status")),
                status_label=message,
                location=head,
                raw=ev,
            ))
        status = _clean(raw.get("current_status"))
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("sls_tracking_number", ""),
            status_code=status,
            status_label=status,
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=None,
            is_terminal="delivered" in status.lower(),
            events=events,
            raw=raw,
        )


class AnjunAdapter(BaseAdapter):
    nid = CARRIER_ANJUN
    name = "Anjun Express"
    host_path = "/anjun"

    def normalize(self, raw: dict) -> NormalizedPayload:
        nodes = raw.get("nodeDataList", []) or []
        events = []
        for ev in nodes:
            events.append(EventData(
                occurred_at=parse_datetime(_clean(ev.get("dateTime"))),
                status_key=_clean(ev.get("statusCode")),
                status_label=_clean(ev.get("signTypeName") or ev.get("status")),
                location=_clean(ev.get("address")),
                raw=ev,
            ))
        status = _clean(raw.get("lastTrackStatus"))
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("trackNo", ""),
            status_code=status,
            status_label=events[0].status_label if events else "",
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=None,
            is_terminal="signed" in status.lower(),
            events=events,
            raw=raw,
        )


class JTExpressAdapter(BaseAdapter):
    nid = CARRIER_JTEXPRESS
    name = "J&T Express"
    host_path = "/jtexpress"
    requires_document = True

    def normalize(self, raw: dict) -> NormalizedPayload:
        details = raw.get("details", [])
        events = []
        for ev in details:
            events.append(EventData(
                occurred_at=parse_datetime(_clean(ev.get("scanTime"))),
                status_key=str(ev.get("code", "")),
                status_label=_clean(ev.get("status") or ev.get("scanTypeName")),
                location=_clean(ev.get("customerTracking")),
                raw=ev,
            ))
        is_terminal = any(str(e.get("code", "")).strip() == "100" for e in details)
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=raw.get("keyword", ""),
            status_code=str(details[0].get("code", "")) if details else "",
            status_label=_clean(details[0].get("status")) if details else "",
            location=events[0].location if events else "",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=None,
            is_terminal=is_terminal,
            events=events,
            raw=raw,
        )


class TotalExpressAdapter(BaseAdapter):
    nid = CARRIER_TOTALEXPRESS
    name = "Total Express"
    host_path = "/totalexpress"
    TERMINAL_STATID = {"1", "104"}

    def normalize(self, raw: dict) -> NormalizedPayload:
        data = raw.get("data", {})
        encomenda = data.get("encomenda", {})
        events = []
        is_terminal = False
        for layout in data.get("layouts", []):
            for etapa in layout.get("etapas", []):
                for st in etapa.get("listaStatus", []):
                    status_id = str(st.get("statid", "")).strip()
                    desc = _clean(st.get("statusDescricao"))
                    if status_id in self.TERMINAL_STATID or "entrega realizada" in desc.lower():
                        is_terminal = True
                    events.append(EventData(
                        occurred_at=parse_datetime(f"{st.get('data')} {st.get('hora')}".strip()),
                        status_key=status_id,
                        status_label=desc,
                        location="",
                        raw=st,
                    ))
        events.sort(key=lambda e: e.occurred_at or datetime.min, reverse=True)
        return NormalizedPayload(
            tracking_code=encomenda.get("awb", ""),
            status_code=str(encomenda.get("ultimoStatusId", "")),
            status_label=events[0].status_label if events else "",
            location="",
            last_event_at=events[0].occurred_at if events else None,
            estimated_delivery=parse_date(_clean(encomenda.get("previsaoEntrega"))),
            is_terminal=is_terminal,
            events=events,
            raw=raw,
        )


ADAPTERS = {
    a.nid: a()
    for a in (CorreiosAdapter, AliExpressAdapter, ShopeeAdapter, AnjunAdapter, JTExpressAdapter, TotalExpressAdapter)
}


def get_adapter(nid: str):
    return ADAPTERS[nid]


_PATTERNS = {
    CARRIER_CORREIOS: re.compile(r"^[A-Z]{2}\d{9}BR$"),
    CARRIER_ALIEXPRESS: re.compile(r"^(LP\d{9,}CN|[A-Z]{2}\d{9,}CN)$", re.I),
    CARRIER_SHOPEE: re.compile(r"^BR\d{12,}$"),
    CARRIER_ANJUN: re.compile(r"^AJ\d{6,}$", re.I),
    CARRIER_JTEXPRESS: re.compile(r"^\d{10,18}$"),
    CARRIER_TOTALEXPRESS: re.compile(r"^[A-Z]{3,5}\d{6,}(?:[tx]{1,2})?$", re.I),
}


def detect_carrier(code: str) -> str | None:
    code = code.strip()
    for nid, pat in _PATTERNS.items():
        if pat.match(code):
            return nid
    return None
```

- [ ] **Step 5: Rodar testes para passar**

Run: `python manage.py test apps.carriers -v 2`
Expected: PASS (10 testes: 7 adapter + 2 JT + detect + registered).

Notas de verificação:
- Eventos são normalizados em ordem **decrescente** (mais recente primeiro); `events[0]`
  é o último evento (o teste espera `events[0].status_key == "BDE"`).
- `test_correios_normalize`: último evento é BDE "ENTREGUE" — `status_label` = "ENTREGUE".
- `test_jtexpress_normalize`: primeiro detail tem `code` 100 → `status_code` "100" e terminal.
- `test_totalexpress_normalize`: 7 eventos no fixture (1+2+2+2) → o teste usa `len(n.events), 7` e previsão "2026-03-23".
- `test_aliexpress_normalize`: `last_event_at` não nulo; `estimated_delivery` calculado de `deliveryMaxTime` (em ms).

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: adapters das 6 transportadoras + detecção automática"
```
### Task 5: Serviço de sincronização + management command `sync_trackings`

**Files:**
- Create: `apps/carriers/sync.py` (funções `sync_package` e `sync_all`)
- Create: `apps/trackings/management/__init__.py`, `apps/trackings/management/commands/__init__.py`, `apps/trackings/management/commands/sync_trackings.py`
- Modify: `apps/carriers/adapters.py` (export correto já feito na Task 4)
- Test: `apps/trackings/tests/test_sync.py`

**Interfaces:**
- Consumes: `apps.carriers.adapters.ADAPTERS/get_adapter/detect_carrier`, `apps.carriers.client.PacoteVicioClient`, `payload.NormalizedPayload`, `apps.trackings.models` (Package, TrackingEvent, make_fingerprint), `apps.core.models.SyncLog`, `settings.COTA_MENSAL`.
- Produces:
  - `apps.carriers.sync.sync_package(package, client=None) -> bool | None` (True = ok, False = erro controlado, None = pausado pela cota; não há o parâmetro `enforce_cota`).
  - `apps.trackings.management.commands.sync_trackings.Command` — `handle(self, *args, **opts)`.
  - fluxo do `sync_package`: consulta cota (`SyncLog.is_paused()`), build params do adapter, `client.fetch(host_path, params)`, `normalize`, atualiza eventos (dedupe via fingerprint), marca estado/atraso, `mark_terminal` se terminal, grava `last_raw`, `last_error`. Propagate de erros 4xx → `last_error` sem retentar. 5xx/timeout → sobe erro (retenta próximo cron). Retorna/`raise`.

- [ ] **Step 1: Escrever teste (failing)**

`apps/trackings/tests/test_sync.py`:
```python
import json
from pathlib import Path
from unittest import mock

from django.test import TestCase

from apps.carriers.sync import sync_package
from apps.core.models import SyncLog
from apps.trackings.models import Package

FIXTURES = Path(__file__).parent.parent.parent / "carriers" / "tests" / "fixtures"


class FakeClient:
    def __init__(self, raw):
        self.raw = raw
        self.calls = 0

    def fetch(self, path, params):
        self.calls += 1
        return self.raw


class SyncTestCase(TestCase):
    def test_sync_package_delivered(self):
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        raw = json.loads((FIXTURES / "correios.json").read_text())
        ok = sync_package(p, FakeClient(raw))
        self.assertTrue(ok)
        p2 = Package.objects.get(pk=p.pk)
        self.assertFalse(p2.is_active)
        self.assertEqual(p2.state, "delivered")
        self.assertEqual(p2.events.count(), 2)

    def test_sync_package_uses_quota(self):
        p = Package.objects.create(tracking_code="X1", carrier="correios")
        with mock.patch("apps.carriers.sync.SyncLog.is_paused", return_value=True):
            res = sync_package(p, FakeClient({}))
        self.assertIsNone(res)
        self.assertIn("Cota", Package.objects.get(pk=p.pk).last_error)

    def test_sync_jt_without_document(self):
        p = Package.objects.create(tracking_code="888030556767025", carrier="jtexpress")
        res = sync_package(p, FakeClient({}))
        self.assertFalse(res)
        self.assertIn("CPF", Package.objects.get(pk=p.pk).last_error)
```

- [ ] **Step 2: Rodar testes para falhar**

Run: `python manage.py test apps.trackings -v 2`
Expected: `ModuleNotFoundError: No module named 'apps.carriers.sync'`.

- [ ] **Step 3: Implementar**

`apps/carriers/sync.py`:
```python
from django.utils import timezone

from apps.carriers.adapters import get_adapter
from apps.carriers.client import PacoteVicioClient
from apps.carriers.exceptions import PacoteVicioClientError, PacoteVicioServerError
from apps.core.models import SyncLog
from apps.trackings.models import (
    Package,
    TrackingEvent,
    STATE_DELIVERED,
)


def _apply_events(package: Package, normalized) -> None:
    for ev in sorted(normalized.events, key=lambda e: (e.occurred_at is None, e.occurred_at or timezone.now())):
        fp = TrackingEvent.make_fingerprint(package.id, ev.occurred_at, ev.status_key, ev.status_label)
        TrackingEvent.objects.get_or_create(
            package=package, fingerprint=fp,
            defaults={
                "occurred_at": ev.occurred_at,
                "status_key": ev.status_key,
                "status_label": ev.status_label,
                "location": ev.location,
                "raw": ev.raw,
            },
        )
    package.status_code = normalized.status_code
    package.status_label = normalized.status_label
    package.location = normalized.location
    package.last_event_at = normalized.last_event_at
    package.estimated_delivery = normalized.estimated_delivery
    package.last_raw = normalized.raw
    package.last_error = ""
    if normalized.is_terminal:
        package.mark_terminal(normalized.status_code, STATE_DELIVERED)
    if package.state == "in_transit" and package.estimated_delivery and package.estimated_delivery < timezone.localdate():
        package.is_delayed = True
    package.last_synced_at = timezone.now()
    package.save()


def sync_package(package: Package, client: PacoteVicioClient | None = None) -> bool | None:
    if SyncLog.is_paused():
        package.last_error = "Cota mensal atingida — sincronização pausada."
        package.save(update_fields=["last_error"])
        return None
    client = client or PacoteVicioClient()
    adapter = get_adapter(package.carrier)
    if adapter.requires_document and not package.document:
        package.last_error = "J&T Express exige o CPF do destinatário (campo 'document')."
        package.save(update_fields=["last_error"])
        return False
    params = adapter.build_params(package.tracking_code, package.document)
    try:
        raw = client.fetch(adapter.host_path, params)
        SyncLog.increment()
    except PacoteVicioClientError as exc:
        package.last_error = f"Erro {exc.status_code}: {exc}"
        package.save(update_fields=["last_error"])
        return False
    except PacoteVicioServerError as exc:
        package.last_error = f"Falha temporária: {exc}"
        package.save(update_fields=["last_error"])
        return False
    normalized = adapter.normalize(raw)
    _apply_events(package, normalized)
    return True


def sync_all(client: PacoteVicioClient | None = None) -> dict:
    client = client or PacoteVicioClient()
    results = {"ok": 0, "erro": 0, "pausado": 0, "sem_documento": 0}
    for package in Package.objects.filter(is_active=True):
        res = sync_package(package, client)
        if res is True:
            results["ok"] += 1
        elif res is False:
            if "CPF" in package.last_error:
                results["sem_documento"] += 1
            else:
                results["erro"] += 1
        else:
            results["pausado"] += 1
    return results
```

- [ ] **Step 4: management command**

`apps/trackings/management/commands/sync_trackings.py`:
```python
from django.core.management.base import BaseCommand
from apps.carriers.sync import sync_all


class Command(BaseCommand):
    help = "Sincroniza tracking de todas as encomendas ativas com a API PacoteVício."

    def handle(self, *args, **options):
        results = sync_all()
        for key, value in results.items():
            self.stdout.write(f"{key}: {value}")
```

- [ ] **Step 5: Rodar testes + comando manual**

Run: `python manage.py test apps.trackings -v 2 && python manage.py sync_trackings`
Expected: testes PASS; comando roda sem erro.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: sincronização de tracking + management command"
```

---

### Task 6: API DRF para o Hermes agent (autenticação por Api-Key)

**Files:**
- Create: `apps/trackings/api.py` (serializers + viewsets)
- Create: `apps/trackings/auth.py` (autenticação customizada `APIKeyAuthentication`)
- Modify: `apps/trackings/api_urls.py`
- Test: `apps/trackings/tests/test_api.py`

**Interfaces:**
- Consumes: `rest_framework`, `rest_framework_api_key.permissions.HasAPIKey` + `rest_framework_api_key.models.APIKey`, models, `detect_carrier`.
- Produces: rotas `/api/v1/health/`, `/api/v1/packages/`, `/api/v1/packages/<code>/`.

- [ ] **Step 1: Escrever testes (failing)**

`apps/trackings/tests/test_api.py`:
```python
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_api_key.models import APIKey
from apps.trackings.models import Package
from apps.carriers.adapters import detect_carrier


class ApiTestCase(APITestCase):
    @classmethod
    def setUpTestData(cls):
        cls.key = APIKey.objects.create_key(name="teste")[1]

    def auth(self):
        return {"HTTP_AUTHORIZATION": f"Api-Key {self.key}"}

    def test_health(self):
        resp = self.client.get("/api/v1/health/", **self.auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data["status"], "ok")

    def test_create_package(self):
        resp = self.client.post(
            "/api/v1/packages/",
            {"tracking_code": "AM101610575BR", "carrier": "correios", "label": "Meu pacote"},
            format="json", **self.auth(),
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.content)
        self.assertTrue(Package.objects.filter(tracking_code="AM101610575BR").exists())

    def test_create_requires_auth(self):
        resp = self.client.post("/api/v1/packages/", {"tracking_code": "X"}, format="json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_list_and_retrieve(self):
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        resp = self.client.get("/api/v1/packages/", **self.auth())
        self.assertEqual(resp.status_code, 200)
        resp2 = self.client.get("/api/v1/packages/AM101610575BR/", **self.auth())
        self.assertEqual(resp2.status_code, 200)
        self.assertEqual(resp2.data["tracking_code"], "AM101610575BR")

    def test_detect_carrier_via_api(self):
        self.assertEqual(detect_carrier("AJ123456789"), "anjun")
```

- [ ] **Step 2: Rodar testes para falhar**

Run: `python manage.py test apps.trackings -v 2`
Expected: 404s (sem rotas), e "no module".

- [ ] **Step 3: Implementar**

> **Nota:** o pacote `djangorestframework-api-key` a partir da v3.1 removeu o módulo
> `rest_framework_api_key.authentication`. Por isso a autenticação é customizada em
> `apps/trackings/auth.py` (referenciada em `base.py` →
> `DEFAULT_AUTHENTICATION_CLASSES`). O `authenticate_header` é **obrigatório** para o DRF
> responder 401 (sem ele, o DRF converte `AuthenticationFailed` em 403).

`apps/trackings/auth.py`:
```python
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_api_key.models import APIKey
from rest_framework_api_key.permissions import KeyParser


class APIKeyAuthentication(BaseAuthentication):
    key_parser = KeyParser()

    def authenticate_header(self, request):
        return "Api-Key"

    def authenticate(self, request):
        key = self.key_parser.get(request)
        if not key:
            raise AuthenticationFailed("Chave de API ausente.")
        if not APIKey.objects.is_valid(key):
            raise AuthenticationFailed("Chave de API inválida.")
        return (None, key)
```

`apps/trackings/api.py`:
```python
from rest_framework import generics
from rest_framework import serializers, viewsets
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_api_key.permissions import HasAPIKey

from apps.trackings.models import Package, TrackingEvent


class HealthView(APIView):
    permission_classes = [HasAPIKey]

    def get(self, request):
        return Response({"status": "ok"})


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = TrackingEvent
        fields = ("occurred_at", "status_key", "status_label", "location", "raw")


class PackageSerializer(serializers.ModelSerializer):
    events = EventSerializer(many=True, read_only=True)
    carrier_display = serializers.CharField(source="get_carrier_display", read_only=True)

    class Meta:
        model = Package
        fields = (
            "tracking_code", "carrier", "carrier_display", "label", "status_code",
            "status_label", "location", "last_event_at", "estimated_delivery",
            "state", "is_active", "is_delayed", "last_synced_at", "last_error",
            "created_at", "events",
        )

    def validate_tracking_code(self, value):
        value = value.strip()
        if Package.objects.filter(tracking_code__iexact=value).exists():
            raise serializers.ValidationError("Código já cadastrado.")
        return value


class PackageViewSet(viewsets.ModelViewSet):
    serializer_class = PackageSerializer
    permission_classes = [HasAPIKey]
    lookup_field = "tracking_code"

    def get_queryset(self):
        qs = Package.objects.all()
        code = self.request.query_params.get("q")
        carrier = self.request.query_params.get("carrier")
        state = self.request.query_params.get("state")
        if code:
            qs = qs.filter(tracking_code__icontains=code)
        if carrier:
            qs = qs.filter(carrier=carrier)
        if state:
            qs = qs.filter(state=state)
        return qs.select_related().prefetch_related("events")
```

`apps/trackings/api_urls.py`:
```python
from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.trackings.api import HealthView, PackageViewSet

router = DefaultRouter()
router.register("packages", PackageViewSet, basename="packages")

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/health/", HealthView.as_view(), name="health"),
]
```

- [ ] **Step 4: Rodar testes**

Run: `python manage.py makemigrations --check --dry-run && python manage.py test apps.trackings -v 2`
Expected: todos PASS (Health, create com auth 201, sem auth 401, list/retrieve, detect).

Nota: `ModelViewSet` já fornece create/list/retrieve em `/api/v1/packages/` e `/api/v1/packages/{tracking_code}/`; lookup usa `tracking_code` (o `lookup_field` sobrescreve `pk` automaticamente, dispensando `get_object` personalizado).

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: API DRF com autenticação por Api-Key"
```

---

### Task 7: Web UI — dashboard, cadastro, detalhe, timeline, login

**Files:**
- Create: `apps/trackings/web_urls.py` (substitui stub), `apps/trackings/views.py`, `apps/trackings/forms.py`
- Create: `apps/templates/base.html`, `apps/templates/registration/login.html`, `apps/templates/dashboard.html`, `apps/templates/package_form.html`, `apps/templates/package_detail.html`, `apps/templates/package_confirm_delete.html`
- Create: `static/css/app.css`, `static/js/app.js`
- Test: `apps/trackings/tests/test_web.py`

**Interfaces:**
- Consumes: models, `detect_carrier`, forms, auth views.
- Produces: rotas `login/logout`, `/` (dashboard), `/packages/new/`, `/packages/<code>/edit/`, `/packages/<code>/delete/`, `/packages/<code>/`.

- [ ] **Step 1: Escrever testes (failing)**

`apps/trackings/tests/test_web.py`:
```python
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from apps.trackings.models import Package


class WebTestCase(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("admin", password="pw12345")

    def login(self):
        self.client.login(username="admin", password="pw12345")

    def test_login_required(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 302)

    def test_dashboard(self):
        self.login()
        Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        resp = self.client.get("/")
        self.assertContains(resp, "AM101610575BR")

    def test_create_package_flow(self):
        self.login()
        resp = self.client.post("/packages/new/", {
            "tracking_code": "AJ123456789012345",
            "label": "Encomenda Anjun",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(Package.objects.filter(tracking_code="AJ123456789012345").exists())
        created = Package.objects.get(tracking_code="AJ123456789012345")
        self.assertEqual(created.carrier, "anjun")

    def test_detail_shows_events(self):
        self.login()
        p = Package.objects.create(tracking_code="AM101610575BR", carrier="correios")
        p.events.create(occurred_at="2025-03-03 23:30:03", status_key="BDE",
                        status_label="Entregue", fingerprint="f1")
        resp = self.client.get(f"/packages/{p.tracking_code}/")
        self.assertContains(resp, "Entregue")
```

- [ ] **Step 2: Rodar para falhar**

Run: `python manage.py test apps.trackings -v 2`
Expected: 404.

- [ ] **Step 3: Implementar**

`apps/trackings/forms.py`:
```python
from django import forms

from apps.carriers.adapters import detect_carrier
from apps.carriers.constants import CARRIER_CHOICES
from apps.trackings.models import Package


class PackageForm(forms.ModelForm):
    carrier = forms.ChoiceField(choices=CARRIER_CHOICES, required=False, label="Transportadora (automática)")

    class Meta:
        model = Package
        fields = ["tracking_code", "label", "carrier", "document"]
        widgets = {
            "tracking_code": forms.TextInput(attrs={"class": "form-control", "autofocus": True}),
            "label": forms.TextInput(attrs={"class": "form-control"}),
            "document": forms.TextInput(attrs={"class": "form-control", "placeholder": "Somente dígitos"}),
        }

    def clean_tracking_code(self):
        code = self.cleaned_data["tracking_code"].strip()
        detected = detect_carrier(code)
        if not detected:
            raise forms.ValidationError("Não foi possível identificar a transportadora pelo código.")
        return code

    def clean_document(self):
        doc = self.cleaned_data.get("document") or ""
        digits = "".join(ch for ch in doc if ch.isdigit())
        carrier = self.cleaned_data.get("carrier") or detect_carrier(self.cleaned_data.get("tracking_code", "")) or ""
        if carrier == "jtexpress" and len(digits) != 11:
            raise forms.ValidationError("CPF do destinatário deve ter 11 dígitos (J&T Express).")
        return digits

    def save(self, commit=True):
        instance = super().save(commit=False)
        if not instance.carrier:
            instance.carrier = detect_carrier(instance.tracking_code)
        if commit:
            instance.save()
        return instance
```

`apps/trackings/views.py`:
```python
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.carriers.sync import sync_package
from apps.trackings.forms import PackageForm
from apps.trackings.models import (
    Package,
    STATE_IN_TRANSIT,
    STATE_DELIVERED,
)


@login_required
def dashboard(request):
    qs = Package.objects.all()
    q = request.GET.get("q", "").strip()
    carrier = request.GET.get("carrier", "").strip()
    state = request.GET.get("state", "").strip()
    if q:
        qs = qs.filter(tracking_code__icontains=q)
    if carrier:
        qs = qs.filter(carrier=carrier)
    if state:
        qs = qs.filter(state=state)
    packages = list(qs.select_related()[:200])
    today = timezone.localdate()
    for p in packages:
        p.is_delayed = (
            p.state == STATE_IN_TRANSIT
            and p.estimated_delivery is not None
            and p.estimated_delivery < today
        )
    ctx = {
        "packages": packages,
        "count_in_transit": Package.objects.filter(state=STATE_IN_TRANSIT).count(),
        "count_delivered": Package.objects.filter(state=STATE_DELIVERED).count(),
        "count_delayed": Package.objects.filter(state=STATE_IN_TRANSIT, estimated_delivery__lt=today).count(),
        "filter_q": q, "filter_carrier": carrier, "filter_state": state,
    }
    return render(request, "dashboard.html", ctx)


@login_required
def package_new(request):
    form = PackageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Encomenda cadastrada!")
        return redirect("dashboard")
    return render(request, "package_form.html", {"form": form, "title": "Nova encomenda"})


@login_required
def package_edit(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    form = PackageForm(request.POST or None, instance=package)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Encomenda atualizada!")
        return redirect("package_detail", tracking_code=package.tracking_code)
    return render(request, "package_form.html", {"form": form, "title": f"Editar {package.tracking_code}"})


@login_required
def package_detail(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    events = package.events.all()
    return render(request, "package_detail.html", {"package": package, "events": events})


@login_required
def package_sync_now(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    sync_package(package)
    messages.info(request, "Sincronização executada.")
    return redirect("package_detail", tracking_code=package.tracking_code)


@login_required
def package_delete(request, tracking_code):
    package = get_object_or_404(Package, tracking_code__iexact=tracking_code)
    if request.method == "POST":
        package.delete()
        messages.success(request, "Encomenda excluída.")
        return redirect("dashboard")
    return render(request, "package_confirm_delete.html", {"package": package})
```

`apps/trackings/web_urls.py`:
```python
from django.urls import path
from django.contrib.auth import views as auth_views
from apps.trackings import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("login/", auth_views.LoginView.as_view(template_name="registration/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("packages/new/", views.package_new, name="package_new"),
    path("packages/<str:tracking_code>/", views.package_detail, name="package_detail"),
    path("packages/<str:tracking_code>/edit/", views.package_edit, name="package_edit"),
    path("packages/<str:tracking_code>/sync/", views.package_sync_now, name="package_sync_now"),
    path("packages/<str:tracking_code>/delete/", views.package_delete, name="package_delete"),
]
```

`apps/templates/base.html`:
```html
{% load static %}
<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{% block title %}Rastreador de Encomendas{% endblock %}</title>
  <link rel="stylesheet" href="{% static 'css/app.css' %}">
</head>
<body>
<header class="topbar">
  <div class="container">
    <a class="brand" href="{% url 'dashboard' %}">📦 Rastreador</a>
    <nav>
      <a href="{% url 'package_new' %}">Nova encomenda</a>
      {% if user.is_authenticated %}
        <a href="{% url 'logout' %}">Sair ({{ user.username }})</a>
      {% endif %}
    </nav>
  </div>
</header>
<main class="container">
  {% if messages %}
    <div class="messages">
      {% for message in messages %}<div class="message">{{ message }}</div>{% endfor %}
    </div>
  {% endif %}
  {% block content %}{% endblock %}
</main>
<script src="{% static 'js/app.js' %}"></script>
</body>
</html>
```

`apps/templates/registration/login.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Entrar</h1>
<form method="post">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Entrar</button>
</form>
{% endblock %}
```

`apps/templates/dashboard.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Minhas encomendas</h1>
<div class="cards">
  <div class="card"><span class="num">{{ count_in_transit }}</span><span>Em trânsito</span></div>
  <div class="card"><span class="num">{{ count_delivered }}</span><span>Entregues</span></div>
  <div class="card"><span class="num">{{ count_delayed }}</span><span>Atrasadas</span></div>
</div>
<form method="get" class="filters">
  <input name="q" value="{{ filter_q }}" placeholder="Buscar código">
  <select name="state">
    <option value="">Estado</option>
    <option value="in_transit" {% if filter_state == "in_transit" %}selected{% endif %}>Em trânsito</option>
    <option value="delivered" {% if filter_state == "delivered" %}selected{% endif %}>Entregue</option>
    <option value="failed" {% if filter_state == "failed" %}selected{% endif %}>Falha</option>
    <option value="returned" {% if filter_state == "returned" %}selected{% endif %}>Devolvida</option>
  </select>
  <button type="submit">Filtrar</button>
  <a href="{% url 'dashboard' %}">Limpar</a>
  <a class="btn" href="{% url 'package_new' %}">+ Nova</a>
</form>
<table>
  <thead><tr><th>Código</th><th>Transportadora</th><th>Status</th><th>Local</th><th>Último evento</th><th></th></tr></thead>
  <tbody>
  {% for p in packages %}
    <tr class="{% if p.is_delayed %}delayed{% endif %}">
      <td><a href="{% url 'package_detail' p.tracking_code %}">{{ p.tracking_code }}</a></td>
      <td>{{ p.get_carrier_display }}</td>
      <td>{{ p.status_label }}
        {% if p.is_delayed %}<span class="state delayed">⚠ Atrasada</span>{% endif %}
      </td>
      <td>{{ p.location }}</td>
      <td>{{ p.last_event_at|date:"d/m/Y H:i" }}</td>
      <td><a href="{% url 'package_detail' p.tracking_code %}">ver</a></td>
    </tr>
  {% empty %}
    <tr><td colspan="6">Nenhuma encomenda.</td></tr>
  {% endfor %}
  </tbody>
</table>
{% endblock %}
```

`apps/templates/package_detail.html`:
```html
{% extends "base.html" %}
{% block title %}{{ package.tracking_code }}{% endblock %}
{% block content %}
<a href="{% url 'dashboard' %}">← Voltar</a>
<h1>{{ package.display_code }}</h1>
<div class="meta">
  <span class="state state-{{ package.state }}">{{ package.get_state_display }}</span>
  {% if package.estimated_delivery %}
    <span>Previsão: {{ package.estimated_delivery|date:"d/m/Y" }}</span>
  {% endif %}
  {% if package.is_delayed %}<span class="state delayed">⚠ Atrasada</span>{% endif %}
  {% if package.carrier == "jtexpress" and package.masked_document %}
    <span>Doc: {{ package.masked_document }}</span>
  {% endif %}
  {% if package.last_error %}<div class="warn">{{ package.last_error }}</div>{% endif %}
  <p>{{ package.status_label }} — {{ package.location }}</p>
  <a class="btn" href="{% url 'package_sync_now' package.tracking_code %}">Atualizar agora</a>
  <a class="btn" href="{% url 'package_edit' package.tracking_code %}">Editar</a>
</div>
<h2>Linha do tempo</h2>
<ul class="timeline">
  {% for e in events %}
    <li>
      <span class="time">{{ e.occurred_at|date:"d/m/Y H:i" }}</span>
      <span class="lab">{{ e.status_label }}</span>
      {% if e.location %}<span class="loc">{{ e.location }}</span>{% endif %}
    </li>
  {% empty %}
    <li>Sem eventos ainda.</li>
  {% endfor %}
</ul>
{% endblock %}
```

`apps/templates/package_form.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>{{ title }}</h1>
<form method="post">
  {% csrf_token %}
  {{ form.as_p }}
  <button type="submit">Salvar</button>
</form>
{% endblock %}
```

`apps/templates/package_confirm_delete.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>Excluir {{ package.tracking_code }}?</h1>
<form method="post">
  {% csrf_token %}
  <button type="submit">Excluir</button>
  <a href="{% url 'package_detail' package.tracking_code %}">Cancelar</a>
</form>
{% endblock %}
```

`static/css/app.css` (simples e amigável):
```css
:root { --accent:#2563eb; --ok:#16a34a; --warn:#d97706; --err:#dc2626; }
* { box-sizing: border-box; }
body { font-family: system-ui, sans-serif; margin: 0; background:#f8fafc; color:#0f172a; }
.container { max-width: 960px; margin: 0 auto; padding: 0 16px; }
.topbar { background:#0f172a; color:#fff; }
.topbar .container { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; }
.topbar a { color:#fff; margin-left:16px; text-decoration:none; }
.brand { font-weight:700; font-size:18px; }
.cards { display:flex; gap:12px; margin:16px 0; }
.card { flex:1; background:#fff; border:1px solid #e2e8f0; border-radius:10px; padding:16px; text-align:center; }
.card .num { font-size:28px; font-weight:700; display:block; color:var(--accent); }
.filters { display:flex; gap:8px; margin-bottom:16px; flex-wrap:wrap; }
.filters input,.filters select { padding:8px; border:1px solid #cbd5e1; border-radius:8px; }
.btn, table a, .filters a { display:inline-block; padding:8px 12px; background:var(--accent); color:#fff; text-decoration:none; border-radius:8px; }
table { width:100%; border-collapse:collapse; background:#fff; }
th,td { text-align:left; padding:10px; border-bottom:1px solid #e2e8f0; }
tr.delayed td { background:#fff7ed; }
.state { display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; background:#e2e8f0; }
.state-delivered { background:#dcfce7; color:#166534; }
.state-failed, .state-returned { background:#fee2e2; color:#991b1b; }
.state.in_transit { background:#dbeafe; color:#1e40af; }
.state.delayed { background:#fef3c7; color:#92400e; }
.meta { background:#fff; border:1px solid #e2e8f0; padding:16px; border-radius:10px; margin:16px 0; display:flex; flex-wrap:wrap; gap:12px; align-items:center; }
.warn { background:#fef3c7; border:1px solid #fcd34d; padding:8px; border-radius:8px; }
.timeline { list-style:none; position:relative; padding-left:20px; }
.timeline::before { content:""; position:absolute; left:6px; top:0; bottom:0; width:2px; background:#e2e8f0; }
.timeline li { position:relative; padding:8px 0 8px 12px; }
.timeline li::before { content:""; position:absolute; left:-18px; top:14px; width:10px; height:10px; border-radius:50%; background:var(--accent); }
.time { color:#64748b; font-size:12px; margin-right:8px; }
.loc { color:#64748b; font-size:12px; }
```

`static/js/app.js` (mínimo):
```js
document.querySelectorAll(".toggle-raw").forEach((btn) => {
  btn.addEventListener("click", () => {
    const raw = btn.nextElementSibling;
    raw.hidden = !raw.hidden;
  });
});
```

- [ ] **Step 4: Rodar testes**

Run: `python manage.py test apps.trackings -v 2`
Expected: PASS.

- [ ] **Step 5: Teste adicional de regra (dashboard marca atrasada)**
Adicionar em `test_web.py`:
```python
    def test_dashboard_marks_delayed_for_display(self):
        self.login()
        Package.objects.create(
            tracking_code="AM101610575BR",
            carrier="correios",
            estimated_delivery="2020-01-01",
            state="in_transit",
        )
        resp = self.client.get("/")
        self.assertContains(resp, "Atrasada")
```
O dashboard computa `is_delayed` em memória (não persiste) para exibição; o template mostra o badge `Atrasada` na linha da encomenda.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: painel web com dashboard, cadastro e timeline"
```

---

### Task 8: Admin Django (registrar modelos) + DEBUG conveniências

**Files:**
- Create: `apps/trackings/admin.py`
- Modify: `apps/core/admin.py` (já existe SyncLog)
- Test: smoke tests de admin (opcional)

**Interfaces:**
- Consumes: models.
- Produces: administração de `Package`/`TrackingEvent` no `/admin/`.

- [ ] **Step 1: Implementar**

`apps/trackings/admin.py`:
```python
from django.contrib import admin
from apps.trackings.models import Package, TrackingEvent


@admin.register(Package)
class PackageAdmin(admin.ModelAdmin):
    list_display = ("tracking_code", "state", "is_active", "is_delayed", "last_event_at")
    list_filter = ("state", "carrier", "is_active")
    search_fields = ("tracking_code", "label")


@admin.register(TrackingEvent)
class TrackingEventAdmin(admin.ModelAdmin):
    list_display = ("package", "occurred_at", "status_label")
    search_fields = ("package__tracking_code", "status_label")
```

- [ ] **Step 2: Criar superuser e testar**

Run: `python manage.py makemigrations --check --dry-run && python manage.py migrate && python manage.py test apps.trackings apps.core apps.carriers -v 2`
Expected: tudo verde.

- [ ] **Step 3: Commit**: `git add -A && git commit -m "feat: admin django para gestão plena"`

---

### Task 9: Documentação (README + docs/ARCHITECTURE, API, DEPLOY, DEV)

**Files:**
- Create: `README.md`
- Create: `docs/ARCHITECTURE.md`, `docs/API.md`, `docs/DEPLOY.md`, `docs/DEV.md`

**Interfaces:** consome todo o projeto.

- [ ] **Step 1: Escrever os doc em pt-BR completos** (ver conteúdo detalhado abaixo).

- [ ] **Step 2: Review** — `grep` nos docs procurando trechos quebrados, e rodar `python manage.py check` final.

- [ ] **Step 3: Commit**: `git add -A && git commit -m "docs: documentação completa e guias de deploy"`

Conteúdo dos docs (a implementar literalmente):

`README.md`: visão, stack, features, estrutura, quickstart local (venv, env, migrate, createsuperuser, runserver, sync), cron, docs list.

`docs/DEPLOY.md` (passo a passo Dokku):
```
dokku apps:create postman
dokku postgres:create postman-db
dokku postgres:link postman-db postman
dokku config:set postman DJANGO_DEBUG=0 DJANGO_SECRET_KEY=... DJANGO_ALLOWED_HOSTS=postman.example.com \
  PACOTE_VICIO_API_KEY=... PACOTE_VICIO_BASE_URL=https://api.pacotevicio.dev PACOTE_VICIO_TIMEOUT=35 COTA_MENSAL=900
dokku domains:add postman postman.example.com
git remote add dokku dokku@server:postman
git push dokku main
dokku run postman python manage.py migrate
dokku run postman python manage.py createsuperuser
dokku letsencrypt:enable postman
```
Cron hotel (10h/13h/19h America/Sao_Paulo):
```
# crontab do host
40 8 * * * dokku run postman python manage.py sync_trackings
0  13 * * * dokku run postman python manage.py sync_trackings
0  19 * * * dokku run postman python manage.py sync_trackings
```

`docs/API.md`: auth (gerar APIKey via shell: `dokku run postman python manage.py shell -c ...` ou admin), endpoints com exemplos cURL.

`docs/ARCHITECTURE.md`: decisões (adapter pattern, normalização, dedupe, cota, estados), diagrama ASCII de fluxo.

`docs/DEV.md`: setup dev (venv, pip), .env, testes, lint (não há), commands úteis.

---

### Task 10: Configuração de deploy final (estáticos, health, seeds) + validação geral

**Files:**
- Modify: `config/urls.py` (health route já inclui packages?), `static/` (já tem), `Procfile` (já consta gunicorn), `.env.sample` final.
- Test: full suite + `manage.py check --deploy` (modo prod)

Passos:
- [ ] **Step 1: Ajustar `config/urls.py`** para incluir rota raiz `/api/v1/health/` já existe (Task 6). Incluir `path("api/v1/health/", ...)`? Já existe via api_urls. OK nada a fazer.
- [ ] **Step 2: `.env.sample`** já cobre. Criar `static/.gitkeep` e garantir `collectstatic`.
- [ ] **Step 3: Rodar suíte completa**

Run: `source .venv/bin/activate && python manage.py migrate && python manage.py collectstatic --noinput && python manage.py test apps -v 2`
Expected: todos testes PASS. `python manage.py check --deploy` com env prod pode alertar sobre DEBUG — ok por design.

- [ ] **Step 4: Commit** `git add -A && git commit -m "fix: ajustes finais de deploy e validação"`

---

## Self-Review (rodado após escrever)

### Cobertura do spec
- ✅ 6 adapters + detecção → Task 4
- ✅ Modelos, estados, dedupe → Task 2
- ✅ Regras (estado final encerra, atraso, cota, J&T doc) → Tasks 2,4,5,7
- ✅ Cliente HTTP/timeout/confidence → Task 3
- ✅ Web UI (dashboard, timeline, cadastro, editar, excluir, login) → Task 7
- ✅ API Hermes agent com Api-Key → Task 6
- ✅ Cron 3×/dia + management command → Tasks 5 e 9 (DEPLOY.md)
- ✅ Deploy Dokku → Tasks 1, 9, 10
- ✅ Documentação completa → Task 9
- ✅ Testes (fixtures doc_api.md, detecção, regras, API, views) → Tasks 2–8
- ⚠️ `SyncLog` quota → Task 2 (modelo) + Task 5 (uso) ✅

### Placeholders
- Removidos: todos os passos trazem código concreto e testável. Nenhum "TBD/TODO".

### Consistência de tipos
- `sync_package(package, client=None) -> bool | None`: `True` ok, `False` erro controlado, `None` pausado pela cota. Testes em `test_sync.py` verificam os três caminhos. ✅
- Cliente HTTP: `PacoteVicioClient.fetch(path, params)`; cada adapter expõe `.host_path` (`/correios`, `/aliexpress`, etc.) e `sync.py` chama `client.fetch(adapter.host_path, params)`. ✅
- `EventData(occurred_at, status_key, status_label, location, raw)` e `NormalizedPayload(tracking_code, status_code, status_label, location, last_event_at, estimated_delivery, is_terminal, events, raw)` — nomes/ordem idênticos em todos os adapters e em `_apply_events`. ✅
- `TrackingEvent.make_fingerprint(package_id, occurred_at, status_key, status_label)` definida na Task 2, usada na Task 5. ✅
- `SyncLog`: `increment()`, `count_today()`, `increment_and_get_count()` e `is_paused()` existem; `sync.py` usa `increment()` e `is_paused()`, o teste de `SyncLog` usa `count_today()`. ✅
- Import único de `detect_carrier` de `apps.carriers.adapters` (usado em forms, api e testes). ✅

### Notas finais já refletidas no plano
1. Task 4 define `host_path` em cada adapter; Task 5 chama `fetch(adapter.host_path, params)`. ✅
2. Task 6 usa `ModelViewSet` com `lookup_field="tracking_code"` e `permission_classes=[HasAPIKey]`. ✅
3. Task 7 views importam corretamente de `apps.carriers.adapters`. ✅
4. Dashboard computa `is_delayed` em memória para exibição. ✅
5. Testes usam URLs reais e `name=` únicos (dashboard, package_new, package_detail, package_edit, package_sync_now, package_delete, login, logout, health). ✅
6. Fixtures JSON da Task 4 contêm structs completas dos exemplos do `doc_api.md` (Correios 2 eventos, AliExpress 3, Shopee 8, Anjun 8, J&T 3, Total Express 7). ✅

## Execution Handoff
Plan complete and saved to `docs/superpowers/plans/2026-09-23-postman-rastreamento.md`.
## Addendum — melhorias de UX e funcionalidade (pós-v1) ✅

Implementadas (commits após `77f84a6`):

- **API:** `carrier` opcional no `POST /api/v1/packages/` com detecção automática no
  `create` (400 se código não reconhecido e sem carrier); nova ação
  `POST /api/v1/packages/{code}/sync/` (retorna `sync_status` + pacote).
- **Web:** `package_sync_now` só aceita **POST** (GET → 405), com mensagens por resultado;
  dashboard com paginação (25/página), painel de cota (`count_today/COTA_MENSAL` + último
  sync) e filtro de transportadora (recursos cookies): view já suportava, faltava o `<select>`.
- **Models:** `mark_terminal` reseta `is_delayed`; novos campos `delivered_notified_at`/
  `delay_notified_at` (migração `0002_notify_and_reset_delay`).
- **Sync:** e-mail opcional (env `PACOTE_NOTIFY_EMAIL`; sem ele não envia) na 1ª entrega e
  na 1ª detecção de atraso (via `django.core.mail`, `fail_silently=True`).
- **Forms:** detecção automática só exigida quando `carrier` não informado (override manual
  permitido); re-detecta carrier se o código mudou na edição.
- **Layout:** CSS refatorado (botões primary/secondary/danger/sm, timeline colorida por
  estado, badges por transportadora, mensagens-flash com tipo + fechar, tabela com scroll
  horizontal, responsivo ≤640px), forms/login/confirm-delete em cards, favicon SVG.
- **Testes:** +18 → **62 testes** verdes; `check --deploy` limpo; `collectstatic` ok.

### Round 2 — correções/ops/funcionalidade/layout ✅

- **Cota**: renomeada para `COTA_DIARIA` (comportamento diário já implementado; docs/env/settings
  refletem). `SyncLog` e dashboard usam `settings.COTA_DIARIA`.
- **`.env.sample`** atualizado (`COTA_DIARIA`, `PACOTE_NOTIFY_EMAIL`, `DJANGO_DEFAULT_FROM_EMAIL`, `PUBLIC_BASE_URL`).
- **API**: `document` agora é aceito como **write-only** (J&T criável/atualizável; não vaza CPF na resposta);
  `GET /api/v1/health/` e `GET /api/v1/schema/` **públicos**; schema OpenAPI 3.0 estático em `apps/trackings/api_schema.py`.
- **Cliente**: retry único em `429`/`5xx` (sleep 1s) com `PacoteVicioServerError` claro p/ 429.
- **sync_all** à prova de falhas: cada pacote em try/except, erro registrado em `last_error` e contabilizado (não derruba o cron); `logging` configurado (`LOGGING` em base.py).
- **E-mail**: corpo ganha link para o pacote via `PUBLIC_BASE_URL` (+`reverse`).
- **Dashboard**: coluna **Rótulo**; busca `q` por código **ou** rótulo; ordenação (`created`/
  `last_event`/`eta`/`carrier`/`state`); células vazias com "—"; empty-state com CTA.
- **Detail**: timeline agrupada por data (`{% ifchanged %}`), botão **raw** por evento com
  `pretty_json` (templatetag `apps/trackings/templatetags/jsonify.py`). Dead code `toggle-raw` agora é usado.
- **Páginas 404/500** customizadas; sessão de 12h (`SESSION_COOKIE_AGE`).
- **Testes**: +16 → **71 testes** verdes; `check --deploy` limpo.

### Round 3 — ops/privacidade/UX/DX ✅

- **Índices**: `db_index` em `estimated_delivery` e `last_event_at` (migração `0003_indexes_eta_and_last_event`).
- **`sync_trackings`**: sai com **exit code ≠ 0** quando há erro/pausa (cron monitora); flags `--quiet` e mensagem de warning na pausa.
- **Gunicorn**: `Procfile` com `--workers ${WEB_CONCURRENCY:-2} --threads 2`.
- **Admin**: ação **"Re-sincronizar encomendas selecionadas"** + coluna `last_synced_at` no `PackageAdmin`; `date_hierarchy`/filtro por transportadora no `TrackingEventAdmin`.
- **Privacidade API**: `EventSerializer` sem o campo `raw` (payloads das transportadoras podem conter nome/telefone/endereço do destinatário); raw continua no admin/painel. Mensagens de pausa unificadas em "Cota diária".
- **UX**: dashboard com **auto-refresh** leve (fetch do corpo a cada 60s); botões com lock anti-duplo-clique (`js-lock` + "Sincronizando…"); botão **copiar código** + contador de eventos no detail.
- **DX**: `Makefile` (`setup/dev/test/sync/check/migrate`), **quickstart no README**, `.editorconfig`.
- **Testes**: +9 → **80 testes** verdes; prod smoke ok (health/schema/404/estáticos).

### Round 4 — correções de caixa/UX, ops (CI/lint) e API ✅

- **Bug de ambigüidade de caixa (500)**: `tracking_code` agora é **normalizado para MAIÚSCULAS**
  no form e na API (com `exclude(self)` no update); migração de dados `0004` consolida códigos
  existentes (junta eventos com re-fingerprint, mantém o registro mais antigo). Elimina
  `MultipleObjectsReturned` em lookups `iexact`.
- **UX**: "Atualizar agora" **escondido** para encomendas inativas/encerradas (economiza cota);
  nova ação **"Reabrir rastreio"** (`POST /packages/{code}/reabrir/`) reativa sem gastar cota
  (testável para re-checar entrega mal detectada).
- **JT Express**: `status_code`/`status_label` passam a derivar do **evento mais recente**
  (`events[0]`, consistente com location).
- **CI**: `.github/workflows/ci.yml` — `test apps`, `makemigrations --check`, `check`,
  `check --deploy` em todo push/PR.
- **Lint**: ruff configurado (`E4/E7/E9/F/I`), `requirements-dev.txt`, alvo `make lint`;
  imports reordenados em `sync.py`/views/tests (`I001`), F401 removido.
- **API**: paginação documentada no schema (`limit`/`offset`); `DELETE` + paginação
  ganharam testes (já existentes em `ModelViewSet`/settings).
- **Testes**: +8 → **88 testes** verdes; lint limpo.
