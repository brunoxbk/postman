# Postman — Rastreador de Encomendas

Aplicação Django (painel web + API) que consome a [API PacoteVício](https://api.pacotevicio.dev) para cadastrar e rastrear encomendas de **6 transportadoras** em um só lugar, com sincronização automática via cron e uma API protegida para consumo por um Hermes agent.

## Funcionalidades

- **6 transportadoras**: Correios, AliExpress, Shopee Xpress, Anjun Express, J&T Express e Total Express.
- **Detecção automática** da transportadora pelo formato do código de rastreio (com opção de override manual).
- **Painel web (pt-BR)**: dashboard com cards (em trânsito / entregues / atrasadas), busca, filtros, timeline de eventos por encomenda, cadastrar/editar/excluir, botão "Atualizar agora".
- **API protegida** por `Api-Key` para o Hermes agent (listar, consultar, cadastrar encomendas); health e schema (`/api/v1/schema/`) são públicos.
- **Regras de negócio**: encomenda em estado final é encerrada (para de consultar), detecção de atraso, dedupe de eventos, e **cota mensal** da PacoteVício controlada para não estourar o plano; "Atualizar todos" só re-consulta o que ainda não foi sincronizado no dia.
- **E-mail opcional** em entregas/atrasos (configurar `PACOTE_NOTIFY_EMAIL`).
- **Cron 3×/dia** (08:40, 13:00, 19:00 America/Sao_Paulo) via management command `sync_trackings`.

## Rodar local

```bash
make setup            # venv, deps, migrate, createsuperuser
make dev              # python manage.py runserver
make test             # suite completa (apps)
make lint             # ruff (estilo/erros de código)
make sync             # dispara sincronização manual
```

O backend de e-mail é opcional: configure `PACOTE_NOTIFY_EMAIL`/`DJANGO_DEFAULT_FROM_EMAIL`
para receber avisos de entrega/atraso (sem valor, não envia).

## Stack

Python 3.12 (prod) · Django 5.2 · Django REST Framework · djangorestframework-api-key · django-environ · requests · whitenoise · PostgreSQL (prod) / SQLite (dev) · gunicorn.

## Estrutura

```
config/                settings (base/dev/prod), urls, wsgi/asgi
apps/
  core/                SyncLog (controle de cota) + testes de config
  carriers/            client HTTP, parsers, adapters das 6 transportadoras, sync
  trackings/           models (Package/TrackingEvent), API, views web, management command
  templates/           templates Django (base, dashboard, forms, timeline, login)
static/                css/js
docs/                  documentação (ARCHITECTURE, API, DEPLOY, DEV)
doc_api.md             documentação da API PacoteVício
```

## Quickstart local

```bash
python3 -m virtualenv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.sample .env        # preencha PACOTE_VICIO_API_KEY se quiser sincronizar contra a API real
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

- Painel: http://localhost:8000/
- Admin: http://localhost:8000/admin/
- API: http://localhost:8000/api/v1/

Testes:

```bash
python manage.py test apps -v 2
```

## Documentação

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — decisões, fluxo de sincronização, modelo de dados.
- [`docs/API.md`](docs/API.md) — API do Hermes agent (auth, endpoints, exemplos cURL).
- [`docs/DEPLOY.md`](docs/DEPLOY.md) — deploy no Dokku + cron + variáveis de ambiente.
- [`docs/DEV.md`](docs/DEV.md) — ambiente de desenvolvimento, testes e comandos úteis.