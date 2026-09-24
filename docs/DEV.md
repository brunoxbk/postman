# Desenvolvimento

## Setup local

Python 3.10+ basta para dev (prod usa 3.12 via `runtime.txt`).

```bash
python3 -m virtualenv .venv            # ou: python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

### Sobre o venv

Nesta máquina o binário `python3` veio sem `venv`/`ensurepip`. Use `virtualenv`:

```bash
pip install --user virtualenv
python3 -m virtualenv .venv
```

(Alternativa: container Docker `python:3.12-slim`.)

## Configuração (variáveis de ambiente)

Tudo vem de variáveis de ambiente via `django-environ` (veja `.env.sample`):

| Variável | Default | Descrição |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` | `dev` (sqlite, DEBUG) ou `prod` |
| `DJANGO_DEBUG` | `False` | debug on/off |
| `DJANGO_SECRET_KEY` | `""` (dev tem valor fixo) | segredo do Django |
| `DJANGO_ALLOWED_HOSTS` | `["*"]` | hosts permitidos |
| `DJANGO_TIME_ZONE` | `America/Sao_Paulo` | fuso da aplicação |
| `DATABASE_URL` | sqlite `db.sqlite3` | só relevante em prod (Postgres) |
| `PACOTE_VICIO_API_KEY` | `""` | chave da API PacoteVício (RapidAPI) |
| `PACOTE_VICIO_BASE_URL` | `https://api.pacotevicio.dev` | base da API |
| `PACOTE_VICIO_TIMEOUT` | `35` | timeout do HTTP (s) |
| `COTA_DIARIA` | `900` | teto de requisições/dia do `SyncLog` |
| `SYNC_WORKERS` | `4` | threads paralelas do `sync_all` (1 = sequencial; sempre sequencial em SQLite) |
| `PACOTE_NOTIFY_EMAIL` | `""` | e-mail para receber avisos (entrega/atraso); vazio = sem envio |
| `DJANGO_DEFAULT_FROM_EMAIL` | `no-reply@rastreador.local` | remetente dos e-mails |
| `PUBLIC_BASE_URL` | `""` | base pública (ex.: `https://postman.example.com`) para links nos e-mails; vazio = sem link |

O arquivo `.env` é lido automaticamente pelo `django-environ` na base de settings.

## Testes

```bash
python manage.py test apps -v 2
```

O test runner é o `django.test` padrão. As fixtures JSON usadas pelos testes de
adapters ficam em `apps/carriers/tests/fixtures/` (extraídas dos exemplos do
`doc_api.md`).

Rodar apenas um grupo:

```bash
python manage.py test apps.carriers -v 2
python manage.py test apps.trackings.tests.test_sync -v 2
```

> **SQLite nos testes:** o test runner usa SQLite em memória, que não suporta escritas
> concorrentes entre threads. Os testes de concorrência (`SyncAllParallelTestCase`,
> `SyncLogConcurrentTestCase`) são pulados sob SQLite (`skipUnless(connection.vendor ==
> "postgresql")`) — rode-os contra um Postgres local para validar o caminho paralelo.

## Comandos úteis

Há um `Makefile` com os atalhos mais usados (`make setup|dev|test|lint|sync|check|migrate`). Direto:

```bash
python manage.py sync_trackings                # sincroniza encomendas ativas manualmente
python manage.py sync_trackings --quiet        # imprime só os totais (para cron/monitor)
python manage.py makemigrations --check --dry-run   # valida que não há migrações pendentes
python manage.py check --deploy                # checagens de segurança (modo prod)
.venv/bin/ruff check .                         # lint (categorias E4/E7/E9/F/I, ver .ruff.toml)
python manage.py shell -c "
from rest_framework_api_key.models import APIKey
k, key = APIKey.objects.create_key(name='regen')  # gerar chave de API
print(key)
"
```

O `sync_trackings` sai com **código ≠ 0** se alguma encomenda falhou ou a cota foi
atingida (ideal para o cron alertar sobre problemas).

## Autenticação da API (chave de API)

A API `/api/v1/` é protegida por chave (`djangorestframework-api-key`). Como o pacote
removeu o módulo de autenticação nativo na v3.1, existe uma classe customizada em
`apps/trackings/auth.py` (`APIKeyAuthentication`) conectada via
`REST_FRAMEWORK.DEFAULT_AUTHENTICATION_CLASSES` em `config/settings/base.py`.

Ela lê o cabeçalho `Authorization: Api-Key <chave>` (via `KeyParser` do pacote) e valida
contra `APIKey.objects.is_valid()`. O método `authenticate_header()` retorna `"Api-Key"` —
sem ele o DRF converte as falhas de autenticação de 401 para 403. A permissão
`rest_framework_api_key.permissions.HasAPIKey` continua como default.

Gerar uma chave:

```bash
python manage.py shell -c "
from rest_framework_api_key.models import APIKey
k, key = APIKey.objects.create_key(name='hermes-agent')
print(key)
"
```

## Estrutura dos apps

- `apps/core` — `SyncLog` (+ testes de config)
- `apps/carriers` — cliente HTTP (`client.py`), parsing (`parsing.py`), payload
  (`payload.py`), adapters + detecção (`adapters.py`), regras de sync (`sync.py`)
- `apps/trackings` — modelos `Package`/`TrackingEvent`, `forms.py`, `views.py`
  (web), `api.py` + `api_urls.py` (API DRF), admin, management command
  `sync_trackings`

O lint roda via `ruff` (`.ruff.toml`, categorias E4/E7/E9/F/I) — `make lint`.
Fora isso, o código segue o padrão do Python (PEP 8) e o estilo dos arquivos vizinhos.